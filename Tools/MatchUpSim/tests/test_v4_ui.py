# -*- coding: utf-8 -*-
"""v4 UI (Playwright): AC-R5 (JSON 탭에서 낫 amount 를 바꿔 저장 → 실선·점선·수정 효과·기준 칩, 라이트·다크 스크린샷),
AC-R2 의 'JSON 편집 시뮬 값 변화 없음' 안내, 피해 모델 digits 전환(모델 혼합 배지·몬스터 탭 반영 표시), AC-G2(12 + 5항)."""
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)

from test_server import SHOTS, Sandbox, read_all  # noqa: E402

try:
    from playwright.sync_api import sync_playwright
except ImportError:  # pragma: no cover
    sync_playwright = None

SCY = "fan_damage_scythe"


@unittest.skipIf(sync_playwright is None, "playwright 미설치")
class V4UI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.makedirs(SHOTS, exist_ok=True)
        cls.sb = Sandbox(xs="400:800:200", runs="200", stages="100,200")
        cls.pw = sync_playwright().start()
        ch = os.environ.get("VIEWER_BROWSER_CHANNEL", "msedge")
        cls.browser = cls.pw.chromium.launch(**({"channel": ch} if ch else {}))

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.pw.stop()
        cls.sb.stop()
        cls.sb.cleanup()

    def setUp(self):
        for k, i in list(self.sb.app.overlay.work):
            self.sb.req("POST", f"/api/files/{k}/{i}/revert", {})
        self.sb.req("POST", "/api/reference/pin", {"source": "disk"})

    def page(self, hash_="#t=curve&x=600", scheme="light"):
        ctx = self.browser.new_context(viewport={"width": 1400, "height": 1000}, color_scheme=scheme)
        pg = ctx.new_page()
        errs = []
        pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.goto(f"http://127.0.0.1:{self.sb.port}/{hash_}")
        pg.wait_for_function("window.__viewerReady === true")
        return ctx, pg, errs

    def wait_job(self, pg, kind=None, timeout=180000):
        pg.wait_for_function("(k) => window.__lastJob && window.__lastJob.end != null && (!k || window.__lastJob.kind === k)",
                             arg=kind, timeout=timeout)
        return pg.evaluate("window.__lastJob")

    def json_edit(self, pg, fid, old, new):
        pg.evaluate(f"() => {{ window.__JS.kind = 'fantasy'; window.__JS.id = '{fid}'; window.__JS.loaded = null; }}")
        pg.click('.tab[data-t="json"]')
        pg.wait_for_selector("#jsText")
        pg.wait_for_function("() => document.querySelector('#jsText').value.length > 50")
        txt = pg.eval_on_selector("#jsText", "e => e.value")
        self.assertIn(old, txt)
        pg.fill("#jsText", txt.replace(old, new))
        pg.click("#jsSave")

    def test_r5_json_ghost(self):
        src0 = read_all(self.sb.src)
        for scheme in ("light", "dark"):
            self.setUp()
            ctx, pg, errs = self.page(f"#t=curve&x=600&f={SCY}", scheme)
            pg.wait_for_selector("#refChip #refLabel")
            self.assertIn("디스크 원본", pg.inner_text("#refChip"))
            self.assertTrue(pg.is_visible("#refSame"))
            self.json_edit(pg, SCY, '"amount":  20.0', '"amount":  1.0')
            self.assertEqual(self.wait_job(pg, "recompute")["result"]["type"], "done")
            pg.click('.tab[data-t="curve"]')
            pg.wait_for_selector("#refDiff")
            pg.wait_for_function(f"() => document.querySelectorAll('#chart path.ghost').length >= 2")
            ghosts = pg.eval_on_selector_all("#chart path.ghost", "ps => ps.map(p => p.getAttribute('data-id'))")
            self.assertIn(SCY + "_ghost", ghosts)
            self.assertIn("__baseline___ghost", ghosts)
            self.assertTrue(pg.query_selector(f'#chart path.series[data-id="{SCY}"]'))
            self.assertIn("점선 = 수정 전", pg.inner_text("#legend"))
            ee = pg.evaluate(f"() => [...window.__LIVE.after['{SCY}'].values()].filter(p => p.edit_effect != null).length")
            self.assertGreater(ee, 0)
            # 고스트 토글
            pg.uncheck("#ghostToggle")
            pg.wait_for_function("() => document.querySelectorAll('#chart path.ghost').length === 0")
            pg.check("#ghostToggle")
            pg.wait_for_function("() => document.querySelectorAll('#chart path.ghost').length >= 2")
            pg.screenshot(path=os.path.join(SHOTS, f"v4_json_ghost_{scheme}.png"), full_page=True)
            # 기준 다시 잡기 → 고스트 해제
            pg.click("#btnPin")
            pg.wait_for_selector("#refSame")
            self.assertEqual(errs, [])
            ctx.close()
        self.assertEqual(read_all(self.sb.src), src0)       # 원본은 그대로 (작업 사본만)

    def test_r2_whitespace_notice(self):
        ctx, pg, errs = self.page(f"#t=curve&x=600&f={SCY}")
        self.json_edit(pg, SCY, '"rarity":  "blue"', '"rarity":"blue"')
        pg.wait_for_function("() => window.__jsonSave && window.__jsonSave.saved")
        self.assertFalse(pg.evaluate("window.__jsonSave.sim_changed"))
        pg.wait_for_selector("#jsNote")
        self.assertIn("시뮬 값 변화 없음", pg.inner_text("#jsNote"))
        self.assertIsNone(pg.evaluate("window.__lastJob"))            # 재계산 작업을 시작하지 않음 (계산 점 0개)
        self.assertEqual(errs, [])
        ctx.close()

    def test_digits_switch_and_guide(self):
        ctx, pg, errs = self.page(f"#t=curve&x=600&f=fan_turn_boots")
        self.assertTrue(pg.is_visible("#modelWrap"))
        pg.select_option("#dmodel", "digits+g")
        self.assertEqual(self.wait_job(pg, "recompute")["result"]["type"], "done")
        pg.wait_for_selector("#modelMix")
        self.assertIn("피해 모델 혼합", pg.inner_text("#modelBadge"))
        cs = pg.evaluate("window.__S.cfgSet")
        self.assertEqual(cs.get("monsters.damage_model"), "digits")
        self.assertEqual(cs.get("monsters.model"), "table")
        # 환상 충실도가 digits 기준으로 바뀐다 (예: 종이학 approx → exact)
        self.assertEqual(pg.evaluate("window.__BYID['fan_start_papercrane'].fidelity"), "exact")
        pg.click('.tab[data-t="mon"]')
        pg.wait_for_selector("#monFid")
        self.assertIn("digits + 기믹", pg.inner_text("#monModel"))
        pg.screenshot(path=os.path.join(SHOTS, "v4_digits_monsters_light.png"), full_page=True)
        pg.select_option("#dmodel", "gauss")
        pg.wait_for_function("() => !window.__S.cfgSet['monsters.damage_model']")
        self.assertEqual(pg.evaluate("window.__BYID['fan_start_papercrane'].fidelity"), "approx")
        pg.click('.tab[data-t="guide"]')
        self.assertEqual(len(pg.query_selector_all("#guideList li")), 17)
        pg.click('a.info[data-g="13"]', force=True) if pg.query_selector('a.info[data-g="13"]:visible') else None
        self.assertEqual(errs, [])
        ctx.close()


if __name__ == "__main__":
    unittest.main()
