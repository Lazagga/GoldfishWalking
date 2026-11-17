# -*- coding: utf-8 -*-
"""v4.5 F21 턴 피해 분해 (AC-T2~T6·T8~T13 의 서버 수준) — `turn` 트레이스 이벤트의 `calc`."""
import copy
import os
import sys
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)

import fantasy_scan as fs  # noqa: E402
import matchup_sim as ms  # noqa: E402
from sim_service import fight_digits as fd  # noqa: E402
from sim_service import turncalc as tcalc  # noqa: E402
from test_v45_cosmictree import fights as cosmic_fights, spec as cosmic_spec  # noqa: E402
from test_v4_digits import battle, cfg_of, mon_of  # noqa: E402


def run_cfg(**sets):
    cfg, _ = fs.build_cfg(None, ["monsters.damage_model=digits", "monsters.gimmicks=on"] + [f"{k}={v}" for k, v in sets.items()], os.path.join(ROOT, "fantasy_effects.json"))
    cfg["monsters"]["model"] = "table"
    cfg["monsters"]["table_file"] = os.path.join(ROOT, "monster_table.json")
    return cfg


def turns_of(cfg, ctx, n, prefix="mon1"):
    for r in range(n):
        tr = []
        ms.simulate_run(cfg, f"{prefix}-{r}", ctx=ctx, trace=tr)
        for e in tr:
            if e.get("ev") == "turn":
                yield e


def duel(fids, n=40, patterns=("2_Single", "2_Multi_1"), hp=10 ** 6, mhp=10 ** 7, seed="tc", skill=0.7, g="off"):
    c = cfg_of(g=g, skill=skill, hp=hp)
    out = []
    for i in range(n):
        mon = mon_of(patterns, hp=mhp, ai="static")
        _, stt, tr = battle(c, mon, f"{seed}{i}", fids=fids, hp=hp)
        out.append((stt, tr))
    return out


