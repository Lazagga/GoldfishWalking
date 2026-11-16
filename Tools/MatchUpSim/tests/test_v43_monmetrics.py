# -*- coding: utf-8 -*-
"""몬스터별 지표가 편집을 바로 반영한다 (서버 작업 monster_metrics + 몬스터 탭).

- 서버: 몬스터·설정 편집을 반영해 단계별로 계산, 같은 상태는 조각 캐시, 취소, 곡선 재계산과 기기(client)가 다르면 서로 끊지 않음.
- 뷰어: 몬스터 체력을 고치면 표의 체력·지표가 갱신되고, ‘버튼만’ 모드에서는 이전 값 표시 + 지금 계산.
"""
import json
import os
import sys
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)

from test_server import SHOTS, Sandbox  # noqa: E402

try:
    from playwright.sync_api import sync_playwright
except ImportError:  # pragma: no cover
    sync_playwright = None

MID = "Mob_10102_WildDog"


def hp_edit(new, old=120):
    return {"target": "monster", "mid": MID, "key": "hp", "old": old, "new": new}


class ServerJob(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sb = Sandbox(xs="500:700:200", runs="60", stages="30,60")

    @classmethod
    def tearDownClass(cls):
        cls.sb.stop()
        cls.sb.cleanup()

    def run_metrics(self, **body):
        jid = self.sb.job({"kind": "monster_metrics", **body})
        return self.sb.events(jid)

    def test_stages_and_edit_reflected(self):
        evs = self.run_metrics(stages=[40, 80], chunk=40, edits=[])
        mets = [e for e in evs if e["type"] == "metrics"]
        self.assertEqual([m["n"] for m in mets], [40, 80])
        self.assertEqual(evs[-1]["type"], "done")
        base = {r["id"]: r for r in mets[-1]["data"]["monsters"]}
        self.assertIn(MID, base)
        self.assertEqual(mets[-1]["data"]["meta"]["runs"], 80)
        self.assertEqual(base[MID]["hp"], 120)
        # 체력을 크게 키우면 표의 체력과 평균 턴 수가 달라진다 (편집 반영)
        evs2 = self.run_metrics(stages=[80], chunk=40, edits=[hp_edit(5000)])
        after = {r["id"]: r for r in [e for e in evs2 if e["type"] == "metrics"][-1]["data"]["monsters"]}
        self.assertEqual(after[MID]["hp"], 5000)
        self.assertGreater(after[MID]["avg_turns"], base[MID]["avg_turns"])

    def test_same_state_uses_cache(self):
        a = self.run_metrics(stages=[60], chunk=30, edits=[hp_edit(111)])
        p1 = next(e for e in a if e["type"] == "plan")
        t0 = time.perf_counter()
        b = self.run_metrics(stages=[60], chunk=30, edits=[hp_edit(111)])
        p2 = next(e for e in b if e["type"] == "plan")
        self.assertEqual(p1["cached_runs"], 0)
        self.assertEqual(p2["cached_runs"], 60)                                     # 두 번째는 조각을 다시 돌리지 않음
        self.assertEqual([e for e in a if e["type"] == "metrics"][-1]["data"]["monsters"],
                         [e for e in b if e["type"] == "metrics"][-1]["data"]["monsters"])
        self.assertLess(time.perf_counter() - t0, 30)

    def test_cancel(self):
        jid = self.sb.job({"kind": "monster_metrics", "stages": [200000], "chunk": 250, "edits": [hp_edit(222)]})
        time.sleep(0.5)
        code, _ = self.sb.req("DELETE", f"/api/jobs/{jid}")
        self.assertEqual(code, 200)
        evs = self.sb.events(jid)
        self.assertEqual(evs[-1]["type"], "cancelled")

    def test_bad_edit_is_error(self):
        evs = self.run_metrics(stages=[10], edits=[{"target": "monster", "mid": "NoSuchMonster", "key": "hp", "old": 1, "new": 2}])
        self.assertEqual(evs[-1]["type"], "error")

    def test_not_blocked_by_long_job(self):
        """전체 재계산처럼 오래 걸리는 작업이 도는 동안에도 몬스터 지표는 바로 계산된다 (예전에는 그 뒤에 줄을 서서 표가 안 바뀌었다)."""
        big = self.sb.job({"kind": "recompute", "client": "other", "x_values": [500, 600, 700], "stages": [300000]})
        try:
            time.sleep(1.0)
            t0 = time.perf_counter()
            evs = self.run_metrics(client="meB", stages=[40], chunk=40, edits=[hp_edit(444)])
            self.assertEqual(evs[-1]["type"], "done")
            self.assertLess(time.perf_counter() - t0, 60)
            self.assertFalse(self.sb.app.jobs.jobs[big].done)               # 긴 작업은 아직 돌고 있다
        finally:
            self.sb.req("DELETE", f"/api/jobs/{big}")
            self.sb.events(big)

    def test_other_client_not_cancelled(self):
        # 같은 기기의 곡선 재계산(client=A)과 몬스터 지표(client=Am)는 서로 취소하지 않는다
        j1 = self.sb.job({"kind": "monster_metrics", "client": "Am", "stages": [60], "chunk": 30, "edits": [hp_edit(333)]})
        j2 = self.sb.job({"kind": "recompute", "client": "A", "x_values": [500], "stages": [30]})
        e1, e2 = self.sb.events(j1), self.sb.events(j2)
        self.assertEqual(e1[-1]["type"], "done")
        self.assertEqual(e2[-1]["type"], "done")


@unittest.skipIf(sync_playwright is None, "playwright 미설치")
class MonsterTabUI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.makedirs(SHOTS, exist_ok=True)
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

    def open(self):
        ctx = self.browser.new_context(viewport={"width": 1400, "height": 1000})
        pg = ctx.new_page()
        errs = []
        pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.add_init_script("window.__MMSTAGES = [40, 80];")                          # 테스트용으로 판 수를 줄임
        self.sb.req("DELETE", "/api/workspace")   # v4.4: 앞 테스트의 자동 저장 상태가 복원되지 않게
        pg.goto(f"http://127.0.0.1:{self.sb.port}/#t=mon")
        pg.wait_for_function("window.__viewerReady === true", timeout=90000)
        return ctx, pg, errs

    FRESH = "document.querySelector('#mmBanner') && document.querySelector('#mmBanner').textContent.includes('현재 편집 반영')"
    HPCELLS = "Array.from(document.querySelectorAll('#monMetricsTable #monTable tbody tr')).map(r => r.cells[3].innerText.trim())"

    def test_edit_updates_metrics_table(self):
        ctx, pg, errs = self.open()
        pg.wait_for_function(self.FRESH, timeout=120000)                              # 처음 열면 현재 데이터로 서버 계산
        self.assertIn("80판", pg.inner_text("#mmBanner"))
        self.assertNotIn("5000", pg.evaluate(self.HPCELLS))
        hp = f'#monEdit tr[data-mid="{MID}"] input.monIn'
        pg.fill(hp, "5000")
        pg.dispatch_event(hp, "change")
        pg.wait_for_function(f"({self.HPCELLS}).includes('5000')", timeout=120000)    # 편집한 체력이 표에 반영
        pg.wait_for_function(self.FRESH, timeout=120000)
        self.assertEqual(errs, [])
        ctx.close()

    def test_button_mode_shows_stale_until_clicked(self):
        ctx, pg, errs = self.open()
        pg.wait_for_function(self.FRESH, timeout=120000)
        pg.select_option("#rcMode", "button")
        hp = f'#monEdit tr[data-mid="{MID}"] input.monIn'
        pg.fill(hp, "4321")
        pg.dispatch_event(hp, "change")
        pg.wait_for_selector("#mmNow")                                                # 이전 값 표시 + 지금 계산
        self.assertIn("이전 값", pg.inner_text("#mmBanner"))
        self.assertFalse(pg.evaluate("window.__MM.running"))
        self.assertNotIn("4321", pg.evaluate(self.HPCELLS))
        pg.click("#mmNow")
        pg.wait_for_function(f"({self.HPCELLS}).includes('4321')", timeout=120000)
        self.assertEqual(errs, [])
        ctx.close()


if __name__ == "__main__":
    unittest.main()
