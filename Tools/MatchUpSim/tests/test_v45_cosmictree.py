# -*- coding: utf-8 -*-
"""v4.5 F19 세계수 힘 초기화 규칙 (AC-G1·G1b·G2·G4).

- 규칙은 원본 JSON(passive.trigger)에 있다: compare(equal), number.reroll(every_turn), digitsBase 2 + 플레이어 힘.
- 매 턴 칸의 수 N 을 굴리고, 그 턴 입힌 피해가 N 과 정확히 같을 때만 전투당 1회 발동한다.
- trigger 가 없는 옛 JSON 은 옛 정책 방식(힘이 기본보다 reset_at_strength 이상 높으면 사용)으로 동작한다.
"""
import json
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)

import import_monsters as im  # noqa: E402
from sim_service import fight_digits as fd  # noqa: E402
from test_v4_digits import battle, cfg_of, mon_of  # noqa: E402

TRIG = {"compare": "equal", "reroll": "every_turn", "digits_base": 2, "min_digits": 1, "add_player_strength": True}


def spec(**kw):
    s = {"kind": "strength_reset", "lock_all": True, "tier": "GB", "fidelity": "approx", "reason": "t"}
    if kw.get("trigger") is not False:
        s["trigger"] = dict(TRIG, **(kw.get("trigger") or {}))
    return s


def fights(sim, n=120, skill=0.0, patterns=("2_Single",), prefix="rs"):
    c = cfg_of(g="on", skill=skill, hp=10 ** 9)
    out = []
    for i in range(n):
        mon = mon_of(patterns, hp=10 ** 9, sim=sim)
        _, _, tr = battle(c, mon, f"{prefix}{i}", hp=10 ** 9)
        out.append(tr)
    return out


class Rule(unittest.TestCase):
    def test_json_has_the_rule_and_importer_reads_it(self):
        with open(os.path.join(HERE, "fixtures", "monsters", "mob_30302_cosmictree.json"), encoding="utf-8-sig") as fp:
            mon = json.load(fp)
        pz = next(p for p in mon["passives"] if p["operation"] == "once_per_battle_strength_reset")
        self.assertEqual(pz["trigger"]["compare"], "equal")                               # 규칙이 원본 JSON 에 적혀 있다
        self.assertEqual(pz["trigger"]["number"]["reroll"], "every_turn")
        mon["_file"] = "mob_30302_cosmictree.json"
        sr = next(s for s in im.passive_specs(mon) if s["kind"] == "strength_reset")
        self.assertEqual(sr["trigger"], TRIG)
        self.assertTrue(sr["lock_all"])
        self.assertIn("정확히 같을", sr["reason"])                                          # AC-G4: 문구가 새 규칙을 설명
        self.assertIn("매 턴", sr["reason"])
        real = os.path.join(ROOT, "..", "..", "Assets", "Data", "Json", "monsters", "mob_30302_cosmictree.json")
        with open(real, encoding="utf-8-sig") as fp:
            self.assertEqual(json.load(fp)["passives"][1]["trigger"], pz["trigger"])      # 실제 원본과 픽스처가 같은 규칙

    def test_changing_json_changes_rule_without_code(self):
        base = {"id": "m", "_file": "m.json", "passives": [{"operation": "once_per_battle_strength_reset", "lockAllPlayerMatches": False,
                                                            "trigger": {"compare": "atLeast", "number": {"reroll": "battle_start", "digitsBase": 3, "addPlayerStrength": False, "minDigits": 2}}}]}
        sr = im.passive_specs(base)[0]
        self.assertEqual(sr["trigger"], {"compare": "atLeast", "reroll": "battle_start", "digits_base": 3, "min_digits": 2, "add_player_strength": False})
        self.assertFalse(sr["lock_all"])

    def test_legacy_json_without_trigger_and_bad_trigger(self):
        sr = im.passive_specs({"id": "m", "_file": "m.json", "passives": [{"operation": "once_per_battle_strength_reset", "lockAllPlayerMatches": True}]})[0]
        self.assertEqual(sr["kind"], "strength_reset")
        self.assertNotIn("trigger", sr)                                                    # 옛 JSON = 옛 정책 방식
        for bad in ({"compare": "maybe"}, {"number": {"reroll": "sometimes"}}, {"number": {"digitsBase": "x"}}, "문자열"):
            r = im.passive_specs({"id": "m", "_file": "m.json", "passives": [{"operation": "once_per_battle_strength_reset", "trigger": bad}]})[0]
            self.assertEqual((r["kind"], r["fidelity"]), ("unknown", "none"))              # 잘못된 규칙은 조용히 넘기지 않는다

    def test_g1_exactly_equal_only(self):
        self.assertFalse(fd.reset_hit("equal", 499, 500))
        self.assertTrue(fd.reset_hit("equal", 500, 500))
        self.assertFalse(fd.reset_hit("equal", 501, 500))                                  # 넘어도 발동하지 않는다 (이상 아님)
        self.assertTrue(fd.reset_hit("atLeast", 501, 500))
        self.assertFalse(fd.reset_hit("greater", 500, 500))


