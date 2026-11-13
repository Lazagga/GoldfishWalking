# -*- coding: utf-8 -*-
"""v2 속도 개선 수락 기준: AC-S1(정규 해시·캐시 적중), AC-S1b(이어 붙이기), AC-S2b(메모리),
AC-S3(적응형 위양성률·결정성·절감률), AC-S4(거친 격자 세밀화). AC-S2 는 test_identity.py."""
import copy
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

import fantasy_scan  # noqa: E402
import import_fantasies  # noqa: E402
import matchup_sim as ms  # noqa: E402
from sim_service import compute as cp  # noqa: E402
from sim_service import stats as S  # noqa: E402
from sim_service import store as st  # noqa: E402

EFFECTS = os.path.join(ROOT, "fantasy_effects.json")
FIXTURE_SRC = os.path.join(HERE, "fixtures", "fantasies")
WORKERS = max(2, min(8, (os.cpu_count() or 2) - 1))


def base_cfg(effects=EFFECTS, hp=600):
    cfg = ms.legacy_config()
    cfg["monsters"]["act_hp_growth"] = 2.0
    cfg["monsters"]["hp_base"] = hp
    ms.apply_fantasy_args(cfg, effects)
    return cfg


class ACS1Hash(unittest.TestCase):
    def test_reimport_same_hash_and_cache_hits(self):
        with tempfile.TemporaryDirectory() as tmp:
            a, b = os.path.join(tmp, "a.json"), os.path.join(tmp, "b.json")
            import_fantasies.main(["--src", FIXTURE_SRC, "--out", a])
            time.sleep(1.1)  # generated_at 이 달라지도록
            import_fantasies.main(["--src", FIXTURE_SRC, "--out", b])
            with open(a, "rb") as fa, open(b, "rb") as fb:
                self.assertNotEqual(fa.read(), fb.read())  # 파일 바이트는 다름 (generated_at)
            ha, hb = st.load_table(a)[1], st.load_table(b)[1]
            self.assertEqual(ha, hb)
            # 효과 값 하나를 바꾸면 해시가 바뀐다
            data, _ = st.load_table(b)
            data["fantasies"][0]["effects"] = data["fantasies"][0].get("effects", []) + [{"type": "dmg_flat", "value": 1}]
            self.assertNotEqual(st.table_hash(data), hb)
            data2, _ = st.load_table(b)
            for f in data2["fantasies"]:
                if f["effects"] and "value" in f["effects"][0]:
                    f["effects"][0]["value"] = f["effects"][0]["value"] + 1
                    break
            self.assertNotEqual(st.table_hash(data2), hb)
            # 메모만 바꾸면 같다
            data3, _ = st.load_table(b)
            data3["fantasies"][0]["notes"] = "다른 메모"
            data3["fantasies"][0]["fidelity"] = "none"
            self.assertEqual(st.table_hash(data3), hb)
            # a 로 스캔 → b 로 스캔: 전부 캐시 적중
            args = ["--x", "monsters.hp_base=500:700:200", "--fantasies", "fan_turn_boots,fan_damage_anchor",
                    "--runs", "300", "--seed", "h", "--set", "monsters.act_hp_growth=2.0", "--set", 'monsters.model="tier_avg"', "--workers", "2",
                    "--out", tmp, "--quiet"]
            fantasy_scan.main(["--effects", a] + args)
            store = st.PointStore(os.path.join(tmp, "point_cache"))
            n_files = sum(len(f) for _, _, f in os.walk(store.root))
            d2 = fantasy_scan.main(["--effects", b] + args)
            self.assertEqual(sum(len(f) for _, _, f in os.walk(store.root)), n_files)
            self.assertEqual(d2["meta"]["table_hash"], ha)


class ACS1bAppend(unittest.TestCase):
    def test_extend_equals_direct(self):
        cfg = base_cfg()
        thash = st.load_table(EFFECTS)[1]
        with tempfile.TemporaryDirectory() as tmp:
            e1 = cp.Engine(st.PointStore(os.path.join(tmp, "a")), WORKERS)
            e2 = cp.Engine(st.PointStore(os.path.join(tmp, "b")), 1)
            try:
                for fids in ([], ["fan_fantasy_leo"]):
                    r = cp.make_req(cfg, fids, "app", thash)
                    e1.ensure([r], 500)
                    rec_ext = e1.ensure([r], 3000)[r["key"]]
                    rec_dir = e2.ensure([r], 3000)[r["key"]]
                    self.assertEqual(rec_ext, rec_dir)
                    # 디스크에서 다시 읽어도 같다
                    self.assertEqual(st.PointStore(os.path.join(tmp, "a")).load(r["key"]), rec_dir)
            finally:
                e1.close()
                e2.close()


class ACS2bMemory(unittest.TestCase):
    LIMIT_MB = 200

    def test_worker_memory_3000_seeds(self):
        """시드 3000개 x 설정 3종을 한 프로세스에서 돌린 뒤 최대 메모리 ≤ 200MB (워커 1개 기준)."""
        code = (
            "import sys, copy; sys.path.insert(0, r'%s')\n"
            "import matchup_sim as ms\n"
            "from sim_service import compute as cp\n"
            "for hp in (74, 300, 660):\n"
            "    cfg = ms.legacy_config(); cfg['monsters']['hp_base'] = hp\n"
            "    cfg['monsters']['act_hp_growth'] = 2.0\n"
            "    if hp != 74: ms.apply_fantasy_args(cfg, r'%s')\n"
            "    cp.run_chunk((cfg, 'mem', 0, 3000))\n"
            "r = cp.worker_report(); print(r['peak_rss_mb'], r['map_cache'])\n"
        ) % (ROOT, EFFECTS)
        out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True).stdout.split()
        peak, maps = float(out[0]), int(out[1])
        print(f"\n  AC-S2b: 시드 3000개 x 설정 3종 후 최대 메모리 {peak:.0f}MB, 맵 캐시 {maps}개")
        self.assertLessEqual(peak, self.LIMIT_MB)
        self.assertLessEqual(maps, ms.MAP_CACHE_MAX)


