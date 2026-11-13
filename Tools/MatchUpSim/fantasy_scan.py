#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
환상별 승률 곡선 스캔 (v2)
==========================

(환상 또는 기준선) x (X축 값) [x 패싯] 마다 같은 시드 집합으로 판을 돌리고, 기준선과 같은 시드끼리
짝지은 승패 차이로 Δ승률과 95% CI 를 계산한다.

v2 변경
-------
- 점 캐시: <out>/point_cache/ (gzip). 키에 판 수가 없고 시드 접두를 이어 붙인다 (3000판 → 5000판 확장 가능).
  테이블 해시는 시뮬레이션에 영향을 주는 필드만 본다 (임포터를 다시 돌려도 캐시 유지).
- --adaptive: 점마다 n1 → n2 → n3 단계로 늘리다가 Δ 95% CI 반폭 ≤ ε 이면 멈춘다 (S3).
- --refine-around-target: 거친 격자 후 목표 승률 교차 구간에 중점을 최대 2회 추가 (S4). 곡선마다 X 가 다를 수 있다.
- --facet player.skill=0.5,0.7,0.9: 패싯(실력 구간 등)마다 곡선을 따로 계산 (F6).

출력: <out>/fantasy_curves.json (뷰어 입력, schema 2), <out>/fantasy_scans/<scan_id>.json, <out>/fantasy_curves.csv

  python fantasy_scan.py --effects fantasy_effects.json --x monsters.hp_base=200:1200:100 \\
      --fantasies all --runs 3000 --seed scan1 --set monsters.act_hp_growth=2.0 --workers 11
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import sys
import time
from datetime import datetime

import matchup_sim as ms
from sim_service import compute as cp
from sim_service import stats as S
from sim_service import store as st

HERE = os.path.dirname(os.path.abspath(__file__))
BASELINE_ID = "__baseline__"
STRONG_Z = 3.4  # 69개 동시 비교의 Bonferroni 근사 (양측 0.05/69)


# ---------------------------------------------------------------------------
# 설정
# ---------------------------------------------------------------------------
def frange(lo, hi, step):
    vals, k = [], 0
    ints = float(lo).is_integer() and float(step).is_integer()
    while True:
        v = lo + k * step
        if v > hi + 1e-9:
            break
        vals.append(int(v) if ints else round(v, 10))
        k += 1
    return vals


def parse_x(spec):
    key, rng = spec.split("=", 1)
    parts = [float(p) for p in rng.split(":")]
    if len(parts) != 3 or parts[2] <= 0 or parts[1] < parts[0]:
        raise SystemExit(f"--x 형식: KEY=LO:HI:STEP (STEP > 0), 받은 값: {spec}")
    return key.strip(), frange(*parts)


def parse_facet(spec):
    if not spec:
        return None, [None]
    key, vals = spec.split("=", 1)
    return key.strip(), [ms.parse_value(v.strip()) for v in vals.split(",")]


def build_cfg(config=None, sets=(), effects=None, effect_mode=None):
    cfg = copy.deepcopy(ms.DEFAULT_CONFIG)
    if config:
        with open(config, encoding="utf-8") as fp:
            ms.deep_merge(cfg, json.load(fp))
    fixed = {}
    for item in sets:
        k, v = item.split("=", 1)
        val = ms.parse_value(v.strip())
        ms.set_path(cfg, k.strip(), val)
        fixed[k.strip()] = val
    ms.apply_fantasy_args(cfg, effects, effect_mode)
    ms.normalize_models(cfg)
    return cfg, fixed


def facet_label(v):
    return "" if v is None else (json.dumps(v) if not isinstance(v, str) else v)


