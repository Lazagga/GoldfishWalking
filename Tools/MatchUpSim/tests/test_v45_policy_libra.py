# -*- coding: utf-8 -*-
"""v4.5 F22 — 천칭자리 재모델링(AC-L), 배분 정책 보정(AC-B), 소수점 버림(AC-R)."""
import copy
import json
import os
import random
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)

import import_fantasies as imp  # noqa: E402
import matchup_sim as ms  # noqa: E402
from sim_service import box_moves as bm  # noqa: E402
from sim_service import edits as ed  # noqa: E402
from sim_service import fight_digits as fd  # noqa: E402
from sim_service import store as st  # noqa: E402
from test_v4_digits import battle, cfg_of, mon_of  # noqa: E402

with open(os.path.join(ROOT, "fantasy_effects.json"), encoding="utf-8") as _fp:
    TABLE = {f["id"]: f for f in json.load(_fp)["fantasies"]}
LIBRA = "fan_damage_libra"


def fx_of(fids, copies=1):
    return ms.Fx(TABLE, {f: copies for f in fids}, list(fids))


def old_objective(dealt, taken, hp, mhp, kill_first, w, extra_pen=0.0, heal=0, doom=False):
    """F22-B 이전 목적함수 (회귀 비교용)."""
    if doom:
        taken = float("inf")
    alive = taken < hp
    kill = kill_first and dealt >= mhp
    J = w * (dealt - heal) / max(1, mhp) - (1 - w) * (taken if taken != float("inf") else 1e9) / max(1, hp) - extra_pen
    if not alive:
        return (0, 0, -taken, J)
    if kill:
        return (1, 1, -taken, J)
    return (1, 0, J, -taken)


class LibraRule(unittest.TestCase):
    # --- AC-L1 / AC-L9
    def test_l1_rule(self):
        fx = fx_of([LIBRA])
        self.assertEqual([ms.eval_base(v, fx) for v in (0, 40, 45, 1, 99)], [200, 20, 22, 0, 49])
        self.assertNotEqual(ms.eval_base(0, fx), 100)                # 0 → 200 뒤에 ×0.5 를 다시 적용하지 않는다
        self.assertEqual(ms.eval_base(ms.eval_base(1, fx) if False else 1, fx), 0)   # 1 → 0, 다시 200 이 되지 않는다 (판정은 입력 기준 한 번)

    def test_l9_no_stacking(self):
        for c in (1, 2, 3):
            fx = fx_of([LIBRA], copies=c)
            self.assertEqual((ms.eval_base(0, fx), ms.eval_base(40, fx)), (200, 20), c)
        fx_b = ms.Fx(TABLE, {LIBRA: 2}, [LIBRA]).copy().add(LIBRA, 1)     # 임시 복사본까지 포함해도 한 번
        self.assertEqual(ms.eval_base(40, fx_b), 20)

    def test_no_eval_without_libra(self):
        fx = fx_of([])
        self.assertFalse(ms.has_eval_base(fx))
        self.assertEqual(ms.eval_base(37, fx), 37)

    def test_transform_base_skips_eval_ops(self):
        fx = fx_of([LIBRA])
        self.assertEqual(ms.transform_base(60, fx), 60)               # 굴림형 변환은 건너뛴다 (예외도 던지지 않는다)
        self.assertEqual(ms.transform_base(0, fx), 0)

    # --- AC-L6: gauss — 굴림 직후 변환 값은 변경 전과 같다 (기본 피해 10~45)
    def test_l6_gauss_value_unchanged(self):
        fx = fx_of([LIBRA])
        for b in range(10, 46):
            self.assertEqual(ms.eval_base(ms.transform_base(b, fx), fx), int(b * 0.5), b)


