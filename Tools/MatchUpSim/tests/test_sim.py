# -*- coding: utf-8 -*-
"""AC1 (회귀 없음), AC2 (효과 타입 방향), AC3 (강제 포함 정합성).

  python -m unittest discover -s tests -v        (Tools/MatchUpSim 에서)
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
sys.path.insert(0, HERE)

import matchup_sim as ms  # noqa: E402

EFFECTS = os.path.join(ROOT, "fantasy_effects.json")
# table 모드에서 기준선 승률이 10% 근처가 되는 체력 (README 참고). 방향 테스트는 천장/바닥을 피해 여기서 한다.
TABLE_HP = 600


def base_cfg(**sets):
    cfg = copy.deepcopy(ms.DEFAULT_CONFIG)
    cfg["monsters"]["act_hp_growth"] = 2.0
    for k, v in sets.items():
        ms.set_path(cfg, k.replace("__", "."), v)
    return cfg


def run_rows(cfg, n, seed="t"):
    ctx = ms.SimContext(cfg)
    return [ms.simulate_run(cfg, f"{seed}-{i}", ctx=ctx) for i in range(n)]


class AC1Regression(unittest.TestCase):
    """effect_mode=grade 에서 변경 전 코드와 판 단위로 완전히 같아야 한다."""

    def test_rows_identical_to_original(self):
        import _matchup_sim_original as orig
        for hp in (74, 120):
            cfg = base_cfg(monsters__hp_base=hp)
            pool = orig.load_fantasy_pool(cfg)
            for i in range(400):
                seed = f"verify-{i}"
                a = orig.simulate_run(cfg, seed, pool)
                b = ms.simulate_run(cfg, seed)
                self.assertEqual(a, b, f"hp_base={hp} seed={seed}")

    def test_reference_summary(self):
        """명세 참고값: --seed verify --runs 5000 hp_base=74 → 승률 9.1%, 평균 도달 30.1층 (M0 에서 변경 전 코드로 재측정)."""
        cfg = base_cfg(monsters__hp_base=74)
        rows = run_rows(cfg, 5000, "verify")
        s = ms.summarize(rows)
        self.assertEqual(round(s["win_rate"] * 100, 1), 9.1)
        self.assertEqual(round(s["mean_reached_floor"], 1), 30.1)


class _TableHarness:
    """실제 효과 테이블 + 시험용 환상 1개를 담은 임시 테이블로 두 변형을 같은 시드에서 비교."""

    N = 500

    @classmethod
    def setUpClass(cls):
        with open(EFFECTS, encoding="utf-8") as fp:
            cls.base_table = json.load(fp)
        cls.tmp = tempfile.TemporaryDirectory()
        cls._n = 0

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def table_with(self, effects, grade="white", available=False, extra=()):
        data = copy.deepcopy(self.base_table)
        data["fantasies"].append({"id": "t_probe", "name": "probe", "grade": grade, "fidelity": "exact",
                                  "effects": effects, "notes": "", "available": available})
        data["fantasies"].extend(extra)
        type(self)._n += 1
        path = os.path.join(self.tmp.name, f"fx{self._n}.json")
        with open(path, "w", encoding="utf-8") as fp:
            json.dump(data, fp, ensure_ascii=False)
        return path

    def metrics(self, effects, n=None, forced=("t_probe",), at="start", hp=TABLE_HP, available=False, **sets):
        cfg = base_cfg(monsters__hp_base=hp, **sets)
        ms.apply_fantasy_args(cfg, self.table_with(effects, available=available))
        cfg["fantasy"]["forced"] = {"ids": list(forced), "at": at}
        rows = run_rows(cfg, n or self.N, "ac2")
        s = ms.summarize(rows)
        s["fantasies_bought"] = sum(r["fantasies_bought"] for r in rows) / len(rows)
        s["copies"] = sum(r["fantasy_copies"] for r in rows)
        s["voided"] = sum(r["fantasy_voided"] for r in rows)
        s["rows"] = rows
        return s


# 효과 타입 → (넣을 효과, 비교 기준 효과, 지표, 방향). 방향 +1 = 증가해야 함.
UP, DOWN = 1, -1
DIRECTION_CASES = {
    "dmg_mult_add": ([{"type": "dmg_mult_add", "value": 1.0}], [], "mean_reached_floor", UP),
    "dmg_flat": ([{"type": "dmg_flat", "value": 40}], [], "mean_reached_floor", UP),
    "dmg_final_mult": ([{"type": "dmg_final_mult", "value": 2.0}], [], "mean_reached_floor", UP),
    "base_dmg_transform": ([{"type": "base_dmg_transform", "op": "first_digit", "value": 9}], [], "mean_reached_floor", UP),
    "hits_add": ([{"type": "hits_add", "value": 2}], [], "mean_reached_floor", UP),
    "combo_same_dmg_stack": ([{"type": "hits_add", "value": 3}, {"type": "combo_same_dmg_stack", "value": 50}],
                             [{"type": "hits_add", "value": 3}], "mean_reached_floor", UP),
    "end_turn_dmg": ([{"type": "end_turn_dmg", "value": 60}], [], "mean_reached_floor", UP),
    "player_str_add": ([{"type": "player_str_add", "value": 30}], [], "mean_reached_floor", UP),
    "mirror_enemy_str": ([{"type": "mirror_enemy_str", "value": 20}], [], "mean_reached_floor", UP),
    "moves_per_turn_add": ([{"type": "moves_per_turn_add", "value": 1}], [], "mean_reached_floor", UP),
    "moves_per_turn_mult": ([{"type": "moves_per_turn_mult", "value": 2.0}], [], "mean_reached_floor", UP),
    "battle_start_moves": ([{"type": "battle_start_moves", "value": 4}], [], "mean_reached_floor", UP),
    "battle_temp_items": ([{"type": "battle_temp_items", "value": 3}], [], "mean_reached_floor", UP),
    "item_use_refund_chance": ([{"type": "battle_temp_items", "value": 0}, {"type": "item_use_refund_chance", "value": 1.0}],
                               [], "mean_reached_floor", UP),
    "dmg_taken_flat": ([{"type": "dmg_taken_flat", "value": 10}], [], "mean_reached_floor", DOWN),
    "dmg_taken_mult": ([{"type": "dmg_taken_mult", "value": 0.5}], [], "mean_reached_floor", UP),
    "dmg_taken_delay": ([{"type": "dmg_taken_delay", "value": 0.5}], [], "mean_reached_floor", UP),
    "def_cut_add": ([{"type": "def_cut_add", "value": 0.4}], [], "mean_reached_floor", UP),
    "monster_dmg_digit_max": ([{"type": "monster_dmg_digit_max", "value": 2}], [], "mean_reached_floor", UP),
    "monster_str_add": ([{"type": "monster_str_add", "value": 8}], [], "mean_reached_floor", DOWN),
    "str_block": ([{"type": "str_block", "value": 10}], [], "mean_reached_floor", UP),
    "monster_skip_chance_add": ([{"type": "monster_skip_chance_add", "value": 0.3}], [], "mean_reached_floor", UP),
    "enemy_acts_first": ([{"type": "enemy_acts_first", "value": 1}], [], "mean_reached_floor", DOWN),
    "reflect_on_hit": ([{"type": "reflect_on_hit", "value": 60}], [], "mean_reached_floor", UP),
    "heal_on_deal": ([{"type": "heal_on_deal", "value": 15}], [], "mean_reached_floor", UP),
    "heal_on_take": ([{"type": "heal_on_take", "per": 5, "value": 10}], [], "mean_reached_floor", UP),
    "heal_per_unused_move": ([{"type": "moves_per_turn_add", "value": 6}, {"type": "heal_per_unused_move", "value": 40}],
                             [{"type": "moves_per_turn_add", "value": 6}], "mean_reached_floor", UP),
    "revive_once": ([{"type": "revive_once", "value": 1}], [], "mean_reached_floor", UP),
    "battle_start_temp_copy": ([{"type": "dmg_flat", "value": 1}, {"type": "battle_start_temp_copy", "value": 1}],
                               [{"type": "dmg_flat", "value": 1}], "mean_reached_floor", UP),
    "heal_per_battle": ([{"type": "heal_per_battle", "value": 60}], [], "mean_reached_floor", UP),
    "item_drop_chance_add": ([{"type": "item_drop_chance_add", "value": 0.5}], [], "mean_reached_floor", UP),
    "item_drop_mult": ([{"type": "item_drop_mult", "value": 2.0}], [], "mean_reached_floor", UP),
    "item_gain_bonus": ([{"type": "item_gain_bonus", "value": 2}], [], "mean_reached_floor", UP),
    "rest_heal_mult": ([{"type": "rest_heal_mult", "value": 4.0}], [], "mean_reached_floor", UP),
    "rest_heal_add": ([{"type": "rest_heal_add", "value": 300}], [], "mean_reached_floor", UP),
    "rest_extra_uses": ([{"type": "rest_extra_uses", "value": 3}], [], "mean_reached_floor", UP),
    "rest_alt_fantasy": ([{"type": "rest_alt_fantasy", "grade": "white"}], [], "mean_fantasies", UP),
    "shop_price_mult": ([{"type": "shop_price_mult", "value": 0.2}], [], "fantasies_bought", UP),
    "shop_enter_heal": ([{"type": "shop_enter_heal", "value": 500}], [], "mean_reached_floor", UP),
    "shop_moves_add": ([{"type": "shop_moves_add", "value": 4}], [], "fantasies_bought", UP),
    "shop_free_items": ([{"type": "shop_free_items", "value": 5}], [], "mean_reached_floor", UP),
    "on_acquire_heal": ([{"type": "on_acquire_heal", "value": 2000}], [], "mean_reached_floor", UP),
}
# 방향 테스트 대신 별도 테스트로 확인하는 타입 (이유)
SEPARATE = {
    "carry_unused_moves": "시뮬레이터 정책상 남는 이동은 처치 턴에만 생겨 효과가 0 — 기계적 동작만 별도 확인",
    "acquire_dup_or_void": "승률 방향이 정해져 있지 않음 — 복사/무효 발생을 별도 확인",
    "on_acquire_copy_owned": "복사 발생을 별도 확인",
    "combine_into": "조합 발생을 별도 확인",
}


class AC2EffectDirections(_TableHarness, unittest.TestCase):

    def test_every_type_covered(self):
        self.assertEqual(set(DIRECTION_CASES) | set(SEPARATE), ms.EFFECT_TYPES)

    def test_directions(self):
        ref_cache = {}
        failures = []
        for t, (eff, ref, metric, sign) in DIRECTION_CASES.items():
            key = json.dumps(ref)
            if key not in ref_cache:
                ref_cache[key] = self.metrics(ref)
            a, b = self.metrics(eff), ref_cache[key]
            diff = a[metric] - b[metric]
            if not diff * sign > 0:
                failures.append(f"{t}: {metric} {b[metric]} → {a[metric]} (기대 방향 {'+' if sign > 0 else '-'})")
        self.assertFalse(failures, "\n".join(failures))

    def test_dup_or_void(self):
        s = self.metrics([{"type": "acquire_dup_or_void", "chance": 0.5}], n=200)
        self.assertGreater(s["copies"], 0)
        self.assertGreater(s["voided"], 0)

    def test_copy_owned(self):
        s = self.metrics([{"type": "on_acquire_copy_owned", "value": 1}], n=200, at={"floor": 10})
        self.assertGreater(s["copies"], 0)

    def test_combine(self):
        parts = [{"id": f"t_part{k}", "name": f"p{k}", "grade": "white", "fidelity": "exact",
                  "effects": [], "notes": "", "available": False} for k in range(2)]
        res = {"id": "t_combo", "name": "combo", "grade": "red", "fidelity": "exact",
               "effects": [{"type": "combine_into", "from": ["t_part0", "t_part1"]}], "notes": "", "available": False}
        path = self.table_with([], extra=parts + [res])
        cfg = base_cfg(monsters__hp_base=TABLE_HP)
        ms.apply_fantasy_args(cfg, path)
        cfg["fantasy"]["forced"] = {"ids": ["t_part0", "t_part1"], "at": "start"}
        row = ms.simulate_run(cfg, "combo-0")
        self.assertEqual(row["fantasies"].split("|")[:3], ["t_part0", "t_part1", "t_combo"])

    def test_carry_unused_moves_mechanics(self):
        """carry 는 효과가 거의 0 이어야 한다(정책상). 오류 없이 돌고 결과가 기준과 같거나 매우 가깝다."""
        a = self.metrics([{"type": "carry_unused_moves", "value": 1}], n=200)
        b = self.metrics([], n=200)
        self.assertLess(abs(a["win_rate"] - b["win_rate"]), 0.05)

    def test_none_fantasy_has_no_mechanical_effect(self):
        """효과가 빈 환상은 (풀에서 빠지는 효과 외에는) 아무 것도 바꾸지 않는다: 풀 밖 환상이면 결과가 판 단위로 같다."""
        a = self.metrics([], n=100, available=False)
        cfg = base_cfg(monsters__hp_base=TABLE_HP)
        ms.apply_fantasy_args(cfg, self.table_with([]))
        rows = run_rows(cfg, 100, "ac2")
        self.assertEqual([r["result"] for r in rows], [r["result"] for r in a["rows"]])
        self.assertEqual([r["reached_floor"] for r in rows], [r["reached_floor"] for r in a["rows"]])

    def test_grade_mode_ignores_table(self):
        """effects_file 이 있어도 grade 모드면 기존 결과와 같다."""
        cfg = base_cfg(monsters__hp_base=74)
        rows_a = run_rows(cfg, 200)
        cfg2 = copy.deepcopy(cfg)
        cfg2["fantasy"]["effects_file"] = EFFECTS
        cfg2["fantasy"]["effect_mode"] = "grade"
        rows_b = run_rows(cfg2, 200)
        self.assertEqual(rows_a, rows_b)


class AC3Forced(_TableHarness, unittest.TestCase):
    N_SEEDS = 1000

    def _check(self, cfg, fid, n):
        ctx = ms.SimContext(cfg)
        orig_unowned = ms.RunState.unowned
        seen_after = []

        def spy(st, grade):
            res = orig_unowned(st, grade)
            if fid in st.owned_set and fid in res:
                seen_after.append(grade)
            return res

        ms.RunState.unowned = spy
        try:
            rows = [ms.simulate_run(cfg, f"ac3-{i}", ctx=ctx) for i in range(n)]
        finally:
            ms.RunState.unowned = orig_unowned
        for r in rows:
            got = r["fantasies"].split("|")
            self.assertEqual(got.count(fid), 1)                  # (a) 정확히 1번 보유
            self.assertEqual(got[0], fid)                         # (c) 첫 항목
        self.assertEqual(seen_after, [])                          # (b) 이후 후보에 나타나지 않음
        return rows

    def test_forced_table_mode(self):
        for fid in ("fan_damage_slingshot", "fan_turn_boots", "fan_fantasy_leo", "fan_rest_coffee"):
            cfg = base_cfg(monsters__hp_base=TABLE_HP)
            ms.apply_fantasy_args(cfg, EFFECTS, force=fid)
            self._check(cfg, fid, self.N_SEEDS if fid == "fan_damage_slingshot" else 200)

    def test_forced_low_hp_long_runs(self):
        """보상·상점 후보가 많이 소모되는 긴 런(낮은 체력)에서도 성립."""
        cfg = base_cfg(monsters__hp_base=100)
        ms.apply_fantasy_args(cfg, EFFECTS, force="fan_damage_anchor")
        rows = self._check(cfg, "fan_damage_anchor", 300)
        self.assertGreater(sum(r["result"] == "win" for r in rows), 200)

    def test_forced_grade_mode(self):
        cfg = base_cfg(monsters__hp_base=74)
        ms.apply_fantasy_args(cfg, force="W05")
        self._check(cfg, "W05", self.N_SEEDS)

    def test_forced_at_floor(self):
        cfg = base_cfg(monsters__hp_base=100)
        ms.apply_fantasy_args(cfg, EFFECTS, force="fan_turn_boots", force_at=18)
        ctx = ms.SimContext(cfg)
        for i in range(200):
            r = ms.simulate_run(cfg, f"f18-{i}", ctx=ctx)
            got = r["fantasies"].split("|") if r["fantasies"] else []
            if r["reached_floor"] >= 18:
                self.assertEqual(got.count("fan_turn_boots"), 1)
            else:
                self.assertNotIn("fan_turn_boots", got)


if __name__ == "__main__":
    unittest.main()
