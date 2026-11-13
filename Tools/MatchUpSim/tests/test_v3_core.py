# -*- coding: utf-8 -*-
"""v3 수락 기준 (시뮬레이터·통계): 불씨 AC-B1~B10, 조합 AC-C1~C4·C6, AC-S1(data_hash)."""
import copy
import json
import math
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

import matchup_sim as ms  # noqa: E402
from sim_service import combo as cb  # noqa: E402
from sim_service import compute as cp  # noqa: E402
from sim_service import stats as S  # noqa: E402
from sim_service import store as st  # noqa: E402

EFFECTS = os.path.join(ROOT, "fantasy_effects.json")
WORKERS = max(2, min(8, (os.cpu_count() or 2) - 1))


def cfg_of(table=True, hp=300, ember=True, effects=EFFECTS, **em):
    c = ms.legacy_config()
    c["monsters"]["act_hp_growth"] = 2.0
    c["monsters"]["hp_base"] = hp if table else 74
    if table:
        ms.apply_fantasy_args(c, effects)
    if ember:
        c["rewards"]["normal_battle"]["mode"] = "ember"
        c["rewards"]["ember"].update(em)
    return c


def rows_of(c, n, seed="em", trace=False):
    ctx = ms.SimContext(c)
    out = []
    for i in range(n):
        tr = [] if trace else None
        r = ms.simulate_run(c, f"{seed}-{i}", ctx=ctx, trace=tr)
        out.append((r, tr))
    return out


