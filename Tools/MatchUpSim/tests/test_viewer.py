# -*- coding: utf-8 -*-
"""AC6 (뷰어 스모크), AC7 (성능). Playwright 필요: pip install playwright

브라우저: 기본은 설치된 Edge(channel=msedge). 다른 것을 쓰려면 환경 변수 VIEWER_BROWSER_CHANNEL
(예: chrome, 또는 빈 문자열 = Playwright 번들 Chromium; 그 경우 `playwright install chromium` 필요).
스크린샷은 tests/screenshots/ 에 저장된다.
"""
import copy
import json
import os
import random
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

import build_viewer  # noqa: E402

SHOTS = os.path.join(HERE, "screenshots")
EFFECTS = os.path.join(ROOT, "fantasy_effects.json")

try:
    from playwright.sync_api import sync_playwright
except ImportError:  # pragma: no cover
    sync_playwright = None


def synthetic_data(effect_mode="table"):
    """실제 효과 테이블 69종 x 11점짜리 가짜 스캔 결과 (뷰어 동작 확인용, 수치는 무의미)."""
    with open(EFFECTS, encoding="utf-8") as fp:
        fants = json.load(fp)["fantasies"]
    rnd = random.Random(7)
    xs = list(range(200, 1201, 100))
    n = 3000

    def point(x, shift):
        w = max(0.0, min(1.0, 0.9 / (1 + ((x - shift) / 350.0) ** 2 * 6) + rnd.uniform(-0.01, 0.01)))
        reach = [max(w, 1 - f / 45 * (1 - w)) for f in range(1, 46)]
        return {"x": x, "n": n, "wins": round(w * n), "win_rate": round(w, 4), "mean_reached_floor": round(10 + 30 * w, 2),
                "mean_fantasies": 9.0, "death_by_act": [round((1 - w) * 0.5, 4), round((1 - w) * 0.3, 4), round((1 - w) * 0.2, 4)],
                "reach_rate": [round(r, 4) for r in reach]}

    base = [point(x, 0) for x in xs]
    curves = {}
    for k, f in enumerate(fants):
        sh = 0 if f["fidelity"] == "none" else rnd.uniform(-60, 250)
        pts = []
        for b, x in zip(base, xs):
            p = point(x, sh)
            d = round(p["win_rate"] - b["win_rate"], 5)
            se = 0.006
            p.update({"delta": d, "delta_se": se, "delta_ci": [round(d - 1.96 * se, 5), round(d + 1.96 * se, 5)]})
            pts.append(p)
        curves[f["id"]] = {"points": pts}
    meta = {"scan_id": "synthetic", "generated_at": "2026-11-11T00:00:00", "sim_version": 1, "master_seed": "syn",
            "runs_per_point": n, "x_param": "monsters.hp_base", "x_values": xs,
            "fixed_overrides": {"monsters.act_hp_growth": 2.0}, "forced_at": "start", "effect_mode": effect_mode,
            "effects_hash": "deadbeef00", "target_win_rate": 0.10, "strong_signal_z": 3.4, "fantasy_pick": "random"}
    return {"meta": meta, "fantasies": [dict(f, grade=f["grade"]) for f in fants], "baseline": {"points": base}, "curves": curves}


