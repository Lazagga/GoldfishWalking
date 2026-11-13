#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""수치 보정 (명세 v2 F3).

  python calibrate.py --playtest playtest_runs.csv --params player.skill \\
      --effects fantasy_effects.json                       # v4.2 기본 (몬스터 JSON 체력)
  (구버전) ... --set 'monsters.model="tier_avg"' --set monsters.act_hp_growth=2.0 --set monsters.hp_base=660

플레이 기록 CSV 형식은 playtest_runs.template.csv 참고 (필수 열: run_id, result, end_act, end_floor).
결과: sim_results/calibration.json (맞춘 파라미터, 적합도, 층별 잔차, 목적함수 프로파일, cfg_edits)
"""
import argparse
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import fantasy_scan as fs  # noqa: E402
import matchup_sim as ms  # noqa: E402
from sim_service import calibrate as cal  # noqa: E402
from sim_service import compute as cp  # noqa: E402
from sim_service import store as st  # noqa: E402


def main(argv=None):
    ap = argparse.ArgumentParser(description="플레이 기록으로 시뮬레이터 파라미터 보정")
    ap.add_argument("--playtest", required=True)
    ap.add_argument("--params", default="player.skill", help="쉼표 구분, 최대 3개")
    ap.add_argument("--effects", default=os.path.join(HERE, "fantasy_effects.json"))
    ap.add_argument("--set", action="append", default=[])
    ap.add_argument("--n-sim", type=int, default=3000)
    ap.add_argument("--seed", default="cal")
    ap.add_argument("--max-evals", type=int, default=60)
    ap.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2) - 1))
    ap.add_argument("--results", default=os.path.join(HERE, "sim_results"))
    ap.add_argument("--out", default=None)
    args = ap.parse_args(argv)
    cfg, fixed = fs.build_cfg(None, args.set, args.effects)
    ctx = ms.SimContext(cfg)
    thash = st.table_hash(list(ctx.table.values())) if ctx.table else "grade"
    rows = cal.read_playtest(args.playtest)
    engine = cp.Engine(st.PointStore(os.path.join(args.results, "point_cache")), args.workers)
    t0 = time.perf_counter()
    try:
        res = cal.calibrate(engine, cfg, thash, args.seed, rows, [p.strip() for p in args.params.split(",") if p.strip()],
                            n_sim=args.n_sim, max_evals=args.max_evals,
                            on_eval=lambda p, sse: print(f"  {p} → 가중 SSE {sse:.2f}", flush=True))
    finally:
        engine.close()
    res["meta"] = {"playtest": os.path.basename(args.playtest), "fixed_overrides": fixed, "seed": args.seed,
                   "table_hash": thash, "elapsed_s": round(time.perf_counter() - t0, 1)}
    out = args.out or os.path.join(args.results, "calibration.json")
    with open(out, "w", encoding="utf-8") as fp:
        json.dump(res, fp, ensure_ascii=False, indent=1)
    print(f"→ {res['params']}  (가중 SSE {res['fit']['weighted_sse']}, χ²/자유도 {res['fit']['chi2_per_dof']}, "
          f"관측 {res['fit']['n_obs']}판)  {out}")
    for w in res["warnings"]:
        print(f"  ※ {w}")
    return res


if __name__ == "__main__":
    main()
