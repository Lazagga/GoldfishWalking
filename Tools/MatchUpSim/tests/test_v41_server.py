# -*- coding: utf-8 -*-
"""v4.1 F10 서버: AC-Y4(무효화), Y5·Y19(격리·재계산 동일성), Y6(캐시 재사용), Y9(양보·재개), Y11(워커 무관),
Y13(몬스터 체력), Y14(기본 힘 이산, 실제와 일치), Y15(영향 없음), Y18(몬스터는 자동 학습 안 함).
모든 쓰기는 임시 폴더의 fixtures 사본에만 한다."""
import copy
import glob
import gzip
import json
import os
import shutil
import sys
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)

from sim_service import compute as cp  # noqa: E402
from sim_service import surrogate as sg  # noqa: E402
from sim_service import surrogate_train as sgt  # noqa: E402
from test_server import Sandbox  # noqa: E402

SLING = "fan_damage_slingshot"


def wipe_cache(app):
    shutil.rmtree(app.store.root, ignore_errors=True)
    app.store._mem.clear()


class FantasyTarget(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sb = Sandbox(xs="400:800:200", runs="200", stages="200")

    @classmethod
    def tearDownClass(cls):
        cls.sb.stop()
        cls.sb.cleanup()

    def wait(self, jid, timeout=600):
        ev = self.sb.events(jid, until=lambda e: e.get("type") in ("done", "error", "cancelled"))
        self.assertEqual(ev[-1]["type"], "done", ev[-1])
        return ev

    def fit(self, field="0.value", n=200, fid=SLING):
        s, r = self.sb.req("POST", "/api/surrogate/fit", {"targets": [{"kind": "fantasy", "id": fid, "field": field}], "n": n})
        self.assertEqual(s, 200, r)
        self.assertGreater(r["estimate"]["runs"], 0)
        return self.wait(r["id"])

    def model(self, fid=SLING, field="0.value"):
        s, m = self.sb.req("GET", f"/api/surrogate/model?kind=fantasy&id={fid}&field={field}")
        self.assertEqual(s, 200, m)
        return m

    def recompute(self, edits, stages=(200,), cfg_set=None):
        jid = self.sb.job({"kind": "recompute", "edits": edits, "fids": [SLING], "stages": list(stages), "cfg_set": cfg_set or {}})
        ev = self.wait(jid)
        return {(e["series"], e["fid"], e["x"]): {k: v for k, v in e["point"].items() if k != "stage"}
                for e in ev if e["type"] == "point"}

    def test_y5_y6_isolation_and_cache(self):
        sb = self.sb
        old = next(e for e in sb.app.table_data["fantasies"] if e["id"] == SLING)["effects"][0]["value"]
        off_grid = old * 0.37 + 1.3
        edit = [{"fid": SLING, "effect": 0, "key": "value", "old": old, "new": off_grid}]
        before = self.recompute(edit)                      # 학습 없이
        self.fit()
        m = self.model()
        self.assertIn(m["status"], ("신뢰", "주의", "근사 불가", "효과 미검출"))
        # (Y5) 학습 후 같은 편집의 재계산 = 학습 전과 비트 단위 같음, 캐시를 지우고 처음부터 돌려도 같음
        self.assertEqual(self.recompute(edit), before)
        wipe_cache(sb.app)
        self.assertEqual(self.recompute(edit), before)
        # 저장 파일 검사: 점 캐시 레코드·스캔 JSON·시나리오에 근사값이 없다
        bad = ("surrogate", "sg_", "approx_p", "pred")
        for p in glob.glob(os.path.join(sb.app.store.root, "**", "*.json.gz"), recursive=True):
            with gzip.open(p, "rt", encoding="utf-8") as fp:
                rec = json.load(fp)
            self.assertFalse(set(rec) - {"key", "fids", "banned", "seed", "table_hash", "data_hash", "sim_version", "n", "wins",
                                         "reached", "death_act", "nfant", "agg", "fbf_sum", "fbf_n"}, p)
        with open(sb.app.scan_path, encoding="utf-8") as fp:
            txt = fp.read()
        self.assertFalse(any(b in txt for b in ("sgline", "surrogate_ok", "\"pred\"")))
        s, sc = sb.req("POST", "/api/scenarios", {"name": "y5", "edits": edit, "note": ""})
        self.assertEqual(s, 200, sc)
        self.assertNotIn("surrogate", json.dumps(sc, ensure_ascii=False))
        files = os.listdir(os.path.join(sb.app.results, "surrogate"))
        self.assertTrue(all(f.endswith(".json") for f in files))
        # (Y6) 격자와 같은 θ → 캐시 적중, 처음부터와 같음
        grid_t = next(t for t in m["thetas"] if abs(t - old) > 1e-9)
        e2 = [{"fid": SLING, "effect": 0, "key": "value", "old": old, "new": grid_t}]
        self.fit()                                          # 위에서 캐시를 지웠으므로 다시 채움
        n0 = sb.app.engine.runs_computed
        hit = self.recompute(e2)
        self.assertEqual(sb.app.engine.runs_computed, n0)
        wipe_cache(sb.app)
        self.assertEqual(self.recompute(e2), hit)

    def test_y4_invalidation(self):
        sb = self.sb
        self.fit(fid="fan_turn_boots")
        old_b = next(e for e in sb.app.table_data["fantasies"] if e["id"] == "fan_turn_boots")["effects"][0]["value"]
        old_s = next(e for e in sb.app.table_data["fantasies"] if e["id"] == SLING)["effects"][0]["value"]

        def validity(body):
            s, r = sb.req("POST", "/api/surrogate/models", body)
            return next(m["validity"] for m in r["models"] if m.get("id") == "fan_turn_boots")
        self.assertEqual(validity({}), "ok")
        own = {"edits": [{"fid": "fan_turn_boots", "effect": 0, "key": "value", "old": old_b, "new": 3}]}
        self.assertEqual(validity(own), "ok")                                   # 자기 θ 변경은 무효 아님
        other = {"edits": [{"fid": SLING, "effect": 0, "key": "value", "old": old_s, "new": old_s + 5}]}
        self.assertEqual(validity(other), "weak")                               # 다른 환상 → 약한 경고
        mon = sb.app.monster_data["monsters"][0]
        hp = {"edits": [{"target": "monster", "mid": mon["id"], "key": "hp", "old": mon["hp"], "new": mon["hp"] + 10}]}
        self.assertIn(validity(hp), ("ok", "invalid"))   # tier_avg 스캔: 몬스터 해시는 data_hash 에 없지만 상태 해시에는 들어감
        self.assertEqual(validity({"cfg_set": {"rewards.normal_battle.mode": "ember"}}), "invalid")   # 설정 → 강한 무효
        self.assertEqual(validity({"cfg_edits": [{"path": "monsters.act_hp_growth", "old": 2.0, "new": 2.2}]}), "invalid")

    def test_y9_y11_yield_and_determinism(self):
        sb = self.sb
        wipe_cache(sb.app)
        s, r = sb.req("POST", "/api/surrogate/fit", {"targets": [{"kind": "fantasy", "id": "fan_rest_pillow", "field": "0.value"}], "n": 600})
        bg = r["id"]
        time.sleep(1.0)
        t0 = time.perf_counter()
        jid = sb.job({"kind": "recompute", "edits": [], "fids": ["fan_turn_boots"], "stages": [200]})
        ev = sb.events(jid, until=lambda e: e.get("type") in ("started",))
        waited = time.perf_counter() - t0
        print(f"\n  AC-Y9: 학습 → 인터랙티브 작업 시작까지 {waited:.2f}s")
        self.assertLess(waited, 1.0)
        self.wait(jid)
        self.wait(bg)
        job = sb.app.jobs.jobs[bg]
        m1 = sgt.load_model(sb.app, "fantasy", "fan_rest_pillow", "0.value")
        # 캐시를 지우고 워커 1개로 중단 없이 다시 학습 → 계수가 같다 (재개 동일성 + 워커 수 무관)
        wipe_cache(sb.app)
        eng = sb.app.engine
        sb.app.engine = cp.Engine(sb.app.store, 1)
        try:
            s, r = sb.req("POST", "/api/surrogate/fit", {"targets": [{"kind": "fantasy", "id": "fan_rest_pillow", "field": "0.value"}], "n": 600})
            self.wait(r["id"])
        finally:
            sb.app.engine.close()
            sb.app.engine = eng
        m2 = sgt.load_model(sb.app, "fantasy", "fan_rest_pillow", "0.value")
        self.assertEqual(m1["x"], m2["x"])
        self.assertTrue(any(e["type"] == "yield" for e in job.events), "학습이 양보한 기록이 있어야 함")

    def test_predict_api_matches_python(self):
        self.fit(fid="fan_turn_boots")
        m = self.model("fan_turn_boots")
        x = 600
        s, p = self.sb.req("GET", "/api/surrogate/predict?kind=fantasy&id=fan_turn_boots&field=0.value&theta=3&x=600&anchor=0.3&theta_anchor=2")
        q = sg.predict(m, x, 3.0, 0.3, 2.0)
        self.assertEqual(p.get("reject"), q.get("reject"))
        if "p" in q:
            self.assertLess(abs(p["p"] - q["p"]), 1e-12)

    def test_audit(self):
        sb = self.sb
        s, r = sb.req("POST", "/api/surrogate/audit", {"kind": "fantasy", "id": SLING, "field": "0.value", "theta": 5,
                                                       "x": [600], "pred": [0.3], "actual": [0.28], "status": "신뢰"})
        self.assertEqual(s, 200, r)
        s, a = sb.req("GET", "/api/surrogate/audit")
        self.assertTrue(any(x["id"] == SLING and x["theta"] == 5 for x in a["records"]))


class MonsterTarget(unittest.TestCase):
    MID = "Mob_10101_Fairy"

    @classmethod
    def setUpClass(cls):
        cls.sb = Sandbox(xs="0.6:1.0:0.2", runs="100", stages="300", table_model=True)

    @classmethod
    def tearDownClass(cls):
        cls.sb.stop()
        cls.sb.cleanup()

    def wait(self, jid):
        ev = self.sb.events(jid, until=lambda e: e.get("type") in ("done", "error", "cancelled"))
        self.assertEqual(ev[-1]["type"], "done", ev[-1])
        return ev

    def fit(self, mid, field, n=300):
        s, r = self.sb.req("POST", "/api/surrogate/fit", {"targets": [{"kind": "monster", "id": mid, "field": field}], "n": n,
                                                          "x_points": "selected3", "x_sel": 0.8})
        self.assertEqual(s, 200, r)
        self.wait(r["id"])
        return sgt.load_model(self.sb.app, "monster", mid, field)

    def test_y13_y14_hp_and_strength(self):
        sb = self.sb
        self.assertFalse(any(m["kind"] == "monster" for m in sgt.list_models(sb.app)))      # Y18: 자동 학습 없음
        m = self.fit(self.MID, "hp", n=3000)          # 명세 기본 점당 시드 3000 (Q37)
        self.assertEqual(m["kind"], "monster")
        self.assertGreater(min(m["encounter"].values()), 0.5)
        mon = next(x for x in sb.app.monster_data["monsters"] if x["id"] == self.MID)
        th = int(mon["hp"] * 1.37)
        x = 0.8
        pr = sg.predict(m, x, th)
        # 실제 재계산 (기준선 수정 효과 = 같은 시드 짝지은 Δ)
        jid = sb.job({"kind": "recompute", "edits": [{"target": "monster", "mid": self.MID, "key": "hp", "old": mon["hp"], "new": th}],
                      "fids": [], "stages": [3000], "x_values": [x]})
        ev = self.wait(jid)
        pt = [e["point"] for e in ev if e["type"] == "point" and e["series"] == "after" and e["fid"] == "__baseline__"
              and "edit_effect" in e["point"]][-1]
        print("\n  AC-Y13 모델:", m["status"], {k: (v["status"], v.get("reason", "")) for k, v in m["x"].items()})
        self.assertIn("p", pr, pr)
        if "p" in pr:
            thr = max(sg.TRUST, 2 * m["x"][str(x)]["mean_se"])
            print(f"\n  AC-Y13: 근사 Δ {sg.delta_hat(m, x, th)[0] * 100:+.2f}%p / 실제 {pt['edit_effect'] * 100:+.2f}%p (임계 {thr * 100:.2f}%p)")
            self.assertLess(abs(sg.delta_hat(m, x, th)[0] - pt["edit_effect"]), thr + 2 * pt["edit_effect_se"])
        else:
            print(f"\n  AC-Y13: 근사 거절 ({pr['reject']}) — 실제 Δ {pt['edit_effect'] * 100:+.2f}%p")
        ms_ = self.fit(self.MID, "strength")
        self.assertTrue(ms_["discrete"])
        self.assertEqual(ms_["thetas"], [0, 1, 2])
        self.assertIsNone(sg.delta_hat(ms_, x, 1.5)[0])
        self.assertIsNone(sg.delta_hat(ms_, x, 3)[0])
        d1 = sg.delta_hat(ms_, x, 1)[0]
        jid = sb.job({"kind": "recompute", "edits": [{"target": "monster", "mid": self.MID, "key": "strength", "old": 0, "new": 1}],
                      "fids": [], "stages": [300], "x_values": [x]})
        ev = self.wait(jid)
        pt = [e["point"] for e in ev if e["type"] == "point" and e["series"] == "after" and e["fid"] == "__baseline__"
              and "edit_effect" in e["point"]][-1]
        self.assertAlmostEqual(d1, pt["edit_effect"], places=6)               # 값별 Δ 표 = 실제 재계산

    def test_y15_no_encounter(self):
        sb = self.sb
        mid = "Mob_30303_Whale"
        md = sb.app.monster_data
        keep = copy.deepcopy(md)
        keep_file = sb.app.base_cfg["monsters"]["table_file"]
        try:
            for m in md["monsters"]:
                if m["id"] == mid:
                    m["enabled"] = False                       # 풀에 없는 몬스터
            sb.app.base_cfg["monsters"]["table_file"] = sb.app.materialize_monsters(md)
            m = self.fit(mid, "hp", n=200)
            self.assertEqual(m["status"], "영향 없음")
            self.assertTrue(all(r == 0 for r in m["encounter"].values()))
            for sx in m["x"].values():
                self.assertTrue(all(d == 0 and s == 0 for _, d, s in sx["points"]))   # 모든 시드에서 Δ 정확히 0
                self.assertEqual(sx["status"], "영향 없음")
        finally:
            sb.app.monster_data = keep
            sb.app.base_cfg["monsters"]["table_file"] = keep_file

    def test_probe_model(self):
        s, r = self.sb.req("POST", "/api/surrogate/probe_fit", {"mid": self.MID, "field": "hp", "n": 300})
        self.wait(r["id"])
        s, m = self.sb.req("GET", f"/api/surrogate/model?kind=monster&id={self.MID}&field=hp&probe=1")
        self.assertEqual(s, 200, m)
        self.assertEqual(len(m["grid"]), len(m["rows"]))
        turns = [r[1] for r in m["rows"]]
        self.assertGreaterEqual(turns[-1], turns[0])            # 체력이 늘면 평균 턴 수가 줄지 않는다


if __name__ == "__main__":
    unittest.main()
