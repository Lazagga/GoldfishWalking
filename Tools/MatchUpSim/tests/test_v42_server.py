# -*- coding: utf-8 -*-
"""v4.2 F11 (M28·M29) 서버·통계 수락 기준.

AC-H3 구버전 스캔 재현 설정 / AC-H4·H6 증가 곡선(시작 체력)에서 교차·등가 시작 체력 / AC-H8 승률 맞추기(CLI = 서버,
파일 바이트 불변, 범위 밖) / AC-H12 X축이 바뀌면 근사 학습 무효.
모든 파일 쓰기는 임시 샌드박스(tests/fixtures 사본) 안에서만 한다.
"""
import csv
import hashlib
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)

import matchup_sim as ms  # noqa: E402
from sim_service import stats as S  # noqa: E402
from sim_service import surrogate_train as sgt  # noqa: E402
from test_server import Sandbox  # noqa: E402


def tree_digest(*paths):
    h = hashlib.sha1()
    for p in paths:
        if os.path.isdir(p):
            for dp, _, fs in sorted(os.walk(p)):
                for f in sorted(fs):
                    with open(os.path.join(dp, f), "rb") as fp:
                        h.update(f.encode() + fp.read())
        elif os.path.exists(p):
            with open(p, "rb") as fp:
                h.update(fp.read())
    return h.hexdigest()


class IncreasingCurve(unittest.TestCase):
    """X = 시작 체력이면 승률이 X 에 대해 증가한다 (F11.4)."""
    XS = [50, 100, 150, 200, 250, 300]

    @staticmethod
    def f(x):
        return min(0.95, 0.02 + 0.0012 * x)

    def test_h4_crossing_direction(self):
        pts = [{"x": x, "win_rate": self.f(x)} for x in self.XS]
        c = S.crossing(pts, 0.10)
        self.assertAlmostEqual(c["x"], (0.10 - 0.02) / 0.0012, places=6)
        # 모두 목표 위 → 증가 곡선이므로 교차는 X 최소 아래 (dir = −1). 감소 곡선이면 X 최대 위 (dir = 1)
        self.assertEqual(S.crossing([{"x": x, "win_rate": 0.5 + x / 1e4} for x in self.XS], 0.10)["dir"], -1)
        self.assertEqual(S.crossing([{"x": x, "win_rate": 0.5 - x / 1e4} for x in self.XS], 0.10)["dir"], 1)
        self.assertEqual(S.crossing([{"x": x, "win_rate": 0.01 + x / 1e5} for x in self.XS], 0.10)["dir"], 1)

    def test_h6_equiv_start_hp(self):
        # 환상 = 시작 체력 +40 과 같은 효과 → 등가 시작 체력 +40 을 복원
        for x0 in (100, 150, 200):
            g, why = S.equiv_gain(self.XS, [self.f(x) for x in self.XS], self.f(x0 + 40), x0)
            self.assertIsNone(why)
            self.assertAlmostEqual(g, 40, places=6)
        # 평탄 구간은 산출 불가
        g, why = S.equiv_gain(self.XS, [0.3] * len(self.XS), 0.31, 150)
        self.assertIsNone(g)
        self.assertIn("평탄", why)


