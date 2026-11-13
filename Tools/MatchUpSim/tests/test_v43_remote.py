# -*- coding: utf-8 -*-
"""원격 서버·외부 수정 반영·기기별 작업·조합(모두 보유) — 2026-11-13 요청.

- 원격 모드(--host 가 루프백 아님): 페이지(/)도 토큰(?k=)이 있어야 열리고, 토큰은 파일에 저장돼 재시작해도 같다.
  Host 는 검사하지 않고(토큰으로 막음) Origin 은 같은 출처만 허용한다.
- 서버 밖에서 원본 JSON 을 고치면 다음 요청 때 다시 읽는다 (비교 기준은 그대로 → 수정 전/후).
- 작업은 기기(client)마다 자기 이전 작업만 취소한다.
- 조합 arms="full": 기준선 + 단독 + 전체 집합만 계산하고, 팔마다 생존 곡선(reach_rate)을 준다.
- 몬스터 지표의 조우 시 전투 승률·조우한 런 승률.
테스트는 원본 Assets 를 건드리지 않는다 (fixtures 사본만 수정).
"""
import glob
import http.client
import json
import os
import sys
import threading
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)

import viewer_server  # noqa: E402
from sim_service import jobs as jb  # noqa: E402
from test_server import Sandbox  # noqa: E402

BOOTS = "fan_turn_boots"
REMOTE_HOST = "127.0.0.2"     # 루프백이지만 기본(127.0.0.1)이 아니므로 원격 모드 — 방화벽 창 없이 시험


def boots_file(src):
    for p in glob.glob(os.path.join(src, "*.json")):
        with open(p, encoding="utf-8-sig") as fp:
            if json.load(fp).get("id") == BOOTS:
                return p
    raise AssertionError("boots 없음")


def get(host, port, path, headers):
    c = http.client.HTTPConnection(host, port, timeout=60)
    c.request("GET", path, headers=headers)
    r = c.getresponse()
    raw = r.read()
    c.close()
    return r.status, raw.decode("utf-8", "replace")