# ---------------------------------------------------------------------------
# 스캔 본체 (CLI 와 서버가 같이 씀)
# ---------------------------------------------------------------------------
class Scan:
    """cfg + 테이블 해시 + 시드 위에서 곡선(환상 x X 점)들을 계산한다.

    - stages: 단계별 목표 판 수 (마지막 = n_max). adaptive=False 면 마지막 단계만 쓴다.
    - 반환되는 점은 항상 "결정된 판 수 n 의 접두" 로 계산하므로 캐시 상태와 워커 수에 관계없이 같다.
    """

    def __init__(self, engine, cfg, thash, seed, x_key, stages=(3000,), adaptive=False, epsilon=0.015,
                 forced_at=None, cancel=None, on_point=None, log=print, progress=None):
        self.engine, self.cfg, self.thash, self.seed, self.x_key = engine, cfg, thash, seed, x_key
        self.stages = sorted(set(int(s) for s in stages))
        self.adaptive = adaptive
        if not adaptive:
            self.stages = self.stages[-1:]
        self.epsilon = epsilon
        self.forced_at = forced_at
        self.cancel = cancel
        self.on_point = on_point
        self.log = log
        self.progress = progress   # cp.Progress (v4.3) — 없으면 진행 표시 없음
        self.final_n = {}     # (fid, x) → 결정된 n
        self.recs = {}        # (fid, x) → 레코드
        self.reqs = {}

    def req(self, fid, x):
        k = (fid, x)
        if k not in self.reqs:
            c = copy.deepcopy(self.cfg)
            ms.set_path(c, self.x_key, x)
            if self.forced_at is not None:
                c["fantasy"]["forced"] = {"ids": [], "at": {"floor": self.forced_at}}
            fids = [] if fid == BASELINE_ID else (list(fid) if isinstance(fid, tuple) else [fid])
            self.reqs[k] = cp.make_req(c, fids, self.seed, self.thash, tag=k)
        return self.reqs[k]

    def _emit(self, fid, x):
        if self.on_point:
            self.on_point(fid, x, self.point(fid, x))

    def compute(self, pairs):
        """pairs: [(fid, x)] (기준선 포함 가능). 같은 X 의 기준선은 자동 추가. 단계별로 채운다.

        - 환상 점: 단계 n 이 끝날 때 Δ 95% CI 반폭 ≤ ε 이면 n 에서 확정 (비적응형이면 마지막 단계에서 확정).
        - 기준선 점: 같은 X 의 환상 점이 하나라도 남아 있으면 같이 늘린다. 확정 n = 그 X 환상 점 n 의 최댓값.
          환상 점이 없는 X(세밀화로 기준선만 추가된 점)는 승률 CI 반폭으로 같은 규칙을 적용한다.
        """
        pairs = list(dict.fromkeys(pairs))
        xs = sorted({x for _, x in pairs})
        for x in xs:
            if (BASELINE_ID, x) not in pairs:
                pairs.append((BASELINE_ID, x))
        fant = [p for p in pairs if p[0] != BASELINE_ID and p not in self.final_n]
        fant_x = {x for _, x in pairs if _ != BASELINE_ID}
        known_fant_x = {x for (f, x) in self.final_n if f != BASELINE_ID}
        base_only = [x for x in xs if x not in fant_x and x not in known_fant_x and (BASELINE_ID, x) not in self.final_n]
        base_final = {}
        for si, n in enumerate(self.stages):
            last = si == len(self.stages) - 1
            act_x = {x for _, x in fant} | set(base_only)
            if not act_x:
                break
            targets = [self.req(*p) for p in fant] + [self.req(BASELINE_ID, x) for x in act_x]

            def on_pt(req, rec):
                self.recs[req["tag"]] = rec

            self.engine.ensure(targets, n, on_point=on_pt, cancel=self.cancel, progress=self.progress)
            still = []
            for fid, x in fant:
                if not last:
                    d = S.paired_delta(self.recs[(fid, x)], self.recs[(BASELINE_ID, x)], n)
                    if S.half_width(d["delta_se"]) > self.epsilon:
                        still.append((fid, x))
                        continue
                self.final_n[(fid, x)] = n
            nb = []
            for x in base_only:
                if not last:
                    p = S.point_stats(self.recs[(BASELINE_ID, x)], x, n)
                    se = (p["win_rate"] * (1 - p["win_rate"]) / n) ** 0.5
                    if S.half_width(se) > self.epsilon:
                        nb.append(x)
                        continue
                base_final[x] = n
            fant, base_only = still, nb
        # 기준선 확정
        for x in xs:
            ns = [n for (f, xx), n in self.final_n.items() if f != BASELINE_ID and xx == x]
            if ns:
                self.final_n[(BASELINE_ID, x)] = max(ns + [self.final_n.get((BASELINE_ID, x), 0)])
            elif x in base_final:
                self.final_n[(BASELINE_ID, x)] = base_final[x]
        for fid, x in pairs:
            if (fid, x) in self.final_n:
                self._emit(fid, x)
        return pairs

    def point(self, fid, x):
        n = self.final_n.get((fid, x))
        rec = self.recs[(fid, x)]
        p = S.point_stats(rec, x, n)
        p["stage"] = self.stages.index(p["n"]) + 1 if p["n"] in self.stages else None
        if fid != BASELINE_ID and (BASELINE_ID, x) in self.recs:
            p.update(S.paired_delta(rec, self.recs[(BASELINE_ID, x)], p["n"]))
        return p

    def runs_used(self):
        return sum(self.final_n.values())


