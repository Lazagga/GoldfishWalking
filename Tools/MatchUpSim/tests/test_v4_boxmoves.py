# -*- coding: utf-8 -*-
"""v4 AC-D1 / AC-K5: 한 상자 안의 성냥 이동 표(reach)를 세그먼트 BFS 와 대조.

기본 실행 범위 (몇 분 이내):
- d = 1, 2: 모든 값 × k ≤ 4 × 제약 조합(없음, 분할, 잠금, 잠긴 자릿수, 이동 불가, 분할+잠금)
- d = 3: 모든 값 1000개 × k ≤ 3 (제약 없음) + 분할/잠금 표본
- d = 4: 표본 값(시드 고정) × k ≤ 3
MATCHUPSIM_FULL_BOXMOVES=1 이면 d = 3 전체를 k ≤ 4 와 모든 제약 조합으로, d = 4 를 더 많은 표본으로 돈다
(명세의 v ∈ [0, 9999], k ≤ 4 완전 대조는 BFS 비용 때문에 기본 실행에 넣지 않았다 — README 참고).
"""
import os
import random
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from sim_service import box_moves as bm  # noqa: E402

FULL = os.environ.get("MATCHUPSIM_FULL_BOXMOVES") == "1"


def cons_variants(d, rng):
    out = [dict()]
    out.append(dict(split=True))
    out.append(dict(movable=False))
    locked = tuple(rng.choice([0, bm.T, bm.UR | bm.M, bm.LL, bm.B | bm.UL]) for _ in range(d))
    out.append(dict(locked=locked))
    out.append(dict(split=True, locked=locked))
    if d >= 2:
        out.append(dict(locked_digits=(0,)))
    return out


def check(tc, masks, k, **cons):
    a = bm.reach_masks(masks, k, **cons)
    b = bm.bfs_reach(tuple(masks), k, **cons)
    tc.assertEqual(a, b, "masks=%s k=%d cons=%s" % (masks, k, cons))


class Known(unittest.TestCase):
    def test_6_to_9_one_move(self):
        self.assertEqual(bm.reach(1, 6, 1).get(9), 1)
        self.assertEqual(bm.reach(1, 9, 1).get(6), 1)

    def test_7_to_1_impossible(self):
        # 7 은 성냥 3개, 1 은 2개 → 상자 안 개수 보존 때문에 불가
        for k in range(5):
            self.assertNotIn(1, bm.reach(1, 7, k))

    def test_zero_moves_is_identity(self):
        self.assertEqual(bm.reach(2, 38, 0), {38: 0})

    def test_leading_zero_allowed(self):
        # 사용자 확인 Q18: 앞자리 0 허용. 68 → 08 (6 의 가운데를 오른쪽 위로) = 값 8, 이동 1
        self.assertEqual(bm.reach(2, 68, 1).get(8), 1)
        self.assertEqual(bm.parse(bm.masks_of(7, 2)), 7)

    def test_known_reach_38(self):
        self.assertEqual(set(bm.reach(2, 38, 1)), {28, 38, 58, 90, 96, 99})

    def test_split_blocks_cross_digit(self):
        # 11 (2+2) → 4 (4개, 한 자리) 는 한쪽 자리를 비워야 하므로 자릿수 사이 이동이 필요
        free = bm.reach(2, 11, 2)
        split = bm.reach(2, 11, 2, split=True)
        self.assertEqual(free.get(4), 2)
        self.assertNotIn(4, split)

    def test_immovable(self):
        self.assertEqual(bm.reach(2, 38, 4, movable=False), {38: 0})

    def test_locked_segment(self):
        # 6 의 위쪽 왼쪽(UL) 을 잠그면 9 는 가능(UL 유지), 잠긴 LL 이면 9 는 불가(9 에는 LL 없음)
        self.assertIn(9, bm.reach(1, 6, 1, locked=(bm.UL,)))
        self.assertNotIn(9, bm.reach(1, 6, 1, locked=(bm.LL,)))

    def test_locked_digit(self):
        r = bm.reach(2, 38, 2, locked_digits=(0,))
        self.assertTrue(all(v // 10 == 3 or v < 10 for v in r), r)


class VersusBFS(unittest.TestCase):
    def test_d1_d2_all(self):
        rng = random.Random(11)
        n = 0
        for d in (1, 2):
            for v in range(10 ** d):
                masks = bm.masks_of(v, d)
                for cons in cons_variants(d, rng):
                    for k in range(5):
                        check(self, masks, k, **cons)
                        n += 1
        self.assertGreater(n, 2000)

    def test_d3(self):
        rng = random.Random(13)
        kmax = 4 if FULL else 3
        vals = range(1000)
        for v in vals:
            masks = bm.masks_of(v, 3)
            variants = cons_variants(3, rng) if FULL else [dict()]
            for cons in variants:
                for k in range(kmax + 1):
                    check(self, masks, k, **cons)
        # 제약 표본 (기본 실행)
        if not FULL:
            for v in rng.sample(range(1000), 60):
                masks = bm.masks_of(v, 3)
                for cons in cons_variants(3, rng)[1:]:
                    for k in range(4):
                        check(self, masks, k, **cons)

    def test_d4_sampled(self):
        rng = random.Random(17)
        n_vals = 200 if FULL else 25
        for v in rng.sample(range(10000), n_vals):
            masks = bm.masks_of(v, 4)
            for cons in (dict(), dict(split=True)):
                for k in range(3 if not FULL else 4):
                    check(self, masks, k, **cons)


class BestPerCost(unittest.TestCase):
    """큰 상자용 DP(이동 수별 최선 값)가 완전 열거의 이동 수별 최선 값과 같다."""

    def test_dp_matches_enumeration(self):
        rng = random.Random(23)
        for _ in range(300):
            d = rng.randint(1, 4)
            v = rng.randint(0, 10 ** d - 1)
            k = rng.randint(0, 4)
            kw = rng.choice([dict(), dict(split=True), dict(locked_digits=(0,)) if d > 1 else dict()])
            masks = bm.masks_of(v, d)
            cons = bm.norm_cons(d, masks=masks, **kw)
            full = bm.reach_masks(masks, k, **kw)
            for better in (+1, -1):
                dp = bm.best_per_cost(masks, k, cons, better)
                # 기대: 이동 수 c 이하에서 처음으로 더 좋아지는 값들 (파레토 프런트)
                exp, best = {}, None
                for c in sorted(set(full.values())):
                    cand = [x for x, cc in full.items() if cc == c]
                    vbest = max(cand) if better > 0 else min(cand)
                    if best is None or better * vbest > better * best:
                        exp[vbest] = c
                        best = vbest
                self.assertEqual(dp, exp, (d, v, k, kw, better))

    def test_large_box_is_fast(self):
        import time
        t = time.perf_counter()
        r = bm.reach_best(10, 5535025534, 12, -1)
        self.assertLess(time.perf_counter() - t, 2.0)
        self.assertLessEqual(min(r), 5535025534)
        self.assertEqual(r[5535025534], 0)


if __name__ == "__main__":
    unittest.main()
