# -*- coding: utf-8 -*-
"""v4.4 F15 시뮬레이션 데이터 내려받기 — 서버 수준 (AC-X1~X10). 점 캐시는 읽기만 한다."""
import csv
import http.client
import io
import json
import os
import sys
import unittest
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)

from sim_service import export as exp  # noqa: E402
from test_server import Sandbox  # noqa: E402

BOOTS, SLING = "fan_turn_boots", "fan_damage_slingshot"


def raw(sb, method, path, body=None, token=True, origin=None):
    c = http.client.HTTPConnection("127.0.0.1", sb.port, timeout=120)
    h = {"Host": f"127.0.0.1:{sb.port}"}
    if token:
        h["X-MatchUp-Token"] = sb.token if token is True else token
    if origin:
        h["Origin"] = origin
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        h["Content-Type"] = "application/json"
    c.request(method, path, body=data, headers=h)
    r = c.getresponse()
    b = r.read()
    hd = {k.lower(): v for k, v in r.getheaders()}
    c.close()
    return r.status, hd, b


def parse_csv(b):
    assert b[:3] == b"\xef\xbb\xbf", "UTF-8 BOM 이 없다"
    return list(csv.DictReader(io.StringIO(b[3:].decode("utf-8"), newline="")))


class Export(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sb = Sandbox(xs="500:700:200", runs="30", stages="20,30")
        cls.pts = {}
        evs = cls.sb.events(cls.sb.job({"kind": "recompute", "fids": [BOOTS], "stages": [30], "client": "x"}))
        assert evs[-1]["type"] == "done"
        for e in evs:
            if e["type"] == "point" and e["series"] == "after":
                cls.pts[(e["fid"], e["x"])] = e["point"]
        cls.seed = cls.sb.app.seed

    @classmethod
    def tearDownClass(cls):
        cls.sb.stop()
        cls.sb.cleanup()

    def get(self, dataset, **body):
        return raw(self.sb, "POST", f"/api/export/{dataset}", body)

    # --- AC-X1
    def test_x1_curves_csv_matches_screen(self):
        s, h, b = self.get("curves", scope={"fids": [BOOTS], "x": "all", "series": ["after"]})
        self.assertEqual(s, 200)
        self.assertIn("attachment", h["content-disposition"])
        self.assertTrue(h["content-type"].startswith("text/csv"))
        meta = json.loads(h["x-matchup-meta"])
        self.assertEqual(meta["sim_version"], self.sb.app.build_info()["sim_version"])
        rows = parse_csv(b)
        self.assertEqual([c for c, _ in exp.CURVE_COLS], list(rows[0].keys()))
        self.assertEqual(len(rows), 2 * 2)                                          # (기준선 + 환상) × X 2점 (500, 700)
        for r in rows:
            p = self.pts[(r["fantasy_id"], float(r["x"]) if r["x"].replace(".", "").isdigit() and "." in r["x"] else int(r["x"]))]
            self.assertEqual(int(r["n"]), p["n"])
            self.assertEqual(int(r["wins"]), p["wins"])
            self.assertEqual(float(r["win_rate"]), p["win_rate"])                   # 반올림 없이 같은 값
            if r["fantasy_id"] != "__baseline__":
                self.assertEqual(float(r["delta"]), p["delta"])
        self.assertTrue(all(r["series"] == "after" for r in rows))
        s, h2, jb = self.get("curves", scope={"fids": [BOOTS], "x": 700}, format="json")
        d = json.loads(jb)
        self.assertEqual(len(d["rows"]), 2)
        self.assertEqual(d["meta"]["dataset"], "curves")

    def test_reach_long_form(self):
        s, h, b = self.get("reach", scope={"fids": [BOOTS], "x": 700})
        rows = parse_csv(b)
        self.assertEqual(len(rows), 2 * 45)
        self.assertEqual([int(r["floor"]) for r in rows[:45]], list(range(1, 46)))
        p = self.pts[(BOOTS, 700)]
        mine = [float(r["reach_rate"]) for r in rows if r["fantasy_id"] == BOOTS]
        self.assertEqual(mine, p["reach_rate"])

    # --- AC-X2 / X3
    def test_x2_runs_consistent_with_point(self):
        s, h, b = self.get("runs", scope={"fids": [BOOTS], "x": 700})
        rows = parse_csv(b)
        self.assertEqual(len(rows), 2 * 30)
        for fid in ("__baseline__", BOOTS):
            mine = [r for r in rows if r["fantasy_id"] == fid]
            p = self.pts[(fid, 700)]
            self.assertEqual(len(mine), p["n"])
            self.assertEqual(sum(int(r["win"]) for r in mine), p["wins"])
            self.assertAlmostEqual(sum(int(r["reached_floor"]) for r in mine) / len(mine), p["mean_reached_floor"], places=3)
            self.assertEqual(mine[0]["seed"], f"{self.seed}-0")
            self.assertEqual(mine[7]["run_index"], "7")
        s, h, nd = self.get("runs", scope={"fids": [BOOTS], "x": 700}, format="ndjson")
        self.assertEqual(len(nd.decode("utf-8").strip().split("\n")), 60)

    def test_x3_missing_not_computed(self):
        before = self.sb.app.engine.runs_computed
        s, fj = self.sb.req("GET", "/api/fantasies")
        old = next(f for f in fj["fantasies"] if f["id"] == BOOTS)["effects"][0]["value"]
        edit = {"fid": BOOTS, "effect": 0, "key": "value", "old": old, "new": old + 5}      # 계산해 둔 적 없는 상태
        s, h, b = self.get("curves", scope={"fids": [BOOTS], "x": "all"}, edits=[edit])
        self.assertEqual(s, 200)
        self.assertEqual(int(h["x-matchup-missing"]), 4)                            # (기준선 + 환상) × 2점 모두 캐시에 없음
        self.assertEqual(parse_csv(b), [])
        self.assertEqual(self.sb.app.engine.runs_computed, before)                   # 새로 돌리지 않음
        meta = json.loads(h["x-matchup-meta"])
        self.assertEqual(meta["missing_count"], 4)
        s, est = self.sb.req("POST", "/api/export/estimate", {"id": "curves", "scope": {"fids": [BOOTS], "x": "all"}, "edits": [edit]})
        self.assertEqual((est["missing_count"], est["rows"]), (4, 0))
        self.assertEqual(self.sb.app.engine.runs_computed, before)

    # --- AC-X5
    def test_x5_auth_ticket_origin(self):
        self.assertEqual(raw(self.sb, "POST", "/api/export/curves", {}, token=False)[0], 403)
        self.assertEqual(raw(self.sb, "POST", "/api/export/curves", {}, token="wrong")[0], 403)
        self.assertEqual(raw(self.sb, "POST", "/api/export/curves", {}, origin="http://evil.example")[0], 403)
        self.assertEqual(raw(self.sb, "GET", "/api/export", token=False)[0], 403)
        s, t = self.sb.req("POST", "/api/export/ticket", {"id": "curves", "scope": {"fids": [BOOTS], "x": 700}})
        self.assertEqual(s, 200)
        s1, h1, b1 = raw(self.sb, "GET", t["url"], token=False)                       # 티켓만으로 받는다 (헤더 없음)
        self.assertEqual(s1, 200)
        self.assertEqual(len(parse_csv(b1)), 2)
        self.assertEqual(raw(self.sb, "GET", t["url"], token=False)[0], 403)         # 재사용
        s, t2 = self.sb.req("POST", "/api/export/ticket", {"id": "curves"})
        exp._tickets[t2["t"]]["exp"] = 0                                             # 만료
        self.assertEqual(raw(self.sb, "GET", t2["url"], token=False)[0], 403)
        self.assertEqual(raw(self.sb, "GET", "/api/export/dl/not-a-ticket", token=False)[0], 403)
        self.assertEqual(raw(self.sb, "GET", t["url"], token=False, origin="http://evil.example")[0], 403)
        self.assertEqual(self.sb.req("POST", "/api/export/ticket", {"id": "nope"})[0], 400)

    # --- AC-X6
    def test_x6_bundle_zip(self):
        s, h, b = self.get("bundle", datasets=["curves", "edits", "monsters"], scope={"fids": [BOOTS], "x": "all"})
        self.assertEqual(s, 200)
        zf = zipfile.ZipFile(io.BytesIO(b))
        self.assertIsNone(zf.testzip())
        names = zf.namelist()
        self.assertTrue(any(n.startswith("matchup_curves_") for n in names))
        self.assertTrue(any(n.startswith("matchup_edits_") for n in names))
        self.assertIn("meta.json", names)
        self.assertIn("README.txt", names)
        meta = json.loads(zf.read("meta.json"))
        self.assertEqual(meta["view_data_hash"], self.sb.app.data_hash)               # 화면 해시와 같다
        self.assertEqual(meta["master_seed"], self.seed)
        self.assertIn("시드 규칙", zf.read("README.txt").decode("utf-8"))
        self.assertEqual(self.get("bundle", datasets=["evil"])[0], 400)

    # --- AC-X7
    def test_x7_csv_injection(self):
        self.assertEqual(exp.cell("=1+1", text=True), "'=1+1")
        self.assertEqual(exp.cell("@SUM(A1)", text=True), "'@SUM(A1)")
        self.assertEqual(exp.cell("-5", text=True), "'-5")
        self.assertEqual(exp.cell(-5), "-5")                                           # 숫자 열은 대상이 아니다
        self.assertEqual(exp.cell('a,b"c'), '"a,b""c"')
        s, info = self.sb.req("GET", f"/api/files/fantasy/{BOOTS}")
        obj = json.loads(info["text"])
        obj["designerName"] = "=HYPERLINK(\"http://x\")"
        obj["localization"] = {"name": "=HYPERLINK(\"http://x\")", "description": ""}
        s, r = self.sb.req("PUT", f"/api/files/fantasy/{BOOTS}", {"text": json.dumps(obj, ensure_ascii=False, indent=4)})
        self.assertTrue(r["saved"], r)
        try:
            s, fj = self.sb.req("GET", "/api/fantasies")
            old = next(f for f in fj["fantasies"] if f["id"] == BOOTS)["effects"][0]["value"]
            s, h, b = self.get("edits", edits=[{"fid": BOOTS, "effect": 0, "key": "value", "old": old, "new": old + 1}])
            rows = parse_csv(b)
            self.assertEqual(len(rows), 1)
            self.assertTrue(rows[0]["name"].startswith("'="), rows[0]["name"])
        finally:
            self.sb.req("POST", f"/api/files/fantasy/{BOOTS}/revert", {})

    # --- AC-X8
    def test_x8_path_and_param_safety(self):
        self.assertEqual(self.get("scans", scope={"scan_id": "../../x"})[0], 400)
        self.assertEqual(self.get("scans", scope={"scan_id": "/etc/passwd"})[0], 400)
        self.assertEqual(self.get("scans", scope={"scan_id": "20200101-000000-abcdef"})[0], 400)    # 형식은 맞지만 없음
        self.assertEqual(self.get("results", scope={"kind": "../x", "key": "0123456789abcdef"})[0], 400)
        self.assertEqual(self.get("results", scope={"kind": "combo", "key": "..%2F..%2Fx"})[0], 400)
        self.assertEqual(self.get("nope")[0], 400)
        self.assertEqual(self.get("curves", format="xlsx")[0], 400)
        self.assertEqual(self.get("curves", scope={"fids": ["../../x"]})[0], 400)
        self.assertEqual(self.get("curves", scope={"x": 12345})[0], 400)
        self.assertEqual(self.get("curves", scope={"series": ["evil"]})[0], 400)
        sid = self.sb.app.active_scan_id()
        if sid:
            s, h, b = self.get("scans", scope={"scan_id": sid})
            self.assertEqual(s, 200)
            self.assertIn("meta", json.loads(b))                                       # 스캔 파일 원본 그대로

    # --- AC-X9
    def test_x9_edits_rows(self):
        s, fj = self.sb.req("GET", "/api/fantasies")
        old = next(f for f in fj["fantasies"] if f["id"] == BOOTS)["effects"][0]["value"]
        s, st = self.sb.req("GET", "/api/state")
        path = next(iter(st["base_cfg"]))
        cur = st["base_cfg"][path]
        s, h, b = self.get("edits", edits=[{"fid": BOOTS, "effect": 0, "key": "value", "old": old, "new": old + 2}],
                           cfg_edits=[{"path": path, "old": cur, "new": cur}], cfg_set={"monsters.gimmicks": "off"})
        if s == 200:
            rows = parse_csv(b)
            self.assertEqual(len(rows), 3)
            fe = next(r for r in rows if r["target"] == "fantasy")
            self.assertEqual((float(fe["old"]), float(fe["new"])), (float(old), float(old + 2)))
            self.assertIn(fe["source"], ("원본연결", "시뮬전용", "시나리오전용"))
            self.assertEqual(next(r for r in rows if r["target"] == "cfg_set")["path"], "monsters.gimmicks")

    # --- AC-X10
    def test_x10_seed_reproduces_reached_floor(self):
        s, h, b = self.get("runs", scope={"fids": [BOOTS], "x": 700})
        rows = parse_csv(b)
        forced = [r for r in rows if r["fantasy_id"] == BOOTS]
        base = [r for r in rows if r["fantasy_id"] == "__baseline__"]
        for i in (0, 3, 9, 17, 29):
            s, tr = self.sb.req("POST", "/api/trace", {"fid": BOOTS, "x": 700, "seed": forced[i]["seed"]})
            self.assertEqual(s, 200, tr)
            self.assertEqual(tr["forced"]["row"]["reached_floor"], int(forced[i]["reached_floor"]))
            self.assertEqual(tr["base"]["row"]["reached_floor"], int(base[i]["reached_floor"]))

    # --- F15.8 한도
    def test_limits_rows_and_concurrency(self):
        old = exp.MAX_ROWS
        exp.MAX_ROWS = 10
        try:
            self.assertEqual(self.get("runs", scope={"fids": [BOOTS], "x": 700})[0], 413)
        finally:
            exp.MAX_ROWS = old
        taken = []
        try:
            for _ in range(exp.MAX_CONCURRENT):
                exp.acquire()
                taken.append(1)
            self.assertEqual(self.get("curves", scope={"fids": [BOOTS], "x": 700})[0], 429)
        finally:
            for _ in taken:
                exp.release()
        self.assertEqual(self.get("curves", scope={"fids": [BOOTS], "x": 700})[0], 200)

    def test_catalog_and_workspace_dataset(self):
        s, cat = self.sb.req("GET", "/api/export")
        ids = {d["id"] for d in cat["datasets"]}
        self.assertTrue({"curves", "reach", "runs", "edits", "monsters", "bundle", "workspace", "ranking", "monster_hp"} <= ids)
        s, h, b = self.get("workspace")
        self.assertEqual(s, 200)
        self.assertIn("state", json.loads(b))


if __name__ == "__main__":
    unittest.main()
