#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
환상별 승률 곡선 스캔
=====================

(환상 또는 기준선) x (X축 값) 마다 같은 시드 집합으로 n판을 돌리고, 기준선과 같은 시드끼리
짝지은 승패 차이로 Δ승률과 95% 신뢰구간을 계산한다. 결과는

  <out>/fantasy_curves.csv   (누적)
  <out>/fantasy_curves.json  (뷰어 입력, 최신 스캔)
  <out>/fantasy_scans/<scan_id>.json (스캔별 보관본)
  <out>/fantasy_cache/<key>.json     (점 단위 캐시 — 중단 후 재실행하면 이어서 진행)

사용 예
-------
  python fantasy_scan.py --effects fantasy_effects.json --x monsters.hp_base=300:1300:100 \\
      --fantasies all --runs 3000 --seed scan1 --set monsters.act_hp_growth=2.0 --workers 8
  (python matchup_sim.py --fantasy-scan ... 도 같다)
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import multiprocessing as mp
import os
import sys
import time
from datetime import datetime

import matchup_sim as ms

BASELINE_ID = "__baseline__"
STRONG_Z = 3.4  # 69개 동시 비교의 Bonferroni 근사 (양측 0.05/69)


# ---------------------------------------------------------------------------
# 설정
# ---------------------------------------------------------------------------
def frange(lo, hi, step):
    vals, k = [], 0
    while True:
        v = lo + k * step
        if v > hi + 1e-9:
            break
        vals.append(int(v) if float(v).is_integer() and float(step).is_integer() and float(lo).is_integer() else round(v, 10))
        k += 1
    return vals


def parse_x(spec):
    key, rng = spec.split("=", 1)
    parts = [float(p) for p in rng.split(":")]
    if len(parts) != 3 or parts[2] <= 0 or parts[1] < parts[0]:
        raise SystemExit(f"--x 형식: KEY=LO:HI:STEP (STEP > 0), 받은 값: {spec}")
    return key.strip(), frange(*parts)


def build_cfg(args):
    cfg = copy.deepcopy(ms.DEFAULT_CONFIG)
    if args.config:
        with open(args.config, encoding="utf-8") as fp:
            ms.deep_merge(cfg, json.load(fp))
    fixed = {}
    for item in args.set:
        k, v = item.split("=", 1)
        val = ms.parse_value(v.strip())
        ms.set_path(cfg, k.strip(), val)
        fixed[k.strip()] = val
    ms.apply_fantasy_args(cfg, args.effects, args.effect_mode)
    return cfg, fixed


def point_cfg(cfg, x_key, x, fid, forced_at):
    c = copy.deepcopy(cfg)
    ms.set_path(c, x_key, x)
    if fid != BASELINE_ID:
        c["fantasy"]["forced"] = {"ids": [fid], "at": "start" if forced_at is None else {"floor": forced_at}}
    else:
        c["fantasy"]["forced"] = {"ids": [], "at": "start"}
    return c


def cache_key(c, fid, x, seed, runs, effects_hash):
    c2 = copy.deepcopy(c)
    c2["fantasy"]["effects_file"] = ""  # 파일 위치가 아니라 내용(해시)으로 구분
    blob = json.dumps(c2, sort_keys=True, ensure_ascii=False)
    raw = f"{blob}|{fid}|{x}|{seed}|{runs}|{effects_hash}|{ms.SIM_VERSION}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:20]


# ---------------------------------------------------------------------------
# 점 하나 실행 (워커)
# ---------------------------------------------------------------------------
def run_point(task):
    """task = (cfg, fid, x, seed, runs, cache_path). 판별 결과를 압축해 캐시에 쓰고 돌려준다."""
    c, fid, x, seed, runs, path = task
    ctx = ms.SimContext(c)
    wins, reached, death_act, nfant = [], [], [], []
    for i in range(runs):
        r = ms.simulate_run(c, f"{seed}-{i}", ctx=ctx)
        win = r["result"] == "win"
        wins.append("1" if win else "0")
        reached.append(r["reached_floor"])
        death_act.append(0 if win else r["end_act"])
        nfant.append(r["fant_white"] + r["fant_blue"] + r["fant_red"])
    rec = {"fid": fid, "x": x, "seed": seed, "runs": runs, "sim_version": ms.SIM_VERSION,
           "wins": "".join(wins), "reached": reached, "death_act": death_act, "nfant": nfant}
    tmp = path + f".{os.getpid()}.tmp"
    with open(tmp, "w", encoding="utf-8") as fp:
        json.dump(rec, fp, separators=(",", ":"))
    os.replace(tmp, path)
    return fid, x, rec


def load_cached(path):
    try:
        with open(path, encoding="utf-8") as fp:
            return json.load(fp)
    except (OSError, ValueError):
        return None