class LibraBoxes(unittest.TestCase):
    # --- AC-L4: 0 에 닿을 수 있으면 후보에 남는다 (작은 상자·큰 상자 경로 모두)
    def test_l4_zero_candidate_kept(self):
        fx = fx_of([LIBRA])
        rank = lambda v: ms.eval_base(v, fx)
        for v, d, k in ((60, 2, 1), (69, 2, 2), (6000, 4, 1), (6900, 4, 2), (600, 3, 1)):
            for limit in (None, 1):          # limit=1 → 큰 상자(DP) 경로를 강제
                pr = bm.reach_best(d, v, k, +1, rank=rank, limit=limit)
                self.assertIn(0, pr, (v, d, k, limit))                  # 후보 열거에는 항상 남는다
                kept = dict(fd.prune(pr, +1, None, rank=rank))
                if d == 2:                                              # 2자리 상자는 최대 49 < 200 이라 0 이 최상위 → 가지치기 뒤에도 남는다
                    self.assertIn(0, kept, (v, d, k, limit))
                else:                                                   # 3자리 이상은 ⌊999/2⌋ = 499 > 200 이라 큰 값이 더 좋다 (0 이 밀리는 게 맞다)
                    self.assertGreater(max(rank(x) for x in kept), 200)

    def test_l4_unreachable_zero_not_invented(self):
        rank = lambda v: ms.eval_base(v, fx_of([LIBRA]))
        for limit in (None, 1):
            self.assertNotIn(0, bm.reach_best(2, 88, 1, +1, rank=rank, limit=limit))    # 88 → 00 은 이동 1 로 안 닿는다

    # --- AC-L5: 평가형 변환이 없는 설정은 변경 전과 같다
    def test_l5_non_eval_unchanged(self):
        rng = random.Random(5)
        for _ in range(1000):
            v, k = rng.randint(10, 99), rng.randint(0, 3)
            a = bm.reach_best(2, v, k, +1)
            self.assertEqual(a, bm.reach_best(2, v, k, +1, rank=None))
            self.assertEqual(a, dict(bm._reach(bm.masks_of(v, 2), k, bm.norm_cons(2, False, None, (), True, bm.masks_of(v, 2)))))
        for v, k in ((6969, 3), (88888, 2)):             # 큰 상자: rank 없이 부르면 DP 결과 그대로
            masks = bm.masks_of(v, len(str(v)))
            cons = bm.norm_cons(len(str(v)), False, None, (), True, masks)
            self.assertEqual(bm.reach_best(len(str(v)), v, k, +1, limit=1), bm.best_per_cost(masks, k, cons, +1))

    def test_big_box_rank_only_adds_zero(self):
        rank = lambda v: ms.eval_base(v, fx_of([LIBRA]))
        for v, k in ((6969, 3), (5000, 1), (7777, 4)):
            plain = bm.reach_best(len(str(v)), v, k, +1, limit=1)
            ranked = bm.reach_best(len(str(v)), v, k, +1, rank=rank, limit=1)
            self.assertEqual({a: b for a, b in ranked.items() if a != 0}, {a: b for a, b in plain.items() if a != 0})


