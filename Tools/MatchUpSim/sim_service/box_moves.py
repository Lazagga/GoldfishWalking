# -*- coding: utf-8 -*-
"""한 상자 안의 성냥 이동 표 (v4 F8.3).

게임 규칙 (Assets/1Scripts 에서 확인)
- 숫자 모양: 표준 7세그먼트 (MatchPatternTable). 7 = 위·오른쪽 위·오른쪽 아래 (3개).
- 성냥 1개를 집어 빈 자리에 놓으면 이동 1회. 한 번에 상자 하나만 연다 → 상자 안의 성냥 수는 보존된다.
- 분할(split): 자릿수 사이 이동 불가 (MatchEditSession_PreventsCrossDigitMovesWhenSplit).
- 잠긴 성냥: 집을 수 없다 (그 자리에 남아야 한다). 잠긴 자릿수(LockLeadingDigits): 그 자릿수의 성냥을 집거나 놓을 수 없다.
- 이동 불가(matchesMovable=false): 상자를 바꿀 수 없다.
- 닫을 때(MatchPatternInterpreter.ParseNumber): 빈 자릿수는 무시하고, 나머지 자릿수는 모두 유효한 숫자여야 한다.
  앞자리 0 허용(07 → 7, 사용자 확인 Q18). 모든 자릿수가 비면 무효.

reach(d, v, k, cons) = {도달 가능한 값: 최소 이동 횟수}. 상자 안 총 성냥 수가 보존되므로
목표 배치 T 가 도달 가능 ⇔ |T| = |S|, T ⊇ 잠긴 성냥, (분할이면 자릿수마다 |T_i| = |S_i|), 잠긴 자릿수는 그대로.
최소 이동 횟수 = Σ |T_i \\ S_i| (옮겨야 하는 성냥 수). 열거는 자릿수별 목표(0~9, 빈칸)의 곱을 가지치기하며 돈다.
"""
from __future__ import annotations


T, UR, LR, B, LL, UL, M = 1, 2, 4, 8, 16, 32, 64
DIGIT_MASK = (T | UR | LR | B | LL | UL, UR | LR, T | UR | M | LL | B, T | UR | M | LR | B, UL | M | UR | LR,
              T | UL | M | LR | B, T | UL | M | LL | LR | B, T | UR | LR, T | UR | LR | B | LL | UL | M,
              T | UR | LR | B | UL | M)
MASK_DIGIT = {m: d for d, m in enumerate(DIGIT_MASK)}
EMPTY = 0
TARGETS = tuple(DIGIT_MASK) + (EMPTY,)
VERSION = 1


def popcount(x):
    return bin(x).count("1")


def digits_of(v, d):
    s = str(int(v)).rjust(max(1, d), "0")
    return tuple(int(c) for c in s)


def masks_of(v, d):
    return tuple(DIGIT_MASK[c] for c in digits_of(v, d))


def parse(masks):
    """자릿수 마스크 → 값. 빈 자릿수는 무시, 나머지가 숫자가 아니면 None, 모두 비면 None."""
    out = []
    for m in masks:
        if m == EMPTY:
            continue
        dg = MASK_DIGIT.get(m)
        if dg is None:
            return None
        out.append(dg)
    if not out:
        return None
    v = 0
    for dg in out:
        v = v * 10 + dg
    return v


def norm_cons(d, split=False, locked=None, locked_digits=(), movable=True, masks=None):
    locked = tuple(locked) if locked else (0,) * d
    if masks is not None:   # 잠금은 실제로 놓여 있는 성냥에만 의미가 있다
        locked = tuple((locked[i] if i < len(locked) else 0) & masks[i] for i in range(len(masks)))
    return (bool(split), locked, tuple(sorted(locked_digits)), bool(movable))


_CACHE = {}
CACHE_MAX = 5000           # 항목 수 상한 (워커마다 메모리를 작게 유지)
CACHE_ITEM_MAX = 500       # 결과가 이보다 크면 캐시하지 않음 (큰 상자·큰 k)


def _reach(masks, k, cons):
    key = (masks, k, cons)
    hit = _CACHE.get(key)
    if hit is not None:
        return hit
    out = _reach_calc(masks, k, cons)
    if len(out) <= CACHE_ITEM_MAX:
        if len(_CACHE) >= CACHE_MAX:
            _CACHE.clear()
        _CACHE[key] = out
    return out


def _options(masks, k, cons):
    split, locked, locked_digits, movable = cons
    opts = []
    for i, S in enumerate(masks):
        L = locked[i] if i < len(locked) else 0
        if i in locked_digits:
            opts.append(((S, 0, 0),))
            continue
        o = []
        for Tm in TARGETS:
            if Tm & L != L:
                continue
            a, r = popcount(Tm & ~S), popcount(S & ~Tm)
            if split and a != r:
                continue
            if a > k or r > k:
                continue
            o.append((Tm, a, r))
        opts.append(tuple(o))
    return opts


def space_size(masks, k, cons):
    """완전 열거의 조합 수 (상한 추정)."""
    p = 1
    for o in _options(masks, k, cons):
        p *= max(1, len(o))
    return p


def _reach_calc(masks, k, cons):
    split, locked, locked_digits, movable = cons
    v0 = parse(masks)
    if not movable or k <= 0:
        return {v0: 0} if v0 is not None else {}
    n = len(masks)
    opts = _options(masks, k, cons)
    best = {}

    def rec(i, sa, sr, acc):
        if sa > k or sr > k:
            return
        if i == n:
            if sa != sr:
                return
            v = parse(acc)
            if v is not None and (v not in best or sa < best[v]):
                best[v] = sa
            return
        for Tm, a, r in opts[i]:
            rec(i + 1, sa + a, sr + r, acc + (Tm,))

    rec(0, 0, 0, ())
    return best