# ---------------------------------------------------------------------------
# 통계
# ---------------------------------------------------------------------------
def point_stats(rec):
    n = rec["runs"]
    w = [ch == "1" for ch in rec["wins"]]
    wins = sum(w)
    reached = rec["reached"]
    da = rec["death_act"]
    return {
        "x": rec["x"],
        "n": n,
        "wins": wins,
        "win_rate": round(wins / n, 6),
        "mean_reached_floor": round(sum(reached) / n, 4),
        "mean_fantasies": round(sum(rec["nfant"]) / n, 4),
        "death_by_act": [round(sum(1 for a in da if a == k) / n, 6) for k in (1, 2, 3)],
        "reach_rate": [round(sum(1 for r in reached if r >= f) / n, 6) for f in range(1, ms.TOTAL_FLOORS + 1)],
    }


def paired_delta(rec_f, rec_b):
    """같은 시드 i 끼리 d_i = win_i(환상) - win_i(기준선). 평균, 표본표준편차/√n, 95% CI."""
    a, b = rec_f["wins"], rec_b["wins"]
    if len(a) != len(b):
        raise ValueError("짝지을 판 수가 다름")
    n = len(a)
    d = [(ca == "1") - (cb == "1") for ca, cb in zip(a, b)]
    mean = sum(d) / n
    if n > 1:
        var = sum((x - mean) ** 2 for x in d) / (n - 1)
        se = math.sqrt(var / n)
    else:
        se = 0.0
    return round(mean, 6), round(se, 6), [round(mean - 1.96 * se, 6), round(mean + 1.96 * se, 6)]


