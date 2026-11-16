# -*- coding: utf-8 -*-
"""v4.4 뷰어: 작업 공간 자동 저장·복원 (AC-W1·W3·W12·W13) 과 내려받기 UI (AC-X11).  Playwright."""
import io
import json
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)

import build_viewer  # noqa: E402
from test_server import SHOTS, Sandbox  # noqa: E402
from test_viewer import synthetic_data  # noqa: E402

try:
    from playwright.sync_api import sync_playwright
except ImportError:  # pragma: no cover
    sync_playwright = None

SCYTHE, BOOTS, ANCHOR = "fan_damage_scythe", "fan_turn_boots", "fan_damage_anchor"
SAVED = "window.__WS && window.__WS.status === 'saved' && !window.__WS.dirty"


@unittest.skipIf(sync_playwright is None, "playwright 미설치")
class WorkspaceUI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.makedirs(SHOTS, exist_ok=True)
        cls.pw = sync_playwright().start()
        ch = os.environ.get("VIEWER_BROWSER_CHANNEL", "msedge")
        cls.browser = cls.pw.chromium.launch(**({"channel": ch} if ch else {}))

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.pw.stop()

    def setUp(self):
        self.sb = Sandbox(xs="500:700:200", runs="30", stages="20,30")

    def tearDown(self):
        self.sb.stop()
        self.sb.cleanup()

    def open(self, hash_="#t=curve", ctx=None):
        ctx = ctx or self.browser.new_context(viewport={"width": 1400, "height": 1000})
        ctx.add_init_script("window.__IMMEDIATE_EDITS = true")   # v4.5 F17: 이 테스트는 즉시 반영 흐름을 검증한다
        pg = ctx.new_page()
        errs = []
        pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.goto(f"http://127.0.0.1:{self.sb.port}/{hash_}")
        pg.wait_for_function("window.__viewerReady === true", timeout=90000)
        return ctx, pg, errs

    def edit(self, pg, fid, delta=1):
        if not pg.query_selector(f'#list .row[data-id="{fid}"] input:checked'):
            pg.click(f'#list .row[data-id="{fid}"] input')
        sel = f'#detail .editor[data-fid="{fid}"] input.val'
        pg.wait_for_selector(sel)
        v = float(pg.input_value(sel))
        pg.fill(sel, str(round(v + delta, 6)))
        pg.dispatch_event(sel, "change")

    # --- AC-W1 / W3
    def test_w1_w3_reload_restores_edits_undo_and_view(self):
        ctx, pg, errs = self.open()
        pg.select_option("#metric", "delta")
        self.edit(pg, SCYTHE, 1)
        self.edit(pg, SCYTHE, 2)
        self.edit(pg, BOOTS, 1)
        n_undo = pg.evaluate("window.__S.undo.length")
        self.assertGreaterEqual(n_undo, 3)
        pg.wait_for_function(SAVED, timeout=20000)
        self.assertIn("저장됨", pg.inner_text("#wsChip"))
        edits = pg.evaluate("window.__S.edits")
        ctx.close()
        ctx2, pg2, errs2 = self.open("")                                              # 해시 없는 주소로 새로 연다
        self.assertEqual(pg2.evaluate("window.__S.edits"), edits)                     # 편집 개수와 값이 같다
        self.assertEqual(pg2.evaluate("window.__S.undo.length"), n_undo)             # 실행 취소 단계도 (AC-W3)
        self.assertEqual(pg2.evaluate("window.__S.metric"), "delta")                 # 보기 상태
        self.assertIn("이전 작업을 복원했습니다", pg2.inner_text("#wsBanner"))
        self.assertIn("변경 2", pg2.inner_text("#wsBanner"))
        for _ in range(3):                                                            # 실행 취소를 3번 할 수 있다
            pg2.click("#btnUndo")
        self.assertEqual(pg2.evaluate("window.__S.undo.length"), n_undo - 3)
        self.assertEqual(errs + errs2, [])
        ctx2.close()

    def test_w1_hash_overrides_saved_view(self):
        ctx, pg, _ = self.open("#t=curve&m=delta")
        self.edit(pg, SCYTHE, 1)
        pg.wait_for_function(SAVED, timeout=20000)
        ctx.close()
        ctx2, pg2, errs = self.open("#t=rank&m=floor")                                # 해시가 보기 상태보다 우선
        self.assertEqual(pg2.evaluate("window.__S.tab"), "rank")
        self.assertEqual(pg2.evaluate("window.__S.metric"), "floor")
        self.assertEqual(len(pg2.evaluate("window.__S.edits")), 1)
        self.assertEqual(errs, [])
        ctx2.close()

    # --- AC-W9 (뷰어): 새로고침하면 저장된 계산이 돌아온다
    def test_w9_curves_come_back_from_cache(self):
        ctx, pg, _ = self.open()
        self.edit(pg, SCYTHE, 1)
        pg.wait_for_function("window.__lastJob && window.__lastJob.result && window.__lastJob.kind === 'recompute'", timeout=120000)
        pg.wait_for_function(SAVED, timeout=20000)
        before = self.sb.app.engine.runs_computed
        ctx.close()
        ctx2, pg2, errs = self.open("")
        pg2.wait_for_function("window.__lastJob && window.__lastJob.result && window.__lastJob.kind === 'recompute'", timeout=60000)
        self.assertEqual(self.sb.app.engine.runs_computed, before)                    # 새로 돌린 판 0
        self.assertIn("저장된 계산 불러옴", pg2.inner_text("#wsBanner"))
        self.assertTrue(pg2.evaluate("Object.keys(window.__LIVE.after).length > 0"))
        self.assertEqual(errs, [])
        ctx2.close()

    def test_reload_after_full_recompute_has_no_stale_badges(self):
        """편집 + 전체 재계산 뒤 새로고침해도 모든 환상이 '이전 데이터'가 되지 않는다 (저장된 계산을 전부 불러온다)."""
        ctx, pg, _ = self.open("#t=curve")
        self.edit(pg, SCYTHE, 1)
        pg.wait_for_function("window.__lastJob && window.__lastJob.kind === 'recompute' && window.__lastJob.result", timeout=120000)
        pg.click("#btnFull")
        pg.wait_for_function("window.__lastJob && window.__lastJob.kind === 'scan' && window.__lastJob.result", timeout=180000)
        pg.wait_for_function(SAVED, timeout=20000)
        pg.click('.tab[data-t="rank"]')
        self.assertEqual(len(pg.query_selector_all("#rank .badge.stale")), 0)           # 전체 재계산 직후는 이전 배지 없음
        before = self.sb.app.engine.runs_computed
        ctx.close()
        ctx2, pg2, errs = self.open("#t=rank")
        pg2.wait_for_function("window.__lastJob && window.__lastJob.kind === 'recompute' && window.__lastJob.result", timeout=120000)
        pg2.wait_for_timeout(800)
        self.assertEqual(self.sb.app.engine.runs_computed, before)                       # 저장된 계산만 읽었다
        stale = len(pg2.query_selector_all("#rank .badge.stale"))
        total = len(pg2.query_selector_all("#rank tbody tr"))
        self.assertGreater(total, 50)
        self.assertEqual(stale, 0, f"새로고침 뒤 이전 배지 {stale}/{total}")
        self.assertEqual(errs, [])
        ctx2.close()

    # --- AC-W12
    def test_w12_save_failure_retry_and_no_loss(self):
        ctx, pg, errs = self.open()
        pg.route("**/api/workspace", lambda route: route.fulfill(status=500, content_type="application/json", body=json.dumps({"error": "주입 실패"}))
                 if route.request.method == "PUT" else route.continue_())
        self.edit(pg, SCYTHE, 1)
        pg.wait_for_function("window.__WS.status === 'fail'", timeout=20000)
        self.assertIn("저장 실패", pg.inner_text("#wsChip"))
        self.assertEqual(len(pg.evaluate("window.__S.edits")), 1)                     # 편집은 막지 않고 잃지 않는다
        self.edit(pg, SCYTHE, 2)
        self.assertEqual(len(pg.evaluate("window.__S.edits")), 1)
        pg.unroute("**/api/workspace")
        pg.click("#wsRetry")
        pg.wait_for_function(SAVED, timeout=20000)                                    # 복구되면 저장됨
        s, w = self.sb.req("GET", "/api/workspace")
        self.assertEqual(len(w["state"]["edits"]), 1)
        self.assertGreater(abs(w["state"]["edits"][0]["new"] - w["state"]["edits"][0]["old"]), 2.9)   # 마지막 편집값까지 저장됨
        ctx.close()

    # --- AC-W13
    def test_w13_concurrent_tabs_409_nothing_lost(self):
        ctx, a, errs_a = self.open()
        ctx_b, b, errs_b = self.open()                                                # b 는 rev 0 으로 열려 있음
        self.edit(a, SCYTHE, 1)
        a.wait_for_function(SAVED, timeout=20000)
        self.edit(b, BOOTS, 1)                                                        # b 가 옛 rev 로 저장 → 409
        b.wait_for_function("window.__WS.status === 'conflict'", timeout=20000)
        self.assertIn("다른 기기에서 수정됨", b.inner_text("#wsChip"))
        b.click("#wsTake")                                                            # 서버 값 채택, 내 변경은 보류
        b.wait_for_function(SAVED, timeout=20000)
        fids = {e["fid"] for e in b.evaluate("window.__S.edits")}
        held = [h["item"]["fid"] for h in b.evaluate("window.__WS.held") if h["type"] == "edit"]
        self.assertEqual(fids, {SCYTHE})
        self.assertEqual(held, [BOOTS])                                               # 아무것도 사라지지 않는다
        self.assertIn("보류 1건", b.inner_text("#wsBanner"))
        s, w = self.sb.req("GET", "/api/workspace")
        self.assertEqual([h["item"]["fid"] for h in w["state"]["held"]], [BOOTS])     # 보류도 서버에 남는다
        # 보류 항목 '그래도 적용'
        b.click("#wsHeldBtn")
        b.wait_for_selector(".heldApply")
        b.click(".heldApply")
        b.wait_for_function("window.__S.edits.length === 2", timeout=20000)
        self.assertEqual(b.evaluate("window.__WS.held.length"), 0)
        self.assertEqual(errs_a + errs_b, [])
        ctx.close()
        ctx_b.close()

    def test_conflict_force_overwrite(self):
        ctx, a, _ = self.open()
        ctx_b, b, _ = self.open()
        self.edit(a, SCYTHE, 1)
        a.wait_for_function(SAVED, timeout=20000)
        self.edit(b, BOOTS, 1)
        b.wait_for_function("window.__WS.status === 'conflict'", timeout=20000)
        b.click("#wsForce")
        b.wait_for_function(SAVED, timeout=20000)
        s, w = self.sb.req("GET", "/api/workspace")
        self.assertEqual({e["fid"] for e in w["state"]["edits"]}, {BOOTS, SCYTHE} & {e["fid"] for e in b.evaluate("window.__S.edits")})
        ctx.close()
        ctx_b.close()

    # --- 내려받기 UI (서버 모드)
    def test_server_csv_button_and_dialog(self):
        ctx, pg, errs = self.open()
        with pg.expect_download() as dl:
            pg.click('.csvBtn[data-ds="curves"]')
        d = dl.value
        raw = open(d.path(), "rb").read()
        self.assertTrue(raw.startswith(b"\xef\xbb\xbf"))                              # BOM
        self.assertIn("series,fantasy_id", raw[3:].decode("utf-8").split("\r\n")[0])
        self.assertTrue(d.suggested_filename.startswith("matchup_curves_"))
        pg.click("#btnExport")
        pg.wait_for_selector("#exGo")
        pg.wait_for_function("document.querySelector('#exEst').textContent.includes('예상')")
        pg.check(".exds[value=runs]")
        pg.check("#exZip")
        with pg.expect_download() as dl2:
            pg.click("#exGo")
        self.assertTrue(dl2.value.suggested_filename.endswith(".zip"))
        self.assertEqual(errs, [])
        ctx.close()


