# -*- coding: utf-8 -*-
"""점 레코드(시드 접두 결과)에서 통계를 계산한다. 모든 함수는 앞 n판(접두)만 쓸 수 있다."""
from __future__ import annotations

import math

import matchup_sim as ms

Z95 = 1.96
MDE_K = 2.8        # 최소 검출 효과 ≈ 2.8·se (유의수준 5%, 검정력 80% 근사)
LOW_INFO_FLIPS = 30


def _n(rec, n):
    return rec["n"] if n is None else min(n, rec["n"])


def point_stats(rec, x, n=None):
    n = _n(rec, n)
    if n <= 0:
        return {"x": x, "n": 0, "wins": 0, "win_rate": None, "mean_reached_floor": None, "mean_fantasies": None,
                "death_by_act": [None, None, None], "reach_rate": [None] * ms.TOTAL_FLOORS}
    wins = rec["wins"][:n].count("1")
    reached = rec["reached"][:n]
    da = rec["death_act"][:n]
    counts = [0] * (ms.TOTAL_FLOORS + 2)
    for r in reached:
        counts[r] += 1
    reach_rate, acc = [], 0
    for f in range(ms.TOTAL_FLOORS, 0, -1):
        acc += counts[f]
        reach_rate.append(acc)
    reach_rate.reverse()
    return {
        "x": x, "n": n, "wins": wins,
        "win_rate": round(wins / n, 6),
        "mean_reached_floor": round(sum(reached) / n, 4),
        "mean_fantasies": round(sum(rec["nfant"][:n]) / n, 4),
        "death_by_act": [round(sum(1 for a in da if a == k) / n, 6) for k in (1, 2, 3)],
        "reach_rate": [round(v / n, 6) for v in reach_rate],
        "table_hash": rec.get("table_hash"),
        "data_hash": rec.get("data_hash") or rec.get("table_hash"),
        "arm": {"forced": rec.get("fids", []), "banned": rec.get("banned", [])},
        **extra_stats(rec),
    }


def extra_stats(rec):
    """출처별 평균 환상 수·불씨 통계·층별 평균 환상 수. 레코드 전체 n 기준(접두로 자를 수 없는 합계)."""
    n = rec.get("n", 0)
    agg = rec.get("agg")
    if not n or not agg:
        return {}
    out = {"agg_n": n, "src_mean": {k[10:]: round(agg[k] / n, 4) for k in agg if k.startswith("fantasies_")},
           "ember_mean": {k: round(agg[k] / n, 4) for k in agg if not k.startswith("fantasies_")}}
    if not rec.get("fids") and sum(rec.get("fbf_n", ())):
        out["fant_by_floor"] = {"mean": [round(s / c, 3) if c else None for s, c in zip(rec["fbf_sum"], rec["fbf_n"])],
                                "n": list(rec["fbf_n"])}
    return out


def paired_mean_se(diffs):
    n = len(diffs)
    if n == 0:
        return 0.0, 0.0
    mean = sum(diffs) / n
    if n > 1:
        var = sum((d - mean) ** 2 for d in diffs) / (n - 1)
        se = math.sqrt(var / n)
    else:
        se = 0.0
    return mean, se


def _ci(mean, se):
    return [round(mean - Z95 * se, 6), round(mean + Z95 * se, 6)]


def paired_delta(rec_f, rec_b, n=None):
    """같은 시드 i 끼리 d_i = win_i(f) - win_i(b). 공통 접두 n 판."""
    n = min(rec_f["n"], rec_b["n"], n if n is not None else 10 ** 12)
    a, b = rec_f["wins"][:n], rec_b["wins"][:n]
    d = [(ca == "1") - (cb == "1") for ca, cb in zip(a, b)]
    mean, se = paired_mean_se(d)
    up, down = d.count(1), d.count(-1)
    rd = [x - y for x, y in zip(rec_f["reached"][:n], rec_b["reached"][:n])]
    rmean, rse = paired_mean_se(rd)
    return {"delta": round(mean, 6), "delta_se": round(se, 6), "delta_ci": _ci(mean, se), "delta_n": n,
            "flips_up": up, "flips_down": down, "mde": round(MDE_K * se, 6),
            "mean_reach_delta": round(rmean, 4), "mean_reach_delta_se": round(rse, 4)}


def interaction(rec_ab, rec_a, rec_b, rec_0, n=None):
    """시너지 I = Δ(AB) - Δ(A) - Δ(B). 판마다 w_AB - w_A - w_B + w_0."""
    n = min(rec_ab["n"], rec_a["n"], rec_b["n"], rec_0["n"], n if n is not None else 10 ** 12)
    w = lambda r, i: r["wins"][i] == "1"  # noqa: E731
    d = [w(rec_ab, i) - w(rec_a, i) - w(rec_b, i) + w(rec_0, i) for i in range(n)]
    mean, se = paired_mean_se(d)
    return {"I": round(mean, 6), "se": round(se, 6), "ci": _ci(mean, se), "n": n}


