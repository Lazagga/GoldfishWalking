# -*- coding: utf-8 -*-
"""원본 반영 수락 기준 AC-W1~W5, W7. 실제 Assets 는 절대 쓰지 않는다 (fixtures 사본 + 쓰기 금지 가드)."""
import copy
import glob
import hashlib
import json
import os
import shutil
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
REPO = os.path.dirname(os.path.dirname(ROOT))
ASSETS = os.path.join(REPO, "Assets")
sys.path.insert(0, ROOT)
os.environ["MATCHUPSIM_FORBID_PATH"] = ASSETS  # AC-W7: 테스트 중 Assets 쓰기 시도는 예외

import import_fantasies  # noqa: E402
from sim_service import edits as ed  # noqa: E402
from sim_service import writeback as wb  # noqa: E402

FIXTURES = os.path.join(HERE, "fixtures", "fantasies")
OVERRIDES = os.path.join(ROOT, "fantasy_effects.overrides.json")


def assets_digest():
    h = hashlib.sha1()
    for p in sorted(glob.glob(os.path.join(ASSETS, "Data", "Json", "fantasies", "*.json"))):
        with open(p, "rb") as fp:
            h.update(fp.read())
    return h.hexdigest()


class Sandbox:
    def __init__(self):
        self.tmp = tempfile.TemporaryDirectory()
        t = self.tmp.name
        self.src = os.path.join(t, "fantasies")
        shutil.copytree(FIXTURES, self.src)
        self.ov = os.path.join(t, "overrides.json")
        shutil.copy(OVERRIDES, self.ov)
        self.effects = os.path.join(t, "fantasy_effects.json")
        self.backup = os.path.join(t, ".matchupsim_backup")
        self.reimport()
        self.wb = wb.WriteBack(self.src, self.ov, self.effects, self.backup)
        self.wb.snapshot()

    def reimport(self):
        import_fantasies.main(["--src", self.src, "--out", self.effects, "--overrides", self.ov, "--quiet"])
        with open(self.effects, encoding="utf-8") as fp:
            self.table = json.load(fp)
        return self.table

    def bytes_of(self, fn):
        with open(os.path.join(self.src, fn), "rb") as fp:
            return fp.read()

    def all_bytes(self):
        return {fn: self.bytes_of(fn) for fn in os.listdir(self.src)}

    def close(self):
        self.tmp.cleanup()


def new_value(old, sch):
    if sch["int"]:
        v = old + 1 if old + 1 <= sch["max"] else old - 1
        return int(v)
    step = 0.05 if sch["max"] <= 10 else 5
    v = round(old + step, 6)
    if v > sch["max"]:
        v = round(old - step, 6)
    if sch.get("min_exclusive") and v <= sch["min"]:
        v = round(old + step / 2, 6)
    return v


class WriteBackTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.assets_before = assets_digest()

    @classmethod
    def tearDownClass(cls):
        # AC-W7: 실제 원본은 바이트 단위로 그대로
        assert assets_digest() == cls.assets_before, "테스트가 Assets 원본을 바꿨음"

    def setUp(self):
        self.sb = Sandbox()

    def tearDown(self):
        self.sb.close()

    def linked_keys(self):
        out = []
        for f in self.sb.table["fantasies"]:
            info = ed.fantasy_edit_info(f)
            for k in info["editable_keys"]:
                if k["target"] == "source":
                    out.append((f["id"], k))
        return out

    def test_w1_roundtrip_every_linked_field(self):
        keys = self.linked_keys()
        self.assertGreaterEqual(len(keys), 45)
        for fid, k in keys:
            sb = self.sb
            before = sb.all_bytes()
            old = k["value"]
            new = new_value(old, k["schema"])
            edit = {"fid": fid, "effect": k["effect"], "key": k["key"], "old": old, "new": new}
            fn = k["src"]["file"]
            raw, bom, text = wb.read_source(os.path.join(sb.src, fn))
            s, e, old_tok, new_tok, _ = wb.plan_patch(text, k["src"], new)
            res = sb.wb.apply(sb.table, [edit], sb.reimport)
            self.assertEqual(res["roundtrip_mismatch"], [], f"{fid}.{k['key']}")
            after = sb.all_bytes()
            changed = [f for f in after if after[f] != before[f]]
            self.assertEqual(changed, [fn], f"{fid}: 바뀐 파일 {changed}")
            # 바이트 단위: 해당 토큰 하나만 바뀜
            pre = len(wb.BOM) * bom
            sb_ = pre + len(text[:s].encode("utf-8"))
            eb_ = pre + len(text[:e].encode("utf-8"))
            self.assertEqual(after[fn], before[fn][:sb_] + new_tok.encode() + before[fn][eb_:], f"{fid}.{k['key']}")
            # 재임포트된 시뮬 값 = 편집값
            ent = {x["id"]: x for x in sb.table["fantasies"]}[fid]
            self.assertTrue(ed.num_eq(ent["effects"][k["effect"]][k["key"]], new), f"{fid}.{k['key']}")
            # 되돌리기 → 원래 바이트
            sb.wb.revert(res["backup_dir"], sb.reimport)
            self.assertEqual(sb.all_bytes(), before)

    def test_w2_preserve_bom_crlf_number_style(self):
        sb = self.sb
        # BOM + LF 파일 만들기 (새총), CRLF 파일 확인 (싸인펜: 정수 amount 1)
        p = os.path.join(sb.src, "fan_damage_slingshot.json")
        raw = sb.bytes_of("fan_damage_slingshot.json").replace(b"\r\n", b"\n")
        with open(p, "wb") as fp:
            fp.write(wb.BOM + raw)
        pen = sb.bytes_of("fan_shop_pen.json")
        sb.reimport()
        sb.wb.snapshot()
        ents = {x["id"]: x for x in sb.table["fantasies"]}
        e1 = {"fid": "fan_damage_slingshot", "effect": 0, "key": "value",
              "old": ents["fan_damage_slingshot"]["effects"][0]["value"], "new": 25}
        e2 = {"fid": "fan_shop_pen", "effect": 0, "key": "value", "old": ents["fan_shop_pen"]["effects"][0]["value"], "new": 2}
        sb.wb.apply(sb.table, [e1, e2], sb.reimport)
        new1 = sb.bytes_of("fan_damage_slingshot.json")
        self.assertTrue(new1.startswith(wb.BOM))
        self.assertNotIn(b"\r\n", new1)
        self.assertIn(b'"amount":  25.0', new1)          # float 표기 유지
        self.assertEqual(new1.replace(b"25.0", b"30.0"), wb.BOM + raw)
        new2 = sb.bytes_of("fan_shop_pen.json")
        self.assertEqual(new2.count(b"\r\n"), pen.count(b"\r\n"))
        self.assertIn(b'"amount":  2', new2)
        self.assertNotIn(b'"amount":  2.0', new2)          # int 표기 유지
        self.assertEqual(new2.replace(b'"amount":  2', b'"amount":  1'), pen)

    def test_w3_external_change_rejected(self):
        sb = self.sb
        ent = {x["id"]: x for x in sb.table["fantasies"]}["fan_turn_boots"]
        edit = {"fid": "fan_turn_boots", "effect": 0, "key": "value", "old": ent["effects"][0]["value"], "new": 1}
        p = os.path.join(sb.src, "fan_turn_boots.json")
        with open(p, "ab") as fp:
            fp.write(b" ")  # 외부(Unity 편집기 등)에서 바뀜
        with self.assertRaises(wb.WriteBackError) as cm:
            sb.wb.apply(sb.table, [edit], sb.reimport)
        self.assertIn("fan_turn_boots.json", str(cm.exception))

    def test_w4_revert_refused_after_change(self):
        sb = self.sb
        ent = {x["id"]: x for x in sb.table["fantasies"]}["fan_damage_anchor"]
        before = sb.all_bytes()
        edit = {"fid": "fan_damage_anchor", "effect": 0, "key": "value", "old": ent["effects"][0]["value"], "new": -10}
        res = sb.wb.apply(sb.table, [edit], sb.reimport)
        with open(os.path.join(sb.src, "fan_damage_anchor.json"), "ab") as fp:
            fp.write(b"\n")
        with self.assertRaises(wb.WriteBackError):
            sb.wb.revert(res["backup_dir"], sb.reimport)
        # 원래대로 되돌린 뒤에는 복원 가능
        with open(os.path.join(sb.src, "fan_damage_anchor.json"), "rb") as fp:
            b = fp.read()
        with open(os.path.join(sb.src, "fan_damage_anchor.json"), "wb") as fp:
            fp.write(b[:-1])
        sb.wb.revert(res["backup_dir"], sb.reimport)
        self.assertEqual(sb.all_bytes(), before)

    def test_w5_override_edit_leaves_sources(self):
        sb = self.sb
        before = sb.all_bytes()
        ent = {x["id"]: x for x in sb.table["fantasies"]}["fan_rest_pillow"]
        self.assertEqual(ent["mapping"], "override")
        edit = {"fid": "fan_rest_pillow", "effect": 0, "key": "value", "old": ent["effects"][0]["value"], "new": 80}
        res = sb.wb.apply(sb.table, [edit], sb.reimport)
        self.assertEqual(res["files"], [])
        self.assertEqual(sb.all_bytes(), before)
        with open(sb.ov, encoding="utf-8") as fp:
            self.assertEqual(json.load(fp)["fan_rest_pillow"]["effects"][0]["value"], 80)
        ent = {x["id"]: x for x in sb.table["fantasies"]}["fan_rest_pillow"]
        self.assertEqual(ent["effects"][0]["value"], 80)

    def test_scenario_only_not_written(self):
        sb = self.sb
        before = sb.all_bytes()
        ent = {x["id"]: x for x in sb.table["fantasies"]}["fan_start_stamp"]
        edit = {"fid": "fan_start_stamp", "effect": 0, "key": "value", "old": ent["effects"][0]["value"], "new": 2}
        pv = sb.wb.preview(sb.table, [edit])
        self.assertEqual(pv["files"], {})
        self.assertEqual(len(pv["scenario_only"]), 1)
        with self.assertRaises(wb.WriteBackError):
            sb.wb.apply(sb.table, [edit], sb.reimport)
        self.assertEqual(sb.all_bytes(), before)

    def test_w7_forbidden_path_guard(self):
        with self.assertRaises(wb.WriteBackError):
            wb.atomic_write(os.path.join(ASSETS, "Data", "Json", "fantasies", "fan_turn_boots.json"), b"x", [ASSETS])

    def test_safe_child(self):
        for bad in ("../x.json", "..", "/etc/passwd", "C:\\Windows\\x.json", "sub/x.json", ""):
            with self.assertRaises(wb.WriteBackError):
                wb.safe_child(self.sb.src, bad)


if __name__ == "__main__":
    unittest.main()