def refine_points(curves_pts, T, integer):
    """curves_pts: {fid: [point...]} → 교차 구간 중점 {fid: [새 x...]}"""
    add = {}
    for fid, pts in curves_pts.items():
        pts = sorted(pts, key=lambda p: p["x"])
        have = {p["x"] for p in pts}
        for a, b in zip(pts, pts[1:]):
            if a["win_rate"] is None or b["win_rate"] is None:
                continue
            if (a["win_rate"] - T) * (b["win_rate"] - T) < 0:
                mid = (a["x"] + b["x"]) / 2
                mid = int(round(mid)) if integer else round(mid, 6)
                if mid not in have and a["x"] < mid < b["x"]:
                    add.setdefault(fid, []).append(mid)
    return add


def run_scan(engine, cfg, thash, seed, x_key, x_values, fids, *, stages=(3000,), adaptive=False, epsilon=0.015,
             refine=False, refine_iters=2, target=0.10, facet_key=None, facet_values=(None,), forced_at=None,
             cancel=None, on_point=None, log=print, progress=None):
    """여러 패싯에 걸친 스캔. 반환: {facet_label: {"baseline": [pts], "curves": {fid: [pts]}, "scan": Scan}}"""
    integer = all(float(x).is_integer() for x in x_values)
    out = {}
    for fv in facet_values:
        c = copy.deepcopy(cfg)
        if facet_key:
            ms.set_path(c, facet_key, fv)
        sc = Scan(engine, c, thash, seed, x_key, stages, adaptive, epsilon, forced_at, cancel,
                  (lambda fid, x, p, fv=fv: on_point(fv, fid, x, p)) if on_point else None, log, progress)
        xs = {fid: list(x_values) for fid in [BASELINE_ID] + fids}
        sc.compute([(fid, x) for fid in fids for x in x_values] + [(BASELINE_ID, x) for x in x_values])
        for it in range(refine_iters if refine else 0):
            pts = {fid: [sc.point(fid, x) for x in xs[fid]] for fid in xs}
            add = refine_points(pts, target, integer)
            if not add:
                break
            new_pairs = []
            for fid, xx in add.items():
                for x in xx:
                    for f in (fid, BASELINE_ID):
                        if x not in xs[f]:
                            xs[f].append(x)
                            new_pairs.append((f, x))
                    if fid == BASELINE_ID:
                        continue
            # 기준선에 새 X 가 생기면 그 X 에서 Δ 를 위해 기준선만 계산 (환상 곡선은 자기 구간만)
            log(f"  세밀화 {it + 1}회차: 새 점 {len(new_pairs)}개")
            sc.compute(new_pairs)
        out[facet_label(fv)] = {
            "baseline": [sc.point(BASELINE_ID, x) for x in sorted(xs[BASELINE_ID])],
            "curves": {fid: [sc.point(fid, x) for x in sorted(xs[fid])] for fid in fids},
            "scan": sc,
        }
    return out


def _box_moves_version():
    from sim_service import box_moves as bm
    return bm.VERSION


def fidelity_summary(ctx, cfg):
    """곡선에 반영된 환상·몬스터 충실도 분포 (v4 §9.5-3)."""
    from collections import Counter
    dm = cfg["monsters"].get("damage_model", "gauss")
    key = "fidelity_digits" if dm == "digits" else "fidelity"
    out = {"fantasies": dict(Counter(e.get(key, e.get("fidelity")) for e in ctx.table.values())) if ctx.table else {}}
    if ctx.monsters is not None:
        from sim_service import monsters as mo
        seen = {m["id"]: m for v in ctx.monsters.values() for m in v}
        out["monsters"] = dict(Counter(mo.fidelity_for(cfg, m) for m in seen.values()))
    return out


def fantasy_meta(table, grade_of, fids):
    from sim_service import edits as ed
    out = []
    for fid in fids:
        e = table.get(fid, {})
        info = ed.fantasy_edit_info(e) if e else {"src_linked": False, "editable_keys": []}
        out.append({
            "id": fid, "name": e.get("name", fid), "grade": grade_of.get(fid, e.get("grade")),
            "fidelity": e.get("fidelity", "none"), "effects": e.get("effects", []),
            "fidelity_digits": e.get("fidelity_digits", e.get("fidelity", "none")), "notes_digits": e.get("notes_digits", ""),
            "notes": e.get("notes", "" if e else "효과 테이블에 없음"),
            "description": e.get("description", ""), "available": e.get("available", True),
            "mapping": e.get("mapping", ""), **info,
        })
    return out


