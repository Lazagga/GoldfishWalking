# -*- coding: utf-8 -*-
"""v4.3 F13 환상 편집 패널 접근성 (AC-D1~D7) + 재계산 사이에 계산해 둔 곡선 유지.

- AC-D1 체크하면 패널이 그 환상으로 열리고, 풀면 남은 선택으로, 없으면 빈 상태 안내.
- AC-D2 해시 p= 로 패널 대상 복원, 없는 ID·옛 링크도 오류 없음.
- AC-D3 빈 상태 안내.  AC-D4 다른 탭의 '편집 패널 열기' 칩과 목록의 편집 버튼.
- AC-D5 부가 호출 실패(/api/reference 500) → '일부 기능 실패' + 편집기 활성,
        필수 호출 실패(/api/fantasies) → 원인 안내 + '다시 연결'.
- AC-D6 정적 HTML.  AC-D7 /api/ping 의 build, 바뀌면 재시작 안내.
"""
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
import viewer_server  # noqa: E402
from test_server import SHOTS, Sandbox  # noqa: E402
from test_viewer import synthetic_data  # noqa: E402

try:
    from playwright.sync_api import sync_playwright
except ImportError:  # pragma: no cover
    sync_playwright = None

SCYTHE, BOOTS, ANCHOR = "fan_damage_scythe", "fan_turn_boots", "fan_damage_anchor"


class Build(unittest.TestCase):
    def test_build_changes_with_code(self):
        b0 = viewer_server.code_build()
        self.assertEqual(len(b0), 10)
        p = os.path.join(ROOT, "viewer_server.py")
        st = os.stat(p)
        try:
            os.utime(p, ns=(st.st_atime_ns, st.st_mtime_ns + 10_000_000_000))   # 코드 파일이 바뀐 것처럼
            self.assertNotEqual(viewer_server.code_build(), b0)
        finally:
            os.utime(p, ns=(st.st_atime_ns, st.st_mtime_ns))
        self.assertEqual(viewer_server.code_build(), b0)


