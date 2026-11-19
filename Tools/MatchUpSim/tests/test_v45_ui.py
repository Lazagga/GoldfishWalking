# -*- coding: utf-8 -*-
"""v4.5 F17 편집 초안과 저장 (AC-M1~M12) — Playwright.

값을 고치는 동안에는 초안에만 쓰고(계산·파일 쓰기·화면 재그리기 없음), 저장(Ctrl+Enter)하면 미리보기 → 원본 반영 → 재계산이 한 번씩 돈다.
"""
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
BOOTS = "fan_turn_boots"
HP = f'#monEdit tr[data-mid="{MID}"] input.monIn'
FRESH = "document.querySelector('#mmBanner') && document.querySelector('#mmBanner').textContent.includes('현재 편집 반영')"
SAVED = "window.__WS && window.__WS.status === 'saved' && !window.__WS.dirty"


@unittest.skipIf(sync_playwright is None, "playwright 미설치")
class DraftUI(unittest.TestCase):
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
        self.sb = Sandbox(xs="500:700:200", runs="60", stages="30,60")

    def tearDown(self):
        self.sb.stop()
        self.sb.cleanup()

    def open(self, hash_="#t=mon", ctx=None):
        ctx = ctx or self.browser.new_context(viewport={"width": 1400, "height": 1000})
        pg = ctx.new_page()
        self.errs = []
        pg.on("pageerror", lambda e: self.errs.append(str(e)))
        pg.add_init_script("window.__MMSTAGES = [40, 80];")                           # 테스트용으로 판 수를 줄임
        pg.goto(f"http://127.0.0.1:{self.sb.port}/{hash_}")
        pg.wait_for_function("window.__viewerReady === true", timeout=90000)
        return ctx, pg

    def jobs(self):
        return [j.kind for j in self.sb.app.jobs.jobs.values()]

    def mon_hp(self):
        s, r = self.sb.req("GET", "/api/monsters")
        return next(m for m in r["monsters"] if m["id"] == MID)["hp"]

    def quiet(self, pg):
        pg.wait_for_function(FRESH, timeout=120000)                                    # 처음 계산이 끝날 때까지
        pg.wait_for_function("!window.__MM.running && !window.__LIVE.busy", timeout=120000)

    # AC-M1·M2·M5: 값을 고쳐도 계산·재그리기가 없고 스크롤·입력 칸이 그대로, 초안에만 쓰인다
    def test_m1_draft_edit_does_not_compute_or_rebuild(self):
        ctx, pg = self.open()
        self.quiet(pg)
        before = self.jobs()
        pg.evaluate("document.querySelector('%s').__mark = 'same'" % HP)
        pg.evaluate("document.querySelector('%s').scrollIntoView({block: 'center'})" % HP)   # 입력 칸이 보이는 위치에서 시작 (fill 이 스크롤하지 않게)
        y0 = pg.evaluate("window.scrollY")
        self.assertGreater(y0, 0)
        wrap0 = pg.evaluate("(document.querySelector('#monEdit').closest('.rankwrap')||{}).scrollTop || 0")
        pg.fill(HP, "5000")
        pg.dispatch_event(HP, "change")
        time.sleep(1.5)                                                                 # 계산이 시작됐다면 이 사이에 시작된다
        self.assertEqual(self.jobs(), before)                                           # 계산 없음 (R2)
        self.assertEqual(pg.evaluate("window.__S.edits.length"), 0)                     # 저장된 편집은 그대로
        self.assertEqual(pg.evaluate("window.__S.draft.edits.length"), 1)
        self.assertEqual(self.mon_hp(), 120)                                            # 파일도 그대로
        self.assertEqual(pg.evaluate("document.querySelector('%s').__mark" % HP), "same")   # 입력 칸 DOM 이 그대로 (R1)
        # 페이지가 위로 올라가지 않는다 (입력 칸 줄이 `수정 중` 표시로 길어져 아래로 밀리는 것은 허용 — 스크롤 위치 자체는 그대로이거나 보정만)
        self.assertGreaterEqual(pg.evaluate("window.scrollY"), y0 - 2)
        self.assertEqual(pg.evaluate("(document.querySelector('#monEdit').closest('.rankwrap')||{}).scrollTop || 0"), wrap0)
        self.assertEqual(pg.input_value(HP), "5000")
        self.assertIn("저장 안 됨 1개", pg.inner_text("#chgCount"))
        self.assertIn("수정 중(원래 120)", pg.inner_text(f'#monEdit tr[data-mid="{MID}"]'))
        self.assertTrue(pg.evaluate("document.querySelector('%s').classList.contains('drafted')" % HP))
        self.assertTrue(pg.is_visible("#tab-mon .draftbar"))
        self.assertIn("저장 안 됨 1개", pg.inner_text("#tab-mon .draftbar"))
        self.assertTrue(pg.is_enabled("#btnApply"))
        self.assertEqual(self.errs, [])
        ctx.close()

    # AC-M3·M4·M12: Ctrl+Enter → 미리보기 → 적용 → 원본 반영 + 재계산 각 한 번, 토스트, 초안 비움
    def test_m3_ctrl_enter_saves_and_recomputes_once(self):
        ctx, pg = self.open()
        self.quiet(pg)
        before = self.jobs()
        pg.fill(HP, "5000")
        pg.press(HP, "Control+Enter")                                                    # 입력 칸에 포커스가 있어도 저장
        pg.wait_for_selector("#applyGo", timeout=20000)                                  # 저장마다 미리보기 모달 (Q75)
        self.assertEqual(self.mon_hp(), 120)                                             # 적용을 누르기 전에는 파일이 그대로
        pg.keyboard.press("Control+Enter")                                               # 모달에서도 Ctrl+Enter 가 적용
        pg.wait_for_selector("#saveDone", timeout=60000)
        self.assertEqual(self.mon_hp(), 5000)                                            # 원본에 반영됨
        self.assertIn("저장 완료", pg.inner_text("#saveToast"))
        self.assertIn("백업", pg.inner_text("#saveToast"))
        self.assertEqual(pg.evaluate("window.__S.draft"), {"edits": None, "cfgEdits": None, "cfgSet": None})
        self.assertEqual(pg.evaluate("window.__S.edits.length"), 0)                      # 원본에 반영된 변경은 이제 기준값
        pg.wait_for_function("window.__lastJob && window.__lastJob.kind === 'recompute' && window.__lastJob.end != null", timeout=120000)
        pg.wait_for_function("(Array.from(document.querySelectorAll('#monMetricsTable #monTable tbody tr')).map(r => r.cells[3].innerText.trim())).includes('5000')", timeout=120000)
        pg.wait_for_function(FRESH, timeout=120000)
        new = self.jobs()[len(before):]
        self.assertEqual(new.count("recompute"), 1, new)                                 # 곡선 재계산 한 번 (R3)
        self.assertEqual(new.count("monster_metrics"), 1, new)                           # 몬스터별 지표 재계산 한 번
        self.assertNotIn("저장 안 됨", pg.inner_text("#chgCount"))
        self.assertEqual(self.errs, [])
        ctx.close()

    # AC-M5: 초안 버리기 — 입력 칸이 저장된 값으로 돌아오고 계산은 시작하지 않는다
    def test_m5_discard(self):
        ctx, pg = self.open()
        self.quiet(pg)
        before = self.jobs()
        pg.fill(HP, "777")
        pg.dispatch_event(HP, "change")
        self.assertEqual(pg.evaluate("window.__S.draft.edits.length"), 1)
        pg.click("#btnDiscard")
        self.assertEqual(pg.input_value(HP), "120")
        self.assertIsNone(pg.evaluate("window.__S.draft.edits"))
        self.assertFalse(pg.is_visible("#tab-mon .draftbar") if pg.query_selector("#tab-mon .draftbar") else False)
        self.assertEqual(pg.evaluate("document.querySelectorAll('#monEdit .dtag').length"), 0)
        time.sleep(1.0)
        self.assertEqual(self.jobs(), before)
        # Ctrl+Z 로 버린 초안을 되살린다 (초안 되돌리기는 초안에만 동작)
        pg.click("#btnUndo")
        self.assertEqual(pg.input_value(HP), "777")
        self.assertEqual(pg.evaluate("window.__S.draft.edits.length"), 1)
        self.assertEqual(self.errs, [])
        ctx.close()

    # AC-M6: 값 검사 실패 — 칸만 직전 값으로 되돌리고 화면을 다시 그리지 않는다
    def test_m6_invalid_value_restores_input(self):
        ctx, pg = self.open()
        self.quiet(pg)
        pg.evaluate("document.querySelector('%s').__mark = 'same'" % HP)
        pg.fill(HP, "-5")
        pg.dispatch_event(HP, "change")
        self.assertEqual(pg.input_value(HP), "120")
        self.assertEqual(pg.evaluate("document.querySelector('%s').__mark" % HP), "same")
        self.assertIsNone(pg.evaluate("window.__S.draft.edits"))
        self.assertEqual(self.errs, [])
        ctx.close()

    # AC-M7: 모드 드롭다운도 초안 — 선택만으로는 저장된 설정·화면이 바뀌지 않고, 저장하면 적용된다(파일 쓰기 없음 → 모달 없이 재계산)
    def test_m7_mode_dropdown_is_draft_then_saved(self):
        ctx, pg = self.open()
        self.quiet(pg)
        before = self.jobs()
        pg.select_option("#dmodel", "digits")
        time.sleep(1.0)
        self.assertEqual(self.jobs(), before)
        self.assertEqual(pg.evaluate("window.__S.cfgSet"), {})                           # 저장된 모델은 그대로
        self.assertEqual(pg.evaluate("window.__S.draft.cfgSet['monsters.damage_model']"), "digits")
        self.assertTrue(pg.evaluate("document.querySelector('#dmodel').classList.contains('drafted')"))
        self.assertEqual(pg.input_value("#dmodel"), "digits")
        self.assertIn("저장 안 됨", pg.inner_text("#chgCount"))
        pg.click("#btnApply")                                                            # 파일에 쓸 것이 없어 모달 없이 바로 확정
        pg.wait_for_selector("#saveDone", timeout=60000)
        self.assertIsNone(pg.query_selector("#applyGo"))
        self.assertEqual(pg.evaluate("window.__S.cfgSet['monsters.damage_model']"), "digits")
        self.assertIsNone(pg.evaluate("window.__S.draft.cfgSet"))
        self.assertFalse(pg.evaluate("document.querySelector('#dmodel').classList.contains('drafted')"))
        pg.wait_for_function("window.__lastJob && window.__lastJob.kind === 'recompute'", timeout=120000)
        self.assertEqual(self.errs, [])
        ctx.close()

    # F22 AC-B5: 배분 가중치 칸 — 초안으로 들어가 저장 전엔 계산하지 않고, 되돌리면 원래 값
    def test_w1_attack_weight_is_a_draft_setting(self):
        ctx, pg = self.open()
        self.quiet(pg)
        path = "player.policy.attack_weight"
        self.assertEqual(float(pg.input_value("#wtIn")), 0.5)
        before = self.jobs()
        pg.fill("#wtIn", "0.3")
        pg.press("#wtIn", "Tab")
        time.sleep(0.8)
        self.assertEqual(self.jobs(), before)                                              # 초안 — 계산 없음
        self.assertEqual(pg.evaluate("(window.__S.draft.cfgEdits || []).find(c => c.path === '%s').new" % path), 0.3)
        self.assertTrue(pg.evaluate("document.querySelector('#wtIn').classList.contains('drafted')"))
        self.assertIn("저장 안 됨", pg.inner_text("#chgCount"))
        pg.click("#btnDiscard")
        time.sleep(0.5)
        self.assertEqual(float(pg.input_value("#wtIn")), 0.5)
        self.assertFalse(pg.evaluate("document.querySelector('#wtIn').classList.contains('drafted')"))
        pg.fill("#wtIn", "1.5")                                                            # 범위 밖은 받지 않는다
        pg.press("#wtIn", "Tab")
        time.sleep(0.5)
        self.assertEqual(float(pg.input_value("#wtIn")), 0.5)
        self.assertEqual(self.errs, [])
        ctx.close()

    # AC-M8: 환상 편집 패널도 같은 초안 방식 — 곡선 재계산 없음, 입력 칸·포커스 유지
    def test_m8_fantasy_panel_draft(self):
        ctx, pg = self.open("#t=curve")
        pg.click(f'#list .row[data-id="{BOOTS}"] input')
        sel = f'#detail .editor[data-fid="{BOOTS}"] input.val'
        pg.wait_for_selector(sel)
        pg.wait_for_function("window.__lastJob == null || window.__lastJob.end != null", timeout=120000)
        before = self.jobs()
        v = float(pg.input_value(sel))
        pg.evaluate("document.querySelector('%s').__mark = 'same'" % sel)
        pg.fill(sel, str(v + 1))
        pg.dispatch_event(sel, "change")
        time.sleep(1.5)
        self.assertEqual(self.jobs(), before)
        self.assertEqual(pg.evaluate("window.__S.edits.length"), 0)
        self.assertEqual(pg.evaluate("window.__S.draft.edits.length"), 1)
        self.assertEqual(pg.evaluate("document.querySelector('%s').__mark" % sel), "same")
        self.assertIn("수정 중(원래", pg.inner_text(f'#detail .editor[data-fid="{BOOTS}"]'))
        self.assertTrue(pg.is_visible("#detail .draftbar"))
        # 입력 중(아직 확정 전)에 다른 곳에서 화면이 다시 그려져도 입력 칸·포커스·값이 그대로
        pg.click(sel)
        pg.fill(sel, str(v + 7))
        pg.select_option("#metric", "delta")                                              # update() → renderDetail
        self.assertEqual(pg.evaluate("document.activeElement === document.querySelector('%s')" % sel), True)
        self.assertEqual(pg.evaluate("document.querySelector('%s').__mark" % sel), "same")
        self.assertEqual(float(pg.input_value(sel)), v + 7)
        self.assertEqual(self.errs, [])
        ctx.close()

    # AC-M9: 초안은 새로고침해도 복원되고(같은 탭), 다른 탭에서는 '이전 탭의 초안'으로 가져오기를 묻는다 (F14 연계)
    def test_m9_draft_survives_reload_and_other_tab(self):
        ctx, pg = self.open()
        self.quiet(pg)
        pg.fill(HP, "4444")
        pg.dispatch_event(HP, "change")
        pg.wait_for_function(SAVED, timeout=20000)
        pg.reload()
        pg.wait_for_function("window.__viewerReady === true", timeout=90000)
        self.assertEqual(pg.evaluate("window.__S.draft.edits.length"), 1)                # 같은 탭: 그대로 복원
        pg.wait_for_selector(HP)
        pg.wait_for_function("document.querySelector('%s').value === '4444'" % HP, timeout=20000)
        self.assertIn("저장 안 됨 1개", pg.inner_text("#chgCount"))
        pg.wait_for_function(SAVED, timeout=20000)
        ctx.close()
        ctx2, pg2 = self.open()                                                           # 새 탭(새 CLIENT)
        pg2.wait_for_selector("#wsOtherDraft", timeout=30000)
        self.assertIn("이전 탭의 저장 안 된 초안 1개", pg2.inner_text("#wsBanner"))
        self.assertEqual(pg2.evaluate("window.__S.draft.edits"), None)
        pg2.click("#wsDraftImport")
        self.assertEqual(pg2.evaluate("window.__S.draft.edits.length"), 1)
        pg2.wait_for_function("document.querySelector('%s') && document.querySelector('%s').value === '4444'" % (HP, HP), timeout=20000)
        self.assertEqual(self.errs, [])
        ctx2.close()

    # AC-M10: 저장 이력에서 골라 되돌린다
    def test_m10_history_revert(self):
        ctx, pg = self.open()
        self.quiet(pg)
        pg.fill(HP, "5000")
        pg.dispatch_event(HP, "change")
        pg.click("#btnApply")
        pg.wait_for_selector("#applyGo", timeout=20000)
        pg.click("#applyGo")
        pg.wait_for_selector("#saveDone", timeout=60000)
        self.assertEqual(self.mon_hp(), 5000)
        pg.once("dialog", lambda d: d.accept())
        pg.click("#btnUnapply")
        pg.wait_for_selector(".histRow", timeout=20000)
        self.assertEqual(pg.evaluate("document.querySelectorAll('.histRow').length"), 1)
        pg.click(".histRevert")
        pg.wait_for_selector("#revertDone", timeout=60000)
        self.assertEqual(self.mon_hp(), 120)
        self.assertEqual(self.errs, [])
        ctx.close()

    # 저장 실패(원본이 밖에서 바뀜)는 초안을 그대로 두고 파일을 쓰지 않는다
    def test_save_blocked_keeps_draft(self):
        ctx, pg = self.open()
        self.quiet(pg)
        pg.fill(HP, "5000")
        pg.dispatch_event(HP, "change")
        pg.click("#btnApply")
        pg.wait_for_selector("#applyGo", timeout=20000)
        pg.click("#applyCancel")                                                          # 취소 → 아무것도 하지 않음
        self.assertEqual(self.mon_hp(), 120)
        self.assertEqual(pg.evaluate("window.__S.draft.edits.length"), 1)
        self.assertEqual(self.errs, [])
        ctx.close()

    # AC-M12: 탭 둘 — 한 탭이 저장하면 다른 탭은 초안이 그대로이고 띠가 뜨며, 그 탭의 저장은 미리보기에서 막힌다
    def test_m12_two_tabs(self):
        ctxA, pgA = self.open()
        ctxB, pgB = self.open()
        self.quiet(pgA)
        self.quiet(pgB)
        pgB.fill(HP, "777")
        pgB.dispatch_event(HP, "change")
        pgA.fill(HP, "5000")
        pgA.dispatch_event(HP, "change")
        pgA.click("#btnApply")
        pgA.wait_for_selector("#applyGo", timeout=20000)
        pgA.click("#applyGo")
        pgA.wait_for_selector("#saveDone", timeout=60000)
        self.assertEqual(self.mon_hp(), 5000)
        pgB.wait_for_function("!document.querySelector('#baseBand').classList.contains('hidden')", timeout=10000)   # 3초 폴링 + 여유
        self.assertIn("원본이 저장되었습니다", pgB.inner_text("#baseBand"))
        self.assertEqual(pgB.evaluate("window.__S.draft.edits.length"), 1)                # B 의 초안은 지워지지 않았다
        self.assertEqual(pgB.input_value(HP), "777")
        pgB.click("#btnApply")                                                              # B 의 저장: old(120) ≠ 현재(5000) → 미리보기에서 거부
        pgB.wait_for_selector("#applyGo, #saveFail", timeout=20000)
        if pgB.query_selector("#applyGo"):
            self.assertTrue(pgB.is_disabled("#applyGo"))
            self.assertIn("문제", pgB.inner_text(".modal"))
        self.assertEqual(self.mon_hp(), 5000)
        self.assertEqual(self.errs, [])
        ctxA.close()
        ctxB.close()