def assemble(res, cfg, fids, ctx, thash, *, seed, x_key, fixed, target, stages, adaptive, epsilon, facet_key,
             facet_values, forced_at, n_max, elapsed=None):
    labels = [facet_label(v) for v in facet_values]
    default = labels[0]
    if facet_key:
        try:
            cur = ms.set_path  # noqa: F841
            cur_val = cfg
            for k in facet_key.split("."):
                cur_val = cur_val[int(k)] if isinstance(cur_val, list) else cur_val[k]
            if facet_label(cur_val) in labels:
                default = facet_label(cur_val)
        except (KeyError, IndexError, ValueError):
            pass
    base_default = res[default]["baseline"]
    total_pts = sum(len(r["baseline"]) + sum(len(v) for v in r["curves"].values()) for r in res.values())
    used = sum(p["n"] for r in res.values() for p in r["baseline"] + [q for v in r["curves"].values() for q in v])
    cfg_digest = hashlib.sha1(json.dumps(cfg, sort_keys=True).encode()).hexdigest()[:6]
    data = {
        "meta": {
            "schema": 3,
            "scan_id": f"{datetime.now():%Y%m%d-%H%M%S}-{cfg_digest}",
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "sim_version": ms.SIM_VERSION,
            "master_seed": seed,
            "runs_per_point": n_max,
            "x_param": x_key,
            "x_values": [p["x"] for p in base_default],
            "x_current": ms.get_path(cfg, x_key),      # v4.2: 현재 값 (예: 시작 체력 150) — 뷰어 세로선
            "fixed_overrides": fixed,
            "forced_at": "start" if forced_at is None else {"floor": forced_at},
            "effect_mode": ctx.mode,
            "table_hash": thash,
            "monster_hash": st.monster_hash(cfg),
            "data_hash": st.data_hash(thash, st.monster_hash(cfg)),
            "effects_hash": thash,
            "reward_system": (cfg.get("rewards") or {}).get("normal_battle", {}).get("mode", "fantasy"),
            "ember": (cfg.get("rewards") or {}).get("ember"),
            "damage_model": cfg["monsters"].get("damage_model", "gauss"),
            # v4
            "monsters_gimmicks": cfg["monsters"].get("gimmicks", "off"),
            "box_moves_version": _box_moves_version(),
            "ref_hash": st.data_hash(thash, st.monster_hash(cfg)),     # 스캔 = 그 자체가 기준 (고스트 없음)
            "fidelity_summary": fidelity_summary(ctx, cfg),
            "point_layer": "current", "approx_points": False,
            "effects_file": os.path.basename(cfg["fantasy"].get("effects_file") or ""),
            "target_win_rate": target,
            "strong_signal_z": STRONG_Z,
            "fantasy_pick": cfg["policy"].get("fantasy_pick", "random"),
            "reward_mode": (cfg.get("rewards") or {}).get("normal_battle", {}).get("mode", "fantasy"),
            "monster_model": cfg["monsters"].get("model", "tier_avg"),
            "facets": {"key": facet_key, "values": labels, "default": default} if facet_key else None,
            "adaptive": {"enabled": adaptive, "stages": stages, "epsilon": epsilon, "runs_used": used,
                         "runs_nonadaptive": total_pts * n_max,
                         "saving": round(1 - used / max(1, total_pts * n_max), 4)},
            "elapsed_s": round(elapsed, 1) if elapsed is not None else None,
        },
        "fantasies": fantasy_meta(ctx.table, ctx.grade_of, fids),
        "baseline": {"points": base_default},
        "curves": {fid: {"points": res[default]["curves"][fid]} for fid in fids},
    }
    if facet_key:
        data["baseline"]["by_facet"] = {lb: res[lb]["baseline"] for lb in labels}
        for fid in fids:
            data["curves"][fid]["by_facet"] = {lb: res[lb]["curves"][fid] for lb in labels}
    return data


