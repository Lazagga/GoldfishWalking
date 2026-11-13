# -*- coding: utf-8 -*-
"""v3 UI 수락 기준 (Playwright): 통합 스모크, 조합(체크한 환상 모두 보유 — 승률·생존 곡선), AC-G1·G2(경고 배지·해석 가이드), AC-B11(불씨 뷰어).
시너지 히트맵 탭은 뷰어에서 뺐다 (AC-C7 탐색 라벨 테스트 삭제)."""
import copy
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
from test_server import SHOTS, Sandbox, read_all  # noqa: E402
from test_viewer import synthetic_data  # noqa: E402

try:
    from playwright.sync_api import sync_playwright
except ImportError:  # pragma: no cover
    sync_playwright = None

ANCHOR, POIN = "fan_damage_anchor", "fan_damage_poinsettia"


@unittest.skipIf(sync_playwright is None, "playwright 미설치")
class V3UI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.makedirs(SHOTS, exist_ok=True)
        cls.sb = Sandbox(xs="400:800:200", runs="300", stages="100,300", adaptive="100,200")
        cls.pw = sync_playwright().start()
        ch = os.environ.get("VIEWER_BROWSER_CHANNEL", "msedge")
        cls.browser = cls.pw.chromium.launch(**({"channel": ch} if ch else {}))

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.pw.stop()
        cls.sb.stop()
        cls.sb.cleanup()

    def page(self, hash_="#t=curve&x=600", scheme="light"):
        ctx = self.browser.new_context(viewport={"width": 1400, "height": 1000}, color_scheme=scheme)
        pg = ctx.new_page()
        errs = []
        pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.goto(f"http://127.0.0.1:{self.sb.port}/{hash_}")
        pg.wait_for_function("window.__viewerReady === true")
        return ctx, pg, errs

    def wait_job(self, pg, kind=None, timeout=180000):
        pg.wait_for_function("(k) => window.__lastJob && window.__lastJob.end != null && (!k || window.__lastJob.kind === k)", arg=kind, timeout=timeout)
        return pg.evaluate("window.__lastJob")

    def check(self, pg, fid):
        pg.click(f'#list .row[data-id="{fid}"] input')

    def test_smoke_full_flow(self):
        sb = self.sb
        src0, mon0 = read_all(sb.src), read_all(sb.mon)
        ctx, pg, errs = self.page()
        # 1) 환상 수치 편집 → 부분 결과 → 완료
        pg.click('#list .row[data-id="fan_turn_boots"] .fname')
        sel = '#detail .editor[data-fid="fan_turn_boots"][data-key="value"] input.val'
        pg.fill(sel, "1")
        pg.dispatch_event(sel, "change")
        self.assertEqual(self.wait_job(pg, "recompute")["result"]["type"], "done")
        # 2) 닻·포인세티아 체크 → 조합(둘 다 보유) 곡선이 승률·생존 곡선에 같이 그려진다
        pg.click("#clearSel")
        self.check(pg, ANCHOR)
        self.check(pg, POIN)
        pg.wait_for_selector("#comboGo")
        pg.evaluate("window.__lastJob = null")
        pg.click("#comboGo")
        job = self.wait_job(pg, "combo")
        self.assertEqual(job["result"]["type"], "done")
        res = job["result"]["result"]
        self.assertEqual(res["arms"], "full")
        self.assertEqual(sorted(res["by_x"][0]["arms"]), sorted(["__baseline__", ANCHOR, POIN, f"{ANCHOR}+{POIN}"]))   # 부분집합 전체가 아니라 k+2 팔
        pg.wait_for_selector("#comboTable tbody tr")
        self.assertEqual(len(pg.query_selector_all("#comboTable tbody tr")), 4)        # 조합 + 단독 2 + 기준선
        self.assertEqual(len(pg.query_selector_all('#chart path[data-id="combo"]')), 1)
        self.assertIn("조합", pg.inner_text("#comboLegend"))
        self.assertIn("단독 Δ의 합", pg.inner_text("#comboSum"))
        self.assertIn("예상", pg.inner_text("#comboEst"))
        pg.screenshot(path=os.path.join(SHOTS, "v3_combo_light.png"))
        pg.click('.tab[data-t="surv"]')
        pg.wait_for_selector('#chart2 path[data-id="combo"]')
        self.assertIn("조합", pg.inner_text("#legend2"))
        pg.click('.tab[data-t="curve"]')
        # 3) 불씨 모드 전환 (AC-B11): 기준선과 곡선이 새 규칙으로 다시 계산
        pg.evaluate("window.__lastJob = null")
        pg.select_option("#system", "ember")
        self.assertEqual(self.wait_job(pg, "recompute")["result"]["type"], "done")
        self.assertTrue(pg.evaluate("window.__S.cfgSet['rewards.normal_battle.mode'] === 'ember'"))
        pg.click('.tab[data-t="ember"]')
        self.assertIn("게임에 아직 반영되지 않은", pg.inner_text("#tab-ember"))
        self.assertGreaterEqual(len(pg.query_selector_all("#emFbf rect.tband")), 1)                 # 목표 12~15 밴드
        self.assertIn("보상", pg.inner_text("#emSrc"))
        pg.screenshot(path=os.path.join(SHOTS, "v3_ember_light.png"))
        pg.select_option("#system", "fantasy")
        # 4) 몬스터 체력 편집
        pg.click('.tab[data-t="mon"]')
        pg.wait_for_selector("#monEdit tbody tr")
        hp = '#monEdit tr[data-mid="Mob_10102_WildDog"] input.monIn'
        pg.fill(hp, "150")
        pg.dispatch_event(hp, "change")
        self.assertTrue(pg.evaluate("window.__S.edits.some(e => e.target === 'monster' && e.new === 150)"))
        self.assertIn("시뮬 미반영", pg.inner_text("#monEdit"))
        # 5) JSON 탭 편집
        pg.click('#monEdit tr[data-mid="Mob_10102_WildDog"] .monJson')
        pg.wait_for_selector("#jsText")
        text = pg.input_value("#jsText")
        self.assertIn('"health": 150', text.replace("  ", " "))    # 숫자 UI 편집이 JSON 탭에 반영 (AC-J3)
        self.assertIn("150", pg.inner_text("#jsPatched"))
        pg.fill("#jsText", text.replace('"designerNote":  ""', '"designerNote":  "테스트 메모"'))
        pg.click("#jsCheck")
        pg.wait_for_function("window.__jsonCheck != null")
        self.assertTrue(pg.evaluate("window.__jsonCheck.ok"))
        pg.click("#jsSave")
        pg.wait_for_function("window.__jsonSave && window.__jsonSave.saved === true")
        pg.wait_for_function("window.__S.fileEdits.length === 1")
        self.assertFalse(pg.evaluate("window.__S.edits.some(e => e.target === 'monster')"))   # 텍스트에 흡수됨
        # 6) 시나리오 저장
        pg.click('.tab[data-t="curve"]')
        pg.once("dialog", lambda d: d.accept("v3 스모크"))
        pg.on("dialog", lambda d: d.accept(""))
        pg.click("#btnSave")
        pg.wait_for_timeout(600)
        with open(os.path.join(sb.scen, "v3_스모크.json"), encoding="utf-8") as fp:
            scen = json.load(fp)
        self.assertEqual(scen["schema"], 2)
        self.assertEqual([(f["kind"], f["id"]) for f in scen["file_edits"]], [("monster", "Mob_10102_WildDog")])
        self.assertTrue(any(e["fid"] == "fan_turn_boots" for e in scen["edits"]))
        # 7) 미리보기 diff → 반영(fixtures) → 복원
        pg.click("#btnApply")
        pg.wait_for_selector(".modal pre")
        m = pg.inner_text(".modal")
        self.assertIn("fan_turn_boots.json", m)
        self.assertIn("monsters/mob_10102_wilddog.json", m)
        self.assertIn("쓴 텍스트 그대로", m)
        pg.screenshot(path=os.path.join(SHOTS, "v3_apply_preview_light.png"))
        pg.click("#applyGo")
        pg.wait_for_selector("#okClose")
        self.assertIn("반영 완료", pg.inner_text(".modal"))
        pg.click("#okClose")
        s1, m1 = read_all(sb.src), read_all(sb.mon)
        self.assertEqual([k for k in s1 if s1[k] != src0[k]], ["fan_turn_boots.json"])
        self.assertEqual([k for k in m1 if m1[k] != mon0[k]], ["mob_10102_wilddog.json"])
        self.assertIn("테스트 메모".encode("utf-8"), m1["mob_10102_wilddog.json"])
        self.assertIn(b"150", m1["mob_10102_wilddog.json"])
        pg.click("#btnUnapply")
        pg.wait_for_timeout(1000)
        self.assertEqual((read_all(sb.src), read_all(sb.mon)), (src0, mon0))
        self.assertEqual(errs, [])
        ctx.close()

    def test_c5_fifth_check_blocked(self):
        ctx, pg, errs = self.page()
        ids = pg.eval_on_selector_all("#list .row", "els => els.slice(0, 5).map(e => e.dataset.id)")
        for i in ids:
            self.check(pg, i)
        self.assertEqual(pg.evaluate("window.__S.sel.length"), 4)
        self.assertIn("최대 4개", pg.inner_text("#noneNotes"))
        self.assertIn("선택 4/4", pg.inner_text("#selCount"))
        self.assertEqual(errs, [])
        ctx.close()

    def test_b11_system_mix_badge_and_sweep(self):
        ctx, pg, errs = self.page("#f=fan_turn_boots&t=curve&x=600")
        self.assertEqual(len(pg.query_selector_all("#mixWarn")), 0)
        pg.select_option("#system", "ember")
        # 재계산이 끝나기 전에는 화면의 곡선이 현행 규칙 기준 → 혼합 배지
        pg.wait_for_selector("#mixWarn", timeout=5000)
        self.wait_job(pg, "recompute")
        pg.wait_for_timeout(300)
        self.assertEqual(len(pg.query_selector_all("#mixWarn")), 0)     # 선택한 곡선이 새 규칙으로 다시 계산되면 사라짐
        pg.click('.tab[data-t="rank"]')
        self.assertGreater(len(pg.query_selector_all("#rank .badge.stale")), 30)   # 나머지는 이전 규칙 기준(stale)
        pg.click('.tab[data-t="ember"]')
        pg.evaluate("window.__lastJob = null")
        pg.click("#emSweep")
        self.assertEqual(self.wait_job(pg, "ember_sweep")["result"]["type"], "done")
        pg.wait_for_function("document.querySelectorAll('#sweepTable td.swc').length === 16")
        self.assertIn("정수 파라미터", pg.inner_text("#tab-ember"))
        pg.screenshot(path=os.path.join(SHOTS, "v3_ember_sweep_dark.png"))
        self.assertEqual(errs, [])
        ctx.close()

    def test_g2_guide(self):
        ctx, pg, errs = self.page("#t=guide", "dark")
        self.assertEqual(len(pg.query_selector_all("#guideList li")), 17)   # 12항 + v4 5항
        for key in ("없을 때", "한계 효과", "공분산", "상관", "다중 비교", "포화", "충실도", "선택 정책", "생존 편향",
                    "이진 신호", "기준이 바뀐다", "튜닝을 다시"):
            self.assertIn(key, pg.inner_text("#guideList"))
        pg.click('.tab[data-t="rank"]')
        pg.click('#rank thead th[data-k="z"] .info')
        self.assertEqual(pg.evaluate("window.__guideOpened"), 5)
        self.assertTrue(pg.is_visible("#guide-5.hl"))
        pg.click('.tab[data-t="rank"]')
        pg.click('#rank thead th[data-k="delta"] .info')
        self.assertEqual(pg.evaluate("window.__guideOpened"), 1)
        pg.screenshot(path=os.path.join(SHOTS, "v3_guide_dark.png"))
        self.assertEqual(errs, [])
        ctx.close()


