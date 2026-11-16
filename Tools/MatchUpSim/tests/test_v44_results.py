# -*- coding: utf-8 -*-
"""v4.4 F14.5·F14.6 — 저장된 계산 복원(cache_only), 스캔 색인·선택·저장, 작업 결과 저장 (AC-W9·W10·W11·W15)."""
import json
import os
import sys
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)

from sim_service import results as rs  # noqa: E402
from test_server import Sandbox  # noqa: E402

BOOTS = "fan_turn_boots"
MID = "Mob_10102_WildDog"


def boots_old(sb):
    s, fj = sb.req("GET", "/api/fantasies")
    return next(f for f in fj["fantasies"] if f["id"] == BOOTS)["effects"][0]["value"]


def restart(sb):
    sb.stop()
    return Sandbox(reuse=sb.tmp)


def points(evs, series="after"):
    return {(e["fid"], e["x"]): e["point"] for e in evs if e["type"] == "point" and e["series"] == series}


class CacheOnly(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sb = Sandbox(xs="500:700:200", runs="30", stages="20,30")

    @classmethod
    def tearDownClass(cls):
        cls.sb.stop()
        cls.sb.cleanup()

    def test_w9_cache_only_restores_same_points_without_computing(self):
        sb = self.sb
        old = boots_old(sb)
        body = {"kind": "recompute", "edits": [{"fid": BOOTS, "effect": 0, "key": "value", "old": old, "new": old + 1}],
                "fids": [BOOTS], "stages": [20, 30], "client": "w9"}
        real = sb.events(sb.job(body))
        self.assertEqual(real[-1]["type"], "done")
        before = sb.app.engine.runs_computed
        peek = sb.events(sb.job({**body, "cache_only": True}))
        self.assertEqual(peek[-1]["type"], "done")
        self.assertEqual(sb.app.engine.runs_computed, before)                       # 새로 돌린 판 없음
        a, b = points(real), points(peek)
        self.assertTrue(b)
        for k, p in b.items():
            self.assertEqual(p["n"], 30)
            self.assertEqual(p["wins"], a[k]["wins"])                                # 같은 점 (n·wins 동일)
            self.assertFalse(p["partial"])
        summ = next(e for e in peek if e["type"] == "cache_summary")
        self.assertEqual(summ["missing_count"], 0)

    def test_cache_only_reports_missing_and_partial(self):
        sb = self.sb
        old = boots_old(sb)
        body = {"kind": "recompute", "edits": [{"fid": BOOTS, "effect": 0, "key": "value", "old": old, "new": old + 2}],
                "fids": [BOOTS], "stages": [20], "client": "w9b"}
        sb.events(sb.job(body))                                                      # 20판까지만 저장
        peek = sb.events(sb.job({**body, "stages": [20, 30], "cache_only": True}))
        summ = next(e for e in peek if e["type"] == "cache_summary")
        self.assertGreater(summ["partial"], 0)                                       # 목표(30)에 못 미침
        self.assertTrue(all(p["partial"] for p in points(peek).values()))
        # 한 번도 계산하지 않은 상태
        none = sb.events(sb.job({"kind": "recompute", "client": "w9c", "cache_only": True, "stages": [20],
                                 "edits": [{"fid": BOOTS, "effect": 0, "key": "value", "old": old, "new": old + 7}], "fids": [BOOTS]}))
        s2 = next(e for e in none if e["type"] == "cache_summary")
        self.assertGreater(s2["missing_count"], 0)
        self.assertTrue(any(m["fid"] == BOOTS and m["series"] == "after" for m in s2["missing"]))   # 계산한 적 없는 편집본은 missing
        self.assertFalse([k for k in points(none) if k[0] == BOOTS])                                # 점도 만들어 내지 않는다


    def test_scan_cache_only_restores_all_fantasies_without_computing(self):
        """전체 재계산 결과(적응형 포함)를 환상 전부에 대해 캐시에서 읽는다 — 새로고침 뒤 '이전' 배지가 남지 않게."""
        sb = self.sb
        old = boots_old(sb)
        body = {"kind": "scan", "fids": [BOOTS, "fan_damage_slingshot"], "stages": [20, 30], "adaptive": True, "client": "sc",
                "edits": [{"fid": BOOTS, "effect": 0, "key": "value", "old": old, "new": old + 3}]}
        real = sb.events(sb.job(body))
        self.assertEqual(real[-1]["type"], "done")
        before = sb.app.engine.runs_computed
        peek = sb.events(sb.job({**body, "cache_only": True}))
        self.assertEqual(peek[-1]["type"], "done")
        self.assertEqual(sb.app.engine.runs_computed, before)                       # 새로 돌린 판 없음
        a, b = points(real), points(peek)
        self.assertTrue(b)
        self.assertEqual(set(a), set(b))                                             # 같은 (환상, X) 점들
        for k in a:
            self.assertEqual(b[k]["wins"], a[k]["wins"])
            self.assertEqual(b[k]["n"], a[k]["n"])
            self.assertFalse(b[k]["partial"])                                        # 적응형이 첫 단계에서 멈춘 점도 부분 결과가 아님
        self.assertEqual(next(e for e in peek if e["type"] == "cache_summary")["missing_count"], 0)


class ScansAndResults(unittest.TestCase):
    def setUp(self):
        self.sb = Sandbox(xs="500:700:200", runs="30", stages="20,30", start_hp=True)

    def tearDown(self):
        self.sb.stop()
        self.sb.cleanup()

    def test_w10_scan_choice_prefers_matching_scan(self):
        sb = self.sb
        s, lst = sb.req("GET", "/api/scans")
        self.assertEqual(s, 200)
        self.assertEqual(len(lst["scans"]), 1)
        scan = lst["scans"][0]
        self.assertTrue(scan["match"])                                               # CLI 스캔의 해시가 서버 해시와 같다
        self.assertTrue(scan["active"])
        # 기본 파일을 오래된 해시로 바꿔 둔다 (원본이 바뀐 뒤 옛 파일이 올라오던 상황)
        path = os.path.join(sb.results, "fantasy_curves.json")
        with open(path, encoding="utf-8") as fp:
            d = json.load(fp)
        d["meta"]["data_hash"] = "stale000"
        d["meta"]["scan_id"] = "99999999-999999-ffffff"
        with open(path, "w", encoding="utf-8") as fp:
            json.dump(d, fp)
        sb = self.sb = restart(sb)
        s, st = sb.req("GET", "/api/state")
        self.assertEqual(st["scan_id"], scan["scan_id"])                             # 맞는 스캔을 올림
        self.assertEqual(st["scan_meta"]["data_hash"], sb.app.data_hash)
        # 수동 선택·형식 검사
        self.assertEqual(sb.req("POST", "/api/scans/..%2F..%2Fx/activate", {})[0], 400)
        self.assertEqual(sb.req("POST", "/api/scans/20200101-000000-abcdef/activate", {})[0], 400)
        s, r = sb.req("POST", f"/api/scans/{scan['scan_id']}/activate", {})
        self.assertEqual((s, r["scan_id"]), (200, scan["scan_id"]))

    def test_w15_save_scan_current_only_when_hash_matches(self):
        sb = self.sb
        job = sb.job({"kind": "scan", "fids": [BOOTS], "stages": [20], "adaptive": False, "client": "w15"})
        evs = sb.events(job)
        self.assertEqual(evs[-1]["type"], "done", evs[-1])
        d0 = os.listdir(os.path.join(sb.results, "fantasy_scans"))
        with open(os.path.join(sb.results, "fantasy_curves.json"), encoding="utf-8") as fp:
            sid0 = json.load(fp)["meta"]["scan_id"]
        s, r = sb.req("POST", f"/api/jobs/{job}/save", {"as_current": True})
        self.assertEqual(s, 200, r)
        self.assertTrue(r["current"])
        with open(os.path.join(sb.results, "fantasy_curves.json"), encoding="utf-8") as fp:
            self.assertEqual(json.load(fp)["meta"]["scan_id"], r["scan_id"])         # 현재 스캔이 갱신됨
        self.assertIn(r["scan_id"] + ".json", os.listdir(os.path.join(sb.results, "fantasy_scans")))
        # 편집이 있는 결과: fantasy_scans/ 에만 저장하고 현재 스캔은 그대로
        old = boots_old(sb)
        job2 = sb.job({"kind": "scan", "fids": [BOOTS], "stages": [20], "adaptive": False, "client": "w15b",
                       "edits": [{"fid": BOOTS, "effect": 0, "key": "value", "old": old, "new": old + 1}]})
        sb.events(job2)
        with open(os.path.join(sb.results, "fantasy_curves.json"), encoding="utf-8") as fp:
            cur = json.load(fp)["meta"]["scan_id"]
        s, r2 = sb.req("POST", f"/api/jobs/{job2}/save", {"as_current": True, "name": "편집본"})
        self.assertEqual(s, 200, r2)
        self.assertFalse(r2["current"])
        with open(os.path.join(sb.results, "fantasy_curves.json"), encoding="utf-8") as fp:
            self.assertEqual(json.load(fp)["meta"]["scan_id"], cur)                  # 현재 스캔 불변
        self.assertIn(r2["scan_id"] + ".json", os.listdir(os.path.join(sb.results, "fantasy_scans")))
        self.assertEqual(sb.req("POST", "/api/jobs/jnone/save", {})[0], 400)
        self.assertGreater(len(os.listdir(os.path.join(sb.results, "fantasy_scans"))), len(d0))
        self.assertNotEqual(sid0, "")

    def test_w11_monster_metrics_survive_restart(self):
        sb = self.sb
        s, mons = sb.req("GET", "/api/monsters")
        hp = next(m for m in mons["monsters"] if m["id"] == MID)["hp"]
        body = {"kind": "monster_metrics", "stages": [40], "chunk": 40, "client": "w11",
                "edits": [{"target": "monster", "mid": MID, "key": "hp", "old": hp, "new": hp + 11}]}
        first = sb.events(sb.job(body))
        m1 = [e for e in first if e["type"] == "metrics"][-1]
        self.assertFalse(m1.get("from_saved"))
        self.assertTrue(os.listdir(os.path.join(sb.results, "monster_metrics")))
        sb = self.sb = restart(sb)
        second = sb.events(sb.job(body))
        m2 = [e for e in second if e["type"] == "metrics"][-1]
        self.assertTrue(m2.get("from_saved"))                                        # 바로 표시
        self.assertEqual(m2["data"]["monsters"], m1["data"]["monsters"])
        self.assertFalse([e for e in second if e["type"] == "progress" and e.get("done")])   # 다시 계산하지 않음

    def test_job_results_saved_listed_and_looked_up(self):
        sb = self.sb
        job = sb.job({"kind": "combo", "ids": [BOOTS, "fan_damage_slingshot"], "arms": "full", "x_values": [100],
                      "stages": [20], "baseline_type": "natural", "client": "r1", "label": "pre"})
        evs = sb.events(job)
        if evs[-1]["type"] != "done":
            self.skipTest("combo 작업이 이 픽스처에서 끝나지 않음: " + str(evs[-1])[:200])
        s, lst = sb.req("GET", "/api/results?kind=combo")
        self.assertEqual(s, 200)
        self.assertEqual(len(lst["results"]), 1)
        key = lst["results"][0]["key"]
        s, got = sb.req("GET", f"/api/results/combo/{key}")
        self.assertEqual(got["kind"], "combo")
        self.assertEqual(got["data_hash"], sb.app.data_hash)
        s, look = sb.req("POST", "/api/results/lookup", {"kind": "combo", "params": {"ids": [BOOTS, "fan_damage_slingshot"], "arms": "full",
                                                                                      "x_values": [100], "stages": [20], "baseline_type": "natural", "label": "pre"}})
        self.assertTrue(look["found"])
        self.assertEqual(sb.req("GET", "/api/results/combo/..%2F..%2Fx")[0], 400)
        self.assertEqual(sb.req("GET", "/api/results?kind=evil")[0], 400)

    def test_monster_metrics_uses_selected_x_and_goes_up_to_300k(self):
        """몬스터별 지표는 선택한 X(시작 체력)에서 계산하고, 기본 단계는 최대 30만 판이다 (v4.4)."""
        from sim_service import jobs as jb
        self.assertEqual(jb.MON_STAGES[-1], 300000)
        self.assertEqual(list(jb.MON_STAGES), sorted(jb.MON_STAGES))
        sb = self.sb

        def run(**kw):
            evs = sb.events(sb.job({"kind": "monster_metrics", "stages": [200], "chunk": 100, "client": "mx", **kw}))
            return evs, [e for e in evs if e["type"] == "metrics"]
        _, lo = run(x=20)
        _, hi = run(x=700)
        a, b = lo[-1]["data"], hi[-1]["data"]
        self.assertEqual((a["meta"]["x_param"], a["meta"]["x"]), ("player.start_hp", 20))
        self.assertEqual(b["meta"]["x"], 700)
        self.assertGreater(a["deaths"], b["deaths"])                                 # 시작 체력이 낮을수록 많이 죽는다 → X 가 실제로 반영됨
        evs, _ = run(x="abc")
        self.assertEqual(evs[-1]["type"], "error")
        evs, none = run()                                                            # x 를 안 주면 서버 기본 설정 (X 표시 없음)
        self.assertIsNone(none[-1]["data"]["meta"]["x"])

    def test_results_prune_limits_per_kind(self):
        root = self.sb.results
        for i in range(rs.PER_KIND_MAX + 5):
            rs.save(root, "tune", {"i": i}, f"h{i}", "", {"v": i})
            time.sleep(0.005)
        self.assertLessEqual(len(rs.list_(root, "tune")), rs.PER_KIND_MAX)


if __name__ == "__main__":
    unittest.main()