@unittest.skipIf(sync_playwright is None, "playwright 미설치")
class Panel(unittest.TestCase):
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

    def open(self, hash_="#t=curve", routes=None, height=1000):
        ctx = self.browser.new_context(viewport={"width": 1400, "height": height})
        pg = ctx.new_page()
        errs, cons = [], []
        pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.on("console", lambda m: cons.append(m.text) if m.type == "error" else None)
        def fail_with(status):
            def handler(route):
                route.fulfill(status=status, content_type="application/json", body=json.dumps({"error": "테스트 실패 주입"}))
            return handler
        for pat, status in (routes or {}).items():
            pg.route(pat, fail_with(status))
        pg.goto(f"http://127.0.0.1:{self.sb.port}/{hash_}")
        pg.wait_for_function("window.__viewerReady === true", timeout=90000)
        return ctx, pg, errs, cons

    def editors(self, pg, fid):
        return pg.query_selector_all(f'#detail .editor[data-fid="{fid}"] input.val')

    def test_d1_d3_check_opens_panel(self):
        ctx, pg, errs, _ = self.open()
        self.assertIn("환상 이름을 누르거나 체크하면", pg.inner_text("#detailEmpty"))          # AC-D3
        pg.click(f'#list .row[data-id="{SCYTHE}"] input')
        pg.wait_for_selector(f'#detail .editor[data-fid="{SCYTHE}"]')
        self.assertGreater(len(self.editors(pg, SCYTHE)), 0)
        self.assertFalse(self.editors(pg, SCYTHE)[0].is_disabled())
        pg.click(f'#list .row[data-id="{BOOTS}"] input')
        pg.wait_for_selector(f'#detail .editor[data-fid="{BOOTS}"]')                          # 체크한 환상으로 이동
        pg.click(f'#list .row[data-id="{BOOTS}"] input')
        pg.wait_for_selector(f'#detail .editor[data-fid="{SCYTHE}"]')                         # 풀면 남은 선택으로
        self.assertIn(f"p={SCYTHE}", pg.evaluate("location.hash"))
        pg.click(f'#list .row[data-id="{SCYTHE}"] input')
        pg.wait_for_selector("#detailEmpty")                                                  # 선택 없음 → 안내
        self.assertNotIn("p=", pg.evaluate("location.hash"))
        self.assertEqual(errs, [])
        ctx.close()

    def test_d2_hash_restore(self):
        ctx, pg, errs, _ = self.open(f"#t=curve&p={SCYTHE}")
        pg.wait_for_selector(f'#detail .editor[data-fid="{SCYTHE}"]')
        ctx.close()
        ctx, pg, errs2, _ = self.open("#t=curve&p=fan_does_not_exist&m=win")
        pg.wait_for_selector("#detailEmpty")
        ctx.close()
        ctx, pg, errs3, _ = self.open(f"#m=win&x=600&t=curve&f={ANCHOR},{BOOTS}")              # p 없는 옛 링크 → 선택의 마지막
        pg.wait_for_selector(f'#detail .editor[data-fid="{BOOTS}"]')
        self.assertEqual(errs + errs2 + errs3, [])
        ctx.close()

    def test_d4_tab_chip_and_edit_button(self):
        ctx, pg, errs, _ = self.open(f"#t=surv&f={ANCHOR}", height=700)
        pg.wait_for_selector("#btnPanelChip")
        self.assertIn("편집 패널 열기", pg.inner_text("#btnPanelChip"))
        pg.click("#btnPanelChip")
        pg.wait_for_selector(f'#detail .editor[data-fid="{ANCHOR}"]')
        self.assertEqual(pg.evaluate("window.__S.tab"), "curve")
        inview = "() => { const r = document.querySelector('#detail').getBoundingClientRect(); return r.top < window.innerHeight && r.bottom > 0; }"
        pg.wait_for_function(inview)
        pg.click('.tab[data-t="rank"]')
        pg.click(f'#list .row[data-id="{BOOTS}"] .editBtn')                                     # 목록의 편집 버튼
        pg.wait_for_selector(f'#detail .editor[data-fid="{BOOTS}"]')
        self.assertEqual(pg.evaluate("window.__S.tab"), "curve")
        pg.wait_for_function(inview)
        self.assertEqual(errs, [])
        ctx.close()

    def test_d5_partial_failure(self):
        ctx, pg, errs, cons = self.open(f"#t=curve&p={SCYTHE}", routes={"**/api/reference": 500})
        self.assertIn("일부 기능 실패", pg.inner_text("#modeBadge"))
        self.assertIn("/api/reference", pg.get_attribute("#modeBadge", "title"))
        self.assertTrue(any("/api/reference" in c for c in cons))
        pg.wait_for_selector(f'#detail .editor[data-fid="{SCYTHE}"]')
        self.assertFalse(self.editors(pg, SCYTHE)[0].is_disabled())                            # 편집은 그대로 가능
        self.assertEqual(errs, [])
        ctx.close()

    def test_d5_required_failure_and_reconnect(self):
        ctx, pg, errs, cons = self.open(f"#t=curve&p={SCYTHE}", routes={"**/api/fantasies": 500})
        self.assertIn("서버 연결 실패", pg.inner_text("#modeBadge"))
        txt = pg.inner_text("#srvFail")
        self.assertIn("/api/fantasies", txt)
        self.assertIn("HTTP 500", txt)
        self.assertTrue(any("/api/fantasies" in c for c in cons))
        pg.unroute("**/api/fantasies")
        pg.click("#btnReconnect")
        pg.wait_for_function("document.querySelector('#modeBadge').textContent === '서버 모드 · 편집 가능'")
        pg.wait_for_selector(f'#detail .editor[data-fid="{SCYTHE}"]')
        self.assertEqual(pg.locator("#srvFail").count(), 0)
        self.assertEqual(errs, [])
        ctx.close()

    def test_d7_build_and_restart_notice(self):
        code, ping = self.sb.req("GET", "/api/ping")
        self.assertEqual(code, 200)
        self.assertEqual(ping["build"], self.sb.app.build)
        self.assertIn("started_at", ping)
        ctx, pg, errs, _ = self.open()
        self.assertIn(f"서버 build {ping['build']}", pg.get_attribute("#modeBadge", "title"))
        self.assertIn("SIM_VERSION", pg.get_attribute("#modeBadge", "title"))
        self.sb.app.build = "changed000"                                                       # 서버가 새 코드로 재시작된 것처럼
        try:
            pg.wait_for_function("document.querySelector('#modeBadge').textContent.includes('재시작')", timeout=15000)   # 3초 폴링
            pg.wait_for_selector("#srvRestart")
        finally:
            self.sb.app.build = ping["build"]
        self.assertEqual(errs, [])
        ctx.close()

    def test_apply_monster_hp_only(self):
        """몬스터 체력만 고치고 원본에 반영 — 몬스터 편집에는 fid 가 없어 'editable_keys' 오류가 나던 문제."""
        mon0 = {f: open(os.path.join(self.sb.mon, f), "rb").read() for f in os.listdir(self.sb.mon)}
        ctx, pg, errs, _ = self.open("#t=mon")
        hp = '#monEdit tr[data-mid="Mob_10102_WildDog"] input.monIn'
        pg.wait_for_selector(hp)
        pg.fill(hp, "150")
        pg.dispatch_event(hp, "change")
        self.assertTrue(pg.evaluate("window.__S.edits.some(e => e.target === 'monster' && e.new === 150)"))
        pg.click("#btnApply")
        pg.wait_for_selector("#applyGo")
        pg.click("#applyGo")
        pg.wait_for_selector("#okClose")
        self.assertIn("반영 완료", pg.inner_text(".modal"))
        pg.click("#okClose")
        self.assertEqual(pg.evaluate("window.__S.edits.length"), 0)
        self.assertIn(b"150", open(os.path.join(self.sb.mon, "mob_10102_wilddog.json"), "rb").read())
        pg.on("dialog", lambda d: d.accept())
        pg.click("#btnUnapply")
        pg.wait_for_timeout(1000)
        self.assertEqual({f: open(os.path.join(self.sb.mon, f), "rb").read() for f in os.listdir(self.sb.mon)}, mon0)
        self.assertEqual(errs, [])
        ctx.close()

    def test_live_curves_survive_new_recompute(self):
        """재계산이 새로 시작돼도 같은 데이터 기준으로 계산해 둔 곡선은 남는다 (체크를 풀면 '이전'이 다시 붙던 문제)."""
        ctx, pg, errs, _ = self.open("#t=curve")
        pg.evaluate("""() => {
          const L = window.__LIVE; L.after = {}; L.before = {};
          const mk = (h, tag) => new Map([[500, { x: 500, data_hash: h, cfg_tag: tag, win_rate: 0.5, n: 60 }]]);
          L.after.keep = mk("H1", ""); L.after.drop = mk("H0", ""); L.after.dropTag = mk("H1", "x");
          L.before.keep = mk("R1", ""); L.before.drop = mk("R0", "");
          window.__pruneLive("H1", "", "R1");
        }""")
        self.assertEqual(sorted(pg.evaluate("Object.keys(window.__LIVE.after)")), ["keep"])
        self.assertEqual(sorted(pg.evaluate("Object.keys(window.__LIVE.before)")), ["keep"])
        self.assertEqual(errs, [])
        ctx.close()


