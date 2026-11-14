# -*- coding: utf-8 -*-
"""몬스터 피해 숫자 상한(사과파이, monster_dmg_digit_max): 화면 숫자는 그대로 두고 피해 계산에만 상한을 적용한다.

- 성냥 이동은 굴린 원래 숫자에서 시작한다 (예전에는 굴리자마자 5로 깎은 뒤 이동했다).
- 플레이어는 '상한을 적용한 값'이 가장 작아지는 배치를 고른다 (원래 숫자가 작은 배치가 아니라).
- 큰 상자용 DP(best_per_cost)도 같은 기준으로 비교한다.
"""
import os
import random
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)

import matchup_sim as ms  # noqa: E402
from sim_service import box_moves as bm  # noqa: E402
from sim_service import fight_digits as fd  # noqa: E402
from test_v4_digits import battle, cfg_of, mon_of  # noqa: E402

APPLEPIE = "fan_number_applepie"


def cap5(v, cap=5):
    return ms._digits_map(v, lambda d: min(d, cap))


class PruneRank(unittest.TestCase):
    def test_prune_ranks_by_capped_value(self):
        # 58 은 원래 숫자로는 61 보다 작지만, 상한 5 를 적용하면 58 > 51 이다
        reach = {61: 1, 58: 1}
        self.assertEqual(fd.prune(reach, -1), [(58, 1)])
        self.assertEqual(fd.prune(reach, -1, rank=cap5), [(61, 1)])
        # 상한을 적용해 값이 같아지면 더 많이 옮겨야 하는 쪽은 버린다
        self.assertEqual(fd.prune({99: 2, 55: 0}, -1, rank=cap5), [(55, 0)])


class DpCap(unittest.TestCase):
    def test_dp_matches_enumeration_with_cap(self):
        rng = random.Random(31)
        for _ in range(300):
            d = rng.randint(1, 4)
            v = rng.randint(0, 10 ** d - 1)
            k = rng.randint(0, 4)
            cap = rng.randint(1, 8)
            kw = rng.choice([dict(), dict(split=True), dict(locked_digits=(0,)) if d > 1 else dict()])
            masks = bm.masks_of(v, d)
            cons = bm.norm_cons(d, masks=masks, **kw)
            full = bm.reach_masks(masks, k, **kw)
            rk = lambda x: ms._digits_map(x, lambda dg: min(dg, cap))  # noqa: E731
            for better in (+1, -1):
                dp = bm.best_per_cost(masks, k, cons, better, cap)
                self.assertTrue(set(dp) <= set(full), (d, v, k, cap, kw))          # 반환 값은 화면 숫자 그대로
                exp, best = {}, None
                for c in sorted(set(full.values())):
                    cand = [x for x, cc in full.items() if cc == c]
                    rbest = max(rk(x) for x in cand) if better > 0 else min(rk(x) for x in cand)
                    if best is None or better * rbest > better * best:
                        exp[rbest] = c
                        best = rbest
                # 같은 상한 값끼리는 어느 원래 숫자를 돌려주든 상관없으므로 상한 값 기준으로 대조
                self.assertEqual({rk(x): c for x, c in dp.items()}, exp, (d, v, k, cap, kw, better))

    def test_reach_best_passes_cap(self):
        # 조합 수가 limit 를 넘으면 DP 경로 — 결과가 상한 기준으로 정렬돼야 한다
        full = bm.reach_best(4, 6158, 4, -1, cap=5)
        dp = bm.reach_best(4, 6158, 4, -1, limit=1, cap=5)
        self.assertEqual(sorted({cap5(x): c for x, c in full.items()}.items())[0],
                         sorted({cap5(x): c for x, c in dp.items()}.items())[0])


class Battle(unittest.TestCase):
    def test_display_stays_raw_and_damage_is_capped(self):
        c = cfg_of(skill=0.0, hp=10 ** 9)
        mon = mon_of(("2_Single",))
        saw_big = 0
        for i in range(25):
            _, _, tr = battle(c, mon, f"cap{i}", fids=[APPLEPIE], hp=10 ** 9)
            for t in tr:
                self.assertEqual(t["mon_dmg_edit"], t["mon_dmg"])                 # 이동이 없으면 화면 숫자는 굴린 그대로
                self.assertEqual(t["mon_dmg_eff"], cap5(t["mon_dmg"]))             # 피해 계산에만 상한
                self.assertTrue(all(ch <= "5" for ch in str(t["mon_dmg_eff"])))
                saw_big += any(ch > "5" for ch in str(t["mon_dmg"]))
        self.assertGreater(saw_big, 0)                                             # 예전에는 6 이상이 굴림 직후 사라졌다

    def test_damage_taken_uses_capped_number(self):
        c = cfg_of(skill=0.0, hp=10 ** 9)
        mon = mon_of(("2_Single",))
        for i in range(10):
            _, _, tr = battle(c, mon, f"tk{i}", fids=[APPLEPIE], hp=10 ** 9)
            for t in tr:
                if t["intent"] == "attack" and t["hits"] == 1 and t["end"] is None:
                    self.assertLessEqual(t["taken"], t["mon_dmg_eff"] + 0)         # 받은 피해는 상한 값 이하

    def test_moves_start_from_raw_number_and_minimize_capped(self):
        c = cfg_of(skill=1.0, hp=10 ** 9)
        mon = mon_of(("2_Single",))
        moved = 0
        for i in range(25):
            _, _, tr = battle(c, mon, f"mv{i}", fids=[APPLEPIE], hp=10 ** 9)
            for t in tr:
                self.assertTrue(all(ch <= "5" for ch in str(t["mon_dmg_eff"])))
                self.assertLessEqual(t["mon_dmg_eff"], cap5(t["mon_dmg"]))         # 이동은 상한 값을 줄이기만 한다
                moved += t["mon_dmg_edit"] != t["mon_dmg"]
        self.assertGreater(moved, 0)


if __name__ == "__main__":
    unittest.main()
