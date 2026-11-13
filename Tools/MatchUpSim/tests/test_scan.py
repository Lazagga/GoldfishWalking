# -*- coding: utf-8 -*-
"""AC4 (결정성: 워커 수·캐시 무관), AC5 (하네스 위양성률: 효과 없는 더미 30종)."""
import copy
import json
import os
import shutil
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

import fantasy_scan  # noqa: E402

EFFECTS = os.path.join(ROOT, "fantasy_effects.json")
WORKERS = max(2, min(8, (os.cpu_count() or 2) - 1))


def strip_meta(d):
    d = copy.deepcopy(d)
    for k in ("scan_id", "generated_at", "elapsed_s"):
        d["meta"].pop(k, None)
    return d


class AC4Determinism(unittest.TestCase):
    ARGS = ["--effects", EFFECTS, "--x", "monsters.hp_base=400:800:200",
            "--fantasies", "fan_turn_boots,fan_damage_slingshot,fan_cat_head,fan_fantasy_leo,fan_start_stamp",
            "--runs", "300", "--seed", "det", "--set", "monsters.act_hp_growth=2.0", "--set", 'monsters.model="tier_avg"', "--quiet"]

    def test_workers_and_cache(self):
        with tempfile.TemporaryDirectory() as tmp:
            a = fantasy_scan.main(self.ARGS + ["--workers", "1", "--out", os.path.join(tmp, "a")])
            b = fantasy_scan.main(self.ARGS + ["--workers", str(WORKERS), "--out", os.path.join(tmp, "b")])
            self.assertEqual(strip_meta(a), strip_meta(b))
            # 캐시를 쓴 재실행
            c = fantasy_scan.main(self.ARGS + ["--workers", str(WORKERS), "--out", os.path.join(tmp, "b")])
            self.assertEqual(strip_meta(a), strip_meta(c))
            # 캐시를 지우고 재실행
            shutil.rmtree(os.path.join(tmp, "b", "point_cache"))
            d = fantasy_scan.main(self.ARGS + ["--workers", str(WORKERS), "--out", os.path.join(tmp, "b")])
            self.assertEqual(strip_meta(a), strip_meta(d))
            # 파일로 쓴 JSON 도 같은 수치
            with open(os.path.join(tmp, "a", "fantasy_curves.json"), encoding="utf-8") as fp:
                self.assertEqual(strip_meta(json.load(fp)), strip_meta(a))


class AC5NullHarness(unittest.TestCase):
    """효과 없는 더미 환상 30종(풀에 포함, fidelity none)의 95% CI 가 0 을 포함하는 비율 ≈ 95% (±5%p)."""

    N_DUMMY = 30
    X = "monsters.hp_base=450:750:100"   # 기준선 승률이 약 20%→6% 인 구간 (table 모드)
    RUNS = 1000

    def test_false_positive_rate(self):
        with open(EFFECTS, encoding="utf-8") as fp:
            data = json.load(fp)
        dummies = [{"id": f"dummy_{k:02d}", "name": f"더미 {k}", "grade": ("white", "blue", "red")[k % 3],
                    "fidelity": "none", "effects": [], "notes": "AC5 더미", "available": True}
                   for k in range(self.N_DUMMY)]
        data["fantasies"].extend(dummies)
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "fx_dummy.json")
            with open(path, "w", encoding="utf-8") as fp:
                json.dump(data, fp, ensure_ascii=False)
            res = fantasy_scan.main(["--effects", path, "--x", self.X,
                                     "--fantasies", ",".join(d["id"] for d in dummies),
                                     "--runs", str(self.RUNS), "--seed", "null", "--set", "monsters.act_hp_growth=2.0", "--set", 'monsters.model="tier_avg"',
                                     "--workers", str(WORKERS), "--out", tmp, "--quiet"])
        cover, total, deltas, widths = 0, 0, [], []
        for fid, cur in res["curves"].items():
            for p in cur["points"]:
                lo, hi = p["delta_ci"]
                total += 1
                cover += lo <= 0 <= hi
                deltas.append(p["delta"])
                widths.append(hi - lo)
        rate = cover / total
        mean_delta = sum(deltas) / len(deltas)
        mean_half = sum(widths) / len(widths) / 2
        print(f"\n  AC5: CI 가 0 포함 {cover}/{total} = {rate * 100:.1f}%, 더미 평균 Δ {mean_delta * 100:+.2f}%p, "
              f"평균 CI 반폭 {mean_half * 100:.2f}%p")
        self.assertGreaterEqual(rate, 0.90)
        self.assertLessEqual(rate, 1.00)
        self.assertLess(abs(mean_delta), mean_half)

    def test_calibration_independent_seeds(self):
        """위 검사는 더미 30종이 같은 기준선 표본을 공유해 서로 상관된다. 시드를 더미마다 따로 써서
        서로 독립인 z = Δ/se 를 모으고, z 의 분포가 표준정규에 가까운지(평균 z² ≈ 1, 포함률 ≈ 95%) 본다."""
        with open(EFFECTS, encoding="utf-8") as fp:
            data = json.load(fp)
        data["fantasies"].append({"id": "dummy_x", "name": "더미", "grade": "white", "fidelity": "none",
                                  "effects": [], "notes": "", "available": True})
        zs = []
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "fx_dummy.json")
            with open(path, "w", encoding="utf-8") as fp:
                json.dump(data, fp, ensure_ascii=False)
            for k in range(40):
                res = fantasy_scan.main(["--effects", path, "--x", "monsters.hp_base=500:600:100",
                                         "--fantasies", "dummy_x", "--runs", str(self.RUNS), "--seed", f"cal{k}",
                                         "--set", "monsters.act_hp_growth=2.0", "--set", 'monsters.model="tier_avg"', "--workers", "4",
                                         "--out", tmp, "--quiet"])
                for p in res["curves"]["dummy_x"]["points"]:
                    if p["delta_se"] > 0:
                        zs.append(p["delta"] / p["delta_se"])
        mean_z2 = sum(z * z for z in zs) / len(zs)
        cover = sum(abs(z) <= 1.96 for z in zs) / len(zs)
        print(f"\n  AC5(독립): z {len(zs)}개, 평균 z² {mean_z2:.2f} (기대 1), |z|≤1.96 비율 {cover * 100:.1f}%")
        self.assertTrue(0.6 <= mean_z2 <= 1.5, mean_z2)
        self.assertGreaterEqual(cover, 0.88)


if __name__ == "__main__":
    unittest.main()
