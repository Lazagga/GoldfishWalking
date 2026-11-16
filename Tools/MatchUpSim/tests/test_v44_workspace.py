# -*- coding: utf-8 -*-
"""v4.4 F14 작업 상태 서버 저장 — 서버 수준 (AC-W2·W4·W5·W6·W7·W8·W13) 과 API 규칙.

서버를 껐다 켜는 시나리오는 Sandbox(reuse=...) 로 같은 임시 폴더에서 새 서버를 띄운다.
테스트는 fixtures 사본만 쓴다 (실제 Assets/ 쓰기는 MATCHUPSIM_FORBID_PATH 가드가 막는다).
"""
import json
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)

from test_server import Sandbox  # noqa: E402

BOOTS = "fan_turn_boots"


def boots_old(sb):
    s, fj = sb.req("GET", "/api/fantasies")
    e = next(f for f in fj["fantasies"] if f["id"] == BOOTS)
    return e["effects"][0]["value"]


def note_edit(sb, note="ws test"):
    """JSON 편집기(PUT /api/files)로 작업 사본을 고친다 — 디스크는 그대로."""
    s, info = sb.req("GET", f"/api/files/fantasy/{BOOTS}")
    obj = json.loads(info["text"])
    obj["designerNote"] = note
    s, r = sb.req("PUT", f"/api/files/fantasy/{BOOTS}", {"text": json.dumps(obj, ensure_ascii=False, indent=4)})
    assert s == 200 and r["saved"], r
    return r


def restart(sb):
    sb.stop()
    return Sandbox(reuse=sb.tmp)