def half_width(se):
    return Z95 * se


def independent_diff(d1, se1, d2, se2):
    """독립 표본 차이 (실력 패싯 격차 등): d1 - d2, se = √(se1² + se2²)."""
    d = d1 - d2
    se = math.sqrt(se1 * se1 + se2 * se2)
    return {"gap": round(d, 6), "gap_se": round(se, 6), "gap_ci": _ci(d, se)}


def crossing(points, T, key="win_rate"):
    """목표 T 와 만나는 X (이웃 두 점 선형 보간, 외삽 없음, 여러 번이면 가장 큰 X)."""
    pts = sorted((p for p in points if p.get(key) is not None), key=lambda p: p["x"])
    xs = [p["x"] for p in pts]
    ys = [p[key] for p in pts]
    hits = []
    for k in range(len(ys) - 1):
        a, b = ys[k] - T, ys[k + 1] - T
        if a == 0:
            hits.append(xs[k])
        elif a * b < 0:
            hits.append(xs[k] + (xs[k + 1] - xs[k]) * (a / (a - b)))
    if ys and ys[-1] == T:
        hits.append(xs[-1])
    if not hits:
        # 교차가 범위 밖이면 어느 쪽인지: dir = 1 (X 최대보다 위), −1 (X 최소보다 아래). 곡선 방향은 데이터로 판정
        # (v4.2: X = 시작 체력이면 증가 곡선 — 모두 목표 위면 교차는 X 최소 아래)
        above = bool(ys) and all(y > T for y in ys)
        up = len(xs) >= 2 and monotone_direction(xs, ys)
        return {"x": None, "dir": 1 if above != up else -1}
    return {"x": max(hits), "noisy": len(set(round(h, 6) for h in hits)) > 1, "hits": sorted(hits)}


# ---------------------------------------------------------------------------
# 조합 통계 (v3 F4a): 부분집합 팔들의 판별 승패에서 Δ, I, R 을 계산
# ---------------------------------------------------------------------------
def _w(rec, n):
    return [1 if c == "1" else 0 for c in rec["wins"][:n]]


def contrast(vals):
    mean, se = paired_mean_se(vals)
    return round(mean, 6), round(se, 6), _ci(mean, se)


def combo_stats(recs, ids, n=None):
    """recs: {frozenset(ids 부분집합): rec} (같은 X, 같은 시드). 반환: 팔별 Δ·기대 Δ, 쌍별 I, 전체 집합 잔여 R.

    Δ_S = mean(w_S − w_0),  I_ij = mean(w_ij − w_i − w_j + w_0),  R = Δ_K − Σ Δ_i − Σ I_ij  (K = 전체, |K| ≥ 3)
    항등식 Δ_K = Σ Δ_i + Σ I_ij + R 이 판별 값 수준에서 성립한다.
    """
    from itertools import combinations
    n = min([r["n"] for r in recs.values()] + ([n] if n else []))
    w = {k: _w(r, n) for k, r in recs.items()}
    w0 = w[frozenset()]
    single = {}
    arms = {}
    for k in recs:
        d = [a - b for a, b in zip(w[k], w0)]
        mean, se, ci = contrast(d)
        rd = [a - b for a, b in zip(recs[k]["reached"][:n], recs[frozenset()]["reached"][:n])]
        rmean, rse = paired_mean_se(rd)
        arms[k] = {"ids": sorted(k, key=ids.index), "n": n, "wins": sum(w[k]), "win_rate": round(sum(w[k]) / n, 6),
                   "delta": mean, "delta_se": se, "delta_ci": ci, "flips_up": d.count(1), "flips_down": d.count(-1),
                   "mde": round(MDE_K * se, 6), "mean_reach_delta": round(rmean, 4), "mean_reach_delta_se": round(rse, 4)}
        ps = point_stats(recs[k], None, n)      # 생존 곡선·평균 도달 층 (뷰어의 조합 곡선)
        arms[k].update({"reach_rate": ps["reach_rate"], "mean_reached_floor": ps["mean_reached_floor"],
                        "mean_fantasies": ps["mean_fantasies"], "death_by_act": ps["death_by_act"]})
        if len(k) == 1:
            single[next(iter(k))] = mean
    for k, a in arms.items():
        a["expected_delta"] = round(sum(single.get(i, 0.0) for i in k), 6) if k else 0.0
    pairs = []
    pair_vals = {}
    for i, j in combinations(ids, 2):
        kij = frozenset((i, j))
        if kij not in w or frozenset((i,)) not in w or frozenset((j,)) not in w:
            continue
        v = [ab - a - b + z for ab, a, b, z in zip(w[kij], w[frozenset((i,))], w[frozenset((j,))], w0)]
        pair_vals[kij] = v
        mean, se, ci = contrast(v)
        sat = any(arms[x]["win_rate"] < 0.05 or arms[x]["win_rate"] > 0.95
                  for x in (frozenset(), frozenset((i,)), frozenset((j,)), kij))
        label = "뚜렷한 상호작용 없음" if ci[0] <= 0 <= ci[1] else ("상승작용 가능" if mean > 0 else "중복·포화 가능")
        pairs.append({"a": i, "b": j, "I": mean, "se": se, "ci": ci, "n": n, "saturated": sat, "label": label})
    R = None
    full = frozenset(ids)
    if len(ids) >= 3 and full in w and len(pair_vals) == len(list(combinations(ids, 2))):
        v = []
        for t in range(n):
            x = w[full][t] - w0[t]
            x -= sum(w[frozenset((i,))][t] - w0[t] for i in ids)
            x -= sum(pv[t] for pv in pair_vals.values())
            v.append(x)
        mean, se, ci = contrast(v)
        R = {"R": mean, "se": se, "ci": ci, "n": n}
    return {"n": n, "arms": arms, "pairs": pairs, "R": R}