def reach(d, v, k, split=False, locked=None, locked_digits=(), movable=True):
    """자릿수 d(값이 더 길면 그 길이), 현재 값 v, 이동 k 이하로 도달 가능한 {값: 최소 이동}."""
    d = max(d, len(str(int(v))))
    masks = masks_of(v, d)
    return dict(_reach(masks, int(k), norm_cons(d, split, locked, locked_digits, movable, masks)))


EXACT_LIMIT = 50000   # 조합 수가 이보다 크면 reach_best 는 DP(이동 수별 최선 값)로 계산


def best_per_cost(masks, k, cons, better, cap=None):
    """자릿수 DP: 이동 수 c(= Σa = Σr ≤ k)별 최선 값(better=+1 최대, −1 최소)만 정확히 구한다.
    접두 값의 대소는 같은 접미에 대해 보존되므로(빈 자릿수는 곱하지 않음) 상태 (Σa, Σr, 비지 않음) 별 최선 접두만 남기면 된다.
    cap 이 있으면 값의 대소를 '각 자릿수를 min(자릿수, cap) 으로 바꾼 값' 기준으로 비교한다(화면 숫자는 그대로, 계산에서만 상한).
    반환하는 값은 항상 화면에 뜨는 원래 숫자다."""
    split, locked, locked_digits, movable = cons
    v0 = parse(masks)
    if not movable or k <= 0:
        return {v0: 0} if v0 is not None else {}
    states = {(0, 0, False): (0, 0)}            # 상태 → (비교 값, 화면 값)
    for o in _options(masks, k, cons):
        nxt = {}
        for (sa, sr, ne), (rk, raw) in states.items():
            for Tm, a, r in o:
                na, nr = sa + a, sr + r
                if na > k or nr > k:
                    continue
                if Tm == EMPTY:
                    key, nv = (na, nr, ne), (rk, raw)
                else:
                    dg = MASK_DIGIT[Tm]
                    key, nv = (na, nr, True), (rk * 10 + (dg if cap is None else min(dg, cap)), raw * 10 + dg)
                cur = nxt.get(key)
                if cur is None or better * nv[0] > better * cur[0]:
                    nxt[key] = nv
        states = nxt
    by_cost = {}
    for (sa, sr, ne), nv in states.items():
        if sa == sr and ne:
            cur = by_cost.get(sa)
            if cur is None or better * nv[0] > better * cur[0]:
                by_cost[sa] = nv
    out, best = {}, None
    for c in sorted(by_cost):
        rk, raw = by_cost[c]
        if best is None or better * rk > better * best:
            out.setdefault(raw, c)
            best = rk
    return out


def reach_best(d, v, k, better, split=False, locked=None, locked_digits=(), movable=True, limit=None, cap=None):
    """배분 정책용: 작은 상자는 reach() 와 같고(완전 열거), 조합 수가 limit 를 넘는 큰 상자(자릿수·이동이 큰 경우)는
    이동 수별 최선 값만 정확히 구한다 (숫자 내용 특징은 쓰지 않음). 반환 {값: 최소 이동}.
    cap: 값 비교에만 쓰는 자릿수 상한 (몬스터 피해 숫자 상한 환상). 반환 값은 화면 숫자 그대로."""
    d = max(d, len(str(int(v))))
    masks = masks_of(v, d)
    cons = norm_cons(d, split, locked, locked_digits, movable, masks)
    if space_size(masks, int(k), cons) <= (limit or EXACT_LIMIT):
        return dict(_reach(masks, int(k), cons))
    return best_per_cost(masks, int(k), cons, better, cap)


def reach_masks(masks, k, split=False, locked=None, locked_digits=(), movable=True):
    masks = tuple(masks)
    return dict(_reach(masks, int(k), norm_cons(len(masks), split, locked, locked_digits, movable, masks)))


# ---------------------------------------------------------------------------
# 검증용: 실제 세그먼트 배치를 성냥 1개씩 옮기는 너비 우선 탐색 (AC-D1)
# ---------------------------------------------------------------------------
def bfs_reach(masks, k, split=False, locked=None, locked_digits=(), movable=True):
    n = len(masks)
    locked = tuple(((locked[i] if locked and i < len(locked) else 0) & masks[i]) for i in range(n))
    start = tuple(masks)
    seen = {start: 0}
    frontier = [start]
    out = {}
    v0 = parse(start)
    if v0 is not None:
        out[v0] = 0
    if not movable:
        return out
    for depth in range(1, k + 1):
        nxt = []
        for st in frontier:
            for i in range(n):
                if i in locked_digits:
                    continue
                pick = st[i] & ~locked[i]
                b = pick
                while b:
                    s = b & -b
                    b ^= s
                    for j in range(n):
                        if j in locked_digits or (split and j != i):
                            continue
                        base_j = st[j] & ~s if j == i else st[j]
                        free = 127 & ~base_j
                        if j == i:
                            free &= ~s          # 같은 자리에 다시 놓는 것은 이동이 아님
                        f = free
                        while f:
                            t = f & -f
                            f ^= t
                            new = list(st)
                            new[i] = st[i] & ~s
                            new[j] = (new[j] | t)
                            new = tuple(new)
                            if new in seen:
                                continue
                            seen[new] = depth
                            nxt.append(new)
                            v = parse(new)
                            if v is not None and v not in out:
                                out[v] = depth
        frontier = nxt
    return out
