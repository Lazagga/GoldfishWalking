# -*- coding: utf-8 -*-
"""v4.1 F10 뷰어 (Playwright): AC-Y7(50ms·JS=파이썬), Y8(놓으면 실제 재계산·회색·대체·기록, 버튼만 모드),
Y10(근사 해), Y12(조합 미리보기 없음·JSON 단일 필드), Y17(몬스터: 기준선·단독 지표만, tier_avg 없음), 스크린샷."""
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

SLING, BOOTS = "fan_damage_slingshot", "fan_turn_boots"


class Base:
    @classmethod
    def start_browser(cls):
        cls.pw = sync_playwright().start()
        ch = os.environ.get("VIEWER_BROWSER_CHANNEL", "msedge")
        cls.browser = cls.pw.chromium.launch(**({"channel": ch} if ch else {}))

    @classmethod
    def stop_all(cls):
        cls.browser.close()
        cls.pw.stop()
        cls.sb.stop()
        cls.sb.cleanup()

    def page(self, hash_, scheme="light"):
        ctx = self.browser.new_context(viewport={"width": 1400, "height": 1000}, color_scheme=scheme)
        pg = ctx.new_page()
        errs = []
        pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.goto(f"http://127.0.0.1:{self.sb.port}/{hash_}")
        pg.wait_for_function("window.__viewerReady === true")
        return ctx, pg, errs

    @classmethod
    def train(cls, targets, n):
        s, r = cls.sb.req("POST", "/api/surrogate/fit", {"targets": targets, "n": n, "x_sel": 600})
        assert s == 200, r
        ev = cls.sb.events(r["id"], until=lambda e: e.get("type") in ("done", "error", "cancelled"))
        assert ev[-1]["type"] == "done", ev[-1]


