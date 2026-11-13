# -*- coding: utf-8 -*-
"""v4.1 F10 한계효과 모델 코어: AC-Y1(복원), Y2(교차 검증), Y3(거절), Y11(결정성), Y14(이산), Y16(앵커 식)."""
import math
import os
import random
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from sim_service import surrogate as sg  # noqa: E402


def synth(fn, thetas=(0, 4, 8, 12, 16, 20), xs=(400, 600, 800), w=(0.6, 0.3, 0.1), se=0.006, seed=1, noise=True, noise_sd=None):
    r = random.Random(seed)
    grid = {}
    for x, wb in zip(xs, w):
        grid[x] = [(t, fn(t, x) + (r.gauss(0, noise_sd if noise_sd is not None else se) if noise else 0.0), se, wb) for t in thetas]
    return grid


class Core(unittest.TestCase):
    def test_y1_recover(self):
        for a, b in ((0.004, 0.0), (0.006, -0.00012)):
            truth = lambda t, x, a=a, b=b: a * t + b * t * t  # noqa: E731
            m = sg.fit(synth(truth), 1000, 8)
            self.assertTrue(m["ok"], m["status"])
            for x in (400, 600, 800):
                for th in (2, 9, 15):
                    d, why = sg.delta_hat(m, x, th)
                    self.assertIsNone(why)
                    sx = m["x"][str(x)]
                    err_allow = 2 * sg.band(m, x, th) + 2 * sx["mean_se"]
                    self.assertLess(abs(d - truth(th, x)), err_allow, (a, b, x, th))
                mg = sg.marginal(m, x, 8)
                true_m = a + 2 * b * 8
                self.assertEqual(math.copysign(1, mg["m"]), math.copysign(1, true_m))
                self.assertLess(abs(mg["m"] - true_m), 2 * mg["se"], (a, b, x))

    def test_y2_cv_rejects(self):
        # 급격한 계단: 2차 다항식으로 맞지 않음 → 교차 검증 오차 큼 → 근사 불가, 그리지 않음
        step = lambda t, x: 0.0 if t < 10 else 0.12  # noqa: E731
        m = sg.fit(synth(step, se=0.004, noise=False), 1000, 8)
        for x in (400, 600):
            sx = m["x"][str(x)]
            self.assertGreater(sx["cv"], sx["caution_thr"])
            self.assertEqual(sx["status"], "근사 불가")
            self.assertIn("reject", sg.predict(m, x, 9))
        self.assertFalse(m["ok"])

    def test_y3_reject_reasons(self):
        lin = lambda t, x: 0.004 * t  # noqa: E731
        m = sg.fit(synth(lin), 1000, 8)
        self.assertIn("외삽", sg.predict(m, 600, 25)["reject"])
        self.assertIn("외삽", sg.predict(m, 600, -1)["reject"])
        sat = sg.fit(synth(lin, w=(0.01, 0.99, 0.5)), 1000, 8)
        self.assertEqual(sat["x"]["400"]["status"], "포화")
        self.assertEqual(sat["x"]["600"]["status"], "포화")
        self.assertIn("포화", sg.predict(sat, 400, 5)["reject"])
        zig = lambda t, x: [0.0, 0.06, -0.02, 0.07, -0.03, 0.05][int(t // 4)]  # noqa: E731
        nm = sg.fit(synth(zig, se=0.005, noise=False), 1000, 8)
        self.assertTrue(any("비단조" in s["reason"] or s["status"] == "근사 불가" for s in nm["x"].values()))
        flat = sg.fit(synth(lambda t, x: 0.0, se=0.01, noise_sd=0.003), 1000, 8)
        self.assertEqual(flat["status"], "효과 미검출")
        self.assertIn("효과 미검출", sg.predict(flat, 600, 5)["reject"])

    def test_y11_deterministic(self):
        g = synth(lambda t, x: 0.003 * t)
        self.assertEqual(sg.fit(g, 1000, 8), sg.fit(g, 1000, 8))

    def test_y14_discrete(self):
        g = {600: [(0, 0.0, 0.0, 0.3), (1, -0.08, 0.01, 0.3), (2, -0.15, 0.012, 0.3)]}
        m = sg.fit(g, 3000, 0, discrete=True)
        self.assertAlmostEqual(sg.delta_hat(m, 600, 1)[0], -0.08)
        self.assertIsNone(sg.delta_hat(m, 600, 1.5)[0])
        self.assertIsNone(sg.delta_hat(m, 600, 3)[0])
        self.assertIn("정수", sg.delta_hat(m, 600, 3)[1])
        p = sg.predict(m, 600, 2, anchor=0.31, theta_anchor=0)
        self.assertAlmostEqual(p["p"], 0.31 - 0.15, places=12)

    def test_y16_anchor_formula(self):
        m = sg.fit(synth(lambda t, x: 0.004 * t), 1000, 8)
        for x in (400, 600, 800):
            d1, d0 = sg.delta_hat(m, x, 13)[0], sg.delta_hat(m, x, 8)[0]
            p = sg.predict(m, x, 13, anchor=0.4, theta_anchor=8)
            self.assertLess(abs(p["p"] - min(1, max(0, 0.4 + d1 - d0))), 1e-12)
            self.assertFalse(p["no_anchor"])
            q = sg.predict(m, x, 13)
            self.assertTrue(q["no_anchor"])

    def test_solve_and_grid(self):
        m = sg.fit(synth(lambda t, x: 0.004 * t), 1000, 8)
        t = sg.solve_target(m, 600, 0.04)
        self.assertLess(abs(sg.delta_hat(m, 600, t)[0] - 0.04), 1e-6)
        self.assertIsNone(sg.solve_target(m, 600, 0.5))          # 학습 범위 안에 해 없음
        self.assertEqual(sg.theta_grid(2, 0, 20, 6, True), [0, 1, 2, 3, 4])
        self.assertEqual(sg.theta_grid(-5, -100, 0, 6), [-10.0, -8.0, -6.0, -5, -4.0, -2.0, 0.0])
        self.assertEqual(sg.theta_grid(150, 1, 10 ** 6, 6, True, mode="monster_hp")[0], 75)


if __name__ == "__main__":
    unittest.main()