def dummy_table(tmp, n=30):
    with open(EFFECTS, encoding="utf-8") as fp:
        data = json.load(fp)
    dummies = [{"id": f"dummy_{k:02d}", "name": f"더미 {k}", "grade": ("white", "blue", "red")[k % 3],
                "fidelity": "none", "effects": [], "notes": "", "available": True} for k in range(n)]
    data["fantasies"].extend(dummies)
    path = os.path.join(tmp, "fx_dummy.json")
    with open(path, "w", encoding="utf-8") as fp:
        json.dump(data, fp, ensure_ascii=False)
    return path, [d["id"] for d in dummies]


class ACS3Adaptive(unittest.TestCase):
    def test_null_coverage_and_saving(self):
        with tempfile.TemporaryDirectory() as tmp:
            path, ids = dummy_table(tmp)
            args = ["--effects", path, "--x", "monsters.hp_base=450:750:100", "--fantasies", ",".join(ids),
                    "--runs", "3000", "--seed", "nulla", "--set", "monsters.act_hp_growth=2.0", "--set", 'monsters.model="tier_avg"', "--adaptive",
                    "--epsilon", "0.015", "--n-stages", "500,1500,3000", "--quiet"]
            res = fantasy_scan.main(args + ["--workers", str(WORKERS), "--out", os.path.join(tmp, "n")])
            cover = total = 0
            for cur in res["curves"].values():
                for p in cur["points"]:
                    total += 1
                    cover += p["delta_ci"][0] <= 0 <= p["delta_ci"][1]
            a = res["meta"]["adaptive"]
            print(f"\n  AC-S3: 적응형 CI 0 포함 {cover}/{total} = {cover / total * 100:.1f}%, "
                  f"판 수 {a['runs_used']:,} / 비적응형 {a['runs_nonadaptive']:,} (절감 {a['saving'] * 100:.1f}%)")
            self.assertGreaterEqual(cover / total, 0.90)
            self.assertGreater(a["saving"], 0)
            # 워커 수 무관 (작은 부분집합으로)
            small = ["--effects", path, "--x", "monsters.hp_base=500:700:200", "--fantasies", ",".join(ids[:4]),
                     "--runs", "1500", "--seed", "detad", "--set", "monsters.act_hp_growth=2.0", "--set", 'monsters.model="tier_avg"', "--adaptive",
                     "--epsilon", "0.02", "--n-stages", "300,800,1500", "--quiet"]
            r1 = fantasy_scan.main(small + ["--workers", "1", "--out", os.path.join(tmp, "w1")])
            rN = fantasy_scan.main(small + ["--workers", str(WORKERS), "--out", os.path.join(tmp, "wN")])
            for d in (r1, rN):
                for k in ("scan_id", "generated_at", "elapsed_s"):
                    d["meta"].pop(k)
            self.assertEqual(r1, rN)


class ACS4Refine(unittest.TestCase):
    def test_refined_crossing_matches_dense(self):
        with tempfile.TemporaryDirectory() as tmp:
            common = ["--effects", EFFECTS, "--fantasies", "fan_turn_boots,fan_damage_slingshot", "--runs", "1500",
                      "--seed", "ref", "--set", "monsters.act_hp_growth=2.0", "--set", 'monsters.model="tier_avg"', "--workers", str(WORKERS), "--quiet",
                      "--out", tmp]
            dense = fantasy_scan.main(common + ["--x", "monsters.hp_base=200:1200:50"])
            coarse = fantasy_scan.main(common + ["--x", "monsters.hp_base=200:1200:200", "--refine-around-target"])
            T = 0.10
            for name, d, c in [("기준선", dense["baseline"]["points"], coarse["baseline"]["points"])] + [
                    (fid, dense["curves"][fid]["points"], coarse["curves"][fid]["points"]) for fid in dense["curves"]]:
                cd, cc = S.crossing(d, T), S.crossing(c, T)
                xd, xc = cd["x"], cc["x"]
                self.assertIsNotNone(xd)
                self.assertIsNotNone(xc)
                print(f"\n  AC-S4 {name}: 촘촘한 격자 {round(xd)} (교차 {[round(h) for h in cd['hits']]}) / "
                      f"세밀화 {round(xc)} (세밀화 점 {len(c)}개, 촘촘한 점 {len(d)}개)")
                # 허용 오차: 촘촘한 격자 간격(50). 촘촘한 곡선이 노이즈로 여러 번 교차하면 그 교차 구간 안이면 일치로 본다.
                lo, hi = min(cd["hits"]) - 50, max(cd["hits"]) + 50
                self.assertTrue(lo <= xc <= hi, f"{name}: {xc} not in [{lo}, {hi}]")
                self.assertLess(len(c), len(d))


if __name__ == "__main__":
    unittest.main()
