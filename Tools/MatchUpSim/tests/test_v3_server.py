# -*- coding: utf-8 -*-
"""v3 서버 수락 기준: JSON 편집기 AC-J1~J6, 몬스터 AC-M1~M5, 조합·불씨 작업, AC-E4(시나리오 호환), AC-W6 추가.
모든 쓰기는 임시 폴더의 fixtures 사본에만 한다."""
import copy
import json
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)

import matchup_sim as ms  # noqa: E402
from sim_service import monsters as mo  # noqa: E402
from sim_service import store as st  # noqa: E402
from test_server import Sandbox, read_all  # noqa: E402

BOOTS = "fan_turn_boots"


class JsonEditor(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sb = Sandbox()

    @classmethod
    def tearDownClass(cls):
        cls.sb.stop()
        cls.sb.cleanup()

    def setUp(self):   # 테스트마다 작업 사본을 비운다
        for k, i in list(self.sb.app.overlay.work):
            self.sb.req("POST", f"/api/files/{k}/{i}/revert", {})

    def get(self, kind=None, fid=BOOTS):
        s, j = self.sb.req("GET", f"/api/files/{kind or 'fantasy'}/{fid}")
        self.assertEqual(s, 200, j)
        return j

    def put(self, text, kind="fantasy", fid=BOOTS):
        return self.sb.req("PUT", f"/api/files/{kind}/{fid}", {"text": text})

    def test_j1_syntax(self):
        t = self.get()["text"]
        s, j = self.put(t.replace('"rarity":  "white",', '"rarity":  "white"'))   # 쉼표 누락
        self.assertEqual(s, 200)
        self.assertFalse(j["ok"])
        self.assertFalse(j["saved"])
        m = j["messages"][0]
        self.assertEqual((m["stage"], m["level"]), ("syntax", "error"))
        self.assertGreater(m["line"], 1)
        self.assertGreaterEqual(m["col"], 1)
        s, j = self.put(t.replace('"enabled":  true,', '"enabled":  true,\n    "enabled":  false,'))   # 중복 키
        self.assertFalse(j["ok"])
        self.assertIn("중복 키", j["messages"][0]["msg"])
        self.assertGreater(j["messages"][0]["line"], 1)
        s, j = self.put(t.replace('"amount":  2.0', '"amount":  NaN'))
        self.assertFalse(j["ok"])
        s, j = self.put(t.replace('"amount":  2.0', '"amount":  Infinity'))
        self.assertFalse(j["ok"])
        self.assertFalse(self.get()["dirty"])                 # 오류가 있으면 작업 사본이 바뀌지 않음
        s, pv = self.sb.req("POST", "/api/apply/preview", {"edits": []})
        self.assertEqual(pv["files"], {})                      # 반영할 것도 없음

    def test_j2_unchanged_save_keeps_bytes(self):
        before = read_all(self.sb.src)
        for fid in (BOOTS, "fan_damage_anchor", "fan_acquire_Candy"):
            info = self.get(fid=fid)
            s, j = self.put(info["text"], fid=fid)
            self.assertTrue(j["ok"] and j["saved"])
            self.assertFalse(self.get(fid=fid)["dirty"])
        s, pv = self.sb.req("POST", "/api/apply/preview", {"edits": []})
        self.assertEqual(pv["files"], {})
        # 고쳤다가 되돌린 텍스트도 원본 바이트와 같다 (BOM, CRLF/LF, 마지막 줄바꿈)
        ov = self.sb.app.overlay
        for fid in (BOOTS, "fan_damage_anchor"):
            d = ov.disk("fantasy", fid)
            self.assertEqual(ov.encode("fantasy", fid, d["text"]), d["raw"])
            changed = ov.encode("fantasy", fid, d["text"].replace("true", "false", 1))
            self.assertEqual(changed.count(b"\r\n"), d["raw"].count(b"\r\n"))
            self.assertEqual(changed.endswith(b"\n"), d["raw"].endswith(b"\n"))
        self.assertEqual(read_all(self.sb.src), before)

    def test_j3_sync_and_j4_roundtrip(self):
        sb = self.sb
        before = read_all(sb.src)
        tab = {e["id"]: e for e in sb.app.table_data["fantasies"]}
        edit = {"fid": BOOTS, "effect": 0, "key": "value", "old": tab[BOOTS]["effects"][0]["value"], "new": 4}
        # 숫자 편집이 JSON 보기에 반영
        s, v = sb.req("POST", f"/api/files/fantasy/{BOOTS}/view", {"edits": [edit]})
        self.assertEqual(s, 200, v)
        self.assertIn('"amount":  4.0', v["text"])
        self.assertEqual(v["patched"], ["4.0"])
        # 그 텍스트에서 설명을 고쳐 저장 → 숫자 편집과 원문 편집이 한 텍스트에 일관되게 들어감
        text = v["text"].replace("매 턴 이동 횟수 +2", "매 턴 이동 횟수 +4")
        s, j = self.put(text)
        self.assertTrue(j["saved"], j)
        self.assertEqual(j["dryrun"]["affected"], [BOOTS])
        tab = {e["id"]: e for e in sb.app.table_data["fantasies"]}
        self.assertEqual(tab[BOOTS]["effects"][0]["value"], 4.0)     # 숫자 UI 패널이 새 텍스트로 다시 구성됨
        self.assertEqual(tab[BOOTS]["description"], "매 턴 이동 횟수 +4")
        dry_hash = j["dryrun"]["table_hash"]
        self.assertEqual(dry_hash, sb.app.table_hash)
        s, pv = sb.req("POST", "/api/apply/preview", {"edits": []})
        f = pv["files"]["fan_turn_boots.json"]
        self.assertTrue(f["raw"])
        self.assertIn("+4", f["diff"])
        s, r = sb.req("POST", "/api/apply", {"edits": []})
        self.assertEqual(s, 200, r)
        self.assertTrue(r["dryrun_matches_reimport"])                 # AC-J4
        self.assertEqual(sb.app.table_hash, dry_hash)
        after = read_all(sb.src)
        self.assertEqual([k for k in after if after[k] != before[k]], ["fan_turn_boots.json"])
        raw = after["fan_turn_boots.json"]
        self.assertEqual(raw.count(b"\r\n"), before["fan_turn_boots.json"].count(b"\r\n"))   # 줄바꿈 보존
        self.assertIn("매 턴 이동 횟수 +4".encode("utf-8"), raw)
        s, r2 = sb.req("POST", "/api/apply/revert", {})
        self.assertEqual(s, 200, r2)
        self.assertEqual(read_all(sb.src), before)

    def test_j5_structure_edits(self):
        sb = self.sb
        t = self.get()["text"]
        # 등급 변경 → 보상 풀이 바뀜
        s, j = self.put(t.replace('"rarity":  "white"', '"rarity":  "blue"'))
        self.assertTrue(j["saved"], j)
        ch = j["dryrun"]["changes"][0]
        self.assertEqual((ch["before"]["grade"], ch["after"]["grade"]), ("white", "blue"))
        ctx = ms.SimContext(sb.app.base_cfg)
        self.assertIn(BOOTS, ctx.pool["blue"])
        self.assertNotIn(BOOTS, ctx.pool["white"])
        h1 = sb.app.data_hash
        # 효과 추가 → 테이블에 반영 (곡선이 바뀜: 해시 변경 → 재계산)
        obj = json.loads(t)
        extra = copy.deepcopy(obj["effects"][0])
        extra["amount"] = 1.0
        obj["effects"].append(extra)
        obj["effects"].append({"trigger": {"event": "passive"}, "target": {"key": "unknown_thing"}, "operation": "mystery"})
        s, j = self.put(json.dumps(obj, ensure_ascii=False, indent=4))
        self.assertTrue(j["saved"], j)
        e = {x["id"]: x for x in sb.app.table_data["fantasies"]}[BOOTS]
        self.assertEqual([ef["value"] for ef in e["effects"]], [2.0, 1.0])
        self.assertEqual(e["fidelity"], "approx")           # 매핑 불가 효과가 섞임 → 경고
        self.assertIn("미모델링", e["notes"])
        self.assertNotEqual(sb.app.data_hash, h1)
        # 매핑 가능한 효과가 하나도 없으면 none + 경고
        obj["effects"] = obj["effects"][-1:]
        s, j = self.put(json.dumps(obj, ensure_ascii=False, indent=4))
        self.assertTrue(j["saved"])
        self.assertTrue(any("none" in w for w in j["dryrun"]["warnings"]))
        self.assertEqual({x["id"]: x for x in sb.app.table_data["fantasies"]}[BOOTS]["fidelity"], "none")
        # 알 수 없는 필드는 경고, 필수 필드 누락은 오류
        obj2 = json.loads(t)
        obj2["mystery"] = 1
        s, j = self.sb.req("POST", f"/api/files/fantasy/{BOOTS}/dryrun", {"text": json.dumps(obj2)})
        self.assertTrue(j["ok"])
        self.assertTrue(any(m["level"] == "warning" and "mystery" in m["msg"] for m in j["messages"]))
        del obj2["rarity"]
        s, j = self.sb.req("POST", f"/api/files/fantasy/{BOOTS}/dryrun", {"text": json.dumps(obj2)})
        self.assertFalse(j["ok"])

    def test_j6_scope(self):
        sb = self.sb
        t = self.get()["text"]
        self.assertEqual(sb.req("GET", "/api/files/secrets/x")[0], 400)                      # 허용 목록 밖 종류
        self.assertEqual(sb.req("GET", "/api/files/fantasy/..%2F..%2Fx")[0], 400)             # 경로 이탈
        self.assertEqual(self.put(t, fid="fan_brand_new")[0], 400)                            # 새 파일 생성 거부
        self.assertEqual(sb.req("DELETE", f"/api/files/fantasy/{BOOTS}")[0], 405)             # 삭제 거부
        s, j = self.put(t.replace('"id":  "fan_turn_boots"', '"id":  "fan_renamed"'))        # id 변경 거부
        self.assertFalse(j["ok"])
        self.assertTrue(any("id 는 바꿀 수 없음" in m["msg"] for m in j["messages"]))
        self.assertEqual(self.put("x" * (1024 * 1024 + 8192))[0], 413)                        # 1MB 초과
        self.assertTrue(os.path.exists(os.path.join(sb.src, "fan_turn_boots.json")))
        # 편집 후 외부 변경 → 반영 거부
        s, j = self.put(t.replace("매 턴 이동 횟수 +2", "매 턴 이동 +2"))
        self.assertTrue(j["saved"])
        p = os.path.join(sb.src, "fan_turn_boots.json")
        with open(p, "rb") as fp:
            b = fp.read()
        try:
            with open(p, "ab") as fp:
                fp.write(b" ")
            s, r = sb.req("POST", "/api/apply", {"edits": []})
            self.assertEqual(s, 409, r)
            self.assertIn("fan_turn_boots.json", r["error"])
        finally:
            with open(p, "wb") as fp:
                fp.write(b)

    def test_overrides_edit_keeps_sources(self):
        sb = self.sb
        before = read_all(sb.src)
        t = self.get("overrides", "overrides")["text"]
        s, j = self.put(t.replace('"value": 70', '"value": 85'), "overrides", "overrides")
        self.assertTrue(j["saved"], j)
        self.assertEqual({x["id"]: x for x in sb.app.table_data["fantasies"]}["fan_rest_pillow"]["effects"][0]["value"], 85)
        s, r = sb.req("POST", "/api/apply", {"edits": []})
        self.assertEqual(s, 200, r)
        self.assertEqual(read_all(sb.src), before)                    # 원본 게임 파일은 그대로
        with open(sb.ov, encoding="utf-8") as fp:
            self.assertEqual(json.load(fp)["fan_rest_pillow"]["effects"][0]["value"], 85)
        sb.req("POST", "/api/apply/revert", {})

    def test_e4_scenario_schema1_and_file_edits(self):
        sb = self.sb
        tab = {e["id"]: e for e in sb.app.table_data["fantasies"]}
        os.makedirs(sb.scen, exist_ok=True)
        v2 = {"schema": 1, "name": "v2", "base": {"table_hash": "x"}, "applied": None, "results": None, "cfg_edits": [],
              "edits": [{"fid": BOOTS, "effect": 0, "key": "value", "old": tab[BOOTS]["effects"][0]["value"], "new": 1}]}
        with open(os.path.join(sb.scen, "v2.json"), "w", encoding="utf-8") as fp:
            json.dump(v2, fp)
        s, j = sb.req("GET", "/api/scenarios/v2")
        self.assertEqual(s, 200, j)
        self.assertEqual(j["conflicts"], [])                           # schema 1 (target 없는 edits) 도 읽힘
        # file_edits: base_sha1 이 맞으면 충돌 없음, 원본이 바뀌면 충돌
        t = self.get()["text"]
        self.put(t.replace("매 턴 이동 횟수 +2", "매 턴 이동 +2"))
        s, j = sb.req("POST", "/api/scenarios", {"name": "원문", "edits": [], "cfg_edits": []})
        self.assertEqual(j["scenario"]["schema"], 2)
        fe = j["scenario"]["file_edits"]
        self.assertEqual([(x["kind"], x["id"]) for x in fe], [("fantasy", BOOTS)])
        self.assertEqual(sb.req("GET", "/api/scenarios/%EC%9B%90%EB%AC%B8")[1]["conflicts"], [])
        p = os.path.join(sb.src, "fan_turn_boots.json")
        with open(p, "rb") as fp:
            b = fp.read()
        try:
            with open(p, "ab") as fp:
                fp.write(b"\n")
            c = sb.req("GET", "/api/scenarios/%EC%9B%90%EB%AC%B8")[1]["conflicts"]
            self.assertEqual([(x["kind"], x["id"]) for x in c], [("fantasy", BOOTS)])
        finally:
            with open(p, "wb") as fp:
                fp.write(b)


class Monsters(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sb = Sandbox(xs="0.5:1.5:0.5", runs="200", stages="100,200", table_model=True)

    @classmethod
    def tearDownClass(cls):
        cls.sb.stop()
        cls.sb.cleanup()

    def mon(self, mid):
        return next(m for m in self.sb.req("GET", "/api/monsters")[1]["monsters"] if m["id"] == mid)

    def test_m1_m5_table_model(self):
        s, j = self.sb.req("GET", "/api/monsters")
        self.assertEqual(len(j["monsters"]), 39)
        self.assertEqual(j["model"], "table")
        self.assertFalse(j["sim_reflected"]["digits"])           # gauss 모델: 패턴 자릿수는 시뮬 미반영
        self.assertTrue(j["sim_reflected"]["hp"])
        # hp_scale = 2 → 전투에서 쓰이는 체력이 2배
        cfg = copy.deepcopy(self.sb.app.base_cfg)
        hp = {m["id"]: m["hp"] for m in j["monsters"]}
        for scale in (1.0, 2.0):
            cfg["monsters"]["hp_scale"] = scale
            tr = []
            ms.simulate_run(cfg, "m5-0", trace=tr)
            for e in tr:
                if e["ev"] == "battle":
                    self.assertEqual(e["mhp"], round(hp[e["monster"]] * scale))

    def test_m2_m3_edit_and_writeback(self):
        sb = self.sb
        dog = self.mon("Mob_10102_WildDog")
        before_m, before_p, before_f = read_all(sb.mon), read_all(sb.pat), read_all(sb.src)
        edits = [{"target": "monster", "mid": dog["id"], "key": "hp", "old": dog["hp"], "new": 135},
                 {"target": "pattern", "mid": dog["id"], "step": 0, "key": "digits", "old": 2, "new": 3},
                 {"target": "pattern", "pid": "HunterSingle", "key": "digits", "old": 2, "new": 3}]
        s, pv = sb.req("POST", "/api/apply/preview", {"edits": edits})
        self.assertEqual(s, 200, pv)
        self.assertEqual(sorted(pv["files"]), ["monsters/mob_10102_wilddog.json", "patterns/huntersingle.json"])
        self.assertEqual(pv["problems"], [])
        s, r = sb.req("POST", "/api/apply", {"edits": edits})
        self.assertEqual(s, 200, r)
        self.assertEqual(r["roundtrip_mismatch"], [])
        am, ap = read_all(sb.mon), read_all(sb.pat)
        self.assertEqual([k for k in am if am[k] != before_m[k]], ["mob_10102_wilddog.json"])
        self.assertEqual([k for k in ap if ap[k] != before_p[k]], ["huntersingle.json"])
        self.assertEqual(read_all(sb.src), before_f)
        # 숫자 토큰만 바뀜: 체력 120 → 135, 첫 패턴 "2_Single" → "3_Single" (문자열의 나머지 그대로)
        old, new = before_m["mob_10102_wilddog.json"], am["mob_10102_wilddog.json"]
        self.assertEqual(new, old.replace(b"120", b"135", 1).replace(b'"2_Single"', b'"3_Single"', 1))
        self.assertEqual(new.count(b'"2_Single"'), old.count(b'"2_Single"') - 1)
        dog2 = self.mon(dog["id"])
        self.assertEqual((dog2["hp"], dog2["patterns"][0]["key"], dog2["patterns"][0]["dmg_digits"]), (135, "3_Single", 3))
        with open(sb.mtable, encoding="utf-8") as fp:
            mt = json.load(fp)
        self.assertEqual(next(m for m in mt["monsters"] if m["id"] == dog["id"])["hp"], 135)
        # 영향받는 몬스터 목록 = 사용처
        users = sb.req("GET", "/api/monsters")[1]["pattern_users"]
        self.assertEqual(users["HunterSingle"], [m["id"] for m in mt["monsters"] if any(p["key"] == "HunterSingle" for p in m["patterns"])])
        s, rv = sb.req("POST", "/api/apply/revert", {})
        self.assertEqual(s, 200, rv)
        self.assertEqual((read_all(sb.mon), read_all(sb.pat)), (before_m, before_p))
        self.assertEqual(self.mon(dog["id"])["hp"], dog["hp"])

    def test_m4_probe(self):
        sb = self.sb
        dog = self.mon("Mob_10102_WildDog")
        cfg = sb.app.base_cfg
        turns = []
        for hp in (60, 120, 240, 480):
            m = dict(dog, hp=hp)
            turns.append(mo.probe(cfg, m, 400, "pr")["avg_turns"])
        self.assertEqual(turns, sorted(turns))
        self.assertGreater(turns[-1], turns[0] + 1)
        self.assertEqual(mo.probe(cfg, dog, 300, "pr"), mo.probe(cfg, dog, 300, "pr"))      # 재현
        # 힘 토큰(Str_n)을 늘리면 받는 피해가 증가 (자릿수 토큰은 gauss 모델에서 시뮬 미반영)
        strong = copy.deepcopy(dog)
        strong["patterns"][2]["str_units"] = 12
        self.assertGreater(mo.probe(cfg, strong, 600, "pr")["avg_taken"], mo.probe(cfg, dog, 600, "pr")["avg_taken"])
        # 작업으로도 같은 결과 (수정 전·후)
        jid = sb.job({"kind": "monster_probe", "mid": dog["id"], "n": 300,
                      "edits": [{"target": "monster", "mid": dog["id"], "key": "hp", "old": dog["hp"], "new": 480}]})
        res = sb.events(jid)[-1]
        self.assertEqual(res["type"], "done", res)
        self.assertGreater(res["result"]["after"]["avg_turns"], res["result"]["before"]["avg_turns"])

    def test_e3_monster_edit_changes_data_hash(self):
        sb = self.sb
        dog = self.mon("Mob_10102_WildDog")
        edit = {"target": "monster", "mid": dog["id"], "key": "hp", "old": dog["hp"], "new": 300}
        jid = sb.job({"kind": "recompute", "edits": [edit], "fids": [], "x_values": [1.0], "stages": [100]})
        evs = sb.events(jid)
        self.assertEqual(evs[-1]["type"], "done", evs[-1])
        plan = next(e for e in evs if e["type"] == "plan")
        self.assertNotEqual(plan["data_hash"], plan["base_data_hash"])    # 몬스터를 고치면 모든 곡선이 stale
        after = [e for e in evs if e["type"] == "point" and e["series"] == "after" and e["fid"] == "__baseline__"][-1]["point"]
        self.assertEqual(after["data_hash"], plan["data_hash"])
        self.assertIn("edit_effect", after)                               # 기준선의 수정 전후 차이


class ComboEmberJobs(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sb = Sandbox()

    @classmethod
    def tearDownClass(cls):
        cls.sb.stop()
        cls.sb.cleanup()

    def test_combo_job_estimate_and_cache(self):
        sb = self.sb
        body = {"kind": "combo", "ids": ["fan_damage_anchor", "fan_damage_poinsettia"], "baseline_type": "natural",
                "stages": [300]}
        s, est = sb.req("POST", "/api/estimate", body)
        self.assertEqual(s, 200, est)
        self.assertEqual(est["arms"], 4)
        self.assertEqual(est["runs_needed"], 2 * 300)       # 기준선·단독 팔은 스캔 캐시 재사용, 쌍 팔만 새로
        res = sb.events(sb.job(body))[-1]
        self.assertEqual(res["type"], "done", res)
        c = res["result"]
        self.assertEqual(c["label"], "pre")
        self.assertEqual(sorted(c["by_x"][0]["arms"]), sorted(["__baseline__", "fan_damage_anchor", "fan_damage_poinsettia",
                                                                 "fan_damage_anchor+fan_damage_poinsettia"]))
        pair = c["by_x"][0]["pairs"][0]
        self.assertLess(pair["I"], 0)                        # 닻 + 포인세티아: 받는 피해가 0에서 막혀 중복·포화
        self.assertIn("equiv_gain", c)
        s, est2 = sb.req("POST", "/api/estimate", body)
        self.assertEqual(est2["runs_needed"], 0)             # 같은 조합은 즉시 반환
        # 제외 기준선은 팔을 모두 새로 계산
        s, est3 = sb.req("POST", "/api/estimate", {**body, "baseline_type": "banned"})
        self.assertEqual(est3["runs_needed"], 3 * 2 * 300)   # 전체 집합 팔(제외 없음)은 위에서 계산한 쌍 팔과 같은 키
        s, bad = sb.req("POST", "/api/estimate", {**body, "ids": ["a", "b"]})
        self.assertEqual(s, 400)

    def test_ember_sweep_and_system_switch(self):
        sb = self.sb
        res = sb.events(sb.job({"kind": "ember_sweep", "slot_sizes": [2, 3, 4], "blue_chances": [0.0, 0.2], "n": 200, "x": 500}))
        self.assertEqual(res[-1]["type"], "done", res[-1])
        cells = res[-1]["result"]["cells"]
        self.assertEqual(sorted((c["slot_size"], c["blue_chance"]) for c in cells),
                         [(a, b) for a in (2, 3, 4) for b in (0.0, 0.2)])     # 정수 격자 전체
        by = {(c["slot_size"], c["blue_chance"]): c for c in cells}
        self.assertGreater(by[(2, 0.0)]["mean_fantasies"], by[(4, 0.0)]["mean_fantasies"])   # 슬롯이 작을수록 환상이 많다
        # 시스템 스위치: 불씨 규칙으로 기준선 재계산 + 현행 고스트
        jid = sb.job({"kind": "recompute", "cfg_set": {"rewards.normal_battle.mode": "ember"}, "fids": [], "x_values": [500], "stages": [200]})
        evs = sb.events(jid)
        self.assertEqual(evs[-1]["type"], "done", evs[-1])
        pts = {e["series"]: e["point"] for e in evs if e["type"] == "point" and e["fid"] == "__baseline__"}
        self.assertGreater(pts["after"]["ember_mean"]["slots_done"], 0)
        self.assertEqual(pts["before"]["ember_mean"]["slots_done"], 0)
        self.assertLess(pts["after"]["mean_fantasies"], pts["before"]["mean_fantasies"])
        self.assertIn("fant_by_floor", pts["after"])
        s, bad = sb.req("POST", "/api/jobs", {"kind": "recompute", "cfg_set": {"sim.max_turns": "x"}})
        self.assertEqual(sb.events(bad["id"])[-1]["type"], "error")           # 허용 목록 밖 설정 전환 거부


if __name__ == "__main__":
    unittest.main()