class Ember(unittest.TestCase):
    def test_b1_slot_formula(self):
        for table in (True, False):
            for r, _ in rows_of(cfg_of(table), 500):
                tot = r["embers_white"] + r["embers_blue"]
                self.assertEqual(r["slots_done"], tot // 3)
                self.assertEqual(tot, r["normal_wins"])

    def test_b2_blue_chance_0_and_1(self):
        for r, _ in rows_of(cfg_of(blue_chance=0.0), 300):
            self.assertEqual((r["embers_blue"], r["blue_offers"]), (0, 0))
        tot = 0
        for r, _ in rows_of(cfg_of(blue_chance=1.0), 300):
            self.assertEqual(r["embers_white"], 0)
            self.assertEqual(r["blue_offers"] + r["blue_wasted"], r["slots_done"])
            tot += r["blue_offers"]
        self.assertGreater(tot, 100)

    def test_b3_blue_probability(self):
        blue = total = 0
        for r, _ in rows_of(cfg_of(table=False), 10000):
            blue += r["embers_blue"]
            total += r["embers_blue"] + r["embers_white"]
        p0 = 0.10
        z = (blue - total * p0) / math.sqrt(total * p0 * (1 - p0))
        print(f"\n  AC-B3: 불씨 {total:,}개 중 푸른 불씨 {blue:,}개 = {blue / total * 100:.2f}% (기대 10%, z={z:+.2f})")
        self.assertLess(abs(z), 3.29)   # 양측 p > 0.001

    def test_b4_extra_mode(self):
        emb = wins = 0
        for r, _ in rows_of(cfg_of(table=False, blue_mode="extra", blue_chance=0.3), 4000):
            tot = r["embers_white"] + r["embers_blue"]
            self.assertEqual(r["embers_white"], r["normal_wins"])
            self.assertEqual(r["slots_done"], tot // 3)   # 넘친 불씨는 다음 슬롯으로 이월
            emb += tot
            wins += r["normal_wins"]
        z = (emb - wins * 1.3) / math.sqrt(wins * 0.3 * 0.7)
        print(f"\n  AC-B4: 일반 전투 승리당 불씨 {emb / wins:.4f}개 (기대 1.3, z={z:+.2f})")
        self.assertLess(abs(z), 3.29)

    @staticmethod
    def ember_by_pos(tr):
        out, pos = {}, None
        for e in tr:
            if e["ev"] == "node":
                pos = (e["act"], e["floor"])
            elif e["ev"] == "ember":
                out[pos] = e["colors"]
        return out

    def test_b5_dedicated_stream(self):
        base = cfg_of(blue_chance=0.4)
        forced = copy.deepcopy(base)
        forced["fantasy"]["forced"] = {"ids": ["fan_damage_slingshot"], "at": "start"}
        same = 0
        for (rb, tb), (rf, tf) in zip(rows_of(base, 150, trace=True), rows_of(forced, 150, trace=True)):
            a, b = self.ember_by_pos(tb), self.ember_by_pos(tf)
            for pos in set(a) & set(b):
                self.assertEqual(a[pos], b[pos])
                same += 1
        self.assertGreater(same, 300)

    def test_b6_candidate_shortage(self):
        table = ms.load_effects_table(EFFECTS)[0]
        blues = [f for f, e in table.items() if e["grade"] == "blue"]
        whites = [f for f, e in table.items() if e["grade"] == "white"]
        c = cfg_of(blue_chance=1.0)
        c["fantasy"]["banned"] = {"ids": blues}
        wasted = 0
        for r, _ in rows_of(c, 200):
            self.assertEqual(r["blue_offers"], 0)
            self.assertEqual(r["blue_wasted"], r["slots_done"])
            wasted += r["blue_wasted"]
        self.assertGreater(wasted, 50)
        c["fantasy"]["banned"] = {"ids": blues + whites}   # 후보가 전혀 없음 → 보상 없이 진행
        for r, _ in rows_of(c, 100):
            self.assertEqual(r["fant_white"], 0)

    def test_b7_pool_exclusions(self):
        c = cfg_of(blue_chance=0.5)
        ban = ["fan_damage_anchor", "fan_damage_poinsettia", "fan_turn_boots"]
        c["fantasy"]["banned"] = {"ids": ban}
        c["fantasy"]["forced"] = {"ids": ["fan_damage_slingshot", "fan_damage_grapeshot"], "at": "start"}
        n_off = 0
        for r, tr in rows_of(c, 200, trace=True):
            got = r["fantasies"].split("|")
            self.assertEqual(got[:2], ["fan_damage_slingshot", "fan_damage_grapeshot"])
            self.assertFalse(set(got) & set(ban))
            owned = set()
            for e in tr:
                if e["ev"] in ("slot_done", "reward"):
                    n_off += 1
                    for f in e["offered"]:
                        self.assertNotIn(f, ban)
                        self.assertNotIn(f, owned)
                        self.assertNotIn(f, c["fantasy"]["forced"]["ids"])
                elif e["ev"] == "shop":
                    self.assertFalse(set(e["bought"]) & set(ban))
                if e["ev"] == "acquire":
                    owned.add(e["fid"])
        self.assertGreater(n_off, 200)
        with self.assertRaises(ValueError):   # forced 와 banned 가 겹치면 오류
            c["fantasy"]["banned"] = {"ids": ["fan_damage_slingshot"]}
            ms.SimContext(c)

    def test_b8_source_totals(self):
        for ember in (True, False):
            c = cfg_of(ember=ember)
            c["fantasy"]["forced"] = {"ids": ["fan_fantasy_leo"], "at": "start"}
            for r, _ in rows_of(c, 200):
                self.assertEqual(r["fantasies_reward"] + r["fantasies_shop"] + r["fantasies_forced"],
                                 r["acquires"] - r["fantasy_voided"])
                self.assertEqual(r["fantasies_forced"], 1)
            g = cfg_of(table=False, ember=ember)
            for r, _ in rows_of(g, 200):
                self.assertEqual(r["fantasies_reward"] + r["fantasies_shop"] + r["fantasies_forced"],
                                 len([x for x in r["fantasies"].split("|") if x]))

    def test_b9_elite_boss_unchanged(self):
        table = ms.load_effects_table(EFFECTS)[0]
        n = 0
        for r, tr in rows_of(cfg_of(hp=150), 150, trace=True):
            tier = None
            for e in tr:
                if e["ev"] == "battle":
                    tier = e["tier"]
                elif e["ev"] == "reward":     # 현행 방식 보상은 엘리트·보스에서만
                    self.assertIn(tier, ("elite", "boss"))
                    self.assertLessEqual(len(e["offered"]), 3)
                    self.assertEqual({table[f]["grade"] for f in e["offered"]}, {ms.TIER_GRADE[tier]})
                    n += 1
                elif e["ev"] == "slot_done":
                    self.assertIn(tier, ("easy", "normal"))
        self.assertGreater(n, 100)

    def test_b10_tune(self):
        c = cfg_of(table=False)
        with tempfile.TemporaryDirectory() as tmp:
            row = ms.tune(c, "monsters.hp_base", 10, 200, 0.10, 0.02, 10, 600, "tb", "", tmp, "")
            self.assertAlmostEqual(row["win_rate"], 0.10, delta=0.04)
            self.assertLess(row["found_value"], 74)   # 불씨 모드는 환상이 적어 같은 승률이 더 낮은 체력에서 나온다
            c2 = cfg_of(table=True, hp=150)
            row2 = ms.tune(c2, "rewards.ember.slot_size", 1, 6, 8, 2.0, 8, 300, "tb", "", tmp, "", metric="mean_fantasies")
            self.assertTrue(1 <= row2["found_value"] <= 6)
            self.assertAlmostEqual(row2["metric_value"], 8, delta=3)

    def test_default_mode_stats_zero(self):
        for r, _ in rows_of(cfg_of(ember=False), 50):
            self.assertEqual((r["embers_white"], r["embers_blue"], r["slots_done"]), (0, 0, 0))


def synth_table(tmp):
    with open(EFFECTS, encoding="utf-8") as fp:
        data = json.load(fp)
    mk = lambda i, eff: {"id": i, "name": i, "grade": "white", "fidelity": "exact", "effects": eff, "notes": "", "available": False}  # noqa: E731
    data["fantasies"] += [
        mk("c_hits", [{"type": "hits_add", "value": 3}]), mk("c_combo", [{"type": "combo_same_dmg_stack", "value": 300}]),
        mk("c_def1", [{"type": "dmg_taken_flat", "value": -60}]), mk("c_def2", [{"type": "dmg_taken_flat", "value": -60}]),
        mk("c_ind1", [{"type": "heal_per_battle", "value": 4}]), mk("c_ind2", [{"type": "item_drop_chance_add", "value": 0.05}]),
    ]
    path = os.path.join(tmp, "fx.json")
    with open(path, "w", encoding="utf-8") as fp:
        json.dump(data, fp, ensure_ascii=False)
    return path, data


class Combo(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.path, cls.data = synth_table(cls.tmp.name)
        cls.cfg = cfg_of(hp=600, ember=False, effects=cls.path)
        cls.thash = st.table_hash(cls.data)
        cls.order = [f["id"] for f in cls.data["fantasies"]]
        cls.eng = cp.Engine(st.PointStore(os.path.join(cls.tmp.name, "pc")), WORKERS)

    @classmethod
    def tearDownClass(cls):
        cls.eng.close()
        cls.tmp.cleanup()

    def run_c(self, ids, typ="natural", xs=(600,), stages=(1500,)):
        return cb.run_combo(self.eng, self.cfg, self.thash, "cmb", "monsters.hp_base", list(xs), ids, self.order, typ, stages)

    def test_c1_known_interactions(self):
        syn = self.run_c(["c_hits", "c_combo"])["by_x"][600]["pairs"][0]
        sat = self.run_c(["c_def1", "c_def2"])["by_x"][600]["pairs"][0]
        ind = self.run_c(["c_ind1", "c_ind2"])["by_x"][600]["pairs"][0]
        print(f"\n  AC-C1: 상승 I={syn['I']:+.3f} {syn['ci']} | 포화 I={sat['I']:+.3f} {sat['ci']} | 독립 I={ind['I']:+.3f} {ind['ci']}")
        self.assertGreater(syn["ci"][0], 0)
        self.assertEqual(syn["label"], "상승작용 가능")
        self.assertLess(sat["ci"][1], 0)
        self.assertEqual(sat["label"], "중복·포화 가능")
        self.assertTrue(sat["saturated"])        # 승률 95% 초과 구간 경고
        self.assertTrue(ind["ci"][0] <= 0 <= ind["ci"][1])
        self.assertEqual(ind["label"], "뚜렷한 상호작용 없음")

    def test_c2_cache_reuse(self):
        # 단일 환상·기준선을 스캔과 같은 방식으로 먼저 계산
        c = copy.deepcopy(self.cfg)
        ms.set_path(c, "monsters.hp_base", 500)
        base = cp.make_req(c, [], "cmb", self.thash)
        s1 = cp.make_req(c, ["fan_turn_boots"], "cmb", self.thash)
        s2 = cp.make_req(c, ["fan_damage_slingshot"], "cmb", self.thash)
        before = self.eng.ensure([base, s1, s2], 600)
        snap = {k: copy.deepcopy(v) for k, v in before.items()}
        n0 = self.eng.runs_computed
        res = self.run_c(["fan_turn_boots", "fan_damage_slingshot"], xs=(500,), stages=(600,))
        self.assertEqual(self.eng.runs_computed - n0, 600)       # 새로 돌린 것은 쌍 팔 하나뿐
        keys = {r["tag"][1]: r["key"] for r in res["reqs"]}
        self.assertEqual(keys[frozenset()], base["key"])
        self.assertEqual(keys[frozenset(["fan_turn_boots"])], s1["key"])
        for k in (base, s1, s2):
            self.assertEqual(self.eng.store.load(k["key"]), snap[k["key"]])   # 비트 단위로 같음
        n1 = self.eng.runs_computed
        self.run_c(["fan_damage_slingshot", "fan_turn_boots"], xs=(500,), stages=(600,))   # 순서를 바꿔 다시 요청
        self.assertEqual(self.eng.runs_computed, n1)             # 즉시 반환 (재계산 없음)

    def test_c3_identity(self):
        for ids in (["fan_turn_boots", "fan_damage_slingshot", "c_hits"],
                    ["fan_turn_boots", "fan_damage_slingshot", "c_hits", "c_combo"]):
            st_ = self.run_c(ids, stages=(500,))["by_x"][600]
            self.assertEqual(len(st_["arms"]), 2 ** len(ids))
            full = st_["arms"][frozenset(ids)]
            total = sum(st_["arms"][frozenset([i])]["delta"] for i in ids) + sum(p["I"] for p in st_["pairs"]) + st_["R"]["R"]
            self.assertAlmostEqual(full["delta"], total, delta=1e-5)
            self.assertAlmostEqual(full["expected_delta"], sum(st_["arms"][frozenset([i])]["delta"] for i in ids), delta=1e-5)
        js = cb.to_json(self.run_c(["fan_turn_boots", "fan_damage_slingshot"], stages=(500,)))
        self.assertIn("fan_turn_boots+fan_damage_slingshot", js["by_x"][0]["arms"])
        with self.assertRaises(ValueError):
            self.run_c(["fan_turn_boots", "fan_damage_slingshot", "c_hits", "c_combo", "c_def1"])

    def test_c4_banned_baseline(self):
        ids = ["fan_damage_anchor", "fan_damage_poinsettia"]
        res = self.run_c(ids, typ="banned", stages=(300,))
        for r in res["reqs"]:
            sub = r["tag"][1]
            self.assertEqual(set(r["banned"]), set(ids) - sub)
            ctx = ms.SimContext(r["cfg"])
            for i in range(60):
                row = ms.simulate_run(r["cfg"], f"cmb-{i}", ctx=ctx)
                got = row["fantasies"].split("|") if row["fantasies"] else []
                self.assertFalse(set(got) & (set(ids) - sub))
                self.assertEqual(set(got[:len(sub)]), set(sub))
        nat = self.run_c(ids, typ="natural", stages=(300,))
        self.assertNotEqual({r["key"] for r in nat["reqs"]} & {r["key"] for r in res["reqs"]},
                            {r["key"] for r in res["reqs"]})

    def test_c6_equiv_gain(self):
        xs = list(range(200, 1201, 100))
        f = lambda x: 0.9 / (1 + ((x - 100) / 300.0) ** 2)   # 단조 감소  # noqa: E731
        base = [f(x) for x in xs]
        g, why = S.equiv_gain(xs, base, f(700 - 180), 700)   # 팔 = 체력 180 만큼 쉬운 기준선과 같은 승률
        self.assertIsNone(why)
        self.assertAlmostEqual(g, -180, delta=15)
        # 노이즈가 섞여 비단조여도 단조 회귀로 복원
        noisy = [b + (0.01 if k % 2 else -0.01) for k, b in enumerate(base)]
        g2, _ = S.equiv_gain(xs, noisy, f(520), 700)
        self.assertAlmostEqual(g2, -180, delta=40)
        self.assertEqual(S.equiv_gain(xs, [0.3] * len(xs), 0.3, 700), (None, "기준선이 이 구간에서 평탄"))
        self.assertEqual(S.equiv_gain(xs, base, 0.99, 700)[1], "격자 범위 밖")
        # 재표본 CI
        import random
        rnd = random.Random(3)
        recs = [{"n": 800, "wins": "".join("1" if rnd.random() < f(x) else "0" for _ in range(800))} for x in xs]
        arm = {"n": 800, "wins": "".join("1" if rnd.random() < f(520) else "0" for _ in range(800))}
        ci = S.equiv_gain_ci(xs, recs, arm, 700, B=80)
        self.assertIsNotNone(ci["gain"])
        self.assertLess(ci["ci"][0], -180 + 60)
        self.assertGreater(ci["ci"][1], -180 - 60)


class DataHash(unittest.TestCase):
    def test_monster_hash_in_data_hash(self):
        t = {"monsters": [{"id": "m", "act": 1, "tier": "easy", "hp": 100, "ai": "static",
                           "patterns": [{"key": "2_Single", "kind": "attack"}], "name": "이름", "notes": "메모"}]}
        h = st.monster_hash_of(t)
        t2 = copy.deepcopy(t)
        t2["monsters"][0]["name"] = "다른 이름"
        t2["monsters"][0]["notes"] = "x"
        self.assertEqual(st.monster_hash_of(t2), h)          # 이름·메모는 해시에 안 들어감
        t2["monsters"][0]["hp"] = 101
        self.assertNotEqual(st.monster_hash_of(t2), h)       # 몬스터 체력 하나를 바꾸면 해시가 바뀜
        self.assertNotEqual(st.data_hash("abc", h), st.data_hash("abc", st.monster_hash_of(t2)))
        self.assertNotEqual(st.data_hash("abc", ""), st.data_hash("abd", ""))


if __name__ == "__main__":
    unittest.main()