@unittest.skipIf(sync_playwright is None, "playwright 미설치")
class MetricsUI(unittest.TestCase):
    """F18 지표 갱신(AC-P1)과 F16 전투 로그 패널(AC-L1·L10·L12). 값 변경은 즉시 반영 모드(window.__IMMEDIATE_EDITS)로 — 지표 갱신 자체를 본다."""

    @classmethod
    def setUpClass(cls):
        os.makedirs(SHOTS, exist_ok=True)
        cls.pw = sync_playwright().start()
        ch = os.environ.get("VIEWER_BROWSER_CHANNEL", "msedge")
        cls.browser = cls.pw.chromium.launch(**({"channel": ch} if ch else {}))
        cls.sb = Sandbox(xs="500:700:200", runs="60", stages="30,60")

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.pw.stop()
        cls.sb.stop()
        cls.sb.cleanup()

    def open(self, stages="[30, 60, 90]"):
        ctx = self.browser.new_context(viewport={"width": 1400, "height": 1000})
        ctx.add_init_script("window.__IMMEDIATE_EDITS = true")
        pg = ctx.new_page()
        self.errs = []
        pg.on("pageerror", lambda e: self.errs.append(str(e)))
        pg.add_init_script("window.__MMSTAGES = %s;" % stages)
        self.sb.req("DELETE", "/api/workspace")
        pg.goto(f"http://127.0.0.1:{self.sb.port}/#t=mon")
        pg.wait_for_function("window.__viewerReady === true", timeout=90000)
        pg.wait_for_function(FRESH, timeout=120000)
        pg.wait_for_function("!window.__MM.running", timeout=120000)
        return ctx, pg

    # AC-L1: 행·로그 버튼으로 열고 닫고, 한 번에 한 몬스터만
    def test_l1_open_close_one_at_a_time(self):
        ctx, pg = self.open()
        btn = f'.mlOpen[data-mid="{MID}"]'
        pg.wait_for_selector(btn)
        self.assertFalse(pg.is_disabled(btn))
        pg.click(btn)
        pg.wait_for_selector("#monLog h4")
        self.assertIn("전투 로그", pg.inner_text("#monLog"))
        pg.click(btn)                                                                       # 같은 몬스터를 다시 누르면 닫힘
        self.assertEqual(pg.evaluate("document.querySelector('#monLog').innerHTML"), "")
        pg.click(btn)
        pg.wait_for_selector("#monLog h4")
        other = pg.evaluate("Array.from(document.querySelectorAll('#monTable tbody tr[data-mid]')).map(r => r.dataset.mid).filter(m => m !== '%s')[0]" % MID)
        pg.evaluate("(m) => document.querySelector('#monTable tbody tr[data-mid=\"' + m + '\"] .mlOpen').click()", other)
        self.assertEqual(pg.evaluate("document.querySelectorAll('#monLog h4').length"), 1)       # 한 번에 하나
        self.assertEqual(pg.evaluate("document.querySelectorAll('#monTable tbody tr.open').length"), 1)
        self.assertEqual(pg.evaluate("window.__MLOG.mid"), other)
        self.assertEqual(self.errs, [])
        ctx.close()

    # AC-L10: 로그를 볼 수 없는 지표(tier_avg)에서는 버튼이 비활성이고 이유가 보인다
    def test_l10_disabled_with_reason(self):
        ctx, pg = self.open()
        pg.evaluate("window.__MM.data.meta.monster_model = 'tier_avg'")
        pg.select_option("#metric", "delta")                                                # update() → 지표 표 다시 그림
        btn = f'.mlOpen[data-mid="{MID}"]'
        pg.wait_for_function("document.querySelector('%s') && document.querySelector('%s').disabled" % (btn, btn), timeout=10000)
        self.assertIn("tier_avg", pg.get_attribute(btn, "title"))
        self.assertEqual(self.errs, [])
        ctx.close()

    # AC-L12 + AC-P1: 편집으로 지표가 다시 계산되는 동안 열어 둔 패널에 `이전`이 붙고, 3단계 갱신 내내 스크롤·패널·선택이 유지된다
    def test_l12_p1_stale_badge_and_scroll_kept(self):
        ctx, pg = self.open()
        pg.click(f'.mlOpen[data-mid="{MID}"]')
        pg.wait_for_selector("#monLog h4")
        self.assertIsNone(pg.query_selector("#mlStale"))
        pg.evaluate("window.scrollTo(0, 400)")
        wrap0 = pg.evaluate("(function(){ const w = document.querySelector('#monMetricsTable .rankwrap'); if (w) w.scrollTop = 120; return w ? w.scrollTop : 0; })()")
        y0 = pg.evaluate("window.scrollY")
        self.assertGreater(y0, 0)
        pg.evaluate("""() => { window.__samp = []; window.__sampT = setInterval(() => { const w = document.querySelector('#monMetricsTable .rankwrap');
          window.__samp.push([window.scrollY, w ? w.scrollTop : null, window.__MLOG.mid, !!document.querySelector('#monLog h4')]); }, 25); }""")
        pg.evaluate("""() => { const i = document.querySelector('#monNIn'); i.value = '150'; i.dispatchEvent(new Event('change', { bubbles: true })); }""")   # 지표 키가 바뀌어 3단계 재계산
        pg.wait_for_selector("#mlStale", timeout=20000)                                      # 이전 표본 표시
        self.assertTrue(pg.is_visible("#mlRecollect"))
        pg.wait_for_function("window.__MM.running", timeout=20000)
        pg.wait_for_function(FRESH, timeout=120000)
        pg.wait_for_function("!window.__MM.running", timeout=120000)
        pg.evaluate("clearInterval(window.__sampT)")
        samp = pg.evaluate("window.__samp")
        self.assertGreater(len(samp), 10)
        self.assertEqual({s[0] for s in samp}, {y0}, "계산 중 페이지 스크롤이 움직임")
        self.assertEqual({s[1] for s in samp}, {wrap0}, "계산 중 표 스크롤이 움직임")
        self.assertEqual({s[2] for s in samp}, {MID})                                         # 열어 둔 패널(선택)이 유지
        self.assertEqual({s[3] for s in samp}, {True})
        self.assertIsNone(pg.query_selector("#mlStale"))                                    # 새 지표가 끝나면 `이전`이 사라진다
        self.assertEqual(self.errs, [])
        ctx.close()