@unittest.skipIf(sync_playwright is None, "playwright 미설치")
class V3Badges(unittest.TestCase):
    """AC-G1: 합성 데이터에서 경고 배지가 조건대로 켜지고 꺼진다 (정적 모드)."""

    def test_badges(self):
        d = synthetic_data()
        fa, fb = d["fantasies"][2]["id"], d["fantasies"][3]["id"]
        none = next(f for f in d["fantasies"] if f["fidelity"] == "none")["id"]
        for p in d["curves"][fa]["points"]:
            p.update({"flips_up": 9, "flips_down": 5, "mde": 0.02})        # 정보량 부족
        for p in d["curves"][fb]["points"]:
            p.update({"flips_up": 120, "flips_down": 60, "mde": 0.02})

        def combo(ids, w, label="pre"):
            arms = {"__baseline__": 0.30, ids[0]: w[0], ids[1]: w[1], "+".join(ids): w[2]}
            mk = lambda k, v: {"ids": k.split("+") if k != "__baseline__" else [], "n": 3000, "win_rate": v, "wins": int(v * 3000),  # noqa: E731
                               "delta": round(v - 0.30, 4), "delta_se": 0.008, "delta_ci": [v - 0.30 - 0.016, v - 0.30 + 0.016],
                               "flips_up": 200, "flips_down": 40, "mde": 0.022,
                               "expected_delta": round(sum(arms[i] - 0.30 for i in k.split("+")), 4) if k != "__baseline__" else 0}
            I = w[2] - w[0] - w[1] + 0.30
            return {"ids": ids, "baseline_type": "natural", "label": label, "n": 3000, "x_values": [700],
                    "by_x": [{"x": 700, "n": 3000, "arms": {k: mk(k, v) for k, v in arms.items()}, "R": None,
                              "pairs": [{"a": ids[0], "b": ids[1], "I": round(I, 4), "se": 0.012, "ci": [I - 0.0235, I + 0.0235],
                                         "n": 3000, "saturated": w[2] > 0.95, "label": "중복·포화 가능" if I < -0.0235 else "뚜렷한 상호작용 없음"}]}]}

        d["combos"] = [combo([fa, fb], [0.90, 0.92, 0.97]), combo([fa, none], [0.45, 0.31, 0.47])]
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
                # 정보량 부족: fa 에만
                pg.goto(url + "#t=rank&x=700")
                pg.wait_for_function("window.__viewerReady === true")
                self.assertEqual(len(pg.query_selector_all(f'#rank tr[data-id="{fa}"] .badge.lowinfo')), 1)
                self.assertEqual(len(pg.query_selector_all(f'#rank tr[data-id="{fb}"] .badge.lowinfo')), 0)
                self.assertEqual(len(pg.query_selector_all("#mixWarn")), 0)      # 획득 시스템 혼합: 정적 단일 스캔에서는 꺼짐
                # 승률 포화 구간: 조합 fa+fb 에서 켜짐
                pg.goto(url + f"#f={fa},{fb}&t=curve&x=700")
                pg.reload()
                pg.wait_for_function("window.__viewerReady === true")
                pg.wait_for_selector("#comboTable tbody tr")
                self.assertEqual(len(pg.query_selector_all("#combo .satur")), 1)
                self.assertEqual(len(pg.query_selector_all("#combo .badge.none")), 0)   # 시뮬 미반영 포함: 꺼짐
                self.assertIn("합보다 작다", pg.inner_text("#comboSum"))
                self.assertEqual(len(pg.query_selector_all('#chart path[data-id="combo"]')), 1)
                # 시뮬 미반영 포함: none 환상이 든 조합에서 켜지고, 포화 배지는 꺼짐
                pg.goto(url + f"#f={fa},{none}&t=curve&x=700")
                pg.reload()
                pg.wait_for_function("window.__viewerReady === true")
                pg.wait_for_selector("#comboTable tbody tr")
                self.assertEqual(len(pg.query_selector_all("#combo .badge.none")), 1)
                self.assertEqual(len(pg.query_selector_all("#combo .satur")), 0)
                self.assertEqual(errs, [])
                b.close()


if __name__ == "__main__":
    unittest.main()
