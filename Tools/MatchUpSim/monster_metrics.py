#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""몬스터별 지표 실행 (명세 v2 F2, 조우 시 전투 승률·조우한 런 승률 포함).

  python import_monsters.py
  python monster_metrics.py --runs 3000 --set monsters.act_hp_growth=2.0 [--effects fantasy_effects.json]

monsters.model=table (monster_table.json 의 실제 몬스터)로 돌려 sim_results/monster_metrics.json 을 만든다.
"""
import argparse
import json
import multiprocessing as mp
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import fantasy_scan as fs  # noqa: E402
from sim_service import monsters as mo  # noqa: E402


def main(argv=None):
    ap = argparse.ArgumentParser(description="몬스터별 지표")
    ap.add_argument("--table", default=os.path.join(HERE, "monster_table.json"))
    ap.add_argument("--effects", default=os.path.join(HERE, "fantasy_effects.json"))
    ap.add_argument("--set", action="append", default=[])
    ap.add_argument("--runs", type=int, default=3000)
    ap.add_argument("--seed", default="mon1")
    ap.add_argument("--select", default="independent", choices=["independent", "shuffle_bag"])
    ap.add_argument("--hp-scale", type=float, default=1.0, help="monsters.hp_scale")
    ap.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2) - 1))
    ap.add_argument("--out", default=os.path.join(HERE, "sim_results", "monster_metrics.json"))
    args = ap.parse_args(argv)
    cfg, _ = fs.build_cfg(None, args.set, args.effects)
    cfg["monsters"]["model"] = "table"
    cfg["monsters"]["table_file"] = os.path.abspath(args.table)
    cfg["monsters"]["select"] = args.select
    cfg["monsters"]["hp_scale"] = args.hp_scale
    with open(args.table, encoding="utf-8") as fp:
        table = json.load(fp)
    t0 = time.perf_counter()
    if args.workers > 1:
        with mp.get_context("spawn").Pool(args.workers) as pool:
            res = mo.run_metrics(cfg, args.seed, args.runs, pool, monster_table=table)
    else:
        res = mo.run_metrics(cfg, args.seed, args.runs, monster_table=table)
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    mo.write(res, cfg, args.seed, args.runs, args.out)
    print(f"{args.out}: {args.runs}판, {time.perf_counter() - t0:.0f}s, 사망 {res['deaths']}판, 전체 승률 {res['win_rate'] * 100:.1f}%")
    for r in res["monsters"]:
        flag = " ⚠" if r["warning"] else ""
        print(f"  {r['act']}막 {r['tier']:<6} {r['name']:<8} 전투 {r['battles']:>5} | 평균 {r['avg_turns']:5.2f}턴 "
              f"(목표 {r['turn_target']}, {r['turn_verdict']}) | 받은 피해 {r['avg_taken']:6.1f} | "
              f"사망 비중 {r['death_share'] * 100:5.1f}% | 전투 승률 {r['battle_win_rate'] * 100:5.1f}% | "
              f"조우한 런 승률 {r['run_win_rate_met'] * 100:5.1f}% | 최대 1타 {r['max_hit_max']}{flag}")
    return res


if __name__ == "__main__":
    main()
