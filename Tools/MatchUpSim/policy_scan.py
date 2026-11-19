#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""배분 정책 민감도 점검 (v4.5 F22-B, AC-B6).

player.policy.attack_weight(w) 를 바꿔 가며 같은 조건을 돌려 아래를 비교한다.
  - 기준선 승률 (환상 없음), 환상 단독 강제 포함 팔들의 평균 승률
  - 환상별 단독 Δ 순위의 스피어만 상관 (기준 w = 0.5 대비)
  - 보스 사망 비중, 전투당 평균 턴 수 (몬스터별 지표, 환상 없음)
기존 점 캐시(PointStore)와 fantasy_scan 엔진을 그대로 쓴다. w 가 설정 해시에 들어가므로 캐시가 섞이지 않는다.

  python policy_scan.py --runs 1000 --weights 0.3,0.4,0.5,0.6,0.7
  python policy_scan.py --runs 400 --fantasies fan_damage_libra,fan_shop_discount --metric-runs 600
결과는 sim_results/policy_scan/policy_scan.json (+ .csv). 사용자가 w = 0.5 유지를 확정했으므로(D4) 기본값을 바꾸는 근거가 아니라 해석 가이드 참고 정보다.
"""
import argparse
import copy
import csv
import json
import multiprocessing as mp
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import fantasy_scan as fs  # noqa: E402
import matchup_sim as ms  # noqa: E402
from sim_service import compute as cp  # noqa: E402
from sim_service import monsters as mo  # noqa: E402
from sim_service import store as st  # noqa: E402

W_PATH = "player.policy.attack_weight"
DEFAULT_WEIGHTS = (0.3, 0.4, 0.5, 0.6, 0.7)


def ranks(vals):
    """평균 순위 (동률은 평균). 값이 클수록 순위가 크다."""
    order = sorted(range(len(vals)), key=lambda i: vals[i])
    out = [0.0] * len(vals)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and vals[order[j + 1]] == vals[order[i]]:
            j += 1
        for k in range(i, j + 1):
            out[order[k]] = (i + j) / 2 + 1
        i = j + 1
    return out


def spearman(a, b):
    if len(a) != len(b) or len(a) < 2:
        return None
    ra, rb = ranks(a), ranks(b)
    ma, mb = sum(ra) / len(ra), sum(rb) / len(rb)
    cov = sum((x - ma) * (y - mb) for x, y in zip(ra, rb))
    va, vb = sum((x - ma) ** 2 for x in ra), sum((y - mb) ** 2 for y in rb)
    return None if va == 0 or vb == 0 else cov / (va * vb) ** 0.5


def monster_summary(res):
    rows = res["monsters"]
    battles = sum(r["battles"] for r in rows)
    boss_share = sum(r["death_share"] for r in rows if r["tier"] == "boss")
    turns = sum(r["avg_turns"] * r["battles"] for r in rows) / max(1, battles)
    return {"run_win_rate": res["win_rate"], "boss_death_share": round(boss_share, 4), "avg_turns_per_battle": round(turns, 3)}


def run_weight(w, args, fids, engine, table):
    cfg, _ = fs.build_cfg(None, list(args.set) + [f"{W_PATH}={w}", "monsters.damage_model=digits", "monsters.gimmicks=on"], args.effects)
    cfg["monsters"]["model"] = "table"
    cfg["monsters"]["table_file"] = os.path.abspath(args.table)
    ctx = ms.SimContext(cfg)
    thash = st.table_hash(list(ctx.table.values())) if ctx.table else "grade"
    x_key, x_values = "player.start_hp", [cfg["player"]["start_hp"]]
    res = fs.run_scan(engine, cfg, thash, args.seed, x_key, x_values, fids, stages=[args.runs], log=lambda *a, **k: None)
    sc = res[fs.facet_label(None)]
    base = sc["baseline"][0]
    arms = {fid: sc["curves"][fid][0] for fid in fids}
    delta = {fid: round(arms[fid]["win_rate"] - base["win_rate"], 6) for fid in fids}
    mres = mo.run_metrics(cfg, args.seed + "-m", args.metric_runs, engine.pool, monster_table=table)
    return {"w": w, "baseline_win_rate": base["win_rate"], "baseline_n": base["n"],
            "mean_fantasy_win_rate": round(sum(a["win_rate"] for a in arms.values()) / max(1, len(arms)), 6),
            "delta": delta, **monster_summary(mres)}


def main(argv=None):
    ap = argparse.ArgumentParser(description="배분 정책 민감도 (attack_weight)")
    ap.add_argument("--weights", default=",".join(str(w) for w in DEFAULT_WEIGHTS))
    ap.add_argument("--fantasies", default="all", help="all 또는 ID,ID,...")
    ap.add_argument("--runs", type=int, default=1000, help="점당 판 수 (환상·기준선)")
    ap.add_argument("--metric-runs", type=int, default=3000, help="보스 사망 비중·평균 턴을 재는 판 수")
    ap.add_argument("--seed", default="pol1")
    ap.add_argument("--set", action="append", default=[], metavar="KEY=VALUE")
    ap.add_argument("--effects", default=os.path.join(HERE, "fantasy_effects.json"))
    ap.add_argument("--table", default=os.path.join(HERE, "monster_table.json"))
    ap.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2) - 1))
    ap.add_argument("--out", default=os.path.join(HERE, "sim_results", "policy_scan"))
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args(argv)
    log = (lambda *a, **k: None) if args.quiet else print
    weights = [float(x) for x in args.weights.split(",") if x.strip()]
    if not weights or any(not 0 <= w <= 1 for w in weights):
        raise SystemExit("--weights 는 0~1 사이 값")
    if 0.5 not in weights:
        weights = sorted(set(weights) | {0.5})          # 스피어만 기준
    cfg0, _ = fs.build_cfg(None, args.set, args.effects)
    ctx0 = ms.SimContext(cfg0)
    if args.fantasies.strip().lower() == "all":
        fids = list(ctx0.table.keys())
    else:
        fids = [x.strip() for x in args.fantasies.split(",") if x.strip()]
        for f in fids:
            if f not in ctx0.grade_of:
                raise SystemExit(f"알 수 없는 환상 ID: {f}")
    with open(args.table, encoding="utf-8") as fp:
        table = json.load(fp)
    os.makedirs(args.out, exist_ok=True)
    store = st.PointStore(os.path.join(args.out, "point_cache"))
    engine = cp.Engine(store, args.workers)
    t0 = time.perf_counter()
    rows = []
    try:
        for w in weights:
            log(f"w={w}: 환상 {len(fids)}종 x {args.runs}판 + 몬스터 지표 {args.metric_runs}판 …")
            rows.append(run_weight(w, args, fids, engine, table))
            log(f"  기준선 승률 {rows[-1]['baseline_win_rate'] * 100:.1f}% | 경과 {time.perf_counter() - t0:.0f}s")
    finally:
        engine.close()
    ref = next(r for r in rows if r["w"] == 0.5)
    for r in rows:
        r["spearman_vs_0.5"] = round(spearman([r["delta"][f] for f in fids], [ref["delta"][f] for f in fids]), 4) if len(fids) > 1 else None
    out = {"meta": {"runs": args.runs, "metric_runs": args.metric_runs, "seed": args.seed, "fantasies": len(fids), "weights": weights,
                    "sim_version": ms.SIM_VERSION, "elapsed_s": round(time.perf_counter() - t0, 1),
                    "note": "w=0.5 유지가 확정(D4) — 기본값을 바꾸는 근거가 아니라 참고 정보"}, "rows": rows}
    with open(os.path.join(args.out, "policy_scan.json"), "w", encoding="utf-8") as fp:
        json.dump(out, fp, ensure_ascii=False, indent=1)
    cols = ["w", "baseline_win_rate", "mean_fantasy_win_rate", "spearman_vs_0.5", "boss_death_share", "avg_turns_per_battle", "run_win_rate"]
    with open(os.path.join(args.out, "policy_scan.csv"), "w", encoding="utf-8-sig", newline="") as fp:
        wr = csv.writer(fp)
        wr.writerow(cols)
        for r in rows:
            wr.writerow([r.get(c) for c in cols])
    log("\n  w    기준선승률  환상평균승률  스피어만(w=0.5)  보스사망비중  평균턴/전투")
    for r in rows:
        sp = r["spearman_vs_0.5"]
        log(f"  {r['w']:<4} {r['baseline_win_rate'] * 100:9.1f}%  {r['mean_fantasy_win_rate'] * 100:10.1f}%  "
            f"{'-' if sp is None else format(sp, '.3f'):>14}  {r['boss_death_share'] * 100:10.1f}%  {r['avg_turns_per_battle']:9.2f}")
    return out


if __name__ == "__main__":
    mp.freeze_support()
    main()