class WorkspaceApi(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sb = Sandbox(xs="500:700:200", runs="30", stages="20,30")

    @classmethod
    def tearDownClass(cls):
        cls.sb.stop()
        cls.sb.cleanup()

    def test_empty_then_put_get(self):
        s, w = self.sb.req("GET", "/api/workspace")
        self.assertEqual(s, 200)
        self.assertFalse(w["exists"])
        st = {"schema": 1, "edits": [], "cfg_edits": [], "cfg_set": {}, "view": {"tab": "rank"}, "held": []}
        s, r = self.sb.req("PUT", "/api/workspace", {"rev": 0, "client": "A", "state": st})
        self.assertEqual((s, r["rev"]), (200, 1))
        s, w = self.sb.req("GET", "/api/workspace")
        self.assertTrue(w["exists"])
        self.assertEqual(w["state"]["view"], {"tab": "rank"})
        self.assertEqual(w["updated_by"], "A")
        self.sb.req("DELETE", "/api/workspace")

    def test_rev_conflict_and_force(self):
        self.sb.req("DELETE", "/api/workspace")
        s, w = self.sb.req("GET", "/api/workspace")
        rev = w["rev"]
        s, r1 = self.sb.req("PUT", "/api/workspace", {"rev": rev, "client": "A", "state": {"view": {"tab": "a"}}})
        self.assertEqual(s, 200)
        s, r2 = self.sb.req("PUT", "/api/workspace", {"rev": rev, "client": "B", "state": {"view": {"tab": "b"}}})   # 옛 rev
        self.assertEqual(s, 409)
        self.assertEqual(r2["state"]["view"], {"tab": "a"})                                                          # 서버 값을 돌려줌
        self.assertEqual(r2["rev"], r1["rev"])
        s, r3 = self.sb.req("PUT", "/api/workspace", {"rev": rev, "client": "B", "state": {"view": {"tab": "b"}}, "force": True})
        self.assertEqual(s, 200)
        self.assertEqual(r3["rev"], r1["rev"] + 1)

    def test_server_owned_keys_ignored(self):
        s, w = self.sb.req("GET", "/api/workspace")
        s, r = self.sb.req("PUT", "/api/workspace", {"rev": w["rev"], "client": "A", "state": {
            "view": {}, "file_edits": [{"kind": "fantasy", "id": BOOTS, "base_sha1": "x", "new_text": "{}"}],
            "reference": {"source": "pinned", "pinned_file": "../../evil"}}})
        s, w = self.sb.req("GET", "/api/workspace")
        self.assertEqual(w["state"]["file_edits"], [])                                    # 뷰어가 보낸 file_edits 는 무시
        self.assertEqual(w["state"]["reference"]["source"], "disk")

    def test_history_and_restore(self):
        self.sb.req("DELETE", "/api/workspace")
        s, w = self.sb.req("GET", "/api/workspace")
        s, r = self.sb.req("PUT", "/api/workspace", {"rev": w["rev"], "client": "A", "state": {"view": {"tab": "keep"}, "edits": []}})
        self.sb.req("DELETE", "/api/workspace")                                           # 초기화 → 이전 파일이 history 로
        s, h = self.sb.req("GET", "/api/workspace/history")
        self.assertGreaterEqual(len(h["history"]), 1)
        keep = next(x for x in h["history"] if x["rev"] == r["rev"])
        s, rr = self.sb.req("POST", f"/api/workspace/history/{keep['id']}/restore", {})
        self.assertEqual(s, 200)
        s, w = self.sb.req("GET", "/api/workspace")
        self.assertEqual(w["state"]["view"], {"tab": "keep"})
        self.assertEqual(self.sb.req("POST", "/api/workspace/history/..%2F..%2Fx/restore", {})[0], 400)

    def test_auth_and_size(self):
        self.assertEqual(self.sb.req("GET", "/api/workspace", token=False)[0], 403)
        self.assertEqual(self.sb.req("PUT", "/api/workspace", {"rev": 0, "state": {}}, token="wrong")[0], 403)
        self.assertEqual(self.sb.req("PUT", "/api/workspace", b"x", ctype="text/plain")[0], 415)
        self.assertEqual(self.sb.req("PUT", "/api/workspace", {"rev": 0, "state": "문자열"})[0], 400)


class WorkspacePersistence(unittest.TestCase):
    def setUp(self):
        self.sb = Sandbox(xs="500:700:200", runs="30", stages="20,30")

    def tearDown(self):
        self.sb.stop()
        self.sb.cleanup()

    def test_w2_file_edits_survive_restart(self):
        sb = self.sb
        note_edit(sb)
        s, st0 = sb.req("GET", "/api/state")
        self.assertEqual([(d["kind"], d["id"]) for d in st0["dirty_files"]], [("fantasy", BOOTS)])
        sb = self.sb = restart(sb)
        s, st1 = sb.req("GET", "/api/state")
        self.assertEqual(st1["dirty_files"], st0["dirty_files"])
        self.assertEqual(st1["data_hash"], st0["data_hash"])
        s, info = sb.req("GET", f"/api/files/fantasy/{BOOTS}")
        self.assertIn("ws test", info["text"])
        self.assertTrue(info["dirty"])

    def test_w4_file_conflict_is_held_not_lost(self):
        sb = self.sb
        note_edit(sb)
        path = os.path.join(sb.src, "fan_turn_boots.json")
        sb.stop()
        with open(path, "rb") as fp:
            raw = fp.read()
        with open(path, "wb") as fp:                                                      # 서버 밖에서 원본을 고침
            fp.write(raw + b"\n")
        sb = self.sb = Sandbox(reuse=sb.tmp)
        s, st = sb.req("GET", "/api/state")
        self.assertEqual(st["dirty_files"], [])                                           # 복원하지 않음
        s, w = sb.req("GET", "/api/workspace")
        held = [h for h in w["restore"]["held"] if h["type"] == "file"]
        self.assertEqual(len(held), 1)
        self.assertEqual(held[0]["item"]["id"], BOOTS)                                    # 조용히 사라지지 않고 보류
        self.assertIn("ws test", held[0]["item"]["new_text"])

    def test_w4_edit_conflicts_split_into_held(self):
        sb = self.sb
        old = boots_old(sb)
        good = {"fid": BOOTS, "effect": 0, "key": "value", "old": old, "new": old + 1}
        bad = {"fid": BOOTS, "effect": 0, "key": "value", "old": old + 99, "new": 1}
        gone = {"fid": "fan_not_exist", "effect": 0, "key": "value", "old": 1, "new": 2}
        s, w = sb.req("GET", "/api/workspace")
        sb.req("PUT", "/api/workspace", {"rev": w["rev"], "client": "A", "state": {
            "edits": [good, bad, gone], "cfg_edits": [{"path": "no.such.key", "old": 1, "new": 2}],
            "cfg_set": {"sim.nope": "x"}, "view": {}, "held": []}})
        s, w = sb.req("GET", "/api/workspace")
        r = w["restore"]
        self.assertEqual(r["edits"], [good])
        self.assertEqual(sorted(h["type"] for h in r["held"]), ["cfg_edit", "cfg_set", "edit", "edit"])
        self.assertEqual(len(r["edits"]) + len([h for h in r["held"] if h["type"] == "edit"]), 3)   # 3개 모두 어디엔가 있음

    def test_w5_apply_clears_file_edits(self):
        sb = self.sb
        note_edit(sb)
        s, w = sb.req("GET", "/api/workspace")
        self.assertEqual(len(w["state"]["file_edits"]), 1)
        s, r = sb.req("POST", "/api/apply", {"edits": []})
        self.assertEqual(s, 200, r)
        s, w = sb.req("GET", "/api/workspace")
        self.assertEqual(w["state"]["file_edits"], [])                                    # 반영 뒤 새로고침해도 되살아나지 않음

    def test_w6_reference_pin_survives_restart(self):
        sb = self.sb
        note_edit(sb)
        s, ref0 = sb.req("POST", "/api/reference/pin", {"source": "pinned"})
        self.assertEqual(ref0["source"], "pinned")
        sb = self.sb = restart(sb)
        s, ref1 = sb.req("GET", "/api/reference")
        self.assertEqual(ref1["source"], "pinned")
        self.assertEqual(ref1["ref_hash"], ref0["ref_hash"])
        s, _ = sb.req("POST", "/api/reference/pin", {"source": "disk"})                   # 디스크 기준으로 되돌리면 핀 파일도 정리
        names = os.listdir(sb.app.workspace_dir)
        self.assertFalse([n for n in names if n.startswith("reference_")])

    def test_w7_revert_apply_after_restart(self):
        sb = self.sb
        old = boots_old(sb)
        s, r = sb.req("POST", "/api/apply", {"edits": [{"fid": BOOTS, "effect": 0, "key": "value", "old": old, "new": old + 1}]})
        self.assertEqual(s, 200, r)
        sb = self.sb = restart(sb)
        s, st = sb.req("GET", "/api/state")
        self.assertTrue(st["last_apply"])                                                 # 아직 덮어쓰이지 않았으니 되살아남
        s, rv = sb.req("POST", "/api/apply/revert", {})
        self.assertEqual(s, 200, rv)
        self.assertAlmostEqual(boots_old(sb), old)

    def test_w7_revert_refused_when_file_changed(self):
        sb = self.sb
        old = boots_old(sb)
        sb.req("POST", "/api/apply", {"edits": [{"fid": BOOTS, "effect": 0, "key": "value", "old": old, "new": old + 1}]})
        sb.stop()
        path = os.path.join(sb.src, "fan_turn_boots.json")
        with open(path, "ab") as fp:
            fp.write(b"\n")
        sb = self.sb = Sandbox(reuse=sb.tmp)
        s, st = sb.req("GET", "/api/state")
        self.assertIsNone(st["last_apply"])                                               # 반영 뒤 파일이 바뀌었으면 되살리지 않음

    def test_w8_scenario_apply_record_keeps_data(self):
        sb = self.sb
        old = boots_old(sb)
        edit = {"fid": BOOTS, "effect": 0, "key": "value", "old": old, "new": old + 1}
        note_edit(sb)
        s, fe = sb.req("GET", "/api/workspace")
        s, sv = sb.req("POST", "/api/scenarios", {"name": "w8", "edits": [edit], "cfg_edits": [], "cfg_set": {"monsters.gimmicks": "off"},
                                                  "results": {"data_hash": "x"}})
        self.assertEqual(s, 200, sv)
        # 시나리오 파일에 file_edits 를 직접 넣어 두고(저장 대화상자가 넣는 것과 같은 모양) 반영
        sp = os.path.join(sb.scen, "w8.json")
        with open(sp, encoding="utf-8") as fp:
            scen = json.load(fp)
        scen["file_edits"] = [{"kind": "fantasy", "id": BOOTS, "base_sha1": "abc", "new_text": "{}"}]
        with open(sp, "w", encoding="utf-8") as fp:
            json.dump(scen, fp, ensure_ascii=False)
        s, r = sb.req("POST", "/api/apply", {"edits": [edit], "scenario": "w8"})
        self.assertEqual(s, 200, r)
        self.assertNotIn("scenario_update_error", r)
        with open(sp, encoding="utf-8") as fp:
            after = json.load(fp)
        self.assertTrue(after["applied"])                                                 # 반영 기록이 실제로 붙는다
        self.assertEqual(after["cfg_set"], {"monsters.gimmicks": "off"})                  # 설정 스위치·원문 편집은 그대로
        self.assertEqual(len(after["file_edits"]), 1)
        s, lst = sb.req("GET", "/api/scenarios")
        self.assertTrue(next(x for x in lst["scenarios"] if x["name"] == "w8")["applied"])

    def test_w8_scenario_update_error_reported(self):
        sb = self.sb
        old = boots_old(sb)
        edit = {"fid": BOOTS, "effect": 0, "key": "value", "old": old, "new": old + 1}
        sb.req("POST", "/api/scenarios", {"name": "w8b", "edits": [edit], "cfg_edits": []})
        with open(os.path.join(sb.scen, "w8b.json"), "w", encoding="utf-8") as fp:
            fp.write("{ 깨진 json")
        s, r = sb.req("POST", "/api/apply", {"edits": [edit], "scenario": "w8b"})
        self.assertEqual(s, 200, r)
        self.assertIn("scenario_update_error", r)                                         # 삼키지 않고 알림


if __name__ == "__main__":
    unittest.main()