class Totals(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cfg = run_cfg()
        cls.ctx = ms.SimContext(cls.cfg)
        cls.turns = list(turns_of(cls.cfg, cls.ctx, 120))

    # --- AC-T2: 모든 턴에서 calc 합계 = 트레이스의 준·받은 피해, 미분류 0
    def test_t2_totals_match_and_nothing_unclassified(self):
        self.assertGreater(len(self.turns), 1000)
        for e in self.turns:
            c = e["calc"]
            self.assertNotIn("error", c, c)
            self.assertEqual(c["dealt"]["total"], e["dealt"])
            self.assertEqual(c["taken"]["total"], e["taken"])
            for side in ("dealt", "taken"):
                self.assertEqual([x for x in c[side]["extra"] if x["k"] == "unclassified"], [], (e["t"], side))
                steps = c[side]["steps"]
                if steps:
                    self.assertEqual(steps[-1]["to"], c[side]["per_hit"])                       # 단계의 끝 = 한 번 타격 값
                    for a, b in zip(steps, steps[1:]):
                        self.assertEqual(a["to"], b["from"], (side, steps))                      # 단계가 끊김 없이 이어진다

    def test_t2_with_many_fantasies_and_gimmicks(self):
        fids = ["fan_damage_slingshot", "fan_damage_grapeshot", "fan_end_paperplane", "fan_turn_syringe", "fan_damage_anchor", "fan_damage_poinsettia",
                "fan_defend_paperboat", "fan_end_hourglass", "fan_number_applepie", "fan_damage_scorpio", "fan_damage_aries", "fan_damage_Bottle"]
        for stt, tr in duel(fids, n=30, g="on"):
            for e in tr:
                c = e["calc"]
                self.assertNotIn("error", c, c)
                self.assertEqual(c["dealt"]["total"], e["dealt"], (e["t"], c["dealt"]))
                self.assertEqual(c["taken"]["total"], e["taken"], (e["t"], c["taken"]))
                for side in ("dealt", "taken"):
                    self.assertEqual([x for x in c[side]["extra"] if x["k"] == "unclassified"], [])

    # --- AC-T3: calc 를 켠 시뮬(트레이스 켬)과 끈 시뮬의 결과가 같다
    def test_t3_results_unchanged_by_calc(self):
        for r in range(100):
            plain = ms.simulate_run(self.cfg, f"t3-{r}", ctx=self.ctx)
            tr = []
            traced = ms.simulate_run(self.cfg, f"t3-{r}", ctx=self.ctx, trace=tr)
            self.assertEqual(plain, traced, r)

    # --- AC-T9: 성능 — calc 를 만드는 비용이 트레이스 켠 재생을 2배 넘게 느리게 하지 않는다
    def test_t9_calc_is_cheap(self):
        def timed():
            t0 = time.perf_counter()
            for r in range(40):
                ms.simulate_run(self.cfg, f"t9-{r}", ctx=self.ctx, trace=[])
            return time.perf_counter() - t0
        timed()
        with_calc = min(timed() for _ in range(3))
        orig = fd.tcalc.build
        fd.tcalc.build = lambda ctx: {}
        try:
            without = min(timed() for _ in range(3))
        finally:
            fd.tcalc.build = orig
        self.assertLess(with_calc, without * 2.0, (with_calc, without))


class Sources(unittest.TestCase):
    # --- AC-T4: 환상 하나만 가진 전투 — 그 환상이 있는 타입의 단계에만 출처가 나타나고, 빼면 사라진다
    def test_t4_single_fantasy_only_in_its_step(self):
        for stt, tr in duel(["fan_damage_slingshot"], n=10):
            for e in tr:
                steps = e["calc"]["dealt"]["steps"]
                fx = [(s["k"], f[0]) for s in steps if s["src"].get("kind") == "fx" for f in s["src"]["fids"]]
                self.assertEqual({k for k, _ in fx}, {"flat"})
                self.assertEqual({f for _, f in fx}, {"fan_damage_slingshot"})
        for stt, tr in duel([], n=10):
            for e in tr:
                self.assertEqual([s for s in e["calc"]["dealt"]["steps"] if s["src"].get("kind") == "fx"], [])    # 환상을 빼면 단계가 없다

    # --- AC-T5: ablate.delta = 그 환상만 뺀 같은 입력의 직접 계산과의 차이
    def test_t5_ablate_matches_direct_recompute(self):
        fids = ["fan_damage_slingshot", "fan_damage_grapeshot", "fan_turn_syringe"]
        for stt, tr in duel(fids, n=20, patterns=("2_Single",), skill=0.0):
            for e in tr:
                c = e["calc"]["dealt"]
                if e["dealt"] <= 0 or c["hits"]["n"] < 1:
                    continue
                vals = {"fan_damage_slingshot": 30, "fan_damage_grapeshot": 60}
                pp = e["base_edit"]
                n_hits = c["hits"]["n"]
                full = (max(0, pp + sum(vals.values()))) * n_hits
                for a in c["ablate"]:
                    rest = sum(v for k, v in vals.items() if k != a["src"])
                    n2 = n_hits - (1 if a["src"] == "fan_turn_syringe" else 0)
                    direct = max(0, pp + rest) * n2
                    self.assertEqual(a["delta"], full - direct, (a, e["t"]))

    # --- AC-T6: 이동 단계 = 기본 → 편집한 값
    def test_t6_move_step_matches_edit(self):
        seen = 0
        for stt, tr in duel([], n=30, skill=0.9):
            for e in tr:
                for side, a, b in (("dealt", e["base"], e["base_edit"]), ("taken", e["mon_dmg"], e["mon_dmg_edit"])):
                    mv = [s for s in e["calc"][side]["steps"] if s["k"] == "move"]
                    if a != b:
                        seen += 1
                        self.assertEqual(len(mv), 1)
                        self.assertEqual((mv[0]["from"], mv[0]["to"]), (a, b))
                        self.assertEqual(mv[0]["src"]["kind"], "move")
        self.assertGreater(seen, 20)

    # --- AC-T8: 조건이 거짓인 효과는 cond_off 에만 있고 단계표에 없다
    def test_t8_condition_off_is_folded(self):
        fids = ["fan_end_paperplane", "fan_defend_paperboat"]
        off = on = 0
        for stt, tr in duel(fids, n=40, patterns=("2_Single",), skill=0.3):
            for e in tr:
                c = e["calc"]
                in_steps = {f[0] for side in ("dealt", "taken") for s in c[side]["steps"] if s["src"].get("kind") == "fx" for f in s["src"]["fids"]}
                off_f = {o["fid"] for o in c["cond_off"]}
                self.assertFalse(in_steps & off_f, (in_steps, off_f))
                off += bool(off_f)
                on += bool(in_steps)
        self.assertGreater(off, 0)
        self.assertGreater(on, 0)

    # --- AC-T10: 출처 요약에 값이 0이 아닌 모든 출처가 빠짐없이 나온다 (잘림 없음)
    def test_t10_all_sources_listed(self):
        fids = ["fan_damage_slingshot", "fan_damage_grapeshot", "fan_turn_syringe", "fan_damage_anchor", "fan_damage_poinsettia", "fan_end_hourglass",
                "fan_number_applepie", "fan_damage_scorpio", "fan_damage_aries", "fan_damage_Bottle", "fan_end_paperplane", "fan_defend_paperboat"]
        found = set()
        for stt, tr in duel(fids, n=30, patterns=("2_Single", "9_Multi_2"), skill=0.6):
            for e in tr:
                c = e["calc"]
                listed = {r["fid"] for side in ("dealt", "taken") for r in c["sources"][side] if r["fid"]}
                for side in ("dealt", "taken"):
                    ssum = sum(s["to"] - s["from"] for s in c[side]["steps"])
                    self.assertEqual(c[side]["base"] + ssum, c[side]["per_hit"] if c[side]["steps"] else c[side]["base"], (side, e["t"]))
                    for s in c[side]["steps"]:
                        for f in s["src"].get("fids", ()):
                            self.assertIn(f[0], listed)
                    for x in c[side]["extra"]:
                        for f in (x.get("src") or {}).get("fids", ()):
                            self.assertIn(f[0], listed)
                found |= listed
        self.assertGreaterEqual(len(found), 8, found)                                       # 요약이 상위 몇 개로 잘리지 않는다


class Over(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows = []
        for tr in cosmic_fights([cosmic_spec()], n=200, skill=0.0, patterns=("3_Single",)):
            pass
        c = cfg_of(g="on", skill=0.0, hp=60)
        for i in range(250):
            mon = mon_of(("3_Single",), hp=10 ** 9, sim=[cosmic_spec()])
            _, _, tr = battle(c, mon, f"ov{i}", hp=60)
            cls.rows += [t for t in tr if t.get("end") == "death"]

    # --- AC-T11: 사망 턴의 초과 = 받은 피해 − 그 턴 시작 체력, 출처 합 = 초과
    def test_t11_taken_over_sums(self):
        self.assertGreater(len(self.rows), 20)
        with_over = 0
        for t in self.rows:
            ov = t["calc"]["taken"]["over"]
            hp_before = t["hp"] - t["hp_change"]
            self.assertEqual(ov["n"], max(0, t["taken"] - hp_before))
            if ov["n"]:
                with_over += 1
                self.assertEqual(sum(b["n"] for b in ov["by"]), ov["n"])
        self.assertGreater(with_over, 10)

    def test_t11_dealt_over_when_monster_dies(self):
        c = cfg_of(g="off", skill=0.9, hp=10 ** 6)
        n = 0
        for i in range(60):
            mon = mon_of(("2_Single",), hp=30, ai="static")
            _, _, tr = battle(c, mon, f"dv{i}", hp=10 ** 6)
            last = tr[-1]
            if last.get("end") == "win":
                ov = last["calc"]["dealt"]["over"]
                self.assertEqual(ov["n"], max(0, -last["mhp"]))                                   # 준 피해(원본) − 그 턴 시작 몬스터 체력 = 0 밑으로 내려간 양
                if ov["n"]:
                    n += 1
                    self.assertEqual(sum(b["n"] for b in ov["by"]), ov["n"])
        self.assertGreater(n, 10)

    # --- AC-T12: 초과 제거 시 차이 = over − over' (그 출처만 뺀 같은 계산)
    def test_t12_over_ablate(self):
        fids = ["fan_damage_anchor", "fan_damage_poinsettia"]
        c = cfg_of(g="off", skill=0.0, hp=40)
        seen = 0
        for i in range(60):
            mon = mon_of(("4_Single",), hp=10 ** 9)
            _, _, tr = battle(c, mon, f"oa{i}", fids=fids, hp=40)
            for t in tr:
                ov = t["calc"]["taken"]["over"]
                if not ov["n"]:
                    continue
                hp_before = t["hp"] - t["hp_change"]
                for a in t["calc"]["taken"]["ablate"]:
                    o2 = max(0, t["taken"] - a["delta"] - hp_before)
                    got = next((x for x in ov["ablate"] if x["src"] == a["src"]), {"delta": 0})
                    self.assertEqual(got["delta"], ov["n"] - o2)
                    seen += 1
        self.assertGreater(seen, 5)


class Pure(unittest.TestCase):
    def test_split_over_sums_exactly(self):
        by, red = tcalc.split_over(75890, [("base_roll", 61000), ("g", 14890), ("h", 3)], [("d", 120)])
        self.assertEqual(sum(b["n"] for b in by), 75890)
        self.assertTrue(all(b["n"] > 0 for b in by))
        self.assertEqual(tcalc.split_over(0, [("a", 1)], []), ([], []))

    def test_round_parts(self):
        self.assertEqual(sum(tcalc.round_parts([40.0, 10.0, 300.0, 0.0], 350)), 350)
        self.assertEqual(sum(tcalc.round_parts([0.6, 0.6, 0.6], 1)), 1)


if __name__ == "__main__":
    unittest.main()