def write_outputs(data, out_dir, json_path=None):
    json_path = json_path or os.path.join(out_dir, "fantasy_curves.json")
    os.makedirs(os.path.dirname(os.path.abspath(json_path)), exist_ok=True)
    with open(json_path, "w", encoding="utf-8") as fp:
        json.dump(data, fp, ensure_ascii=False, separators=(",", ":"))
    os.makedirs(os.path.join(out_dir, "fantasy_scans"), exist_ok=True)
    with open(os.path.join(out_dir, "fantasy_scans", f"{data['meta']['scan_id']}.json"), "w", encoding="utf-8") as fp:
        json.dump(data, fp, ensure_ascii=False, separators=(",", ":"))
    m = data["meta"]
    fid_map = {f["id"]: f for f in data["fantasies"]}
    rows = []
    facets = (m.get("facets") or {}).get("values") or [""]
    for lb in facets:
        base = data["baseline"]["by_facet"][lb] if m.get("facets") else data["baseline"]["points"]
        series = [(BASELINE_ID, base)] + [
            (fid, c["by_facet"][lb] if m.get("facets") else c["points"]) for fid, c in data["curves"].items()]
        for fid, pts in series:
            for p in pts:
                rows.append({
                    "scan_id": m["scan_id"], "fantasy_id": fid, "facet": lb, "x_param": m["x_param"], "x_value": p["x"],
                    "n": p["n"], "wins": p["wins"], "win_rate": p["win_rate"],
                    "delta": p.get("delta", ""), "delta_se": p.get("delta_se", ""),
                    "delta_ci_lo": p["delta_ci"][0] if "delta_ci" in p else "",
                    "delta_ci_hi": p["delta_ci"][1] if "delta_ci" in p else "",
                    "mean_reached_floor": p["mean_reached_floor"], "mean_fantasies": p["mean_fantasies"],
                    "death_act1_rate": p["death_by_act"][0], "death_act2_rate": p["death_by_act"][1],
                    "death_act3_rate": p["death_by_act"][2],
                    "fidelity": "" if fid == BASELINE_ID else fid_map[fid]["fidelity"],
                    "table_hash": p.get("table_hash", ""),
                })
    ms.append_rows(os.path.join(out_dir, "fantasy_curves.csv"), rows)
    return json_path


