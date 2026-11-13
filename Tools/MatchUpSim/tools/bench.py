#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""속도 벤치마크 (명세 v2 S0).

  python tools/bench.py [--runs 600] [--profile] [--module matchup_sim]

v4.2 기본(몬스터 JSON 체력 + digits + 기믹, 시작 체력 150)과 구버전 설정 3종(tier_avg: grade hp_base=74,
table hp_base=660, table hp_base=300)에서 판당 ms, 평균 도달 층,
(--profile 이면) 함수별 비중을 출력한다. --module 로 비교 대상 모듈(예: tests/_matchup_sim_v1)을 바꿀 수 있다.
"""
import argparse
import copy
import cProfile
import importlib
import os
import pstats
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tests"))

CONFIGS = [
    ("기본 v4.2 (JSON 체력)", "fantasy_effects.json", None),   # v1 모듈에는 없음 (건너뜀)
    ("grade hp_base=74", None, 74),
    ("table hp_base=660", "fantasy_effects.json", 660),
    ("table hp_base=300", "fantasy_effects.json", 300),
    ("table hp_base=300 불씨", "fantasy_effects.json", 300),   # v3: 불씨 획득 모드 (v1 모듈에는 없음)
]


def make_cfg(ms, effects, hp):
    """hp = None 이면 v4.2 기본 설정, 숫자면 구버전(tier_avg + gauss) 설정에 hp_base 를 넣는다."""
    cfg = copy.deepcopy(ms.DEFAULT_CONFIG)
    if hp is None:
        if not hasattr(ms, "LEGACY_MONSTERS"):
            return None
    else:
        if hasattr(ms, "LEGACY_MONSTERS"):
            cfg["monsters"].update(ms.LEGACY_MONSTERS)
        cfg["monsters"]["act_hp_growth"] = 2.0
        cfg["monsters"]["hp_base"] = hp
    if effects:
        cfg["fantasy"]["effects_file"] = os.path.join(ROOT, effects)
        cfg["fantasy"]["effect_mode"] = "table"
    return cfg


def ember(cfg):
    cfg["rewards"]["normal_battle"]["mode"] = "ember"
    return cfg


def run(ms, cfg, runs, seed="bench"):
    ctx = ms.SimContext(cfg)
    rows = []
    t0 = time.perf_counter()
    for i in range(runs):
        rows.append(ms.simulate_run(cfg, f"{seed}-{i}", ctx=ctx))
    dt = time.perf_counter() - t0
    return dt, rows


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=int, default=600)
    ap.add_argument("--repeat", type=int, default=3, help="반복 측정 후 최솟값 사용")
    ap.add_argument("--profile", action="store_true")
    ap.add_argument("--module", default="matchup_sim")
    args = ap.parse_args(argv)
    ms = importlib.import_module(args.module)
    print(f"모듈 {args.module} (SIM_VERSION {getattr(ms, 'SIM_VERSION', '?')}), {args.runs}판 x {args.repeat}회 중 최소")
    out = {}
    for name, eff, hp in CONFIGS:
        cfg = make_cfg(ms, eff, hp)
        if cfg is None:
            continue
        if "불씨" in name:
            if "rewards" not in cfg:
                continue
            cfg = ember(cfg)
        best = None
        for _ in range(args.repeat):
            dt, rows = run(ms, cfg, args.runs)
            best = dt if best is None else min(best, dt)
        floor = sum(r["reached_floor"] for r in rows) / len(rows)
        ms_per = best / args.runs * 1000
        out[name] = ms_per
        print(f"  {name:<20} 판당 {ms_per:6.3f} ms | 평균 도달 {floor:5.2f}층")
        if args.profile:
            pr = cProfile.Profile()
            pr.enable()
            run(ms, cfg, args.runs)
            pr.disable()
            st = pstats.Stats(pr)
            total = sum(v[2] for v in st.stats.values())
            rows = sorted(((v[2], k) for k, v in st.stats.items()), reverse=True)[:8]
            for t, k in rows:
                print(f"      {t / total * 100:5.1f}%  {k[2]} ({os.path.basename(k[0])}:{k[1]})")
    return out


if __name__ == "__main__":
    main()