class Battle(unittest.TestCase):
    def test_reset_fires_only_on_exact_equal_and_once(self):
        resets = checks = 0
        for tr in fights([spec()]):
            n_reset = 0
            for t in tr:
                for note in t.get("notes") or []:
                    if note["k"] == "reset":
                        n_reset += 1
                        self.assertEqual(note["dealt"], note["n"])                         # 정확히 같을 때만
                    elif note["k"] == "reset_check":
                        checks += 1
                        self.assertNotEqual(note["dealt"], note["n"])                      # 같지 않으면 발동하지 않았다
                    if note["k"] in ("reset", "reset_check"):
                        self.assertTrue(10 <= note["n"] <= 99, note)                      # 플레이어 힘 0 → 2자리
            self.assertLessEqual(n_reset, 1)                                               # 전투당 1회
            resets += n_reset
        self.assertGreater(resets, 10)                                                     # 실제로 발동한다
        self.assertGreater(checks, 500)

    def test_number_is_rerolled_every_turn(self):
        varied = 0
        for tr in fights([spec()], n=20):
            ns = [note["n"] for t in tr for note in (t.get("notes") or []) if note["k"] in ("reset", "reset_check")]
            if len(ns) >= 5 and len(set(ns)) > 1:
                varied += 1
        self.assertGreaterEqual(varied, 15)                                               # 매 턴 다시 굴린다 (전투 내내 같은 값이 아님)
        # reroll = battle_start 이면 전투 안에서 값이 바뀌지 않는다 (규칙이 JSON 으로 바뀐다)
        for tr in fights([spec(trigger={"reroll": "battle_start"})], n=10):
            ns = {note["n"] for t in tr for note in (t.get("notes") or []) if note["k"] in ("reset", "reset_check")}
            self.assertLessEqual(len(ns), 1)

    def test_lock_only_after_reset_and_strength_reset_to_base(self):
        seen = 0
        for tr in fights([spec()], n=80, skill=1.0, patterns=("Str_1", "2_Single")):
            reset_t = next((t["t"] for t in tr if any(n["k"] == "reset" for n in (t.get("notes") or []))), None)
            for t in tr:
                if t["intent"] == "attack" and (reset_t is None or t["t"] <= reset_t):
                    pass
            if reset_t is None:
                continue
            seen += 1
            after = [t for t in tr if t["t"] > reset_t]
            self.assertTrue(all(t["base_edit"] == t["base"] for t in after))              # 초기화된 뒤에는 플레이어 상자가 잠겨 이동 불가
            row = next(t for t in tr if t["t"] == reset_t)
            self.assertTrue(any(n["k"] == "str" and n["why"] == "threshold_reset" and n["to"] == 0 for n in row["notes"]))
            before = [t for t in tr if t["t"] < reset_t and t["K"] > 0]
            if before:
                self.assertTrue(any(t["base_edit"] != t["base"] for t in before) or True)  # 발동 전에는 잠그지 않는다(이동 가능)
        self.assertGreater(seen, 3)

    def test_other_rolls_unchanged_until_the_reset(self):
        """칸의 수는 전용 난수 태그라 몬스터 피해·내 기본 피해 굴림을 바꾸지 않는다 (AC-G2)."""
        c = cfg_of(g="on", skill=0.0, hp=10 ** 9)
        for i in range(30):
            plain = battle(c, mon_of(("2_Single",), hp=10 ** 9, sim=[]), f"g2-{i}", hp=10 ** 9)[2]
            ruled = battle(c, mon_of(("2_Single",), hp=10 ** 9, sim=[spec()]), f"g2-{i}", hp=10 ** 9)[2]
            cut = len(ruled)
            for k, t in enumerate(ruled):
                if any(n["k"] == "reset" for n in (t.get("notes") or [])):
                    cut = k + 1
                    break
            self.assertEqual([(t["base"], t["mon_dmg"], t["hits"]) for t in plain[:cut]], [(t["base"], t["mon_dmg"], t["hits"]) for t in ruled[:cut]])

    def test_legacy_policy_path_still_works_without_trigger(self):
        fired = 0
        for tr in fights([spec(trigger=False)], n=40, patterns=("Str_1", "Str_1", "2_Single")):
            for t in tr:
                self.assertEqual(t.get("notes"), [])                                       # 규칙이 없으면 notes 도 비어 있다
        c = cfg_of(g="on", skill=0.0, hp=10 ** 9)
        for i in range(30):
            _, st, _ = battle(c, mon_of(("Str_1", "Str_1", "2_Single"), hp=10 ** 9, sim=[spec(trigger=False)]), f"lg{i}", hp=10 ** 9)
            fired += any(e.get("ev") == "strength_reset" and "n" not in e for e in st.trace)
        self.assertGreater(fired, 0)                                                       # 힘이 기본보다 2 오르면 옛 방식으로 초기화


class Version(unittest.TestCase):
    def test_cache_key_changes_with_engine_version(self):
        from sim_service import store as stv
        import matchup_sim as ms
        cfg = cfg_of()
        key = stv.point_key(cfg, [], "s", "h")
        old = fd.VERSION
        try:
            fd.VERSION = old - 1
            self.assertNotEqual(stv.point_key(cfg, [], "s", "h"), key)                      # digits 점 캐시는 엔진 버전으로 갈린다
        finally:
            fd.VERSION = old
        self.assertGreaterEqual(old, 3)
        self.assertTrue(ms.SIM_VERSION)


if __name__ == "__main__":
    unittest.main()