class Remote(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sb = Sandbox(xs="500:700:200", runs="60", stages="30,60", start_hp=False)
        cls.sb.stop()      # 같은 사본으로 원격 모드 서버를 다시 띄운다
        cls.tokfile = os.path.join(cls.sb.tmp, "remote_token")
        cls.srv, cls.app = cls.start()

    @classmethod
    def start(cls):
        sb = cls.sb
        args = viewer_server.parse_args([
            "--host", REMOTE_HOST, "--token-file", cls.tokfile,
            "--port", "0", "--results", sb.results, "--effects", sb.effects, "--src", sb.src,
            "--monsters", sb.mon, "--patterns", sb.pat, "--monster-table", sb.mtable,
            "--overrides", sb.ov, "--scenarios", sb.scen, "--backup", sb.backup, "--workers", "2",
            "--stages", "30,60", "--surrogate-auto", "manual"])
        srv, app = viewer_server.make_server(args)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        return srv, app

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.srv.server_close()
        cls.app.engine.close()
        cls.sb.cleanup()

    def g(self, path, host=None, token=None, origin=None):
        h = {"Host": host or f"{REMOTE_HOST}:{self.app.port}"}
        if token:
            h["X-MatchUp-Token"] = token
        if origin:
            h["Origin"] = origin
        return get(REMOTE_HOST, self.app.port, path, h)

    def test_page_needs_token(self):
        a = self.app
        self.assertTrue(a.remote)
        self.assertEqual(self.g("/")[0], 403)
        self.assertEqual(self.g("/?k=wrong")[0], 403)
        code, html = self.g(f"/?k={a.token}", host=f"192.168.0.17:{a.port}")    # LAN 주소로 접속해도 열린다
        self.assertEqual(code, 200)
        self.assertIn(a.token, html)
        self.assertIn('"remote":true', html)

    def test_api_token_and_origin(self):
        a = self.app
        self.assertEqual(self.g("/api/ping")[0], 403)                                   # 토큰 없음
        self.assertEqual(self.g("/api/ping", host=f"my-pc:{a.port}", token=a.token)[0], 200)
        self.assertEqual(self.g("/api/ping", token=a.token, origin="http://evil.example")[0], 403)
        self.assertEqual(self.g("/api/ping", token=a.token, origin=f"http://{REMOTE_HOST}:{a.port}")[0], 200)

    def test_token_persisted(self):
        with open(self.tokfile, encoding="utf-8") as fp:
            self.assertEqual(fp.read().strip(), self.app.token)
        self.assertEqual(viewer_server.remote_token(self.tokfile), self.app.token)   # 재시작해도 같은 주소
        self.assertGreaterEqual(len(self.app.token), 16)


class ExternalEdit(unittest.TestCase):
    """에디터·Unity·git pull 로 원본 JSON 이 바뀌면 다음 요청 때 반영 (재계산이 옛 값으로 돌던 문제)."""

    @classmethod
    def setUpClass(cls):
        cls.sb = Sandbox(xs="500:700:200", runs="60", stages="30,60")

    @classmethod
    def tearDownClass(cls):
        cls.sb.stop()
        cls.sb.cleanup()

    def boots_value(self):
        code, fj = self.sb.req("GET", "/api/fantasies")
        self.assertEqual(code, 200)
        f = next(x for x in fj["fantasies"] if x["id"] == BOOTS)
        return f["effects"][0]["value"], fj["data_hash"]

    def test_disk_change_is_picked_up(self):
        sb = self.sb
        v0, h0 = self.boots_value()
        ref0 = sb.req("GET", "/api/reference")[1]
        p = boots_file(sb.src)
        with open(p, encoding="utf-8-sig") as fp:
            obj = json.load(fp)
        obj["effects"][0]["amount"] = 7.0
        time.sleep(0.05)
        with open(p, "w", encoding="utf-8") as fp:
            json.dump(obj, fp, ensure_ascii=False, indent=4)
        v1, h1 = self.boots_value()
        self.assertEqual(v1, 7)
        self.assertNotEqual(v0, v1)
        self.assertNotEqual(h0, h1)
        ref1 = sb.req("GET", "/api/reference")[1]
        self.assertEqual(ref1["ref_hash"], ref0["ref_hash"])          # 비교 기준(수정 전)은 그대로
        self.assertIn(BOOTS, ref1["changed"]["fantasies"])
        # 재계산 작업도 새 값으로 돈다: 작업 준비 시점의 테이블 해시 = 현재 해시
        code, st = sb.req("GET", "/api/state")
        self.assertEqual(st["data_hash"], h1)


class ClientCancel(unittest.TestCase):
    """기기마다 자기 이전 작업만 취소 — 두 기기가 동시에 재계산해도 서로 끊지 않는다."""

    def test_per_client(self):
        gate = threading.Event()

        def slow(app, job):
            gate.wait(5)
            return {"ok": True}

        jb.JOB_KINDS["__test_slow"] = slow
        try:
            jm = jb.JobManager(app=None)
            a1 = jm.submit("__test_slow", {"client": "A"})
            b1 = jm.submit("__test_slow", {"client": "B"})
            self.assertFalse(a1.cancelled)                    # 다른 기기의 작업은 그대로
            a2 = jm.submit("__test_slow", {"client": "A"})
            self.assertTrue(a1.cancelled)                     # 같은 기기의 이전 작업은 취소
            self.assertFalse(b1.cancelled)
            legacy = jm.submit("__test_slow", {})              # client 없음(구버전): 진행 중인 작업 취소 (예전 동작)
            self.assertTrue(a2.cancelled)
            gate.set()
            for j in (b1, legacy):
                with j.cond:
                    j.cond.wait_for(lambda: j.done, timeout=10)
                self.assertEqual(j.events[-1]["type"], "done")
        finally:
            gate.set()
            jb.JOB_KINDS.pop("__test_slow", None)


class ComboFull(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sb = Sandbox(xs="500:700:200", runs="60", stages="30,60")

    @classmethod
    def tearDownClass(cls):
        cls.sb.stop()
        cls.sb.cleanup()

    def test_full_arms_with_survival(self):
        sb = self.sb
        ids = [BOOTS, "fan_damage_slingshot", "fan_damage_anchor"]
        body = {"kind": "combo", "arms": "full", "ids": ids, "stages": [30, 60], "client": "t"}
        code, est = sb.req("POST", "/api/estimate", body)
        self.assertEqual(code, 200)
        self.assertEqual(est["arms"], len(ids) + 2)                     # 2^3 = 8 이 아니라 k + 2
        code, r = sb.req("POST", "/api/jobs", body)
        job = sb.app.jobs.jobs[r["id"]]
        with job.cond:
            job.cond.wait_for(lambda: job.done, timeout=300)
        ev = job.events[-1]
        self.assertEqual(ev["type"], "done", ev.get("message"))
        res = ev["result"]
        self.assertEqual(res["arms"], "full")
        b = res["by_x"][0]
        full = "+".join(res["ids"])
        self.assertEqual(sorted(b["arms"]), sorted(["__baseline__", full] + ids))
        a = b["arms"][full]
        self.assertEqual(len(a["reach_rate"]), 45)
        self.assertEqual(a["reach_rate"][0], 1.0)
        self.assertIsNotNone(a["mean_reached_floor"])
        self.assertEqual(b["pairs"], [])                                # 쌍 팔이 없으니 I 도 없음
        self.assertAlmostEqual(a["expected_delta"], sum(b["arms"][i]["delta"] for i in ids), places=5)



class MonsterEncounterWin(unittest.TestCase):
    """몬스터 조우 시 승률: 전투 승률(이긴 전투 / 전투), 조우한 런 승률(클리어한 런 / 만난 런)."""

    def test_rates(self):
        import tempfile
        import fantasy_scan as fs
        import import_monsters
        from sim_service import monsters as mo
        with tempfile.TemporaryDirectory() as tmp:
            out = os.path.join(tmp, "monster_table.json")
            table = import_monsters.main(["--monsters", os.path.join(HERE, "fixtures", "monsters"),
                                          "--patterns", os.path.join(HERE, "fixtures", "patterns"), "--out", out, "--quiet"])
            cfg, _ = fs.build_cfg(None, [], os.path.join(ROOT, "fantasy_effects.json"))
            cfg["monsters"]["table_file"] = out
            res = mo.run_metrics(cfg, "enc", 300, monster_table=table)
        self.assertEqual(res["wins"] + res["deaths"], res["runs"])
        self.assertAlmostEqual(res["win_rate"], res["wins"] / res["runs"], places=4)
        for r in res["monsters"]:
            self.assertEqual(r["battle_wins"] + round(r["death_rate_in_battle"] * r["battles"]) + r["escapes"] + r["timeouts"], r["battles"])
            self.assertAlmostEqual(r["battle_win_rate"], r["battle_wins"] / r["battles"], places=4)
            self.assertLessEqual(r["battle_win_ci"][0], r["battle_win_rate"])
            self.assertGreaterEqual(r["battle_win_ci"][1], r["battle_win_rate"])
            self.assertLessEqual(r["runs_met"], res["runs"])
            self.assertLessEqual(r["runs_met"], r["battles"])
        fairy = next(r for r in res["monsters"] if r["id"] == "Mob_10101_Fairy")
        self.assertEqual(fairy["runs_met"], res["runs"])                         # 모든 런의 첫 전투
        self.assertAlmostEqual(fairy["run_win_rate_met"], res["win_rate"], places=4)   # 그래서 조우한 런 승률 = 전체 승률


try:
    from playwright.sync_api import sync_playwright
except ImportError:  # pragma: no cover
    sync_playwright = None


@unittest.skipIf(sync_playwright is None, "playwright 미설치")
class ExternalEditUI(unittest.TestCase):
    """뷰어가 스캔에 박힌 옛 효과값 대신 서버의 현재 원본을 보여 주고, 원본이 바뀌면 다시 받는다."""

    @classmethod
    def setUpClass(cls):
        cls.sb = Sandbox(xs="500:700:200", runs="60", stages="30,60")
        cls.pw = sync_playwright().start()
        ch = os.environ.get("VIEWER_BROWSER_CHANNEL", "msedge")
        cls.browser = cls.pw.chromium.launch(**({"channel": ch} if ch else {}))

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.pw.stop()
        cls.sb.stop()
        cls.sb.cleanup()

    def set_amount(self, v):
        p = boots_file(self.sb.src)
        with open(p, encoding="utf-8-sig") as fp:
            obj = json.load(fp)
        obj["effects"][0]["amount"] = float(v)
        time.sleep(0.05)
        with open(p, "w", encoding="utf-8") as fp:
            json.dump(obj, fp, ensure_ascii=False, indent=4)

    def test_list_shows_current_disk_values(self):
        self.set_amount(5)                       # 스캔(값 2) 이후 원본을 고친 상태로 연다
        ctx = self.browser.new_context(viewport={"width": 1400, "height": 1000})
        pg = ctx.new_page()
        errs = []
        pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.goto(f"http://127.0.0.1:{self.sb.port}/#t=curve")
        pg.wait_for_function("window.__viewerReady === true", timeout=90000)
        row = f'#list .row[data-id="{BOOTS}"]'
        self.assertIn("이동 +5", pg.inner_text(row))
        self.set_amount(9)                       # 열어 둔 채로 원본 수정 → 탭 복귀/재계산 때 동기화
        self.assertTrue(pg.evaluate("window.__syncServerTable()"))
        pg.wait_for_function(f"document.querySelector('{row}').innerText.includes('이동 +9')")
        self.assertEqual(errs, [])
        ctx.close()


if __name__ == "__main__":
    unittest.main()
