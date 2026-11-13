# -*- coding: utf-8 -*-
"""v4.3 F12 진행 보고 수락 기준 (AC-P1~P6): 서버 없이 엔진·집계기만으로 확인한다.

P1 완료 판 수가 단조 증가하고 마지막에 전체와 같다 · P2 캐시된 판은 '캐시'로 따로 센다
P3 진행을 켜도 결과(승·패 열)가 달라지지 않는다 · P4 취소하면 total 이 줄어 100% 로 끝난다
P5 이벤트 수가 판 수에 비례해 불어나지 않는다 · P6 한 줄 문구가 필요한 항목을 담는다
"""
import copy
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

import matchup_sim as ms  # noqa: E402
from sim_service import compute as cp  # noqa: E402
from sim_service import store as st  # noqa: E402


import fantasy_scan as fs  # noqa: E402


def small_cfg():
    """실제 환상 테이블(table 모드) 설정 — CLI 와 같은 경로로 만든다."""
    cfg, _ = fs.build_cfg(None, [], os.path.join(ROOT, "fantasy_effects.json"), "table")
    return cfg, st.table_hash(list(ms.SimContext(cfg).table.values()))


class ProgressTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.engine = cp.Engine(st.PointStore(os.path.join(self.tmp, "pc")), 1)   # 직렬 경로
        self.cfg, self.thash = small_cfg()

    def tearDown(self):
        self.engine.close()

    def reqs(self, seed="p"):
        c1, c2 = copy.deepcopy(self.cfg), copy.deepcopy(self.cfg)
        ms.set_path(c2, "player.start_hp", c2["player"]["start_hp"] + 50)
        return [cp.make_req(c1, [], seed, self.thash), cp.make_req(c2, [], seed, self.thash)]

    def test_p1_monotonic_and_total(self):
        snaps = []
        pr = cp.Progress(emit=snaps.append, min_interval=0)
        self.engine.ensure(self.reqs(), 250, progress=pr)
        done = [s["done"] for s in snaps]
        self.assertEqual(done, sorted(done))
        last = pr.snapshot()
        self.assertEqual((last["done"], last["total"]), (500, 500))

    def test_p2_cache_counted_separately(self):
        self.engine.ensure(self.reqs(), 200)
        pr = cp.Progress(min_interval=0)
        self.engine.ensure(self.reqs(), 300, progress=pr)       # 200판은 저장돼 있음, 100판씩 새로
        s = pr.snapshot()
        self.assertEqual((s["done"], s["total"], s["cached"]), (200, 200, 400))

    def test_p3_results_unchanged(self):
        a = self.engine.ensure(self.reqs("a"), 200)
        e2 = cp.Engine(st.PointStore(os.path.join(self.tmp, "pc2")), 1)
        try:
            b = e2.ensure(self.reqs("a"), 200, progress=cp.Progress(min_interval=0))
        finally:
            e2.close()
        for k in a:
            self.assertEqual(a[k]["wins"], b[k]["wins"])

    def test_p4_cancel_shrinks_total(self):
        pr = cp.Progress(min_interval=0)
        calls = {"n": 0}

        def cancel():
            calls["n"] += 1
            return calls["n"] > 2
        with self.assertRaises(cp.Cancelled):
            self.engine.ensure(self.reqs(), 1000, cancel=cancel, progress=pr)
        s = pr.snapshot()
        self.assertGreater(s["done"], 0)
        self.assertEqual(s["done"], s["total"])                  # 남은 판은 전체에서 빠진다
        self.assertLess(s["total"], 2000)

    def test_p4b_plan_two_stages(self):
        pr = cp.Progress(min_interval=0)
        rs = self.reqs()
        pr.plan(2 * 300, cached=0)
        self.engine.ensure(rs, 100, progress=pr)
        self.engine.ensure(rs, 300, progress=pr)
        s = pr.snapshot()
        self.assertEqual((s["done"], s["total"], s["cached"], s["total_final"]), (600, 600, 0, True))

    def test_p5_event_count_bounded(self):
        snaps = []
        pr = cp.Progress(emit=snaps.append, min_interval=0.05)
        self.engine.ensure(self.reqs(), 600, progress=pr)
        self.assertLess(len(snaps), 40)                           # 12조각 + 시작·끝 → 쓰로틀 포함 수십 개 이내

    def test_p6_format(self):
        line = cp.format_progress({"done": 1234, "total": 5000, "cached": 40, "rate": 12.5, "eta_s": 300,
                                   "elapsed_s": 99, "total_final": False}, "스캔")
        for part in ("스캔", "1,234", "5,000+", "24.7%", "캐시 40", "12.5판/초", "5분"):
            self.assertIn(part, line)


if __name__ == "__main__":
    unittest.main()
