#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
환상 쌍 시너지 (명세 v2 F4)
===========================

  python synergy_scan.py --effects fantasy_effects.json --x monsters.hp_base=700 --top 10 \\
      --set monsters.act_hp_growth=2.0 --seed scan1

단일 Δ 상위 K개(기본 10, --include 로 추가) x 전체 환상 쌍을 선택한 X 하나에서 돌린다.
I = Δ(AB) − Δ(A) − Δ(B), 판마다 w_AB − w_A − w_B + w_0 의 평균과 표본표준오차.
쌍이 많으므로 신호는 |I/se| ≥ 4.0 (Bonferroni 근사)일 때만. 적응형 표본 추출을 쓴다.
결과: sim_results/synergy.json
"""
from __future__ import annotations

import argparse
import copy
import json
import os
import sys
import time
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import fantasy_scan as fs  # noqa: E402
import matchup_sim as ms  # noqa: E402
from sim_service import compute as cp  # noqa: E402
from sim_service import stats as S  # noqa: E402
from sim_service import store as st  # noqa: E402

SIGNAL_Z = 4.0


def run_synergy(engine, cfg, thash, seed, x_key, x, fids_all, top_k=10, include=(), stages=(500, 1500, 3000),
                epsilon=0.015, cancel=None, on_pair=None, log=print):
    c = copy.deepcopy(cfg)
    ms.set_path(c, x_key, x)
    order = {f: i for i, f in enumerate(fids_all)}
    req = lambda fids: cp.make_req(c, sorted(fids, key=order.get), seed, thash)  # noqa: E731
    base = req([])
    singles = {f: req([f]) for f in fids_all}
    # 단일 Δ (첫 단계 → 마지막 단계까지 순위용)
    recs = engine.ensure([base] + list(singles.values()), stages[-1], cancel=cancel)
    single = {f: S.paired_delta(recs[r["key"]], recs[base["key"]]) for f, r in singles.items()}
    ranked = sorted(fids_all, key=lambda f: -single[f]["delta"])
    top = list(dict.fromkeys(ranked[:top_k] + [f for f in include if f in order]))
    pairs = []
    seen = set()
    for a in top:
        for b in fids_all:
            if a == b:
                continue
            k = tuple(sorted((a, b), key=order.get))
            if k not in seen:
                seen.add(k)
                pairs.append(k)
    log(f"  상위 {len(top)}종 x 전체 → 쌍 {len(pairs)}개, X={x}")
    active = list(pairs)
    final = {}
    preqs = {p: req(list(p)) for p in pairs}
    for si, n in enumerate(stages):
        if not active:
            break
        last = si == len(stages) - 1
        recs = engine.ensure([preqs[p] for p in active], n, cancel=cancel)
        still = []
        for p in active:
            r_ab = recs[preqs[p]["key"]]
            I = S.interaction(r_ab, engine.store.load(singles[p[0]]["key"]), engine.store.load(singles[p[1]]["key"]),
                              engine.store.load(base["key"]), n)
            if not last and S.half_width(I["se"]) > epsilon:
                still.append(p)
                continue
            final[p] = I
            if on_pair:
                on_pair(p, I)
        active = still
    return top, single, final, len(pairs)


def main(argv=None):
    ap = argparse.ArgumentParser(description="환상 쌍 시너지")
    ap.add_argument("--effects", default=os.path.join(HERE, "fantasy_effects.json"))
    ap.add_argument("--x", required=True, metavar="KEY=VALUE", help="예: monsters.hp_base=700")
    ap.add_argument("--top", type=int, default=10)
    ap.add_argument("--include", default="", help="상위 목록에 추가할 환상 ID (쉼표)")
    ap.add_argument("--fantasies", default="all", help="쌍 상대 후보 (기본 전체)")
    ap.add_argument("--set", action="append", default=[])
    ap.add_argument("--seed", default="scan1")
    ap.add_argument("--n-stages", default="500,1500,3000")
    ap.add_argument("--epsilon", type=float, default=0.015)
    ap.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2) - 1))
    ap.add_argument("--results", default=os.path.join(HERE, "sim_results"))
    ap.add_argument("--out", default=None)
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args(argv)
    log = (lambda *a, **k: None) if args.quiet else print
    cfg, fixed = fs.build_cfg(None, args.set, args.effects)
    x_key, xv = args.x.split("=", 1)
    x = ms.parse_value(xv)
    ctx = ms.SimContext(cfg)
    thash = st.table_hash(list(ctx.table.values()))
    fids = list(ctx.table) if args.fantasies == "all" else [f.strip() for f in args.fantasies.split(",") if f.strip()]
    engine = cp.Engine(st.PointStore(os.path.join(args.results, "point_cache")), args.workers)
    t0 = time.perf_counter()
    try:
        top, single, final, n_pairs = run_synergy(
            engine, cfg, thash, args.seed, x_key.strip(), x, fids, args.top,
            [f.strip() for f in args.include.split(",") if f.strip()],
            [int(s) for s in args.n_stages.split(",")], args.epsilon, log=log)
    finally:
        engine.close()
    meta_f = {f: ctx.table.get(f, {}) for f in fids}
    pairs = []
    for (a, b), I in final.items():
        z = I["I"] / I["se"] if I["se"] > 0 else 0.0
        pairs.append({"a": a, "b": b, **I, "z": round(z, 3), "signal": abs(z) >= SIGNAL_Z,
                      "none_involved": meta_f[a].get("fidelity") == "none" or meta_f[b].get("fidelity") == "none"})
    pairs.sort(key=lambda p: -abs(p["z"]))
    used = sum(p["n"] for p in pairs)
    data = {
        "meta": {"generated_at": datetime.now().isoformat(timespec="seconds"), "x_param": x_key.strip(), "x": x,
                 "seed": args.seed, "table_hash": thash, "fixed_overrides": fixed, "top_k": args.top,
                 "signal_z": SIGNAL_Z, "stages": [int(s) for s in args.n_stages.split(",")], "epsilon": args.epsilon,
                 "pairs": n_pairs, "runs_used_pairs": used, "elapsed_s": round(time.perf_counter() - t0, 1)},
        "top": top,
        "fantasies": [{"id": f, "name": meta_f[f].get("name", f), "grade": meta_f[f].get("grade"),
                       "fidelity": meta_f[f].get("fidelity")} for f in fids],
        "single": single,
        "pairs": pairs,
    }
    out = args.out or os.path.join(args.results, "synergy.json")
    with open(out, "w", encoding="utf-8") as fp:
        json.dump(data, fp, ensure_ascii=False, separators=(",", ":"))
    sig = [p for p in pairs if p["signal"]]
    log(f"완료 {data['meta']['elapsed_s']}s → {out}: 쌍 {len(pairs)}개, 신호 {len(sig)}개")
    names = {f["id"]: f["name"] for f in data["fantasies"]}
    for p in sig[:15]:
        log(f"  {names[p['a']]} + {names[p['b']]}: I = {p['I'] * 100:+.2f}%p (z={p['z']:.1f}, n={p['n']})")
    return data


if __name__ == "__main__":
    main()