# ---------------------------------------------------------------------------
# 등가 체력 이득 (v3 §9.3): 기준선 승률 곡선을 단조 회귀(PAVA)로 고르고 팔의 승률에 해당하는 X 를 역산
# ---------------------------------------------------------------------------
def pava(ys, ws=None, increasing=True):
    """가중 단조 회귀 (pool adjacent violators)."""
    ws = ws or [1.0] * len(ys)
    if not increasing:
        return [-v for v in pava([-y for y in ys], ws, True)]
    blocks = []
    for y, w in zip(ys, ws):
        blocks.append([y * w, w, 1])
        while len(blocks) > 1 and blocks[-2][0] / blocks[-2][1] > blocks[-1][0] / blocks[-1][1]:
            s, w2, c = blocks.pop()
            blocks[-1][0] += s
            blocks[-1][1] += w2
            blocks[-1][2] += c
    out = []
    for s, w, c in blocks:
        out.extend([s / w] * c)
    return out


def monotone_direction(xs, ys):
    mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys)) >= 0


def equiv_gain(xs, base_w, arm_w, x0, base_n=None, flat_tol=1e-4):
    """기준선이 arm_w 를 내는 X(x_eq) 를 구해 (x_eq − x0, None) 을 돌려준다. 산출 불가면 (None, 이유).

    xs: 기준선 X 격자(오름차순), base_w: 기준선 승률, arm_w: X=x0 에서 팔의 승률."""
    if len(xs) < 2:
        return None, "기준선 점 부족"
    inc = monotone_direction(xs, base_w)
    fit = pava(base_w, base_n, inc)
    k0 = min(range(len(xs)), key=lambda k: abs(xs[k] - x0))
    lo, hi = max(0, k0 - 1), min(len(xs) - 1, k0 + 1)
    if abs(fit[hi] - fit[lo]) < flat_tol:
        return None, "기준선이 이 구간에서 평탄"
    fmin, fmax = min(fit), max(fit)
    if arm_w > fmax or arm_w < fmin:
        return None, "격자 범위 밖"
    cands = []
    for k in range(len(xs) - 1):
        a, b = fit[k], fit[k + 1]
        if a == b:
            if a == arm_w:
                cands += [xs[k], xs[k + 1]]
            continue
        if min(a, b) <= arm_w <= max(a, b):
            cands.append(xs[k] + (xs[k + 1] - xs[k]) * (arm_w - a) / (b - a))
    if not cands:
        return None, "격자 범위 밖"
    x_eq = min(cands, key=lambda v: abs(v - x0))
    return x_eq - x0, None


def equiv_gain_ci(xs, base_recs, arm_rec, x0, n=None, B=200, seed=1):
    """시드 재표본(B ≤ 200)으로 등가 체력 이득의 분위수 CI. 기준선 곡선과 팔을 같은 재표본에서 다시 구한다."""
    import random
    n = min([r["n"] for r in base_recs] + [arm_rec["n"]] + ([n] if n else []))
    bw = [_w(r, n) for r in base_recs]
    aw = _w(arm_rec, n)
    point, why = equiv_gain(xs, [sum(w) / n for w in bw], sum(aw) / n, x0)
    if point is None:
        return {"gain": None, "reason": why}
    rnd = random.Random(seed)
    vals, fails = [], 0
    for _ in range(min(B, 200)):
        idx = [rnd.randrange(n) for _ in range(n)]
        g, _why = equiv_gain(xs, [sum(w[i] for i in idx) / n for w in bw], sum(aw[i] for i in idx) / n, x0)
        if g is None:
            fails += 1
        else:
            vals.append(g)
    if len(vals) < 20 or fails > len(vals):
        return {"gain": round(point, 4), "ci": None, "reason": "재표본에서 산출 불가가 많음(평탄 구간)"}
    vals.sort()
    q = lambda p: vals[min(len(vals) - 1, max(0, int(round(p * (len(vals) - 1)))))]  # noqa: E731
    return {"gain": round(point, 4), "ci": [round(q(0.025), 4), round(q(0.975), 4)], "B": len(vals), "n": n}