# ---------------------------------------------------------------------------
# 메인
# ---------------------------------------------------------------------------
def main(argv=None):
    ap = argparse.ArgumentParser(description="환상별 승률 곡선 스캔")
    ap.add_argument("--effects", required=False, help="환상 효과 테이블 JSON")
    ap.add_argument("--effect-mode", choices=["grade", "table"], help="기본: --effects 가 있으면 table")
    ap.add_argument("--x", required=True, metavar="KEY=LO:HI:STEP", help="X축 설정 키와 범위")
    ap.add_argument("--fantasies", default="all", help="all 또는 ID,ID,...")
    ap.add_argument("--runs", type=int, default=3000, help="점당 판 수")
    ap.add_argument("--seed", default="scan1", help="마스터 시드")
    ap.add_argument("--config", help="설정 JSON")
    ap.add_argument("--set", action="append", default=[], metavar="KEY=VALUE", help="고정 파라미터")
    ap.add_argument("--force-at", type=int, metavar="FLOOR", help="강제 포함 시점 (전체 층 번호, 생략 시 시작)")
    ap.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2) - 1))
    ap.add_argument("--out", default="sim_results")
    ap.add_argument("--target", type=float, default=0.10, help="뷰어의 기본 목표 승률")
    ap.add_argument("--json-out", help="뷰어용 JSON 경로 (기본 <out>/fantasy_curves.json)")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args(argv)

    cfg, fixed = build_cfg(args)
    x_key, x_values = parse_x(args.x)
    ms.set_path(copy.deepcopy(cfg), x_key, x_values[0])  # 키 검증
    ctx = ms.SimContext(cfg)
    effect_mode = ctx.mode

    if args.fantasies.strip().lower() == "all":
        if not ctx.table:
            raise SystemExit("--fantasies all 에는 --effects 가 필요함")
        fids = list(ctx.table.keys())
    else:
        fids = [x.strip() for x in args.fantasies.split(",") if x.strip()]
        for fid in fids:
            if fid not in ctx.grade_of:
                raise SystemExit(f"알 수 없는 환상 ID: {fid}")
    if args.runs < 1000 and not args.quiet:
        print(f"  ※ 점당 {args.runs}판: 정규 근사(n ≥ 1000) 가정보다 작음")

    cache_dir = os.path.join(args.out, "fantasy_cache")
    os.makedirs(cache_dir, exist_ok=True)

    tasks, keys, recs = [], {}, {}
    for fid in [BASELINE_ID] + fids:
        for x in x_values:
            c = point_cfg(cfg, x_key, x, fid, args.force_at)
            k = cache_key(c, fid, x, args.seed, args.runs, ctx.effects_hash)
            keys[(fid, x)] = k
            path = os.path.join(cache_dir, f"{k}.json")
            rec = load_cached(path)
            if rec and rec.get("runs") == args.runs and len(rec.get("wins", "")) == args.runs:
                recs[(fid, x)] = rec
            else:
                tasks.append((c, fid, x, args.seed, args.runs, path))

    total = len(keys)
    done0 = total - len(tasks)
    if not args.quiet:
        print(f"스캔: 환상 {len(fids)}종 + 기준선 x X {len(x_values)}점 = {total}점, 점당 {args.runs}판 "
              f"(캐시 {done0}점, 실행 {len(tasks)}점, 워커 {args.workers})")
    t0 = time.perf_counter()
    last = 0.0

    def progress(done_new):
        nonlocal last
        now = time.perf_counter()
        if args.quiet or (now - last < 2 and done_new < len(tasks)):
            return
        last = now
        el = now - t0
        eta = el / done_new * (len(tasks) - done_new) if done_new else 0
        print(f"  {done0 + done_new}/{total} 완료 | 경과 {el:6.0f}s | 남은 시간 약 {eta:6.0f}s", flush=True)

    if tasks:
        if args.workers <= 1:
            for j, t in enumerate(tasks, 1):
                fid, x, rec = run_point(t)
                recs[(fid, x)] = rec
                progress(j)
        else:
            with mp.get_context("spawn").Pool(args.workers) as pool:
                for j, (fid, x, rec) in enumerate(pool.imap_unordered(run_point, tasks, chunksize=1), 1):
                    recs[(fid, x)] = rec
                    progress(j)

    # --- 집계
    base_pts = {x: point_stats(recs[(BASELINE_ID, x)]) for x in x_values}
    curves = {}
    for fid in fids:
        pts = []
        for x in x_values:
            p = point_stats(recs[(fid, x)])
            p["delta"], p["delta_se"], p["delta_ci"] = paired_delta(recs[(fid, x)], recs[(BASELINE_ID, x)])
            pts.append(p)
        curves[fid] = {"points": pts}

    cfg_digest = hashlib.sha1(json.dumps(cfg, sort_keys=True).encode()).hexdigest()[:6]
    scan_id = f"{datetime.now():%Y%m%d-%H%M%S}-{cfg_digest}"
    fant_meta = []
    for fid in fids:
        e = ctx.table.get(fid, {})
        fant_meta.append({
            "id": fid, "name": e.get("name", fid), "grade": ctx.grade_of[fid],
            "fidelity": e.get("fidelity", "none"), "effects": e.get("effects", []),
            "notes": e.get("notes", "" if e else "효과 테이블에 없음"),
            "description": e.get("description", ""), "available": e.get("available", True),
        })
    data = {
        "meta": {
            "scan_id": scan_id,
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "sim_version": ms.SIM_VERSION,
            "master_seed": args.seed,
            "runs_per_point": args.runs,
            "x_param": x_key,
            "x_values": x_values,
            "fixed_overrides": fixed,
            "forced_at": "start" if args.force_at is None else {"floor": args.force_at},
            "effect_mode": effect_mode,
            "effects_hash": ctx.effects_hash,
            "effects_file": os.path.basename(cfg["fantasy"].get("effects_file") or ""),
            "target_win_rate": args.target,
            "strong_signal_z": STRONG_Z,
            "fantasy_pick": cfg["policy"].get("fantasy_pick", "random"),
        },
        "fantasies": fant_meta,
        "baseline": {"points": [base_pts[x] for x in x_values]},
        "curves": curves,
    }

    json_path = args.json_out or os.path.join(args.out, "fantasy_curves.json")
    os.makedirs(os.path.dirname(os.path.abspath(json_path)), exist_ok=True)
    with open(json_path, "w", encoding="utf-8") as fp:
        json.dump(data, fp, ensure_ascii=False, separators=(",", ":"))
    os.makedirs(os.path.join(args.out, "fantasy_scans"), exist_ok=True)
    with open(os.path.join(args.out, "fantasy_scans", f"{scan_id}.json"), "w", encoding="utf-8") as fp:
        json.dump(data, fp, ensure_ascii=False, separators=(",", ":"))

    fid_map = {f["id"]: f for f in fant_meta}
    rows = []
    for fid in [BASELINE_ID] + fids:
        pts = data["baseline"]["points"] if fid == BASELINE_ID else curves[fid]["points"]
        for p in pts:
            rows.append({
                "scan_id": scan_id, "fantasy_id": fid, "x_param": x_key, "x_value": p["x"],
                "n": p["n"], "wins": p["wins"], "win_rate": p["win_rate"],
                "delta": p.get("delta", ""), "delta_se": p.get("delta_se", ""),
                "delta_ci_lo": p["delta_ci"][0] if "delta_ci" in p else "",
                "delta_ci_hi": p["delta_ci"][1] if "delta_ci" in p else "",
                "mean_reached_floor": p["mean_reached_floor"], "mean_fantasies": p["mean_fantasies"],
                "death_act1_rate": p["death_by_act"][0], "death_act2_rate": p["death_by_act"][1],
                "death_act3_rate": p["death_by_act"][2],
                "fidelity": "" if fid == BASELINE_ID else fid_map[fid]["fidelity"],
                "cache_key": keys[(fid, p["x"])],
            })
    ms.append_rows(os.path.join(args.out, "fantasy_curves.csv"), rows)

    if not args.quiet:
        el = time.perf_counter() - t0
        print(f"완료 {el:.0f}s → {os.path.abspath(json_path)} (scan_id {scan_id})")
        bx = "  ".join(f"{p['x']}:{p['win_rate'] * 100:.1f}%" for p in data["baseline"]["points"])
        print(f"  기준선 승률  {bx}")
    return data


if __name__ == "__main__":
    main()