@unittest.skipIf(sync_playwright is None, "playwright 미설치")
class FantasyPreview(Base, unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.makedirs(SHOTS, exist_ok=True)
        cls.sb = Sandbox(xs="400:800:200", runs="200", stages="200")
        cls.train([{"kind": "fantasy", "id": SLING, "field": "0.value"}, {"kind": "fantasy", "id": BOOTS, "field": "0.value"}], 1000)
        cls.start_browser()

    @classmethod
    def tearDownClass(cls):
        cls.stop_all()

    def open_detail(self, pg, fid):
        pg.click(f'#list .row[data-id="{fid}"] .fname')
        pg.wait_for_selector(f'#detail .editor[data-fid="{fid}"]')
        pg.wait_for_function("() => window.__SG && window.__SG.loaded")

    def slide(self, pg, fid, v, release=False):
        pg.evaluate("""([fid, v, rel]) => { const r = document.querySelector(`#detail .editor[data-fid="${fid}"] input.rng`);
            r.value = v; r.dispatchEvent(new Event('input', {bubbles: true})); if (rel) r.dispatchEvent(new Event('change', {bubbles: true})); }""",
                    [fid, v, release])

    def model(self, fid):
        return self.sb.req("GET", f"/api/surrogate/model?kind=fantasy&id={fid}&field=0.value")[1]

    def test_y7_y8_y10_flow(self):
        for scheme in ("light", "dark"):
            ctx, pg, errs = self.page(f"#t=curve&x=600&f={BOOTS}", scheme)
            self.open_detail(pg, BOOTS)
            m = self.model(BOOTS)
            self.assertIn(m["status"], ("신뢰", "주의"), m["status"])
            pg.wait_for_selector("#detail .sgOut .badge.sg")
            self.assertIn("linear-gradient", pg.get_attribute(f'#detail .editor[data-fid="{BOOTS}"] input.rng', "style") or "")
            # Y7: 입력 중 근사선, 서버 왕복·재계산 없음, 50ms 이내
            self.slide(pg, BOOTS, 3)
            pg.wait_for_selector("#chart path.sgline")
            self.assertLess(pg.evaluate("window.__sgLastMs"), 50)
            self.assertIsNone(pg.evaluate("window.__lastJob"))
            self.assertTrue(pg.is_visible("#sgLegend"))
            for th, a, ta in ((3, 0.3, 2), (1, None, None), (4, 0.55, 2)):
                js = pg.evaluate("([m, th, a, ta]) => window.__sgPredict(m, 600, th, a, ta)", [m, th, a, ta])
                q = f"&anchor={a}&theta_anchor={ta}" if a is not None else ""
                py = self.sb.req("GET", f"/api/surrogate/predict?kind=fantasy&id={BOOTS}&field=0.value&theta={th}&x=600{q}")[1]
                self.assertEqual(js.get("reject"), py.get("reject"))
                if "p" in py:
                    self.assertLess(abs(js["p"] - py["p"]), 1e-9)
                    self.assertLess(abs(js["band"] - py["band"]), 1e-9)
            # Y10: 근사 해 (즉시, 저장 안 함)
            pg.fill(f'#detail .editor[data-fid="{BOOTS}"] .solveT', "2")
            pg.wait_for_selector("#detail .sgSolve .sgSol, #detail #sgNoSol")
            pg.fill(f'#detail .editor[data-fid="{BOOTS}"] .solveT', "95")
            pg.wait_for_selector("#detail #sgNoSol")
            # Y8: 놓으면 실제 재계산 → 근사선 회색 → 완료 후 예측 − 실제 표시·기록
            self.slide(pg, BOOTS, 3, release=True)
            pg.wait_for_function("() => window.__lastJob && window.__lastJob.kind === 'recompute'")
            pg.wait_for_function("() => window.__lastJob.end != null", timeout=180000)
            pg.wait_for_selector("#sgAuditBox")
            self.assertIsNone(pg.evaluate("window.__S.preview"))
            pg.screenshot(path=os.path.join(SHOTS, f"v41_preview_audit_{scheme}.png"), full_page=True)
            self.assertEqual(errs, [])
            ctx.close()
        recs = self.sb.req("GET", "/api/surrogate/audit")[1]["records"]
        self.assertTrue(any(r["id"] == BOOTS and r["theta"] == 3 for r in recs))

    def test_y8_button_mode_and_screenshot(self):
        ctx, pg, errs = self.page(f"#t=curve&x=600&f={BOOTS}")
        self.open_detail(pg, BOOTS)
        pg.select_option("#rcMode", "button")
        self.slide(pg, BOOTS, 1)
        pg.wait_for_selector("#chart path.sgline")
        pg.screenshot(path=os.path.join(SHOTS, "v41_preview_drag_light.png"), full_page=True)
        self.slide(pg, BOOTS, 1, release=True)
        time.sleep(1.5)
        self.assertIsNone(pg.evaluate("window.__lastJob"))          # 버튼 전에는 재계산 없음
        self.assertTrue(pg.query_selector("#chart path.sgline"))     # 근사선 유지
        pg.click("#btnRecompute")
        pg.wait_for_function("() => window.__lastJob && window.__lastJob.kind === 'recompute' && window.__lastJob.end != null", timeout=180000)
        self.assertEqual(errs, [])
        ctx.close()

    def test_y12_combo_and_json(self):
        ctx, pg, errs = self.page(f"#t=curve&x=600&f={BOOTS},{SLING}")
        self.open_detail(pg, BOOTS)
        self.slide(pg, BOOTS, 3)
        pg.wait_for_selector("#sgComboNo")
        self.assertIn("미리보기 없음", pg.inner_text("#sgComboNo"))
        # JSON: 단일 수치 필드면 미리보기, 두 필드면 없음
        def json_save(fid, edits):
            pg.evaluate(f"() => {{ window.__jsonInfo = null; window.__JS.kind = 'fantasy'; window.__JS.id = '{fid}'; window.__JS.loaded = null; window.__JS.note = ''; }}")
            pg.click('.tab[data-t="curve"]')
            pg.click('.tab[data-t="json"]')
            pg.wait_for_function("() => window.__jsonInfo && document.querySelector('#jsText') && document.querySelector('#jsText').value.length > 50")
            txt = pg.eval_on_selector("#jsText", "e => e.value")
            for a, b in edits:
                self.assertIn(a, txt)
                txt = txt.replace(a, b)
            pg.evaluate("() => { window.__jsonSave = null; }")
            pg.fill("#jsText", txt)
            pg.click("#jsSave")
            pg.wait_for_function("() => window.__jsonSave && window.__jsonSave.saved && window.__jsonSaveDone")
        json_save(BOOTS, [('"amount":  2.0', '"amount":  3.0')])
        self.assertIsNotNone(pg.evaluate("window.__sgJson"))
        self.sb.req("POST", f"/api/files/fantasy/{BOOTS}/revert", {})
        json_save(BOOTS, [('"amount":  2.0', '"amount":  3.0'), ('"rarity":  "white"', '"rarity":  "red"')])
        self.assertIsNone(pg.evaluate("window.__sgJson"))
        self.sb.req("POST", f"/api/files/fantasy/{BOOTS}/revert", {})
        self.assertEqual(errs, [])
        ctx.close()

    def test_y17_tier_avg_monster(self):
        ctx, pg, errs = self.page("#t=mon&x=600")
        pg.wait_for_selector("#monEdit .monIn")
        sel = '#monEdit tr[data-mid="Mob_10101_Fairy"] .monIn'
        pg.fill(sel, "160")
        pg.wait_for_selector("#sgMonTier")
        self.assertIn("미리보기 없음", pg.inner_text("#sgMonTier"))
        self.assertEqual(errs, [])
        ctx.close()


@unittest.skipIf(sync_playwright is None, "playwright 미설치")
class MonsterPreview(Base, unittest.TestCase):
    MID = "Mob_10101_Fairy"

    @classmethod
    def setUpClass(cls):
        cls.sb = Sandbox(xs="0.6:1.0:0.2", runs="100", stages="300", table_model=True)
        cls.train([{"kind": "monster", "id": cls.MID, "field": "hp"}], 3000)
        cls.start_browser()

    @classmethod
    def tearDownClass(cls):
        cls.stop_all()

    def test_y17_y18_monster_preview(self):
        ctx, pg, errs = self.page("#t=mon&x=0.8")
        pg.wait_for_selector("#monEdit .monIn")
        pg.wait_for_function("() => window.__SG && window.__SG.loaded")
        sel = f'#monEdit tr[data-mid="{self.MID}"] .monIn'
        pg.focus(sel)                                     # 패널을 열면 단독 지표 모델 자동 학습 (Y18)
        pg.wait_for_function(f"() => window.__SG.probe['{self.MID}|hp']", timeout=180000)
        pg.fill(sel, "190")
        pg.wait_for_function("() => (window.__sgMonOut || '').includes('단독')")
        txt = pg.evaluate("window.__sgMonOut")
        self.assertIn("환상 곡선·조합: 미리보기 없음", txt)
        self.assertTrue("기준선 승률(근사" in txt or "기준선:" in txt, txt)
        self.assertEqual(pg.evaluate("window.__S.preview.kind"), "monster")
        pg.click('.tab[data-t="curve"]')
        pg.wait_for_selector("#sgMonNote")
        pg.screenshot(path=os.path.join(SHOTS, "v41_monster_preview_light.png"), full_page=True)
        self.assertEqual(errs, [])
        ctx.close()


if __name__ == "__main__":
    unittest.main()
