# -*- coding: utf-8 -*-
"""v4.5 F16 몬스터 전투 로그 — 서버 수준 (AC-L2~L8·L11·L14) 과 결과 불변(AC-L6)."""
import copy
import http.client
import io
import json
import os
import sys
import time
import unittest
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)

import matchup_sim as ms  # noqa: E402
import monster_log as cli  # noqa: E402
from sim_service import battlelog as bl  # noqa: E402
from sim_service import jobs as jb  # noqa: E402
from sim_service import monsters as mo  # noqa: E402
from test_server import Sandbox  # noqa: E402
from test_v4_digits import cfg_of  # noqa: E402


def metrics(sb, **kw):
    evs = sb.events(sb.job({"kind": "monster_metrics", "stages": [90], "chunk": 30, "client": "ml", **kw}))
    return evs, [e for e in evs if e["type"] == "metrics"]


class ServerLog(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sb = Sandbox(xs="500:700:200", runs="30", stages="20,30")
        xs = cls.sb.app.x_values
        cls.x = xs[len(xs) // 2]                                                      # 내보내기 기본 범위(가운데 X)와 같은 X 로 계산
        evs, mets = metrics(cls.sb, x=cls.x)
        assert evs[-1]["type"] == "done", evs[-1]
        cls.data = mets[-1]["data"]
        cls.rows = {m["id"]: m for m in cls.data["monsters"]}

    @classmethod
    def tearDownClass(cls):
        cls.sb.stop()
        cls.sb.cleanup()

    def pick(self):
        m = max(self.rows.values(), key=lambda r: r["battles"])
        return m

    def log(self, **body):
        return self.sb.req("POST", "/api/monster_log", {"seed": "mon1", **body})

    # --- AC-L2
    def test_l2_sample_lists(self):
        m = self.pick()
        self.assertEqual(set(m["samples"]) <= set(bl.CATS), True)
        for cat, lst in m["samples"].items():
            self.assertLessEqual(len(lst), bl.N_SAMPLES)
            if cat == "death":
                self.assertTrue(all(s["outcome"] == "death" for s in lst))
            if cat == "win":
                self.assertTrue(all(s["outcome"] == "win" for s in lst))
        mh = [s["max_hit"] for s in m["samples"]["max_hit"]]
        self.assertEqual(mh, sorted(mh, reverse=True))                               # 최대 1타 분류는 내림차순
        lg = [s["turns"] for s in m["samples"]["long"]]
        self.assertEqual(lg, sorted(lg, reverse=True))
        early = [e for e in metrics(self.sb, stages=[30, 60], seed="l2seed")[1]][0]                  # 앞 단계 이벤트에는 표본 대신 pending
        self.assertTrue(all(r.get("samples_stage") == "pending" and "samples" not in r for r in early["data"]["monsters"]))

    # --- AC-L4 / L5
    def test_l4_l5_replay_matches_and_sums(self):
        m = self.pick()
        n = 0
        for cat, lst in m["samples"].items():
            for s in lst[:3]:
                s_, r = self.log(mid=m["id"], run=s["run"], ord=s["ord"],
                                 expect={"turns": s["turns"], "taken": s["taken"], "max_hit": s["max_hit"], "outcome": s["outcome"], "floor": s["floor"]})
                self.assertEqual(s_, 200, r)
                self.assertTrue(r["replay_match"], r.get("mismatch"))
                self.assertEqual(sum(t["taken"] for t in r["turns"]), r["battle"]["taken"])        # 턴 합계 = 전투 받은 피해
                self.assertEqual(len(r["turns"]), r["battle"]["turns"])                           # 턴 수
                self.assertEqual(sum(t["taken_cap"] for t in r["turns"]), r["battle"]["taken_cap"])
                self.assertEqual(r["battle"]["hp0"], s["hp0"])
                self.assertEqual(r["seed"], f"mon1-{s['run']}")
                n += 1
        self.assertGreaterEqual(n, 15)
        s = m["samples"]["long"][0]
        s_, r = self.log(mid=m["id"], run=s["run"], ord=s["ord"], expect={"turns": s["turns"] + 1})   # 일부러 틀린 기대값
        self.assertFalse(r["replay_match"])
        self.assertEqual(r["mismatch"]["turns"]["expected"], s["turns"] + 1)
        self.assertEqual(r["mismatch"]["turns"]["replayed"], s["turns"])

    # --- AC-L3: 보유 환상이 같은 시드의 acquire 이벤트와 순서까지 같다
    def test_l3_owned_matches_trace_acquire(self):
        m = self.pick()
        cfg, *_ = jb.monster_metrics_setup(self.sb.app, {"edits": [], "seed": "mon1"})
        s = m["samples"]["random"][0]
        s_, r = self.log(mid=m["id"], run=s["run"], ord=s["ord"])
        tr = []
        ms.simulate_run(cfg, f"mon1-{s['run']}", trace=tr, battle_log=[])
        first_battle = next(i for i, e in enumerate(tr) if e.get("ev") == "battle" and e.get("monster") == m["id"])
        ev = [e["fid"] for e in tr[:first_battle] if e.get("ev") == "acquire"]
        # ord 번째 전투가 첫 전투가 아닐 수 있으므로 같은 전투의 시작 위치를 직접 찾는다
        idx = [i for i, e in enumerate(tr) if e.get("ev") == "battle" and e.get("monster") == m["id"]][s["ord"]]
        ev = [e["fid"] for e in tr[:idx] if e.get("ev") == "acquire"]
        self.assertEqual([o["fid"] for o in r["owned"]], ev)

    # --- AC-L8
    def test_l8_outlier_columns(self):
        for m in self.rows.values():
            self.assertLessEqual(m["avg_taken_cap"], m["avg_taken"] + 1e-9)
            for k in ("taken_p50", "taken_p90", "max_hit_p50", "max_hit_p90", "overkill_share", "outlier", "hp0_mean"):
                self.assertIn(k, m)
            self.assertLessEqual(m["taken_p50"], m["taken_p90"])
            self.assertLessEqual(m["max_hit_p50"], m["max_hit_p90"] * 1.1 + 1)
            self.assertEqual(m["avg_taken"], round(m["avg_taken"], 2))
        # 이상치 기준: 평균이 한도 평균의 3배 이상이거나 최대 1타가 시작 체력의 100배 이상
        rows = mo.build_result(cfg_of(), {"x": {"tier": "boss", "act": 3, "battles": 10, "turns": 50, "turns_sq": 300, "taken": 100000, "deaths": 1,
                                                 "max_hit_sum": 5, "max_hit_max": 90000, "timeouts": 0, "escapes": 0, "taken_cap": 300, "hp0_sum": 2000,
                                                 "h_taken": {1: 10}, "h_max": {1: 10}}}, 1, 10, 0)["monsters"]
        self.assertTrue(rows[0]["outlier"])

    # --- AC-L11
    def test_l11_auth_and_validation(self):
        m = self.pick()
        self.assertEqual(self.sb.req("POST", "/api/monster_log", {"mid": m["id"], "run": 1}, token=False)[0], 403)
        self.assertEqual(self.sb.req("POST", "/api/monster_log", {"mid": m["id"], "run": 1}, token=True, origin="http://evil.example")[0], 403)
        self.assertEqual(self.log(mid="NoSuchMonster", run=1)[0], 400)
        self.assertEqual(self.log(mid=m["id"], run=-1)[0], 400)
        self.assertEqual(self.log(mid=m["id"], run=10_000_000)[0], 400)
        self.assertEqual(self.log(mid=m["id"], run="3")[0], 400)
        self.assertEqual(self.log(mid=m["id"], run=1, seed="../x")[0], 400)
        self.assertEqual(self.log(mid=m["id"], run=1, seed="a" * 65)[0], 400)
        self.assertEqual(self.log(mid=m["id"], run=1, ord=5000)[0], 400)                 # 그 런에 그만큼의 전투가 없음
        self.assertEqual(self.log(mid=m["id"], run=1, expect={"evil": 1})[0], 400)

    # --- AC-L14
    def test_l14_export_battle_log_and_battles(self):
        m = self.pick()
        s = m["samples"]["long"][0]
        scope = {"mid": m["id"], "seed": "mon1", "run": s["run"], "ord": s["ord"]}

        def raw(path, body):
            c = http.client.HTTPConnection("127.0.0.1", self.sb.port, timeout=60)
            c.request("POST", path, body=json.dumps(body).encode(), headers={"Host": f"127.0.0.1:{self.sb.port}", "X-MatchUp-Token": self.sb.token, "Content-Type": "application/json"})
            r = c.getresponse()
            return r.status, r.read()
        st, b = raw("/api/export/battle_log", {"scope": scope, "format": "csv"})
        self.assertEqual(st, 200)
        self.assertEqual(b[:3], b"\xef\xbb\xbf")
        lines = b[3:].decode("utf-8").strip().split("\r\n")
        self.assertEqual(len(lines) - 1, s["turns"])                                   # 행 수 = 화면 턴 수
        st, b = raw("/api/export/battle_log", {"scope": scope, "format": "zip"})
        zf = zipfile.ZipFile(io.BytesIO(b))
        self.assertEqual({"turns.csv", "owned.csv", "battle.json", "meta.json"}, set(zf.namelist()))
        st, b = raw("/api/export/battles", {"format": "csv"})
        self.assertEqual(st, 200)
        rows = b[3:].decode("utf-8").strip().split("\r\n")
        self.assertGreater(len(rows), 1)
        self.assertTrue(rows[0].startswith("mid,name,category,run,ord"))

    def test_cli_replays(self):
        res = cli.main(["--monster", "Mob_10101_Fairy", "--run", "3", "--json"])
        self.assertEqual(res["mid"], "Mob_10101_Fairy")
        self.assertEqual(len(res["turns"]), res["battle"]["turns"])
        self.assertEqual(cli.main(["--monster", "Mob_10101_Fairy", "--run", "3", "--ord", "999"]), 2)


class Invariance(unittest.TestCase):
    """AC-L6: 새 필드는 로그 전용 — 트레이스·전투 기록을 켜도 켜지 않아도 판 결과가 같다."""

    def test_l6_results_unchanged_with_trace_and_battle_log(self):
        c = cfg_of(g="on", skill=0.7)
        ctx = ms.SimContext(c)
        for i in range(60):
            a = ms.simulate_run(c, f"inv-{i}", ctx=ctx)
            tr, log = [], []
            b = ms.simulate_run(c, f"inv-{i}", ctx=ctx, trace=tr, battle_log=log)
            self.assertEqual(a, b, i)
            for rec in log:
                for k in ("hp0", "hp1", "taken_cap", "nfant"):
                    self.assertIn(k, rec)

    # --- AC-L7: 청크 결합
    def test_l7_chunk_size_independent(self):
        c = cfg_of(g="on", skill=0.7)
        c["monsters"]["model"] = "table"
        a = mo.run_metrics(c, "chk", 100, chunk=100)
        b = mo.run_metrics(c, "chk", 100, chunk=30)
        self.assertEqual({m["id"]: m["samples"] for m in a["monsters"]}, {m["id"]: m["samples"] for m in b["monsters"]})
        self.assertEqual([m["avg_taken"] for m in a["monsters"]], [m["avg_taken"] for m in b["monsters"]])

    # --- AC-L9: 표본 수집 비용 (잡음이 커서 느슨한 상한: 계산 시간의 10%)
    def test_l9_sample_collection_cost_is_small(self):
        c = cfg_of(g="on", skill=0.7)
        c["monsters"]["model"] = "table"
        real = bl.sample_add
        best = {"on": 1e9, "off": 1e9}
        try:
            for rep in range(3):
                bl.sample_add = real
                t = time.perf_counter()
                mo.chunk_metrics((c, "perf", 0, 40))
                best["on"] = min(best["on"], time.perf_counter() - t)
                bl.sample_add = lambda *a, **k: None
                t = time.perf_counter()
                mo.chunk_metrics((c, "perf", 0, 40))
                best["off"] = min(best["off"], time.perf_counter() - t)
        finally:
            bl.sample_add = real
        self.assertLess(best["on"] / best["off"] - 1, 0.10, best)


if __name__ == "__main__":
    unittest.main()