@unittest.skipIf(sync_playwright is None, "playwright 미설치")
class PanelStatic(unittest.TestCase):
    def test_d6_static(self):
        d = synthetic_data()
        fid = d["fantasies"][0]["id"]
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "v.html")
            with open(path, "w", encoding="utf-8") as fp:
                fp.write(build_viewer.build(d))
            with sync_playwright() as pw:
                ch = os.environ.get("VIEWER_BROWSER_CHANNEL", "msedge")
                b = pw.chromium.launch(**({"channel": ch} if ch else {}))
                pg = b.new_page(viewport={"width": 1400, "height": 1000})
                errs = []
                pg.on("pageerror", lambda e: errs.append(str(e)))
                url = "file:///" + path.replace("\\", "/")
                pg.goto(url + "#t=curve")
                pg.wait_for_function("window.__viewerReady === true")
                self.assertIn("편집은 서버 모드에서만", pg.inner_text("#detailEmpty"))
                pg.click(f'#list .row[data-id="{fid}"] input')
                pg.wait_for_function("document.querySelector('#detail').innerText.includes('편집은 서버 모드에서만 가능합니다')")
                self.assertEqual(pg.locator("#srvFail").count(), 0)
                self.assertEqual(errs, [])
                b.close()


if __name__ == "__main__":
    unittest.main()
