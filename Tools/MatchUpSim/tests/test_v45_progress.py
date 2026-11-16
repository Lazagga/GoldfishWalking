# -*- coding: utf-8 -*-
"""v4.5 F18 진행 표시 — 서버 수준 (AC-P2·P3·P4·P5·P6) 과 저장 이력 API."""
import os
import sys
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)

from sim_service import jobs as jb  # noqa: E402
from test_server import Sandbox  # noqa: E402

BOOTS = "fan_turn_boots"


def long_job(sb, client, stages=None):
    return sb.job({"kind": "monster_metrics", "stages": stages or [300000], "chunk": 250, "client": client, "seed": f"p-{client}"})


def wait_for(fn, timeout=30.0, step=0.1):
    t0 = time.time()
    while time.time() - t0 < timeout:
        v = fn()
        if v:
            return v
        time.sleep(step)
    return None


class Progress(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sb = Sandbox(xs="500:700:200", runs="30", stages="20,30")

    @classmethod
    def tearDownClass(cls):
        cls.sb.stop()
        cls.sb.cleanup()

    def prog(self, client=None):
        s, r = self.sb.req("GET", "/api/progress" + (f"?client={client}" if client else ""))
        self.assertEqual(s, 200)
        return r

    def cancel_all(self):
        for j in list(self.sb.app.jobs.jobs.values()):
            j.cancel()
        wait_for(lambda: not self.prog()["jobs"], 30)

    def tearDown(self):
        self.cancel_all()

    # --- AC-P2: 종료된 작업은 진행 중으로 남지 않는다 (done 키 충돌 수정)
    def test_p2_finished_jobs_are_not_in_progress(self):
        evs = self.sb.events(self.sb.job({"kind": "monster_metrics", "stages": [10],
                                          "edits": [{"target": "monster", "mid": "NoSuchMonster", "key": "hp", "old": 1, "new": 2}], "client": "p2"}))
        self.assertEqual(evs[-1]["type"], "error")                                     # 오류로 끝난 작업
        r = self.prog()
        self.assertEqual(r["jobs"], [])                                                # 끝나지 않은 작업 목록에 없다
        j = r["job"]
        self.assertTrue(j["finished"])
        self.assertEqual(j["state"], "error")
        self.assertIn("runs_done", j)                                                  # 처리한 판 수는 runs_done
        self.assertIs(j["done"], True)                                                 # 하위 호환: done 은 종료 여부(불리언)
        time.sleep(1.5)
        self.assertEqual(self.prog()["jobs"], [])                                      # 시간이 지나도 '진행 중'으로 되돌아가지 않는다

    def test_p6_all_cached_job_finishes_with_cache(self):
        body = {"kind": "monster_metrics", "stages": [60], "chunk": 30, "client": "p6", "seed": "p6"}
        self.sb.events(self.sb.job(body))
        evs = self.sb.events(self.sb.job(body))                                        # 같은 상태로 한 번 더 — 저장된 결과로 즉시 끝남
        self.assertEqual(evs[-1]["type"], "done")
        r = self.prog()
        self.assertEqual(r["jobs"], [])
        self.assertEqual(r["job"]["state"], "done")
        self.assertTrue(r["job"]["finished"])

    # --- AC-P3: 마지막 진행 줄을 서버 콘솔과 같은 문자열로
    def test_p3_last_progress_line(self):
        long_job(self.sb, "p3")
        j = wait_for(lambda: next((x for x in self.prog("p3")["jobs"] if x["state"] == "running" and x.get("line")), None), 30)
        self.assertIsNotNone(j, "실행 중 작업과 진행 줄이 나와야 함")
        self.assertTrue(j["line"].startswith("[monster_metrics "), j["line"])
        self.assertIn("판", j["line"])
        self.assertIsNotNone(j["line_age_s"])
        self.assertLess(j["line_age_s"], 30)
        job = self.sb.app.jobs.jobs[j["id"]]
        self.assertEqual(j["line"][:12], job.progress.line()[:12])                     # 같은 형식(format_progress)
        self.assertEqual(j["runs_done"], job.progress.snapshot()["done"] if j["runs_done"] == job.progress.snapshot()["done"] else j["runs_done"])

    # --- AC-P5: 줄 서 있는 작업은 대기 중으로
    def test_p5_queued_job_is_distinguished(self):
        a = long_job(self.sb, "p5a")
        wait_for(lambda: next((x for x in self.prog()["jobs"] if x["id"] == a and x["state"] == "running"), None), 30)
        b = long_job(self.sb, "p5b")
        jobs = wait_for(lambda: (lambda js: js if len(js) == 2 else None)(self.prog()["jobs"]), 30)
        self.assertIsNotNone(jobs)
        self.assertEqual([j["state"] for j in jobs], ["running", "queued"])            # 실행 중 → 대기 순
        q = jobs[1]
        self.assertEqual(q["id"], b)
        self.assertEqual(q["line"], "대기 중(앞 작업 1개)")
        self.assertIsNone(q["line_age_s"])

    # --- AC-P4: 이전 탭이 올린 작업만 취소, 닫힌 탭(진행 확인이 끊긴 클라이언트)의 작업은 새 작업이 올라올 때 취소
    def test_p4_stale_client_jobs_are_cancelled(self):
        old = jb.STALE_CLIENT_S
        jb.STALE_CLIENT_S = 0.3
        try:
            a = long_job(self.sb, "tabA")
            self.prog("tabA")                                                          # tabA 가 진행을 확인했다 (last_seen)
            wait_for(lambda: next((x for x in self.prog()["jobs"] if x["id"] == a and x["state"] == "running"), None), 30)
            time.sleep(0.6)                                                            # 탭이 닫혔다: 더 이상 확인하지 않음
            b = long_job(self.sb, "tabB")
            self.assertTrue(wait_for(lambda: self.sb.app.jobs.jobs[a].cancelled, 10))   # 닫힌 탭의 작업은 취소
            self.assertFalse(self.sb.app.jobs.jobs[b].cancelled)
            # 진행 확인을 계속하는 탭의 작업은 취소하지 않는다
            self.prog("tabB")
            c = long_job(self.sb, "tabC")
            self.assertFalse(self.sb.app.jobs.jobs[b].cancelled)
            # 진행 확인을 한 적 없는 클라이언트(구버전 뷰어·CLI)는 건드리지 않는다
            d = long_job(self.sb, "ghost")
            time.sleep(0.5)
            e = long_job(self.sb, "tabD")
            self.assertFalse(self.sb.app.jobs.jobs[d].cancelled)
        finally:
            jb.STALE_CLIENT_S = old

    def test_same_client_new_job_cancels_only_its_own_previous(self):
        a = long_job(self.sb, "same")
        b = long_job(self.sb, "other")
        c = long_job(self.sb, "same")
        self.assertTrue(wait_for(lambda: self.sb.app.jobs.jobs[a].cancelled, 10))
        self.assertFalse(self.sb.app.jobs.jobs[b].cancelled)
        self.assertFalse(self.sb.app.jobs.jobs[c].cancelled)


class ApplyHistory(unittest.TestCase):
    def setUp(self):
        self.sb = Sandbox(xs="500:700:200", runs="30", stages="20,30")

    def tearDown(self):
        self.sb.stop()
        self.sb.cleanup()

    def test_history_lists_saves_and_revert_state(self):
        s, fj = self.sb.req("GET", "/api/fantasies")
        old = next(f for f in fj["fantasies"] if f["id"] == BOOTS)["effects"][0]["value"]
        edit = {"fid": BOOTS, "effect": 0, "key": "value", "old": old, "new": old + 1}
        self.assertEqual(self.sb.req("GET", "/api/apply/history")[1]["history"], [])
        s, r = self.sb.req("POST", "/api/apply", {"edits": [edit]})
        self.assertEqual(s, 200, r)
        h = self.sb.req("GET", "/api/apply/history")[1]["history"]
        self.assertEqual(len(h), 1)
        self.assertTrue(h[0]["can_revert"])
        self.assertTrue(h[0]["last"])
        self.assertEqual(h[0]["files"], 1)
        self.assertEqual(self.sb.req("GET", "/api/apply/history", token=False)[0], 403)
        s, rv = self.sb.req("POST", "/api/apply/revert", {"backup": h[0]["id"]})        # 목록에서 고른 저장을 되돌린다
        self.assertEqual(s, 200, rv)
        h2 = self.sb.req("GET", "/api/apply/history")[1]["history"]
        self.assertFalse(h2[0]["can_revert"])                                          # 되돌린 뒤에는 되돌릴 수 없음

    def test_old_backups_are_pruned_to_twenty(self):
        wb = self.sb.app.wb
        for i in range(25):                                                            # 가짜 백업 25개
            d = os.path.join(wb.backup_root, f"2026010{i % 10}-0000{i:02d}-000000")
            os.makedirs(d, exist_ok=True)
            with open(os.path.join(d, "manifest.json"), "w", encoding="utf-8") as fp:
                fp.write('{"at": "x", "files": {}}')
        n = wb.prune_backups()
        self.assertEqual(n, 25 - wb.BACKUP_KEEP)
        left = [x for x in os.listdir(wb.backup_root) if os.path.isfile(os.path.join(wb.backup_root, x, "manifest.json"))]
        self.assertEqual(len(left), wb.BACKUP_KEEP)


if __name__ == "__main__":
    unittest.main()