@unittest.skipIf(sync_playwright is None, "playwright 미설치 (pip install playwright)")
class AC6Viewer(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        os.makedirs(SHOTS, exist_ok=True)
        cls.tmp = tempfile.TemporaryDirectory()
        data_path = os.environ.get("VIEWER_DATA")
        if data_path:
            with open(data_path, encoding="utf-8") as fp:
                cls.data = json.load(fp)
        else:
            cls.data = synthetic_data()
        cls.html = os.path.join(cls.tmp.name, "fantasy_viewer.html")
        with open(cls.html, "w", encoding="utf-8") as fp:
            fp.write(build_viewer.build(cls.data))
        g = copy.deepcopy(cls.data)
        g["meta"]["effect_mode"] = "grade"
        cls.html_grade = os.path.join(cls.tmp.name, "grade_viewer.html")
        with open(cls.html_grade, "w", encoding="utf-8") as fp:
            fp.write(build_viewer.build(g))
        cls.pw = sync_playwright().start()
        channel = os.environ.get("VIEWER_BROWSER_CHANNEL", "msedge")
        cls.browser = cls.pw.chromium.launch(**({"channel": channel} if channel else {}))
        cls.ids = [f["id"] for f in cls.data["fantasies"]]

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.pw.stop()
        cls.tmp.cleanup()

    def open(self, path, hash_="", scheme="light"):
        ctx = self.browser.new_context(viewport={"width": 1400, "height": 1000}, color_scheme=scheme)
        page = ctx.new_page()
        reqs, errors = [], []
        page.on("request", lambda r: reqs.append(r.url))
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
        url = "file:///" + os.path.abspath(path).replace("\\", "/") + hash_
        page.goto(url)
        page.wait_for_function("window.__viewerReady === true")
        return ctx, page, reqs, errors

    def select(self, page, ids):
        for fid in ids:
            page.click(f'#list .row[data-id="{fid}"]')

    def series_ids(self, page):
        return page.eval_on_selector_all("#chart path.series", "els => els.map(e => e.dataset.id)")

    def test_smoke(self):
        ctx, page, reqs, errors = self.open(self.html)
        picks = self.ids[:3]
        self.select(page, picks)
        # 곡선 3개 + 기준선
        self.assertEqual(sorted(self.series_ids(page)), sorted(["__baseline__"] + picks))
        # Y 지표 → Δ승률
        before = page.get_attribute('#chart path.series[data-id="%s"]' % picks[0], "d")
        page.select_option("#metric", "delta")
        after = page.get_attribute('#chart path.series[data-id="%s"]' % picks[0], "d")
        self.assertNotEqual(before, after)
        self.assertIn("Δ승률", page.get_attribute("#chart", "aria-label"))
        # 목표 승률 → 등가 체력 이득 변경
        eq1 = page.inner_text("#eq")
        page.fill("#target", "25")
        page.dispatch_event("#target", "change")
        eq2 = page.inner_text("#eq")
        self.assertNotEqual(eq1, eq2)
        self.assertIn("25.0%", eq2)
        # 호버 툴팁
        box = page.query_selector("#chart").bounding_box()
        page.mouse.move(box["x"] + box["width"] * 0.5, box["y"] + box["height"] * 0.5)
        self.assertTrue(page.is_visible("#tip"))
        self.assertIn("95% CI", page.inner_text("#tip"))
        # 다른 탭
        page.click('.tab[data-t="surv"]')
        self.assertEqual(len(page.query_selector_all("#chart2 path.series")), 4)
        page.click('.tab[data-t="rank"]')
        self.assertEqual(len(page.query_selector_all("#rank tbody tr")), len(self.ids))
        self.assertIn("약 5%는 우연", page.inner_text("#rankFoot"))
        page.click('.tab[data-t="curve"]')
        # URL 해시로 상태 복원
        url = page.url
        state = page.evaluate("location.hash")
        self.assertIn("m=delta", state)
        ctx2 = self.browser.new_context(viewport={"width": 1400, "height": 1000})
        p2 = ctx2.new_page()
        p2.goto(url)
        p2.wait_for_function("window.__viewerReady === true")
        self.assertEqual(sorted(self.series_ids(p2)), sorted(["__baseline__"] + picks))
        self.assertEqual(p2.input_value("#metric"), "delta")
        self.assertEqual(p2.input_value("#target"), "25")
        self.assertEqual(p2.evaluate("location.hash"), state)
        ctx2.close()
        # 네트워크 요청 0건 (문서 자신 외)
        self.assertEqual([u for u in reqs if not u.startswith("file:")], [])
        self.assertLessEqual(len(reqs), 1, reqs)
        self.assertEqual(errors, [])
        ctx.close()

    def test_rank_click_adds_curve(self):
        ctx, page, _, errors = self.open(self.html, "#t=rank")
        fid = self.ids[5]
        page.click(f'#rank tbody tr[data-id="{fid}"]')
        page.click('.tab[data-t="curve"]')
        self.assertIn(fid, self.series_ids(page))
        self.assertEqual(errors, [])
        ctx.close()

    def test_max_six_and_none_label(self):
        none_ids = [f["id"] for f in self.data["fantasies"] if f["fidelity"] == "none"]
        ctx, page, _, _ = self.open(self.html)
        if none_ids:
            self.select(page, none_ids[:1])
            self.assertIn("효과 미모델링 — 기준선과의 차이는 우연 변동", page.inner_text("#noneNotes"))
        others = [i for i in self.ids if i not in none_ids[:1]]
        self.select(page, others[:7])
        self.assertEqual(len(self.series_ids(page)), 1 + 6)
        ctx.close()

    def test_grade_mode_blocked(self):
        ctx, page, _, _ = self.open(self.html_grade)
        self.assertIn("등급 단위 모델로 만들어져 환상별 비교가 불가능합니다", page.inner_text("#blocked"))
        self.assertIsNone(page.query_selector("#chart"))
        ctx.close()

    def test_screenshots_light_dark(self):
        picks = ",".join(self.ids[i] for i in (6, 20, 40))
        for scheme in ("light", "dark"):
            for tab in ("curve", "surv", "rank"):
                ctx, page, _, errors = self.open(self.html, f"#f={picks}&m=win&t={tab}", scheme)
                if tab == "curve":
                    box = page.query_selector("#chart").bounding_box()
                    page.mouse.move(box["x"] + box["width"] * 0.35, box["y"] + box["height"] * 0.4)
                path = os.path.join(SHOTS, f"viewer_{tab}_{scheme}.png")
                page.screenshot(path=path, full_page=tab != "rank")
                self.assertTrue(os.path.getsize(path) > 10_000)
                self.assertEqual(errors, [])
                ctx.close()

    def test_ac7_performance(self):
        """69종이 목록에 있는 상태에서 선택 변경이 100ms 안에 반영."""
        ctx, page, _, _ = self.open(self.html)
        times = page.evaluate("""(ids) => {
            const out = [];
            for (const id of ids) {
                const row = document.querySelector(`#list .row[data-id="${id}"]`);
                const t = performance.now(); row.click(); out.push(performance.now() - t);
            }
            for (const m of ["delta", "floor", "death", "win"]) {
                const sel = document.getElementById("metric");
                const t = performance.now(); sel.value = m; sel.dispatchEvent(new Event("change")); out.push(performance.now() - t);
            }
            return out;
        }""", self.ids[:6] + self.ids[:3])
        self.assertEqual(page.eval_on_selector_all("#list .row", "e => e.length"), len(self.ids))
        print(f"\n  AC7: 갱신 시간 최대 {max(times):.1f}ms, 평균 {sum(times) / len(times):.1f}ms ({len(times)}회)")
        self.assertLess(max(times), 100)
        ctx.close()


if __name__ == "__main__":
    unittest.main()
