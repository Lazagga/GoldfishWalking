# -*- coding: utf-8 -*-
"""v2 추가 기능 수락 기준: AC-F1(목표 밴드), AC-F2(몬스터), AC-F3(보정), AC-F4(시너지), AC-F5(보상 구조),
AC-F6(패싯·v1 호환), AC-F7(트레이스)."""
import ast
import copy
import csv
import importlib.util
import json
import os
import sys
import tempfile
import time
import types
import unittest


def _legacy(mod):
    """v4.1 까지의 기본 설정 (v4.2 에서 기본이 table+digits 로 바뀜). v1 원본 모듈에는 해당 키가 없다."""
    import copy as _c
    cfg = _c.deepcopy(mod.DEFAULT_CONFIG)
    if hasattr(mod, "LEGACY_MONSTERS"):
        cfg["monsters"].update(mod.LEGACY_MONSTERS)
    return cfg

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)

import build_viewer  # noqa: E402
import import_monsters  # noqa: E402
import matchup_sim as ms  # noqa: E402
import synergy_scan  # noqa: E402
from sim_service import calibrate as cal  # noqa: E402
from sim_service import compute as cp  # noqa: E402
from sim_service import monsters as mo  # noqa: E402
from sim_service import stats as S  # noqa: E402
from sim_service import store as st  # noqa: E402
from sim_service import trace as trc  # noqa: E402
import test_identity  # noqa: E402
from test_viewer import synthetic_data  # noqa: E402

EFFECTS = os.path.join(ROOT, "fantasy_effects.json")
FIX = os.path.join(HERE, "fixtures")
WORKERS = max(2, min(8, (os.cpu_count() or 2) - 1))

try:
    from playwright.sync_api import sync_playwright
except ImportError:  # pragma: no cover
    sync_playwright = None


def table_cfg(hp=600, effects=EFFECTS):
    cfg = ms.legacy_config()
    cfg["monsters"]["act_hp_growth"] = 2.0
    cfg["monsters"]["hp_base"] = hp
    ms.apply_fantasy_args(cfg, effects)
    return cfg