def main(argv=None):
    ap = argparse.ArgumentParser(description="환상별 승률 곡선 스캔 (v2)")
    ap.add_argument("--effects", required=False, help="환상 효과 테이블 JSON")
    ap.add_argument("--effect-mode", choices=["grade", "table"], help="기본: --effects 가 있으면 table")
    ap.add_argument("--x", metavar="KEY=LO:HI:STEP",
                    help="X축 설정 키와 범위 (권장 player.start_hp=100:300:20). 생략하면 현재 시작 체력 한 점")
    ap.add_argument("--fantasies", default="all", help="all 또는 ID,ID,...")
    ap.add_argument("--runs", type=int, default=3000, help="점당 판 수 (적응형이면 최대 n_max)")
    ap.add_argument("--seed", default="scan1", help="마스터 시드")
    ap.add_argument("--config", help="설정 JSON")
    ap.add_argument("--set", action="append", default=[], metavar="KEY=VALUE", help="고정 파라미터")
    ap.add_argument("--force-at", type=int, metavar="FLOOR", help="강제 포함 시점 (전체 층 번호, 생략 시 시작)")
    ap.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2) - 1))
    ap.add_argument("--out", default="sim_results")
    ap.add_argument("--target", type=float, default=0.10, help="목표 승률 (세밀화·뷰어 기본값)")
    ap.add_argument("--json-out", help="뷰어용 JSON 경로 (기본 <out>/fantasy_curves.json)")
    ap.add_argument("--adaptive", action="store_true", help="적응형 표본 추출 (S3)")
    ap.add_argument("--epsilon", type=float, default=0.015, help="적응형 목표 정밀도: Δ 95%% CI 반폭 (기본 0.015)")
    ap.add_argument("--n-stages", default="500,1500,3000", help="적응형 단계 (마지막 값이 --runs 보다 크면 --runs 로 자름)")
    ap.add_argument("--refine-around-target", action="store_true", help="목표 승률 교차 구간 세밀화 (S4)")
    ap.add_argument("--refine-iters", type=int, default=2)
    ap.add_argument("--facet", help="패싯, 예: player.skill=0.5,0.7,0.9 (F6)")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args(argv)
    log = (lambda *a, **k: None) if args.quiet else print

    cfg, fixed = build_cfg(args.config, args.set, args.effects, args.effect_mode)
    if not args.x:
        # 기본: X축 없이 현재 시작 체력 한 점 (몬스터는 JSON 체력 그대로, v4.2 F11.4)
        v = cfg["player"]["start_hp"]
        args.x = f"player.start_hp={v}:{v}:1"
        log(f"  X축 생략 → 시작 체력 {v} 한 점 (몬스터 체력 = {'JSON 그대로' if cfg['monsters'].get('model') == 'table' else '평균 몬스터(구버전)'})")
    x_key, x_values = parse_x(args.x)
    ms.set_path(copy.deepcopy(cfg), x_key, x_values[0])  # 키 검증
    ms.warn_unused(cfg, [x_key] + [i.split("=", 1)[0].strip() for i in args.set], out=log)
    ms.warn_stale_monster_table(cfg, out=log)
    ctx = ms.SimContext(cfg)
    thash = st.table_hash(list(ctx.table.values())) if ctx.table else "grade"
    facet_key, facet_values = parse_facet(args.facet)
    if facet_key:
        ms.set_path(copy.deepcopy(cfg), facet_key, facet_values[0])

    if args.fantasies.strip().lower() == "all":
        if not ctx.table:
            raise SystemExit("--fantasies all 에는 --effects 가 필요함")
        fids = list(ctx.table.keys())
    else:
        fids = [x.strip() for x in args.fantasies.split(",") if x.strip()]
        for fid in fids:
            if fid not in ctx.grade_of:
                raise SystemExit(f"알 수 없는 환상 ID: {fid}")
    stages = [int(s) for s in args.n_stages.split(",")] if args.adaptive else [args.runs]
    stages = sorted({min(s, args.runs) for s in stages} | {args.runs})
    if args.runs < 1000:
        log(f"  ※ 점당 {args.runs}판: 정규 근사(n ≥ 1000) 가정보다 작음")

    store = st.PointStore(os.path.join(args.out, "point_cache"))
    engine = cp.Engine(store, args.workers)
    n_pts = (len(fids) + 1) * len(x_values) * len(facet_values)
    log(f"스캔: 환상 {len(fids)}종 + 기준선 x X {len(x_values)}점 x 패싯 {len(facet_values)} = {n_pts}점, "
        f"단계 {stages}{' (적응형 ε=' + str(args.epsilon) + ')' if args.adaptive else ''}, 워커 {engine.workers}")
    t0 = time.perf_counter()
    done = [0]
    last = [0.0]

    def on_point(fv, fid, x, p):
        done[0] += 1
        now = time.perf_counter()
        if now - last[0] > 2:
            last[0] = now
            log(f"  점 {done[0]} 확정 | 경과 {now - t0:6.0f}s | 계산한 판 {engine.runs_computed:,}", flush=True)

    progress = cp.Progress(log=(lambda line: print(line, flush=True)), log_interval=5.0, label="스캔") \
        if not args.quiet else None
    try:
        res = run_scan(engine, cfg, thash, args.seed, x_key, x_values, fids, stages=stages, adaptive=args.adaptive,
                       epsilon=args.epsilon, refine=args.refine_around_target, refine_iters=args.refine_iters,
                       target=args.target, facet_key=facet_key, facet_values=facet_values, forced_at=args.force_at,
                       on_point=on_point, log=log, progress=progress)
    finally:
        engine.close()
    el = time.perf_counter() - t0
    data = assemble(res, cfg, fids, ctx, thash, seed=args.seed, x_key=x_key, fixed=fixed, target=args.target,
                    stages=stages, adaptive=args.adaptive, epsilon=args.epsilon, facet_key=facet_key,
                    facet_values=facet_values, forced_at=args.force_at, n_max=stages[-1], elapsed=el)
    path = write_outputs(data, args.out, args.json_out)
    a = data["meta"]["adaptive"]
    log(f"완료 {el:.0f}s → {os.path.abspath(path)} (scan_id {data['meta']['scan_id']})")
    log(f"  사용한 판 {a['runs_used']:,} / 비적응형 {a['runs_nonadaptive']:,} (절감 {a['saving'] * 100:.1f}%), "
        f"이번에 새로 계산 {engine.runs_computed:,}판, 캐시 {store.disk_usage() / 1e6:.1f}MB")
    bx = "  ".join(f"{fmt(p['x'])}:{p['win_rate'] * 100:.1f}%" for p in data["baseline"]["points"])
    log(f"  기준선 승률  {bx}")
    return data


def fmt(x):
    return str(int(x)) if float(x).is_integer() else f"{x:g}"


if __name__ == "__main__":
    main()
