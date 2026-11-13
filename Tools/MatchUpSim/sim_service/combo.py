# -*- coding: utf-8 -*-
"""조합 모드 (v3 F4a): 환상 최대 4개의 모든 부분집합 팔을 같은 시드 접두로 돌려 Δ·I·R 을 구한다.

기준선 종류
- natural: 팔 = forced S, banned ∅. 빈 집합 = 일반 기준선, 단독 팔 = 단일 환상 곡선 (기존 캐시 재사용).
- banned : 체크한 집합 K 안에서 팔 = forced S, banned K∖S. 빈 집합 = K 전체를 뺀 기준선 (우연한 획득 없음).

팔 범위 (arms)
- all : 모든 부분집합 (2^k 팔, 쌍 시너지 I 와 잔여 R 계산).
- full: 빈 집합 + 단독 + 전체 집합만 (k + 2 팔). 뷰어의 '체크한 환상 조합 승률' — 단독 팔은 단일 곡선 캐시를 그대로 쓴다.
"""
from __future__ import annotations

import copy
from itertools import combinations

import matchup_sim as ms

from . import compute as cp
from . import stats as S

MAX_IDS = 4


def subsets(ids, arms="all"):
    if arms == "full":
        out = [frozenset()] + [frozenset((i,)) for i in ids]
        return out + ([frozenset(ids)] if len(ids) >= 2 else [])
    out = [frozenset()]
    for r in range(1, len(ids) + 1):
        out += [frozenset(c) for c in combinations(ids, r)]
    return out


def arm_req(cfg, x_key, x, sub, ids, order, baseline_type, seed, thash):
    c = copy.deepcopy(cfg)
    ms.set_path(c, x_key, x)
    forced = sorted(sub, key=order.index)                       # 정렬된 ID 집합 → 같은 조합은 같은 키
    banned = sorted(set(ids) - sub) if baseline_type == "banned" else None
    return cp.make_req(c, forced, seed, thash, tag=(x, sub), banned=banned)


def plan(cfg, x_key, xs, ids, order, baseline_type, seed, thash, engine, n_target, arms="all"):
    """필요한 팔과 새로 돌려야 할 판 수 (캐시 반영)."""
    if not 1 <= len(ids) <= MAX_IDS:
        raise ValueError(f"조합은 환상 1~{MAX_IDS}개")
    if baseline_type not in ("natural", "banned"):
        raise ValueError("baseline_type 은 natural 또는 banned")
    if arms not in ("all", "full"):
        raise ValueError("arms 는 all 또는 full")
    reqs = [arm_req(cfg, x_key, x, sub, ids, order, baseline_type, seed, thash) for x in xs for sub in subsets(ids, arms)]
    need = sum(max(0, n_target - engine.record(r)["n"]) for r in reqs)
    return reqs, need


def run_combo(engine, cfg, thash, seed, x_key, xs, ids, order, baseline_type="natural", stages=(300, 1000, 3000),
              epsilon=0.015, cancel=None, on_stage=None, arms="all"):
    """반환: {"ids", "baseline_type", "x_values", "by_x": {x: combo_stats}, "n"}.
    단계마다 on_stage(n, by_x) 를 부르고, 모든 쌍의 I 95% CI 반폭 ≤ ε 이면 일찍 멈춘다."""
    ids = sorted(ids, key=order.index)
    reqs, _ = plan(cfg, x_key, xs, ids, order, baseline_type, seed, thash, engine, stages[-1], arms)
    full = frozenset(ids)
    by_x = {}
    for n in stages:
        recs = engine.ensure(reqs, n, cancel=cancel)
        by_x = {}
        for x in xs:
            rs = {r["tag"][1]: recs[r["key"]] for r in reqs if r["tag"][0] == x}
            st_ = S.combo_stats(rs, ids, n)
            st_["data_hash"] = reqs[0]["dhash"]
            by_x[x] = st_
        if on_stage:
            on_stage(n, by_x)
        hw = [S.half_width(p["se"]) for st_ in by_x.values() for p in st_["pairs"]] if arms == "all" else             [S.half_width(st_["arms"][full]["delta_se"]) for st_ in by_x.values() if full in st_["arms"]]
        if hw and max(hw) <= epsilon:
            break
    return {"ids": ids, "baseline_type": baseline_type, "arms": arms, "x_values": list(xs), "by_x": by_x,
            "n": next(iter(by_x.values()))["n"] if by_x else 0, "reqs": reqs}


def to_json(res, label="pre", by_x=None):
    """뷰어·결과 파일용 직렬화 (frozenset 키 → 'a+b'). label: pre(사전 지정) | explore(탐색)."""
    key = lambda k: "+".join(sorted(k, key=res["ids"].index)) or "__baseline__"  # noqa: E731
    by_x = by_x if by_x is not None else res["by_x"]
    out = {"ids": res["ids"], "baseline_type": res["baseline_type"], "arms": res.get("arms", "all"),
           "x_values": res["x_values"], "label": label,
           "by_x": []}
    for x in res["x_values"]:
        if x not in by_x:
            continue
        st_ = by_x[x]
        out["by_x"].append({"x": x, "n": st_["n"], "data_hash": st_.get("data_hash"),
                            "arms": {key(k): v for k, v in st_["arms"].items()},
                            "pairs": st_["pairs"], "R": st_["R"]})
    out["n"] = out["by_x"][0]["n"] if out["by_x"] else 0
    return out