@unittest.skipIf(sync_playwright is None, "playwright 미설치")
class TurnCalcUI(unittest.TestCase):
    """F21 AC-T1: 전투 로그의 턴 행을 누르면 분해 패널이 열리고, 같은 행을 다시 누르면 닫히며, ↑↓·Esc 로 넘기고 닫는다."""

    @classmethod
    def setUpClass(cls):
        os.makedirs(SHOTS, exist_ok=True)
        cls.pw = sync_playwright().start()
        ch = os.environ.get("VIEWER_BROWSER_CHANNEL", "msedge")
        cls.browser = cls.pw.chromium.launch(**({"channel": ch} if ch else {}))
        cls.sb = Sandbox(xs="500:700:200", runs="60", stages="30,60")

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.pw.stop()
        cls.sb.stop()
        cls.sb.cleanup()

    def test_t1_open_close_navigate(self):
        ctx = self.browser.new_context(viewport={"width": 1400, "height": 1000})
        ctx.add_init_script("window.__IMMEDIATE_EDITS = true")
        pg = ctx.new_page()
        errs = []
        pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.add_init_script("window.__MMSTAGES = [40, 80];")
        self.sb.req("DELETE", "/api/workspace")
        pg.goto(f"http://127.0.0.1:{self.sb.port}/#t=mon")
        pg.wait_for_function("window.__viewerReady === true", timeout=90000)
        pg.select_option("#dmodel", "digits+g")                                              # 분해는 digits 피해 모델에만 있다
        pg.wait_for_function(FRESH, timeout=120000)
        pg.wait_for_function("!window.__MM.running", timeout=120000)
        pg.wait_for_selector(f'.mlOpen[data-mid="{MID}"]')
        pg.click(f'.mlOpen[data-mid="{MID}"]')
        pg.wait_for_selector("#mlSamples tbody tr.mlRow")
        pg.click("#mlSamples tbody tr.mlRow")
        pg.wait_for_selector("#mlTurns tr.mlturn.mlclick", timeout=60000)
        first = "#mlTurns tr.mlturn.mlclick >> nth=0"
        pg.click(first)
        pg.wait_for_selector(".calcpanel")
        self.assertEqual(pg.evaluate("document.querySelectorAll('.calcpanel').length"), 1)       # 한 번에 한 턴
        self.assertEqual(pg.get_attribute(first, "aria-expanded"), "true")
        self.assertIn("준 피해", pg.inner_text("#calcSum"))
        self.assertIn("순차 증감", pg.inner_text(".calcpanel"))
        if pg.evaluate("document.querySelectorAll('#mlTurns tr.mlturn').length") > 1:
            t0 = pg.evaluate("window.__MLOG.turn")
            pg.keyboard.press("ArrowDown")
            self.assertGreater(pg.evaluate("window.__MLOG.turn"), t0)
            self.assertEqual(pg.evaluate("document.querySelectorAll('.calcpanel').length"), 1)
        pg.keyboard.press("Escape")
        self.assertEqual(pg.evaluate("document.querySelectorAll('.calcpanel').length"), 0)
        pg.click(first)
        pg.click(first)                                                                      # 같은 행을 다시 누르면 닫힘
        self.assertEqual(pg.evaluate("document.querySelectorAll('.calcpanel').length"), 0)
        self.assertEqual(errs, [])
        ctx.close()


if __name__ == "__main__":
    unittest.main()