class StartHpServer(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sb = Sandbox(xs="100:200:50", runs="120", stages="60,120", start_hp=True)

    @classmethod
    def tearDownClass(cls):
        cls.sb.stop()
        cls.sb.cleanup()

    def run_job(self, body):
        jid = self.sb.job(body)
        evs = self.sb.events(jid, until=lambda e: e["type"] in ("done", "error", "cancelled"))
        return evs

    def test_defaults_from_scan(self):
        a = self.sb.app
        self.assertEqual(a.x_key, "player.start_hp")
        M = a.base_cfg["monsters"]
        self.assertEqual((M["model"], M["damage_model"], M["gimmicks"]), ("table", "digits", "on"))
        self.assertEqual(a.scan["meta"]["x_current"], 150)

    def test_h8_tune_matches_cli_and_writes_nothing(self):
        sb = self.sb
        protected = (sb.mon, sb.pat, sb.mtable, sb.src, sb.effects, sb.ov, sb.scen)
        before = tree_digest(*protected)
        body = {"kind": "tune", "key": "monsters.hp_scale", "lo": 0.5, "hi": 2.0, "target": 0.10, "runs": 80,
                "max_evals": 4, "seed": "tq"}
        evs = self.run_job(body)
        done = evs[-1]
        self.assertEqual(done["type"], "done", done)
        r = done["result"]
        self.assertEqual(len([e for e in evs if e["type"] == "tune_point"]), len(r["evals"]))
        self.assertIn("table", r)
        self.assertEqual(len(r["table"]["monsters"]), 39)
        self.assertTrue(all(m["scaled"] == max(1, round(m["hp"] * r["found"])) for m in r["table"]["monsters"]))
        self.assertLessEqual(r["ci"][0], r["win_rate"])
        self.assertGreaterEqual(r["ci"][1], r["win_rate"])
        # 같은 시드·판 수의 CLI 결과와 같다
        with tempfile.TemporaryDirectory() as tmp:
            ms.main(["--effects", sb.effects, "--set", "monsters.table_file=\"" + sb.mtable.replace("\\", "/") + "\"",
                     "--tune", "monsters.hp_scale=0.5:2", "--target", "0.10", "--runs", "80", "--max-evals", "4",
                     "--seed", "tq", "--out", tmp])
            with open(os.path.join(tmp, "tune_results.csv"), encoding="utf-8-sig") as fp:
                row = list(csv.DictReader(fp))[-1]
        self.assertAlmostEqual(float(row["found_value"]), r["found"], places=6)
        self.assertAlmostEqual(float(row["win_rate"]), r["win_rate"], places=6)
        self.assertEqual(row["stop_reason"], r["stop"])
        self.assertEqual(tree_digest(*protected), before)          # 몬스터 JSON·설정·시나리오 바이트 불변

    def test_h8_start_hp_and_out_of_range(self):
        evs = self.run_job({"kind": "tune", "key": "player.start_hp", "lo": 50, "hi": 400, "target": 0.10, "runs": 60,
                            "max_evals": 4, "seed": "tq2"})
        r = evs[-1]["result"]
        self.assertIsInstance(r["found"], int)
        self.assertEqual(r["current"], 150)
        self.assertNotIn("table", r)
        evs = self.run_job({"kind": "tune", "key": "player.start_hp", "lo": 50, "hi": 100, "target": 0.99, "runs": 40,
                            "max_evals": 4, "seed": "tq3"})
        r = evs[-1]["result"]
        self.assertFalse(r["in_range"])
        self.assertIn("범위 밖", r["stop"])

    def test_h8_rejects_other_keys(self):
        evs = self.run_job({"kind": "tune", "key": "monsters.hp_base", "lo": 1, "hi": 2, "runs": 10})
        self.assertEqual(evs[-1]["type"], "error")

    def test_h12_x_param_in_fit_hash(self):
        a = self.sb.app
        fid = "fan_turn_boots"
        cand = next((c for c in sgt.fantasy_targets(a) if c["id"] == fid), None) if hasattr(sgt, "fantasy_targets") else None
        field = cand["field"] if cand else "0.value"
        h1 = sgt.state_hashes(a, "fantasy", fid, field)
        old = a.x_key
        try:
            a.x_key = "monsters.hp_scale"
            h2 = sgt.state_hashes(a, "fantasy", fid, field)
        finally:
            a.x_key = old
        self.assertNotEqual(h1[0], h2[0])      # 강한 무효 (다시 학습)
        self.assertEqual(h1[1], h2[1])


class LegacyScan(unittest.TestCase):
    """AC-H3: 과거 x_param = hp_base (tier_avg) 스캔이 구버전 설정으로 열린다."""

    @classmethod
    def setUpClass(cls):
        cls.sb = Sandbox(xs="500:700:200", runs="60", stages="30,60")

    @classmethod
    def tearDownClass(cls):
        cls.sb.stop()
        cls.sb.cleanup()

    def test_h3_legacy_config(self):
        a = self.sb.app
        M = a.base_cfg["monsters"]
        self.assertEqual((M["model"], M["damage_model"], M["gimmicks"]), ("tier_avg", "gauss", "off"))
        self.assertEqual(a.x_key, "monsters.hp_base")
        st_, _ = self.sb.req("GET", "/")
        self.assertEqual(st_, 200)


if __name__ == "__main__":
    unittest.main()
