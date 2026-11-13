# -*- coding: utf-8 -*-
"""v4.2 몬스터 배정 = 게임 MonsterSelector 규칙 (monsters.encounter = game).

- 1막 첫 일반 전투(roomIndex 0)는 encounter_rules.fixed 의 몬스터(기본 요정)
- 1막 방 1·2 의 일반 전투는 1막 easy 중 무작위
- 그 밖의 일반 전투는 그 막의 easy + normal 중 무작위
- 요정 기본 힘 90 → 피해 상자 92자리 → 첫 전투에서 처치하지 못하면 사망
- encounter = tier 는 v4 이전 배정, tier_avg 모델의 점 키는 바뀌지 않음
"""
import copy
import json
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

import matchup_sim as ms  # noqa: E402
from sim_service import store as st  # noqa: E402

EFFECTS = os.path.join(ROOT, "fantasy_effects.json")
MTABLE = os.path.join(ROOT, "monster_table.json")
FAIRY = "Mob_10101_Fairy"


def cfg_of(table=MTABLE, dm="digits", g="on", enc="game"):
    c = copy.deepcopy(ms.DEFAULT_CONFIG)
    ms.apply_fantasy_args(c, EFFECTS)
    c["monsters"].update({"model": "table", "table_file": table, "damage_model": dm, "gimmicks": g, "encounter": enc})
    return c


def battles(cfg, n, seed="enc"):
    ctx = ms.SimContext(cfg)
    out = []
    for i in range(n):
        log = []
        res = ms.simulate_run(cfg, f"{seed}-{i}", ctx=ctx, battle_log=log)
        out.append((res, log))
    return out


class GameEncounter(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(MTABLE, encoding="utf-8") as fp:
            cls.table = json.load(fp)
        cls.by_id = {m["id"]: m for m in cls.table["monsters"]}

    def test_first_battle_is_fairy(self):
        for res, log in battles(cfg_of(), 60):
            self.assertTrue(log, "전투 기록이 없음")
            self.assertEqual(log[0]["monster"], FAIRY)

    def test_room_pools(self):
        easy1 = {m["id"] for m in self.table["monsters"] if m["act"] == 1 and m["tier"] == "easy"}
        pool = {a: {m["id"] for m in self.table["monsters"] if m["act"] == a and m["tier"] in ("easy", "normal")}
                for a in (1, 2, 3)}
        seen_later_easy = False
        for res, log in battles(cfg_of(), 80, seed="pool"):
            for b in log:
                if b.get("tier") not in ("easy", "normal"):
                    continue
                act, fl = b["act"], b["floor"]
                self.assertIn(b["monster"], pool[act])
                if act == 1 and fl in (2, 3):
                    self.assertIn(b["monster"], easy1)
                if act == 1 and fl > 3 and b["monster"] in easy1:
                    seen_later_easy = True
        self.assertTrue(seen_later_easy, "1막 방 3 이후에도 easy 가 풀에 있어야 함 (게임 규칙)")

    def test_fairy_strength_90_blocks_floor_one(self):
        t = copy.deepcopy(self.table)
        for m in t["monsters"]:
            if m["id"] == FAIRY:
                m["strength"] = 90
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "t.json")
            with open(p, "w", encoding="utf-8") as fp:
                json.dump(t, fp, ensure_ascii=False)
            runs = battles(cfg_of(p), 100, seed="f90")
        one_shot = sum(1 for _, log in runs if log[0]["outcome"] == "win")
        wins = sum(1 for r, _ in runs if r["result"] == "win")
        self.assertLessEqual(one_shot, 25)          # 대부분 첫 층에서 사망
        self.assertLessEqual(wins, one_shot)        # 이긴 판은 모두 요정을 첫 턴에 처치한 판
        for r, log in runs:
            first = log[0]
            # 첫 전투에서 진 판은 몬스터가 92자리 피해를 냈다. 살아남은 판은 한 번도 맞지 않았다
            # (요정이 행동하기 전에 처치 — 플레이어 선공 — 또는 연타 수 상자를 0 으로 바꿔 피해 0)
            if first["outcome"] != "win":
                self.assertGreaterEqual(len(str(first["max_hit"])), 90)
            else:
                self.assertEqual(first["taken"], 0)

    def test_tier_mode_and_keys(self):
        c_game, c_tier = cfg_of(), cfg_of(enc="tier")
        self.assertNotEqual(st.point_key(c_game, [], 0, "h"), st.point_key(c_tier, [], 0, "h"))
        # tier_avg 모델은 encounter 와 무관 → 기본값 키 그대로
        c = ms.legacy_config()
        c2 = copy.deepcopy(c)
        c2["monsters"]["encounter"] = "tier"
        del c["monsters"]["encounter"], c["monsters"]["encounter_rules"]
        self.assertEqual(st.point_key(ms.legacy_config(), [], 0, "h"), st.point_key(c, [], 0, "h"))
        res = battles(cfg_of(enc="tier"), 20, seed="tier")
        self.assertTrue(any(log[0]["monster"] != FAIRY for _, log in res))

    def test_unknown_fixed_id_rejected(self):
        c = cfg_of()
        c["monsters"]["encounter_rules"] = {"fixed": [{"act": 1, "room": 0, "id": "Mob_nope"}]}
        with self.assertRaises(ValueError):
            ms.SimContext(c)


if __name__ == "__main__":
    unittest.main()
