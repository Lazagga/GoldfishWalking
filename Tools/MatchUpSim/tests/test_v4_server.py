# -*- coding: utf-8 -*-
"""v4 서버: AC-K9 (기믹 값 편집 → 원본 반영 → 재임포트 라운드트립, diff 는 숫자 토큰 하나),
digits 모델 전환(cfg_set), monster_probe 의 gauss↔digits 비교, AC-M3/D6 의 '시뮬 미반영' 정보.
모든 쓰기는 임시 폴더의 fixtures 사본에만 한다."""
import json
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)

from test_server import Sandbox, read_all  # noqa: E402

VAMP = "Mob_30201_Vampire"


class V4Server(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sb = Sandbox(xs="1.0:1.0:1", runs="100", stages="100", table_model=True)

    @classmethod
    def tearDownClass(cls):
        cls.sb.stop()
        cls.sb.cleanup()

    def done(self, body):
        jid = self.sb.job(body)
        ev = self.sb.events(jid, until=lambda e: e.get("type") in ("done", "error", "cancelled"))
        self.assertEqual(ev[-1]["type"], "done", ev[-1])
        return ev

    def test_k9_gimmick_roundtrip(self):
        sb = self.sb
        mons = sb.req("GET", "/api/monsters")[1]
        self.assertIn("rate", mons["gimmick_schema"])
        self.assertTrue(mons["sim_reflected_by_model"]["digits"]["digits"])
        self.assertFalse(mons["sim_reflected_by_model"]["gauss"]["digits"])
        m = next(x for x in mons["monsters"] if x["id"] == VAMP)
        gi = next(i for i, s in enumerate(m["sim"]) if s["kind"] == "lifesteal")
        self.assertEqual(m["sim"][gi]["rate"], 0.3)
        before = read_all(sb.mon)
        edit = {"target": "gimmick", "mid": VAMP, "gi": gi, "key": "rate", "old": 0.3, "new": 0.45}
        s, pv = sb.req("POST", "/api/apply/preview", {"edits": [edit]})
        self.assertEqual(s, 200, pv)
        self.assertEqual(list(pv["files"]), ["monsters/mob_30201_vampire.json"])
        rows = pv["files"]["monsters/mob_30201_vampire.json"]["rows"]
        self.assertEqual([(r["token_old"], r["token_new"]) for r in rows], [("0.3", "0.45")])
        s, r = sb.req("POST", "/api/apply", {"edits": [edit]})
        self.assertEqual(s, 200, r)
        self.assertEqual(r["roundtrip_mismatch"], [])
        after = read_all(sb.mon)
        changed = [k for k in after if after[k] != before[k]]
        self.assertEqual(changed, ["mob_30201_vampire.json"])
        a, b = before[changed[0]], after[changed[0]]
        self.assertEqual(a.replace(b'"ratio":  0.3', b'"ratio":  0.45'), b)     # 숫자 토큰 하나만
        with open(sb.mtable, encoding="utf-8") as fp:
            mt = json.load(fp)
        mv = next(x for x in mt["monsters"] if x["id"] == VAMP)
        self.assertEqual(mv["sim"][gi]["rate"], 0.45)
        s, r2 = sb.req("POST", "/api/apply/revert", {})
        self.assertEqual(s, 200, r2)
        self.assertEqual(read_all(sb.mon), before)

    def test_digits_switch_and_probe_compare(self):
        sb = self.sb
        ev = self.done({"kind": "recompute", "edits": [], "fids": ["fan_turn_boots"],
                        "cfg_set": {"monsters.damage_model": "digits", "monsters.gimmicks": "on"}})
        plan = next(e for e in ev if e["type"] == "plan")
        pts = [e for e in ev if e["type"] == "point" and e["series"] == "after"]
        self.assertTrue(pts)
        self.assertTrue(plan["ghost"])          # 설정 전환 → 수정 전 = 기준(gauss) 고스트
        befores = [e for e in ev if e["type"] == "point" and e["series"] == "before"]
        self.assertTrue(befores)
        # 다른 모델이므로 기준선 승률이 같지 않다 (같을 수도 있지만 이 시드에서는 다름)
        b_after = next(e["point"]["win_rate"] for e in pts if e["fid"] == "__baseline__")
        b_before = next(e["point"]["win_rate"] for e in befores if e["fid"] == "__baseline__")
        self.assertNotEqual(b_after, b_before)
        # 허용 목록 밖 값은 거부
        s, j = sb.req("POST", "/api/jobs", {"kind": "recompute", "edits": [], "cfg_set": {"monsters.damage_model": "evil"}})
        if s == 200:
            ev = sb.events(j["id"], until=lambda e: e.get("type") in ("done", "error", "cancelled"))
            self.assertEqual(ev[-1]["type"], "error")
        ev = self.done({"kind": "monster_probe", "mid": "Mob_10101_Fairy", "n": 200, "edits": [], "compare_models": True,
                        "gimmicks": "on"})
        res = ev[-1]["result"]
        g, d = res["models"]["gauss"], res["models"]["digits"]
        self.assertEqual((g["damage_model"], d["damage_model"]), ("gauss", "digits"))
        self.assertNotEqual(g["avg_taken"], d["avg_taken"])
        # 패턴 편집(2_Single → 3_Single 자릿수)이 digits 에서 받는 피해를 키운다 (AC-D6)
        mons = sb.req("GET", "/api/monsters")[1]
        fairy = next(x for x in mons["monsters"] if x["id"] == "Mob_10101_Fairy")
        k = next(i for i, p in enumerate(fairy["patterns"]) if p["key"] == "2_Single")
        ed = {"target": "pattern", "mid": "Mob_10101_Fairy", "step": k, "key": "digits", "old": 2, "new": 3}
        ev = self.done({"kind": "monster_probe", "mid": "Mob_10101_Fairy", "n": 300, "edits": [ed],
                        "cfg_set": {"monsters.damage_model": "digits"}})
        r = ev[-1]["result"]
        self.assertGreater(r["after"]["avg_taken"] / max(1, r["after"]["avg_turns"]),
                           2 * r["before"]["avg_taken"] / max(1, r["before"]["avg_turns"]))


if __name__ == "__main__":
    unittest.main()