class LibraBattle(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fx = fx_of([LIBRA])

    def duel(self, n=120, moves=1, patterns=("Skip",), mhp=10 ** 6, hp=10 ** 6, fids=(LIBRA,), seed="LB", skill=1.0):
        c = cfg_of(skill=skill, hp=hp)
        c["player"]["moves_per_turn"] = moves
        out = []
        for i in range(n):
            mon = mon_of(patterns, hp=mhp, ai="static")
            _, stt, tr = battle(c, mon, f"{seed}{i}", fids=fids, hp=hp)
            out += tr
        return out

    # --- AC-L2 / AC-L3: 피해만 보는 상황(몬스터가 안 때림)에서 AI 는 평가 값이 가장 큰 상자를 만든다
    def test_l2_l3_ai_maximizes_eval(self):
        turns = self.duel(n=150, moves=1)
        zero = 0
        for e in turns:
            if e["K"] != 1:
                continue
            best = max(ms.eval_base(v, self.fx) for v in bm.reach(max(2, len(str(e["base"]))), e["base"], e["K"]))
            self.assertEqual(e["base_eval"], best, e)
            self.assertEqual(e["base_eval"], ms.eval_base(e["base_edit"], self.fx))
            self.assertEqual(e["dealt"], e["base_eval"], e)
            if e["base"] == 60:
                self.assertEqual((e["base_edit"], e["base_eval"]), (0, 200))      # 굴림 60, K=1 → 00, 타격당 200
                zero += 1
        self.assertGreater(zero, 5)

    def test_l2_edited_value_is_halved_not_pre_halved(self):
        turns = self.duel(n=60, moves=2)
        for e in turns:
            if e["base_edit"] != 0:
                self.assertEqual(e["base_eval"], e["base_edit"] // 2)            # 편집 끝난 값의 절반 (굴림 직후 절반에서 시작하지 않는다)

    def test_no_libra_event_fields_equal(self):
        for e in self.duel(n=20, fids=()):
            self.assertEqual(e["base_eval"], e["base_edit"])

    # --- AC-L7: 로그·분해
    def test_l7_log_and_calc_eval_step(self):
        turns = self.duel(n=80, moves=1)
        seen = 0
        for e in turns:
            c = e["calc"]
            self.assertNotIn("error", c, c)
            self.assertEqual(c["dealt"]["total"], e["dealt"], e)
            st_ = c["dealt"]["steps"]
            for a, b in zip(st_, st_[1:]):
                self.assertEqual(a["to"], b["from"], st_)
            ev = [s for s in st_ if s["k"] == "eval"]
            self.assertEqual(len(ev), 1 if e["base_edit"] != e["base_eval"] else 0, e)
            if ev:
                self.assertEqual((ev[0]["from"], ev[0]["to"]), (e["base_edit"], e["base_eval"]))
                if e["base_edit"] == 0:
                    self.assertEqual((ev[0]["from"], ev[0]["to"]), (0, 200))
                    seen += 1
            tf = [s for s in st_ if s["k"] == "transform"]
            self.assertEqual(tf, [])                                             # 천칭자리는 굴림형 변환이 아니다
        self.assertGreater(seen, 5)

    def test_l7_zero_set_other_transform_still_roll_time(self):
        # 큐대(first_digit)는 굴림 직후 변환 그대로: base(표시 숫자)가 이미 바뀌어 있다
        fid = next((f for f, v in TABLE.items() if any(e.get("op") == "first_digit" for e in v["effects"])), None)
        self.assertIsNotNone(fid)
        for e in self.duel(n=10, fids=(fid,)):
            self.assertEqual(e["base_eval"], e["base_edit"])
            self.assertEqual(str(e["base"])[0], str(next(x["value"] for x in TABLE[fid]["effects"] if x.get("op") == "first_digit"))[0])

    def test_battle_with_libra_and_monster_damage_runs(self):
        turns = self.duel(n=20, patterns=("2_Single", "2_Multi_1"), mhp=3000, hp=1500, moves=2, skill=0.7)
        self.assertGreater(len(turns), 20)
        for e in turns:
            self.assertNotIn("error", e["calc"], e["calc"])
            self.assertEqual(e["calc"]["dealt"]["total"], e["dealt"])


class LibraData(unittest.TestCase):
    # --- AC-L8
    def test_l8_override_and_auto_import(self):
        eff = TABLE[LIBRA]["effects"]
        self.assertEqual(len(eff), 1)
        self.assertEqual((eff[0]["type"], eff[0]["op"], eff[0]["zero_value"], eff[0]["value"]), ("base_dmg_transform", "zero_else_mult", 200, 0.5))
        self.assertEqual(TABLE[LIBRA]["fidelity_digits"], "exact")
        d = tempfile.mkdtemp()
        out = os.path.join(d, "fe.json")
        self.assertEqual(imp.main(["--out", out, "--quiet"]), 0)
        with open(out, encoding="utf-8") as fp:
            e2 = {f["id"]: f for f in json.load(fp)["fantasies"]}[LIBRA]
        self.assertEqual(e2["effects"], eff)
        # overrides 가 없어도(원본 두 효과를 읽어) 한 규칙으로 합친다 — 다시 둘로 풀지 않는다
        src_dir = imp.DEFAULT_SRC
        with open(os.path.join(src_dir, "fan_damage_libra.json"), encoding="utf-8-sig") as fp:
            src = json.load(fp)
        src["_file"] = "fan_damage_libra.json"
        auto = imp.convert(src, {})
        self.assertEqual(len(auto["effects"]), 1, auto["effects"])
        a = auto["effects"][0]
        self.assertEqual((a["op"], a["zero_value"], a["value"]), ("zero_else_mult", 200, 0.5))
        self.assertEqual([s["sim_key"] for s in a["src"]], ["zero_value", "value"])
        self.assertEqual(auto["fidelity"], "exact")

    def test_l8_editable_ranges(self):
        ef = {"type": "base_dmg_transform", "op": "zero_else_mult", "zero_value": 200, "value": 0.5}
        self.assertIsNone(ed.validate(ed.key_schema(ef, "zero_value"), 150))
        self.assertIsNotNone(ed.validate(ed.key_schema(ef, "zero_value"), 1000))
        self.assertIsNone(ed.validate(ed.key_schema(ef, "value"), 0.4))
        self.assertIsNotNone(ed.validate(ed.key_schema(ef, "value"), 0))


class Objective(unittest.TestCase):
    # --- AC-B1: 선공 처치는 몬스터가 행동하지 못하므로 받을 피해가 체력 이상이어도 처치를 고른다
    def test_b1_first_strike_kill_beats_defence(self):
        kill = fd.objective(100, 999, 40, 100, False, 0.5)
        defend = fd.objective(10, 0, 40, 100, False, 0.5)
        self.assertGreater(kill, defend)
        self.assertLess(old_objective(100, 999, 40, 100, True, 0.5), old_objective(10, 0, 40, 100, True, 0.5))   # 변경 전: 방어를 골랐다

    # --- AC-B2: 후공 — 맞고 살아남은 뒤 처치하면 처치 등급, 초과 피해는 가치가 없다
    def test_b2_second_strike_kill_grade(self):
        kill = fd.objective(100, 30, 40, 100, True, 0.5)
        alive = fd.objective(99, 0, 40, 100, True, 0.5)
        self.assertGreater(kill, alive)
        self.assertLess(fd.objective(100, 40, 40, 100, True, 0.5), alive)                # 맞고 죽으면 처치해도 사망 등급
        self.assertEqual(fd.objective(100, 30, 40, 100, True, 0.5)[:3], fd.objective(10 ** 6, 30, 40, 100, True, 0.5)[:3])   # 초과 피해로 더 좋아지지 않는다
        self.assertEqual(fd.objective(100, 30, 40, 100, True, 0.5), fd.objective(10 ** 6, 30, 40, 100, True, 0.5))
        j1, j2 = fd.objective(60, 5, 40, 100, True, 0.5), fd.objective(10 ** 6, 5, 40, 100, True, 0.5)
        self.assertGreater(j2, j1)                                                       # 비처치(60)보다 처치(초과)는 등급이 높다

    def test_b2_j_clips_over_damage(self):
        # 처치 못 하는 조합끼리는 J 가 같은 식, 자른 값은 mhp 이상일 때만 의미가 있다
        self.assertEqual(fd.objective(99, 5, 40, 100, False, 0.5)[2], 0.5 * 99 / 100 - 0.5 * 5 / 40)

    # --- AC-B3: 선공 처치이면 카운트다운(doom)을 무시한다
    def test_b3_doom_ignored_on_first_strike_kill(self):
        a = fd.objective(100, 5, 40, 100, False, 0.5, doom=True)
        b = fd.objective(100, 5, 40, 100, False, 0.5, doom=False)
        self.assertEqual(a, b)
        self.assertEqual(a[:2], (1, 1))
        self.assertEqual(fd.objective(50, 5, 40, 100, False, 0.5, doom=True)[:2], (0, 0))      # 처치 못 하면 여전히 사망 등급

    def test_b3_item_pen_breaks_first_strike_ties(self):
        self.assertGreater(fd.objective(100, 5, 40, 100, False, 0.5, item_pen=0.0), fd.objective(100, 5, 40, 100, False, 0.5, item_pen=0.3))

    # --- AC-B4: 처치 불가(dealt < mhp) 입력의 키는 변경 전과 같다
    def test_b4_non_kill_regression(self):
        rng = random.Random(44)
        for _ in range(10000):
            mhp, hp = rng.randint(1, 3000), rng.randint(1, 1500)
            dealt, taken = rng.randint(0, mhp - 1), rng.randint(0, 3000)
            w, pen, heal = rng.choice([0.3, 0.5, 0.7]), rng.choice([0.0, 0.25, -0.25]), rng.choice([0, 0, 7])
            doom = rng.random() < 0.2
            ef = rng.random() < 0.5
            self.assertEqual(fd.objective(dealt, taken, hp, mhp, ef, w, pen, heal, doom), old_objective(dealt, taken, hp, mhp, not ef, w, pen, heal, doom))


class PolicyWeight(unittest.TestCase):
    # --- AC-B5
    def test_b5_attack_weight_editable_and_keyed(self):
        path = "player.policy.attack_weight"
        self.assertIn(path, ed.CFG_EDITABLE)
        self.assertIsNone(ed.validate(ed.CFG_EDITABLE[path], 0.3))
        self.assertIsNotNone(ed.validate(ed.CFG_EDITABLE[path], 1.5))
        cfg = cfg_of()
        c2, conf, err = ed.apply_cfg_edits(cfg, [{"path": path, "old": 0.5, "new": 0.3}])
        self.assertEqual((conf, err), ([], []))
        self.assertEqual(c2["player"]["policy"]["attack_weight"], 0.3)
        self.assertEqual(fd.policy_of(c2)["w"], 0.3)
        self.assertNotEqual(st.point_key(cfg, [], "s", "h"), st.point_key(c2, [], "s", "h"))
        self.assertIn(path, ed.schema_json()["cfg"])

    def test_b5_weight_changes_choices(self):
        outs = []
        for w in (0.1, 0.9):
            c = cfg_of(skill=0.7, hp=300)
            c["player"]["policy"]["attack_weight"] = w
            res = []
            for i in range(30):
                mon = mon_of(("2_Single", "2_Multi_1"), hp=800, ai="static")
                o, stt, tr = battle(c, mon, f"W{i}", fids=(), hp=300)
                res.append([(e["base_edit"], e["mon_dmg_edit"]) for e in tr])
            outs.append(res)
        self.assertNotEqual(outs[0], outs[1])


class Truncation(unittest.TestCase):
    # --- AC-R3
    def test_r3_trunc(self):
        self.assertEqual((ms.trunc(100 * 0.29), ms.trunc(-1.0), ms.trunc(-2.5), ms.trunc(0), ms.trunc(2.999999)), (29, -1, -2, 0, 2))
        self.assertEqual(ms.trunc(7 * 0.5), 3)
        self.assertEqual(ms.trunc(5 * (1 - 0.3)), 3)
        self.assertEqual(ms.trunc(15 * 0.9), 13)
        self.assertEqual(round(0.5), 0)

    # --- AC-R1: 소수점 버림이 실제 경로에 걸려 있다
    def test_r1_acquire_heal_and_price(self):
        c = cfg_of()
        c0 = copy.deepcopy(c)
        c0["monsters"].update({"damage_model": "gauss", "gimmicks": "off", "model": "tier_avg"})
        ctx = ms.SimContext(c0)
        stt = ms.RunState(c, ctx.pool, ctx, "r1")
        stt.hp = 333
        stt.acquire(ctx.grade_of["fan_acquire_Candy"], "fan_acquire_Candy", "forced")
        self.assertEqual(stt.hp, 333 + ms.trunc(0.1 * 333))            # 33.3 → 33
        stt.hp = 355
        stt.acquire(ctx.grade_of["fan_acquire_Candy"], "fan_acquire_Candy", "forced")
        self.assertEqual(stt.hp, 355 + 35)                              # 35.5 → 35 (round 는 36 이었다)

    def test_r1_player_hit_and_monster_cut_in_digits(self):
        # 몬스터 피해 감소(def_cut)·내 피해 배율은 타격당 버림: 이벤트의 타격당 값으로 확인
        fid_cut, cut = "fan_test_cut", 0.3
        with open(os.path.join(ROOT, "fantasy_effects.json"), encoding="utf-8") as fp:
            tab = json.load(fp)
        tab["fantasies"].append({"id": fid_cut, "name": "테스트 감소", "grade": "white", "fidelity": "exact", "fidelity_digits": "exact", "available": True,
                                 "effects": [{"type": "def_cut_add", "value": cut}], "notes": "", "description": ""})
        p = os.path.join(tempfile.mkdtemp(), "fe.json")
        with open(p, "w", encoding="utf-8") as fp:
            json.dump(tab, fp)
        c = cfg_of(skill=1.0, hp=10 ** 6)
        ms.apply_fantasy_args(c, p)
        n = 0
        for i in range(30):
            mon = mon_of(("2_Single",), hp=10 ** 7, ai="static")
            _, stt, tr = battle(c, mon, f"R{i}", fids=(fid_cut,), hp=10 ** 6)
            for e in tr:
                if e["taken"]:
                    self.assertEqual(e["taken"], ms.trunc(e["mon_dmg_eff"] * (1 - cut)), e)
                    n += 1
        self.assertGreater(n, 20)

    def test_r2_excluded_roundings_unchanged(self):
        with open(os.path.join(ROOT, "matchup_sim.py"), encoding="utf-8") as fp:
            src = fp.read()
        self.assertIn("round(rng.gauss(hp_mean, hp_mean * t[\"hp_cv\"]))", src)      # 표본 근사는 그대로
        self.assertIn("round(mon[\"hp\"] * M.get(\"hp_scale\", 1.0))", src)             # hp_scale 은 그대로
        self.assertIn("return max(1, round(p))", src)                                    # 상점 가격 수정(확률 표본)은 제외 목록


class Versions(unittest.TestCase):
    def test_versions_bumped(self):
        self.assertGreaterEqual(ms.SIM_VERSION, 3)
        self.assertGreaterEqual(fd.VERSION, 4)
        self.assertGreaterEqual(bm.VERSION, 2)
        c = cfg_of()
        self.assertIn(f"dg{fd.VERSION}.{bm.VERSION}", "dg%s.%s" % (fd.VERSION, bm.VERSION))


if __name__ == "__main__":
    unittest.main()