# ---------------------------------------------------------------------------
@unittest.skipIf(sync_playwright is None, "playwright 미설치")
class ACF1F6Viewer(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.pw = sync_playwright().start()
        ch = os.environ.get("VIEWER_BROWSER_CHANNEL", "msedge")
        cls.browser = cls.pw.chromium.launch(**({"channel": ch} if ch else {}))

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.pw.stop()
        cls.tmp.cleanup()

    def open(self, data, name, hash_="", targets="default"):
        path = os.path.join(self.tmp.name, name)
        with open(path, "w", encoding="utf-8") as fp:
            fp.write(build_viewer.build(data, targets=targets))
        pg = self.browser.new_page(viewport={"width": 1400, "height": 1000})
        errs = []
        pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.goto("file:///" + path.replace("\\", "/") + hash_)
        pg.wait_for_function("window.__viewerReady === true")
        return pg, errs

    def test_f1_band_verdicts(self):
        targets = {"x_mode": "selected", "bands": {"white": [0.005, 0.02], "blue": [0.02, 0.05], "red": [0.05, 0.10]}}
        data = synthetic_data()
        # 알려진 Δ·CI 를 가진 환상 4종 (백색) + none 1종
        whites = [f for f in data["fantasies"] if f["grade"] == "white" and f["fidelity"] != "none"][:4]
        none = [f for f in data["fantasies"] if f["fidelity"] == "none"][0]
        want = {whites[0]["id"]: ([0.03, 0.05], "above"), whites[1]["id"]: ([-0.02, -0.01], "below"),
                whites[2]["id"]: ([0.008, 0.015], "in"), whites[3]["id"]: ([0.0, 0.03], "unsure"),
                none["id"]: ([0.03, 0.05], "excl")}
        for fid, (ci, _) in want.items():
            for p in data["curves"][fid]["points"]:
                p["delta_ci"] = ci
                p["delta"] = sum(ci) / 2
                p["delta_se"] = (ci[1] - ci[0]) / 3.92
        pg, errs = self.open(data, "f1.html", "#t=rank", targets)
        for fid, (_, k) in want.items():
            got = pg.get_attribute(f'#rank tbody tr[data-id="{fid}"] td.verdict', "data-v")
            self.assertEqual(got, k, fid)
        # 직접 판정 함수: stale 은 제외
        v = pg.evaluate("window.__verdict({grade:'white', fidelity:'exact'}, {delta_ci:[0.03,0.05]}, true)")
        self.assertEqual(v["k"], "excl")
        self.assertIn("stale", v["why"])
        # 조정 후보 패널: 너프 후보에 above, 버프 후보에 below
        panel = pg.inner_text("#candPanel")
        self.assertIn(whites[0]["name"], panel)
        self.assertIn(whites[1]["name"], panel)
        self.assertNotIn(none["name"], panel)
        # Δ 차트에 밴드 음영
        pg.goto(pg.url.split("#")[0] + f"#f={whites[0]['id']}&m=delta&t=curve")
        pg.reload()
        pg.wait_for_function("window.__viewerReady === true")
        self.assertGreaterEqual(len(pg.query_selector_all("#chart rect.tband")), 1)
        self.assertEqual(errs, [])
        pg.close()

    def test_f6_v1_json_and_facet_gap(self):
        # v1 형식(스키마·table_hash·facets 없음)도 열린다
        v1 = synthetic_data()
        pg, errs = self.open(v1, "v1.html", "#t=rank")
        self.assertEqual(len(pg.query_selector_all("#rank tbody tr")), len(v1["fantasies"]))
        self.assertEqual(len(pg.query_selector_all("#rank .badge.stale")), 0)
        self.assertEqual(errs, [])
        pg.close()
        # 패싯 데이터: 격차 = Δ(높은 실력) − Δ(낮은 실력), se = √(se₁² + se₂²)
        d = synthetic_data()
        d["meta"]["facets"] = {"key": "player.skill", "values": ["0.5", "0.9"], "default": "0.5"}
        d["baseline"]["by_facet"] = {"0.5": d["baseline"]["points"], "0.9": copy.deepcopy(d["baseline"]["points"])}
        fid = d["fantasies"][3]["id"]
        for f2, c in d["curves"].items():
            lo = c["points"]
            hi = copy.deepcopy(lo)
            if f2 == fid:
                for p in lo:
                    p.update({"delta": 0.02, "delta_se": 0.003, "delta_ci": [0.02 - 0.00588, 0.02 + 0.00588]})
                for p in hi:
                    p.update({"delta": 0.07, "delta_se": 0.004, "delta_ci": [0.07 - 0.00784, 0.07 + 0.00784]})
            c["by_facet"] = {"0.5": lo, "0.9": hi}
        pg, errs = self.open(d, "facet.html", "#t=rank")
        g = pg.evaluate(f"window.__facetGap('{fid}')")
        self.assertAlmostEqual(g["gap"], 0.05, places=9)
        self.assertAlmostEqual(g["se"], 0.005, places=9)
        self.assertEqual(g["cls"], "격차 확대")
        ind = S.independent_diff(0.07, 0.004, 0.02, 0.003)
        self.assertAlmostEqual(ind["gap"], 0.05, places=6)
        self.assertAlmostEqual(ind["gap_se"], 0.005, places=6)
        self.assertIn("격차 확대", pg.inner_text(f'#rank tbody tr[data-id="{fid}"]'))
        # 패싯 겹쳐 그리기: 환상 1개 선택 시 패싯 수만큼 곡선
        pg.click(f'#rank tbody tr[data-id="{fid}"]')
        pg.click('.tab[data-t="curve"]')
        pg.check("#overlay")
        n = pg.eval_on_selector_all("#chart path.series", f"els => els.filter(e => e.dataset.id === '{fid}').length")
        self.assertEqual(n, 2)
        self.assertEqual(errs, [])
        pg.close()


# ---------------------------------------------------------------------------
class ACF2Monsters(unittest.TestCase):
    def test_import_and_metrics(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = os.path.join(tmp, "monster_table.json")
            data = import_monsters.main(["--monsters", os.path.join(FIX, "monsters"),
                                         "--patterns", os.path.join(FIX, "patterns"), "--out", out, "--quiet"])
            self.assertEqual(data["counts"], {"monsters": 39, "patterns": 38})
            self.assertEqual(len(data["monsters"]), 39)
            for m in data["monsters"]:
                self.assertIn(m["fidelity"], ("exact", "approx", "none"), m["id"])
                self.assertTrue(m["patterns"], m["id"])
                self.assertEqual(m["fidelity"] == "none", bool(m["gimmicks"]), m["id"])
                self.assertFalse(m["warnings"], m["warnings"])   # 모든 패턴 키가 해석됨 (대체 없음)
            cfg = table_cfg(hp=600)
            cfg["monsters"].update({"model": "table", "table_file": out})
            res = mo.run_metrics(cfg, "mon", 300, monster_table=data)
            self.assertGreater(len(res["monsters"]), 25)
            for r in res["monsters"]:
                self.assertGreater(r["battles"], 0)
                self.assertGreaterEqual(r["avg_taken"], 0)
                # 기믹이 모델링되지 않은 몬스터에는 경고
                self.assertEqual(bool(r["warning"]), bool(r["gimmicks"]), r["id"])
            self.assertTrue(any(r["warning"] for r in res["monsters"]))
            # shuffle_bag 옵션도 돈다
            cfg["monsters"]["select"] = "shuffle_bag"
            self.assertGreater(len(mo.run_metrics(cfg, "mon", 60, monster_table=data)["monsters"]), 10)
            # v4: digits 피해 모델은 table 모델에서만 (tier_avg 와 함께 쓰면 오류, AC-D8)
            cfg["monsters"]["damage_model"] = "digits"
            ms.SimContext(cfg)
            cfg["monsters"]["model"] = "tier_avg"
            with self.assertRaises(ValueError):
                ms.SimContext(cfg)

    def test_viewer_shows_monster_warnings(self):
        if sync_playwright is None:
            self.skipTest("playwright 미설치")
        with tempfile.TemporaryDirectory() as tmp:
            out = os.path.join(tmp, "monster_table.json")
            data = import_monsters.main(["--monsters", os.path.join(FIX, "monsters"),
                                         "--patterns", os.path.join(FIX, "patterns"), "--out", out, "--quiet"])
            cfg = table_cfg(hp=600)
            cfg["monsters"].update({"model": "table", "table_file": out})
            res = mo.write(mo.run_metrics(cfg, "mon", 100, monster_table=data), cfg, "mon", 100, os.path.join(tmp, "mm.json"))
            d = synthetic_data()
            d["monster_metrics"] = res
            html = os.path.join(tmp, "v.html")
            with open(html, "w", encoding="utf-8") as fp:
                fp.write(build_viewer.build(d))
            with sync_playwright() as pw:
                ch = os.environ.get("VIEWER_BROWSER_CHANNEL", "msedge")
                b = pw.chromium.launch(**({"channel": ch} if ch else {}))
                pg = b.new_page()
                pg.goto("file:///" + html.replace("\\", "/") + "#t=mon")
                pg.wait_for_function("window.__viewerReady === true")
                self.assertEqual(len(pg.query_selector_all("#monTable tbody tr")), len(res["monsters"]))
                self.assertEqual(len(pg.query_selector_all("#monTable .badge.stale")), sum(1 for r in res["monsters"] if r["warning"]))
                self.assertEqual(len(pg.query_selector_all("#monTable td.bwin")), len(res["monsters"]))   # 조우 시 전투 승률
                self.assertEqual(len(pg.query_selector_all("#monTable td.rwin")), len(res["monsters"]))   # 조우한 런 승률
                self.assertIn("조우한 런 승률", pg.inner_text("#monWinNote"))
                self.assertTrue(pg.is_visible("#monWinAll"))
                b.close()


# ---------------------------------------------------------------------------
class ACF3Calibration(unittest.TestCase):
    TRUE_SKILL = 0.55

    def _fake_playtest(self, path, n, cfg):
        c = copy.deepcopy(cfg)
        c["player"]["skill"] = self.TRUE_SKILL
        ctx = ms.SimContext(c)
        with open(path, "w", encoding="utf-8", newline="") as fp:
            w = csv.writer(fp)
            w.writerow(["run_id", "result", "end_act", "end_floor", "final_hp", "fantasies", "notes"])
            for i in range(n):
                r = ms.simulate_run(c, f"play-{i}", ctx=ctx)
                w.writerow([f"p{i}", r["result"], r["end_act"], r["end_floor_in_act"], r["final_hp"], "", ""])

    def test_recovers_known_parameter(self):
        cfg = ms.legacy_config()
        cfg["monsters"]["act_hp_growth"] = 2.0
        cfg["monsters"]["hp_base"] = 74
        with tempfile.TemporaryDirectory() as tmp:
            pt = os.path.join(tmp, "playtest.csv")
            self._fake_playtest(pt, 2000, cfg)
            rows = cal.read_playtest(pt)
            self.assertEqual(len(rows), 2000)
            eng = cp.Engine(st.PointStore(os.path.join(tmp, "pc")), WORKERS)
            try:
                res = cal.calibrate(eng, cfg, "grade", "calsim", rows, ["player.skill"], n_sim=2000, max_evals=30)
                small = cal.calibrate(eng, cfg, "grade", "calsim", rows[:20], ["player.skill"], n_sim=500, max_evals=6)
            finally:
                eng.close()
            got = res["params"]["player.skill"]
            print(f"\n  AC-F3: 참값 skill {self.TRUE_SKILL} → 보정 {got} (시작 0.7, 평가 {res['fit']['evals']}회, χ²/자유도 {res['fit']['chi2_per_dof']})")
            self.assertAlmostEqual(got, self.TRUE_SKILL, delta=0.05)
            self.assertFalse(res["warnings"])
            self.assertEqual(res["cfg_edits"][0]["path"], "player.skill")
            self.assertEqual(len(res["residuals"]), 45)
            self.assertIn("player.skill", res["profile"])
            # 관측 30판 미만 경고
            self.assertTrue(any("과적합" in w for w in small["warnings"]))
            # 4개 이상 동시 보정은 거부
            with self.assertRaises(ValueError):
                cal.calibrate(None, cfg, "grade", "x", rows, ["a", "b", "c", "d"])

    def test_template_is_readable(self):
        rows = cal.read_playtest(os.path.join(ROOT, "playtest_runs.template.csv"))
        self.assertEqual([r["reached"] for r in rows], [22, 45, 12])


# ---------------------------------------------------------------------------
class ACF4Synergy(unittest.TestCase):
    def test_known_interactions_and_null(self):
        with open(EFFECTS, encoding="utf-8") as fp:
            data = json.load(fp)
        mk = lambda i, eff, avail=False: {"id": i, "name": i, "grade": "white", "fidelity": "exact" if eff else "none",  # noqa: E731
                                          "effects": eff, "notes": "", "available": avail}
        syn = [mk("syn_A", [{"type": "dmg_flat", "value": 5000}]), mk("syn_B", [{"type": "dmg_flat", "value": 5000}]),
               mk("syn_C", [{"type": "hits_add", "value": 3}]), mk("syn_D", [{"type": "combo_same_dmg_stack", "value": 300}])]
        dummies = [mk(f"dum_{k}", [], True) for k in range(8)]
        data["fantasies"].extend(syn + dummies)
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "fx.json")
            with open(path, "w", encoding="utf-8") as fp:
                json.dump(data, fp, ensure_ascii=False)
            cfg = table_cfg(hp=600, effects=path)
            thash = st.table_hash(data)
            eng = cp.Engine(st.PointStore(os.path.join(tmp, "pc")), WORKERS)
            ids = [f["id"] for f in syn + dummies]
            try:
                top, single, final, n_pairs = synergy_scan.run_synergy(
                    eng, cfg, thash, "syn", "monsters.hp_base", 600, ids, top_k=2,
                    include=["syn_C", "dum_0", "dum_1", "dum_2"], stages=(500, 1500), epsilon=0.02, log=lambda *a: None)
            finally:
                eng.close()
        z = lambda I: I["I"] / I["se"] if I["se"] > 0 else 0.0  # noqa: E731
        # 포화: A, B 각각이 거의 항상 이기게 하므로 I ≈ −Δ(A)
        iab = final[("syn_A", "syn_B")]
        da = single["syn_A"]["delta"]
        print(f"\n  AC-F4: Δ(A)={da:+.3f}, I(A,B)={iab['I']:+.3f} (기대 ≈ {-da:+.3f}) | I(C,D)={final[('syn_C', 'syn_D')]['I']:+.3f} z={z(final[('syn_C', 'syn_D')]):.1f}")
        self.assertGreater(da, 0.5)
        self.assertLess(iab["I"], 0)
        self.assertAlmostEqual(iab["I"], -da, delta=0.05)
        self.assertLessEqual(z(iab), -synergy_scan.SIGNAL_Z)
        # 상승: 타수 +3 과 '같은 피해 연속 시 누적' 은 같이 있을 때만 강하다
        icd = final[("syn_C", "syn_D")]
        self.assertGreater(icd["I"], 0)
        self.assertGreaterEqual(z(icd), synergy_scan.SIGNAL_Z)
        # 효과 없는 쌍: 신호 비율이 보정된 임계값(|z| ≥ 4) 아래
        null = [I for (a, b), I in final.items() if a.startswith("dum_") and b.startswith("dum_")]
        self.assertGreaterEqual(len(null), 15)
        sig = sum(1 for I in null if abs(z(I)) >= synergy_scan.SIGNAL_Z)
        print(f"  AC-F4: 효과 없는 쌍 {len(null)}개 중 신호 {sig}개, 최대 |z| {max(abs(z(I)) for I in null):.2f}")
        self.assertEqual(sig, 0)


# ---------------------------------------------------------------------------
class ACF5Rewards(unittest.TestCase):
    def test_default_options_identical_to_v1(self):
        """새 옵션을 기본값으로 명시해도 v1 과 같다 (전체 검사는 test_identity)."""
        def extra(c):
            c["rewards"] = {"normal_battle": {"mode": "fantasy", "fantasy_chance": 1.0, "heal_amount": 40}}
            c["policy"]["fantasy_pick"] = "random"
            c["monsters"]["model"] = "tier_avg"
        test_identity.compare(self, n=150, extra=extra)

    def test_tune_mean_fantasies(self):
        cfg = table_cfg(hp=200)
        cfg["rewards"]["normal_battle"]["mode"] = "chance"
        with tempfile.TemporaryDirectory() as tmp:
            row = ms.tune(cfg, "rewards.normal_battle.fantasy_chance", 0.05, 1.0, 13, 1.0, 10, 500, "tf", "", tmp, "",
                          integer=False, metric="mean_fantasies")
        self.assertTrue(row["in_search_range"])
        self.assertAlmostEqual(row["metric_value"], 13, delta=1.5)
        self.assertTrue(0.2 < row["found_value"] < 0.9)

    def test_modes_and_policies_change_results(self):
        base = table_cfg(hp=200)
        ctx = ms.SimContext(base)
        ref = [ms.simulate_run(base, f"m-{i}", ctx=ctx) for i in range(200)]
        nf = lambda rows: sum(r["fant_white"] + r["fant_blue"] + r["fant_red"] for r in rows) / len(rows)  # noqa: E731
        c1 = copy.deepcopy(base)
        c1["rewards"]["normal_battle"].update({"mode": "chance", "fantasy_chance": 0.3})
        r1 = [ms.simulate_run(c1, f"m-{i}") for i in range(200)]
        self.assertLess(nf(r1), nf(ref) * 0.8)
        c2 = copy.deepcopy(base)
        c2["rewards"]["normal_battle"]["mode"] = "choice"
        r2 = [ms.simulate_run(c2, f"m-{i}") for i in range(200)]
        self.assertLess(nf(r2), nf(ref))
        # greedy_value: 가치표 최상위 환상을 random 보다 자주 얻는다
        c3 = copy.deepcopy(base)
        c3["policy"]["fantasy_pick"] = "greedy_value"
        c3["policy"]["value_table"] = {"fan_damage_anchor": 1.0}
        r3 = [ms.simulate_run(c3, f"m-{i}") for i in range(200)]
        has = lambda rows: sum("fan_damage_anchor" in r["fantasies"].split("|") for r in rows)  # noqa: E731
        self.assertGreater(has(r3), has(ref))
        # 가치표 없이 greedy → random 으로 대체 (결과 동일)
        c4 = copy.deepcopy(base)
        c4["policy"]["fantasy_pick"] = "greedy_value"
        r4 = [ms.simulate_run(c4, f"m-{i}") for i in range(50)]
        self.assertEqual(r4, ref[:50])


# ---------------------------------------------------------------------------
def strip_trace(src):
    """트레이스 검사(if tr/trace/st.trace/self.trace is not None)를 통째로 뺀 소스."""
    names = {"tr", "trace"}

    class T(ast.NodeTransformer):
        def visit_If(self, node):
            self.generic_visit(node)
            t = node.test
            if isinstance(t, ast.Compare) and len(t.ops) == 1 and isinstance(t.ops[0], ast.IsNot) \
                    and isinstance(t.comparators[0], ast.Constant) and t.comparators[0].value is None:
                left = t.left
                if (isinstance(left, ast.Name) and left.id in names) or (isinstance(left, ast.Attribute) and left.attr == "trace"):
                    return node.orelse or None
            return node

    tree = T().visit(ast.parse(src))
    ast.fix_missing_locations(tree)
    return ast.unparse(tree)


class ACF7Trace(unittest.TestCase):
    def test_trace_does_not_change_results(self):
        test_identity.compare(self, n=150, trace=True)

    def test_overhead_within_2_percent(self):
        with open(os.path.join(ROOT, "matchup_sim.py"), encoding="utf-8") as fp:
            src = fp.read()
        stripped = types.ModuleType("matchup_sim_notrace")
        stripped.__file__ = os.path.join(ROOT, "matchup_sim.py")
        exec(compile(strip_trace(src), "matchup_sim_notrace", "exec"), stripped.__dict__)
        self.assertNotIn("tr is not None", strip_trace(src))
        results = []
        for hp in (660, 300):
            cfgs = {}
            for name, mod in (("cur", ms), ("strip", stripped)):
                c = _legacy(mod)
                c["monsters"]["act_hp_growth"] = 2.0
                c["monsters"]["hp_base"] = hp
                c["fantasy"]["effects_file"] = EFFECTS
                c["fantasy"]["effect_mode"] = "table"
                cfgs[name] = (mod, c, mod.SimContext(c))
            best = {"cur": 1e9, "strip": 1e9}
            rows = {}
            for rep in range(27):
                # 타이밍 잡음 대비: 9회 뒤 이미 2% 안이면 멈추고, 아니면 더 재서 최솟값을 쓴다
                if rep >= 9 and rep % 9 == 0 and best["cur"] / best["strip"] - 1 <= 0.02:
                    break
                for name in (("cur", "strip") if rep % 2 == 0 else ("strip", "cur")):
                    mod, c, ctx = cfgs[name]
                    t0 = time.perf_counter()
                    rows[name] = [mod.simulate_run(c, f"ov-{i}", ctx=ctx) for i in range(500)]
                    best[name] = min(best[name], time.perf_counter() - t0)
            self.assertEqual([{k: v for k, v in r.items()} for r in rows["cur"]], rows["strip"])
            over = best["cur"] / best["strip"] - 1
            results.append((hp, over))
            print(f"\n  AC-F7: hp_base={hp} 트레이스 끔 오버헤드 {over * 100:+.2f}% (현재 {best['cur'] * 2:.3f} / 제거본 {best['strip'] * 2:.3f} ms/판)")
        for hp, over in results:
            self.assertLessEqual(over, 0.02, f"hp_base={hp}")

    def test_divergence_point(self):
        cfg = table_cfg(hp=600)
        found_div = 0
        for i in range(12):
            r = trc.compare(cfg, f"dv-{i}", "fan_damage_slingshot")
            be, fe = r["base"]["events"], r["forced"]["events"]
            self.assertEqual(be[0]["ev"], "node")
            self.assertEqual(fe[0], {"ev": "acquire", "fid": "fan_damage_slingshot", "source": "forced", "hp": cfg["player"]["start_hp"]})
            dv = r["divergence"]
            fe2 = [e for e in fe if not (e.get("ev") == "acquire" and e.get("source") == "forced")]
            if dv is None:
                self.assertEqual([trc.project(e) for e in be], [trc.project(e) for e in fe2])
                continue
            found_div += 1
            k = dv["base"]
            self.assertEqual(dv["forced"], k + 1)   # 강제 포함 획득 이벤트 1개만큼 밀림
            self.assertEqual([trc.project(e) for e in be[:k]], [trc.project(e) for e in fe2[:k]])
            self.assertNotEqual(trc.project(be[k]) if k < len(be) else None, trc.project(fe2[k]) if k < len(fe2) else None)
            # 새총(+30/타)은 첫 전투 첫 턴에 준 피해가 달라진다
            self.assertEqual(fe[dv["forced"]]["ev"], "turn")
        self.assertGreater(found_div, 8)
        # 전투 이벤트에 발동 환상 효과가 기록된다
        r = trc.compare(cfg, "dv-0", "fan_damage_slingshot")
        battle = next(e for e in r["forced"]["events"] if e["ev"] == "battle")
        self.assertEqual(battle["fx"]["dmg_flat"][0]["fid"], "fan_damage_slingshot")
        self.assertEqual(battle["fx"]["dmg_flat"][0]["value"], 30.0)

    def test_suggest_seeds(self):
        b = {"n": 6, "wins": "010011"}
        f = {"n": 6, "wins": "110001"}
        s = trc.suggest_seeds(b, f, "s")
        self.assertEqual(s["turned_win"], ["s-0"])
        self.assertEqual(s["turned_lose"], ["s-4"])
        self.assertEqual(s["win"], ["s-0", "s-1", "s-5"])


if __name__ == "__main__":
    unittest.main()
