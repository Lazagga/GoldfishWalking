# -*- coding: utf-8 -*-
"""v4 §6.8 비교 기준 스냅샷과 JSON 편집 고스트: AC-R1 ~ AC-R4 (AC-R5 UI 는 test_v4_ui.py).
모든 쓰기는 임시 폴더의 fixtures 사본에만 한다."""
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)

from sim_service import store as st  # noqa: E402
from sim_service.jobs import BASE  # noqa: E402
from test_server import Sandbox, read_all  # noqa: E402

SCY = "fan_damage_scythe"
MON = "Mob_10101_Fairy"


def points(evs):
    """마지막 단계의 점: {(series, fid, x): point}"""
    out = {}
    for e in evs:
        if e.get("type") == "point":
            out[(e["series"], e["fid"], e["x"])] = e["point"]
    return out


def strip(p):
    return {k: v for k, v in p.items() if k not in ("stage",)}


class Reference(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sb = Sandbox(xs="500:700:200", runs="200", stages="200")

    @classmethod
    def tearDownClass(cls):
        cls.sb.stop()
        cls.sb.cleanup()

    def setUp(self):
        for k, i in list(self.sb.app.overlay.work):
            self.sb.req("POST", f"/api/files/{k}/{i}/revert", {})
        self.sb.req("POST", "/api/reference/pin", {"source": "disk"})

    def run_job(self, body):
        jid = self.sb.job({"kind": "recompute", **body})
        evs = self.sb.events(jid, until=lambda e: e.get("type") in ("done", "error", "cancelled"))
        self.assertEqual(evs[-1]["type"], "done", evs[-1])
        return evs

    def text(self, kind="fantasy", fid=SCY):
        return self.sb.req("GET", f"/api/files/{kind}/{fid}")[1]["text"]

    def put(self, text, kind="fantasy", fid=SCY):
        s, j = self.sb.req("PUT", f"/api/files/{kind}/{fid}", {"text": text})
        self.assertEqual(s, 200, j)
        self.assertTrue(j["saved"], j)
        return j

    # --- AC-R1
    def test_r1_json_equals_numeric(self):
        sb = self.sb
        old = next(e for e in sb.app.table_data["fantasies"] if e["id"] == SCY)["effects"][0]["value"]
        # 편집 전 캐시 점 (기준 = 현재)
        base = points(self.run_job({"edits": [], "fids": [SCY]}))
        # (a) 숫자 UI
        ev_a = self.run_job({"edits": [{"fid": SCY, "effect": 0, "key": "value", "old": old, "new": 1}], "fids": [SCY]})
        a = points(ev_a)
        plan_a = next(e for e in ev_a if e["type"] == "plan")
        # (b) JSON 탭 편집
        t = self.text()
        j = self.put(t.replace('"amount":  %s' % ("%.1f" % old), '"amount":  1.0'))
        self.assertTrue(j["sim_changed"])
        self.assertEqual(j["reference"]["changed"]["fantasies"], [SCY])
        self.assertFalse(j["reference"]["same"])
        ev_b = self.run_job({"edits": [], "fids": [SCY]})
        b = points(ev_b)
        plan_b = next(e for e in ev_b if e["type"] == "plan")
        self.assertEqual(plan_b["edited"], [SCY])
        self.assertTrue(plan_b["ghost"])
        self.assertEqual(plan_a["data_hash"], plan_b["data_hash"])
        self.assertEqual(set(a), set(b))
        for k in a:
            self.assertEqual(strip(a[k]), strip(b[k]), k)       # 수정 후·수정 전·수정 효과 비트 단위 동일
        for x in sb.app.x_values:
            for fid in (SCY, BASE):
                bp = strip(b[("before", fid, x)])
                cp_ = strip(base[("after", fid, x)])
                self.assertEqual(bp["layer"], "reference")
                self.assertEqual(cp_["layer"], "current")
                bp.pop("layer"), cp_.pop("layer")
                self.assertEqual(bp, cp_)                         # 수정 전 = 편집 전 캐시 점
            self.assertIn("edit_effect", b[("after", SCY, x)])

    # --- AC-R2
    def test_r2_whitespace_and_monster_scope(self):
        sb = self.sb
        self.run_job({"edits": [], "fids": [SCY]})
        t = self.text()
        j = self.put(t.replace('"rarity":  "blue"', '"rarity":"blue"').replace('"designerNote"', '"designerNote" '))
        self.assertFalse(j["sim_changed"])
        self.assertTrue(j["reference"]["same"])
        self.assertEqual(j["reference"]["changed"], {"fantasies": [], "monsters": [], "patterns": [], "cfg_keys": []})
        n0 = sb.app.engine.runs_computed
        ev = self.run_job({"edits": [], "fids": [SCY]})
        self.assertFalse(next(e for e in ev if e["type"] == "plan")["ghost"])
        self.assertEqual(sb.app.engine.runs_computed, n0)        # 새로 계산한 점 0개
        # tier_avg 모델에서는 몬스터 JSON 편집이 시뮬 값을 바꾸지 않는다 (변경 집합에는 보임)
        mt = self.text("monster", MON)
        j = self.put(mt.replace('"health":  150', '"health":  180'), "monster", MON)
        self.assertEqual(j["reference"]["changed"]["monsters"], [MON])
        self.assertFalse(j["sim_changed"])

    # --- AC-R3
    def test_r3_lifetime(self):
        sb = self.sb
        before_bytes = read_all(sb.src)
        t = self.text()
        self.put(t.replace('"amount":  20.0', '"amount":  7.0'))
        info = sb.req("GET", "/api/reference")[1]
        self.assertFalse(info["same"])
        self.assertEqual(info["source"], "disk")
        # 기준 다시 잡기 → 고스트 해제
        info = sb.req("POST", "/api/reference/pin", {})[1]
        self.assertTrue(info["same"])
        self.assertEqual(info["source"], "pinned")
        # 편집 되돌리기 (기준 = 디스크) → 같아짐
        sb.req("POST", "/api/reference/pin", {"source": "disk"})
        self.assertFalse(sb.req("GET", "/api/reference")[1]["same"])
        sb.req("POST", f"/api/files/fantasy/{SCY}/revert", {})
        self.assertTrue(sb.req("GET", "/api/reference")[1]["same"])
        # 원본 반영 → 기준 갱신
        self.put(t.replace('"amount":  20.0', '"amount":  7.0'))
        s, r = sb.req("POST", "/api/apply", {"edits": []})
        self.assertEqual(s, 200, r)
        info = sb.req("GET", "/api/reference")[1]
        self.assertTrue(info["same"])
        self.assertFalse(info["stale"])
        s, r = sb.req("POST", "/api/apply/revert", {})
        self.assertEqual(s, 200, r)
        self.assertEqual(read_all(sb.src), before_bytes)
        self.assertTrue(sb.req("GET", "/api/reference")[1]["same"])
        # 외부 변경 → 기준이 오래됨
        p = os.path.join(sb.src, "fan_damage_scythe.json")
        with open(p, "rb") as fp:
            raw = fp.read()
        try:
            with open(p, "wb") as fp:
                fp.write(raw.replace(b'"amount":  20.0', b'"amount":  21.0'))
            info = sb.req("GET", "/api/reference")[1]
            self.assertTrue(info["stale"])
            self.assertIn("fantasy/" + SCY, info["stale_files"])
        finally:
            with open(p, "wb") as fp:
                fp.write(raw)
        self.assertFalse(sb.req("GET", "/api/reference")[1]["stale"])

    # --- AC-R4
    def test_r4_cache_protect(self):
        sb = self.sb
        self.run_job({"edits": [], "fids": [SCY]})                 # 현재(=기준) 점
        t = self.text()
        self.put(t.replace('"amount":  20.0', '"amount":  2.0'))
        other = sb.app.data_hash
        self.run_job({"edits": [], "fids": [SCY]})                 # 다른 해시의 점 + 고스트(캐시 적중)
        sb.req("POST", f"/api/files/fantasy/{SCY}/revert", {})
        s, r = sb.req("POST", "/api/cache/prune", {"max_mb": 0})
        self.assertEqual(s, 200, r)
        self.assertGreater(r["removed"], 0)
        self.assertGreater(r["kept_protected"], 0)
        self.assertIn(sb.app.data_hash, r["protected"])
        self.assertNotIn(other, r["protected"])
        n0 = sb.app.engine.runs_computed
        self.run_job({"edits": [], "fids": [SCY]})
        self.assertEqual(sb.app.engine.runs_computed, n0)        # 현재·기준 캐시는 남아 있음
        # 다른 해시의 점은 지워져 다시 계산된다
        remaining = set()
        for dp, _, fs_ in os.walk(sb.app.store.root):
            for f in fs_:
                if f.endswith(".json.gz"):
                    remaining.add(f)
        self.assertTrue(remaining)
        # store 수준 확인
        recs = [sb.app.store.load(f[:-8]) for f in remaining]
        self.assertTrue(all(r_ is None or r_["data_hash"] in r["protected"] for r_ in recs))


class ReferenceTableModel(unittest.TestCase):
    """AC-R2 후반: monsters.model = table 에서 몬스터 JSON 편집은 기준선과 선택 항목에만 고스트."""
    @classmethod
    def setUpClass(cls):
        cls.sb = Sandbox(xs="1.0:1.0:1", runs="100", stages="100", table_model=True)

    @classmethod
    def tearDownClass(cls):
        cls.sb.stop()
        cls.sb.cleanup()

    def test_r2_monster_scope(self):
        sb = self.sb
        mt = sb.req("GET", f"/api/files/monster/{MON}")[1]["text"]
        self.assertIn('"health":  150', mt)
        s, j = sb.req("PUT", f"/api/files/monster/{MON}", {"text": mt.replace('"health":  150', '"health":  180')})
        self.assertTrue(j["saved"], j)
        self.assertTrue(j["sim_changed"])
        self.assertEqual(j["reference"]["changed"]["monsters"], [MON])
        self.assertEqual(j["reference"]["changed"]["fantasies"], [])
        jid = sb.job({"kind": "recompute", "edits": [], "fids": [SCY]})
        ev = sb.events(jid, until=lambda e: e.get("type") in ("done", "error", "cancelled"))
        self.assertEqual(ev[-1]["type"], "done", ev[-1])
        plan = next(e for e in ev if e["type"] == "plan")
        self.assertEqual(plan["edited"], [])
        self.assertTrue(plan["ghost"])
        pts = points(ev)
        befores = {k for k in pts if k[0] == "before"}
        self.assertTrue(befores)
        self.assertEqual({k[1] for k in befores}, {BASE, SCY})    # 고스트 = 기준선 + 선택 항목
        self.assertTrue(all("edit_effect" in pts[("after", SCY, x)] for x in sb.app.x_values))
        sb.req("POST", f"/api/files/monster/{MON}/revert", {})


if __name__ == "__main__":
    unittest.main()