@unittest.skipIf(sync_playwright is None, "playwright 미설치")
class StaticExport(unittest.TestCase):
    def test_x11_static_html_exports(self):
        d = synthetic_data()
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "v.html")
            with open(path, "w", encoding="utf-8") as fp:
                fp.write(build_viewer.build(d))
            with sync_playwright() as pw:
                ch = os.environ.get("VIEWER_BROWSER_CHANNEL", "msedge")
                b = pw.chromium.launch(**({"channel": ch} if ch else {}))
                pg = b.new_page(viewport={"width": 1400, "height": 1000}, accept_downloads=True)
                errs = []
                pg.on("pageerror", lambda e: errs.append(str(e)))
                pg.goto("file:///" + path.replace("\\", "/") + "#t=curve")
                pg.wait_for_function("window.__viewerReady === true")
                with pg.expect_download() as dl:
                    pg.click('.csvBtn[data-ds="curves"]')
                raw = open(dl.value.path(), "rb").read()
                self.assertTrue(raw.startswith(b"\xef\xbb\xbf"))
                lines = raw[3:].decode("utf-8").strip().split("\r\n")
                self.assertIn("series,fantasy_id,fantasy_name", lines[0])
                self.assertGreater(len(lines), 1)
                pg.click('.tab[data-t="rank"]')
                with pg.expect_download() as dl2:
                    pg.click('.csvBtn[data-ds="ranking"]')
                rk = open(dl2.value.path(), "rb").read().decode("utf-8")
                self.assertIn("fantasy_id,fantasy_name,grade", rk)
                self.assertEqual(len(rk.strip().split("\r\n")) - 1, len(d["fantasies"]))   # 환상마다 한 행
                pg.click("#btnExport")                                                    # runs·bundle 은 비활성이고 이유가 보인다
                pg.wait_for_selector("#exGo")
                self.assertTrue(pg.is_disabled(".exds[value=runs]"))
                self.assertTrue(pg.is_disabled("#exZip"))
                self.assertIn("서버 전용", pg.inner_text(".exgrid"))
                self.assertIn("정적 HTML", pg.inner_text("#exEst"))
                self.assertEqual(errs, [])
                b.close()


if __name__ == "__main__":
    unittest.main()
