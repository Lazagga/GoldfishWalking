# -*- coding: utf-8 -*-
"""v4.2 UI (Playwright): AC-H4 X축 라벨·현재 값, AC-H9 규모 불일치 배지, AC-H7 몬스터 체력 리포트(편집 즉시 갱신),
AC-H8 승률 맞추기 패널(서버 작업 결과와 같음, 범위 밖 안내), AC-H3 구버전 배지."""
import json
import os
import sys
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

FAIRY = "Mob_10101_Fairy"


def hp_cells(mtable):
    with open(mtable, encoding="utf-8") as fp:
        mons = [m for m in json.load(fp)["monsters"] if m.get("enabled", True)]
    g = {}
    for m in mons:
        g.setdefault(f"{m['act']}|{m['tier']}", []).append(m["hp"])
    return {k: sum(v) / len(v) for k, v in g.items()}


@unittest.skipIf(sync_playwright is None, "playwright 미설치")
class V42UI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.makedirs(SHOTS, exist_ok=True)
        cls.sb = Sandbox(xs="100:200:50", runs="80", stages="40,80", start_hp=True)
        cls.pw = sync_playwright().start()
        ch = os.environ.get("VIEWER_BROWSER_CHANNEL", "msedge")
        cls.browser = cls.pw.chromium.launch(**({"channel": ch} if ch else {}))

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.pw.stop()
        cls.sb.stop()
        cls.sb.cleanup()

    def page(self, sb=None, hash_="#t=curve", scheme="light"):
        sb = sb or self.sb
        ctx = self.browser.new_context(viewport={"width": 1400, "height": 1000}, color_scheme=scheme)
        pg = ctx.new_page()
        errs = []
        pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.goto(f"http://127.0.0.1:{sb.port}/{hash_}")
        pg.wait_for_function("window.__viewerReady === true", timeout=90000)
        return ctx, pg, errs

    def test_h4_axis_and_h9_badge(self):
        ctx, pg, errs = self.page()
        head = pg.inner_text("#banner")
        self.assertIn("시작 체력 (player.start_hp)", head)
        self.assertEqual(pg.inner_text("#xCur"), "150")
        self.assertEqual(pg.locator("#legacyBadge").count(), 0)
        self.assertIn("현재 150", pg.text_content("#chart"))
        self.assertIn("시작 체력", pg.text_content("#chart"))
        self.assertEqual(pg.inner_html("#scaleBadge").strip(), "")          # table + digits: 배지 없음
        pg.select_option("#dmodel", "gauss")
        pg.wait_for_selector("#scaleWarn")
        self.assertIn("규모 불일치", pg.inner_text("#scaleWarn"))
        pg.select_option("#dmodel", "digits+g")
        pg.wait_for_function("() => !document.querySelector('#scaleWarn')")
        pg.screenshot(path=os.path.join(SHOTS, "v42_start_hp_axis.png"))
        self.assertEqual(errs, [])
        ctx.close()

    def test_h7_hp_report_live(self):
        ctx, pg, errs = self.page(hash_="#t=mon")
        pg.wait_for_selector("#hpReport #hpTable")
        exp = hp_cells(self.sb.mtable)
        got = pg.evaluate("() => { const R = window.__hpReportData(window.__monList()); const o = {}; for (const k in R.cell) o[k] = R.cell[k].mean; return o; }")
        for k, v in exp.items():
            self.assertAlmostEqual(got[k], v, places=6, msg=k)
        self.assertIn("1 : 3 : 5", pg.inner_text("#hpTarget"))
        self.assertIn("임시값", pg.inner_text("#hpTarget"))
        before = pg.inner_text('#hpTable td[data-c="1|easy"]')
        inp = pg.locator(f'tr[data-mid="{FAIRY}"] input.monIn').first
        inp.fill("1500")
        inp.dispatch_event("change")
        pg.wait_for_function("(b) => document.querySelector('#hpTable td[data-c=\"1|easy\"]').innerText !== b", arg=before)
        after = pg.inner_text('#hpTable td[data-c="1|easy"]')
        self.assertIn("1500", after)          # 최대값에 반영
        pg.screenshot(path=os.path.join(SHOTS, "v42_hp_report.png"))
        self.assertEqual(errs, [])
        ctx.close()

    def test_h8_tune_panel(self):
        ctx, pg, errs = self.page()
        pg.click("#btnTune")
        pg.wait_for_selector("#tunePanel #tuneRun")
        pg.fill("#tuneRuns", "40")
        pg.fill("#tuneSeed", "ui")
        pg.click("#tuneRun")
        pg.wait_for_selector("#tuneResult", timeout=300000)
        job = pg.evaluate("window.__lastJob")
        self.assertEqual(job["kind"], "tune")
        res = job["result"]["result"]
        self.assertIn(str(round(res["found"], 4)).rstrip("0").rstrip("."), pg.inner_text("#tuneResult"))
        self.assertEqual(pg.locator("#tuneTable tbody tr").count(), len(res["table"]["summary"]))
        pg.click("#tuneCopy")
        tsv = pg.evaluate("window.__tuneTsv")
        self.assertEqual(len(tsv.strip().split("\n")), 1 + len(res["table"]["monsters"]))
        # 범위 밖
        pg.select_option("#tuneKey", "player.start_hp")
        pg.fill("#tuneLo", "50")
        pg.fill("#tuneHi", "60")
        pg.fill("#tuneT", "99")
        pg.fill("#tuneRuns", "20")
        pg.click("#tuneRun")
        pg.wait_for_selector("#tuneNoSol", timeout=300000)
        pg.screenshot(path=os.path.join(SHOTS, "v42_tune_panel.png"))
        self.assertEqual(errs, [])
        ctx.close()



@unittest.skipIf(sync_playwright is None, "playwright 미설치")
class V42UILegacy(unittest.TestCase):
    """AC-H3: 과거 hp_base(tier_avg) 스캔이 열리고 구버전 배지가 붙는다 (별도 서버 — 다른 샌드박스와 겹치지 않게)."""

    @classmethod
    def setUpClass(cls):
        cls.sb = Sandbox(xs="500:700:200", runs="40", stages="20,40")
        cls.pw = sync_playwright().start()
        ch = os.environ.get("VIEWER_BROWSER_CHANNEL", "msedge")
        cls.browser = cls.pw.chromium.launch(**({"channel": ch} if ch else {}))

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.pw.stop()
        cls.sb.stop()
        cls.sb.cleanup()

    def test_h3_legacy_badge(self):
        ctx = self.browser.new_context(viewport={"width": 1400, "height": 1000})
        pg = ctx.new_page()
        errs = []
        pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.goto(f"http://127.0.0.1:{self.sb.port}/#t=curve")
        pg.wait_for_function("window.__viewerReady === true")
        self.assertTrue(pg.is_visible("#legacyBadge"))
        self.assertIn("평균 몬스터 체력(구버전)", pg.inner_text("#banner"))
        self.assertEqual(errs, [])
        ctx.close()


if __name__ == "__main__":
    unittest.main()
