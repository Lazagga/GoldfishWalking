# -*- coding: utf-8 -*-
"""서버·편집 수락 기준: AC-W6(보안), AC-E1(정합성), AC-E2(반응성·취소), AC-E3(stale), AC-E4(시나리오),
그리고 UI 스모크(편집 → 부분 결과 → 완료 → 시나리오 저장 → 미리보기 diff → 반영(fixtures) → 복원, 라이트·다크 스크린샷).

모든 쓰기는 임시 폴더의 fixtures 사본에만 한다 (MATCHUPSIM_FORBID_PATH = 실제 Assets).
"""
import csv
import http.client
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
REPO = os.path.dirname(os.path.dirname(ROOT))
sys.path.insert(0, ROOT)
os.environ["MATCHUPSIM_FORBID_PATH"] = os.path.join(REPO, "Assets")

import fantasy_scan  # noqa: E402
import import_fantasies  # noqa: E402
import viewer_server  # noqa: E402
from sim_service import store as st  # noqa: E402

FIXTURES = os.path.join(HERE, "fixtures", "fantasies")
SHOTS = os.path.join(HERE, "screenshots")
FIDS = "fan_turn_boots,fan_damage_slingshot,fan_damage_anchor,fan_rest_pillow,fan_start_stamp"

try:
    from playwright.sync_api import sync_playwright
except ImportError:  # pragma: no cover
    sync_playwright = None


def read_all(folder):
    out = {}
    for fn in os.listdir(folder):
        with open(os.path.join(folder, fn), "rb") as fp:
            out[fn] = fp.read()
    return out


class Sandbox:
    """fixtures 사본 + 작은 스캔 + 서버 (포트 0)."""

    def __init__(self, xs="500:700:200", runs="300", stages="100,300", reuse=None, adaptive=None, table_model=False,
                 start_hp=False):
        self.tmp = reuse or tempfile.mkdtemp(prefix="matchupsim_srv_")
        t = self.tmp
        self.src = os.path.join(t, "fantasies")
        self.ov = os.path.join(t, "overrides.json")
        self.effects = os.path.join(t, "fantasy_effects.json")
        self.results = os.path.join(t, "results")
        self.scen = os.path.join(t, "scenarios")
        self.backup = os.path.join(t, ".matchupsim_backup")
        self.mon = os.path.join(t, "monsters")
        self.pat = os.path.join(t, "patterns")
        self.mtable = os.path.join(t, "monster_table.json")
        if not reuse:
            shutil.copytree(os.path.join(HERE, "fixtures", "monsters"), self.mon)
            shutil.copytree(os.path.join(HERE, "fixtures", "patterns"), self.pat)
            shutil.copytree(FIXTURES, self.src)
            shutil.copy(os.path.join(ROOT, "fantasy_effects.overrides.json"), self.ov)
            import_fantasies.main(["--src", self.src, "--out", self.effects, "--overrides", self.ov, "--quiet"])
            import import_monsters
            import_monsters.main(["--monsters", self.mon, "--patterns", self.pat, "--out", self.mtable, "--quiet"])
            if start_hp:      # v4.2 기본: 몬스터 JSON 체력 + digits + 기믹, X축 = 시작 체력
                fantasy_scan.main(["--effects", self.effects, "--x", f"player.start_hp={xs}", "--fantasies",
                                   "fan_turn_boots,fan_damage_slingshot", "--runs", runs, "--seed", "srv",
                                   "--set", "monsters.table_file=" + json.dumps(self.mtable),
                                   "--workers", "4", "--out", self.results, "--quiet"])
            elif table_model:   # 실제 몬스터 테이블 모델: X축 = monsters.hp_scale
                fantasy_scan.main(["--effects", self.effects, "--x", f"monsters.hp_scale={xs}", "--fantasies",
                                   "fan_turn_boots,fan_damage_slingshot", "--runs", runs, "--seed", "srv",
                                   "--set", 'monsters.model="table"', "--set", "monsters.table_file=" + json.dumps(self.mtable),
                                   "--set", 'monsters.damage_model="gauss"', "--set", 'monsters.gimmicks="off"',
                                   "--workers", "4", "--out", self.results, "--quiet"])
            else:
                fantasy_scan.main(["--effects", self.effects, "--x", f"monsters.hp_base={xs}", "--fantasies", "all",
                                   "--runs", runs, "--seed", "srv", "--set", "monsters.act_hp_growth=2.0", "--set", 'monsters.model="tier_avg"',
                                   "--workers", "4", "--out", self.results, "--quiet"])
        args = viewer_server.parse_args([
            "--port", "0", "--results", self.results, "--effects", self.effects, "--src", self.src,
            "--monsters", self.mon, "--patterns", self.pat, "--monster-table", self.mtable,
            "--overrides", self.ov, "--scenarios", self.scen, "--backup", self.backup, "--workers", "4",
            "--stages", stages, "--adaptive-stages", adaptive or stages, "--surrogate-auto", "manual", "--targets", os.path.join(ROOT, "balance_targets.json")])
        self.srv, self.app = viewer_server.make_server(args)
        self.port = self.app.port
        self.token = self.app.token
        self.thread = threading.Thread(target=self.srv.serve_forever, daemon=True)
        self.thread.start()

    def stop(self):
        self.srv.shutdown()
        self.srv.server_close()
        self.app.engine.close()

    def cleanup(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def req(self, method, path, body=None, token=True, host=None, origin=None, ctype="application/json"):
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=120)
        h = {"Host": host or f"127.0.0.1:{self.port}"}
        if token:
            h["X-MatchUp-Token"] = self.token if token is True else token
        if origin:
            h["Origin"] = origin
        data = None
        if body is not None:
            data = json.dumps(body).encode() if not isinstance(body, bytes) else body
            h["Content-Type"] = ctype
        c.request(method, path, body=data, headers=h)
        r = c.getresponse()
        raw = r.read()
        c.close()
        try:
            return r.status, json.loads(raw)
        except ValueError:
            return r.status, raw

    def job(self, body):
        st_, j = self.req("POST", "/api/jobs", body)
        assert st_ == 200, j
        return j["id"]

    def events(self, job_id, until=None):
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=300)
        c.request("GET", f"/api/jobs/{job_id}/events", headers={"Host": f"127.0.0.1:{self.port}", "X-MatchUp-Token": self.token})
        r = c.getresponse()
        evs, buf = [], b""
        while True:
            chunk = r.read1(65536)
            if not chunk:
                break
            buf += chunk
            while b"\n\n" in buf:
                blk, buf = buf.split(b"\n\n", 1)
                for line in blk.decode("utf-8").split("\n"):
                    if line.startswith("data: "):
                        e = json.loads(line[6:])
                        evs.append(e)
                        if until and until(e):
                            c.close()
                            return evs
        c.close()
        return evs


class ServerAPI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sb = Sandbox()

    @classmethod
    def tearDownClass(cls):
        cls.sb.stop()
        cls.sb.cleanup()

    # --- AC-W6
    def test_w6_security(self):
        sb = self.sb
        self.assertEqual(sb.srv.server_address[0], "127.0.0.1")
        self.assertEqual(sb.req("GET", "/api/ping", token=False)[0], 403)
        self.assertEqual(sb.req("GET", "/api/ping", token="wrong")[0], 403)
        self.assertEqual(sb.req("GET", "/api/ping")[0], 200)
        self.assertEqual(sb.req("GET", "/api/ping", host="evil.example:80")[0], 403)
        self.assertEqual(sb.req("GET", f"/api/ping", host=f"attacker.localhost:{sb.port}")[0], 403)  # DNS 리바인딩
        self.assertEqual(sb.req("GET", "/api/ping", origin="http://evil.example")[0], 403)
        self.assertEqual(sb.req("GET", "/api/ping", origin=f"http://localhost:{sb.port}")[0], 200)
        self.assertEqual(sb.req("GET", "/", host="evil.example")[0], 403)
        # 쓰기 API 는 JSON 만
        self.assertEqual(sb.req("POST", "/api/scenarios", b"name=x", ctype="text/plain")[0], 415)
        self.assertEqual(sb.req("POST", "/api/scenarios", b"name=x", ctype="application/x-www-form-urlencoded")[0], 415)
        # 경로 이탈: 시나리오 이름은 서버가 안전한 파일 이름으로 바꾼다 → 시나리오 폴더 밖에 쓰지 못함
        s, j = sb.req("POST", "/api/scenarios", {"name": "../../evil", "edits": [], "cfg_edits": []})
        self.assertEqual(s, 200)
        self.assertTrue(os.path.exists(os.path.join(sb.scen, "evil.json")))
        self.assertFalse(os.path.exists(os.path.join(sb.tmp, "evil.json")))
        self.assertEqual(sb.req("GET", "/api/scenarios/..%2F..%2Fresults%2Ffantasy_curves")[0], 400)
        s, j = sb.req("POST", "/api/apply/revert", {"backup": "../../fantasies"})
        self.assertIn(s, (400, 409))
        # 클라이언트가 보낸 파일 경로는 쓰지 않는다: 편집은 환상 ID 로만, 파일은 서버가 src 로 해석
        s, j = sb.req("POST", "/api/apply/preview", {"edits": [{"fid": "../../x", "effect": 0, "key": "value", "old": 1, "new": 2}]})
        self.assertEqual(s, 200)
        self.assertEqual(j["files"], {})
        self.assertTrue(j["problems"])
        # 허용 목록 밖 쓰기 차단
        from sim_service import writeback as wb
        with self.assertRaises(wb.WriteBackError):
            wb.atomic_write(os.path.join(tempfile.gettempdir(), "matchupsim_outside.txt"), b"x", sb.app.wb.allowed)

    # --- AC-E1
    def test_e1_matches_cli(self):
        sb = self.sb
        tab = {e["id"]: e for e in sb.app.table_data["fantasies"]}
        old = tab["fan_turn_boots"]["effects"][0]["value"]
        edit = {"fid": "fan_turn_boots", "effect": 0, "key": "value", "old": old, "new": 1}
        jid = sb.job({"kind": "recompute", "edits": [edit], "fids": [], "x_values": [600], "stages": [300]})
        evs = sb.events(jid)
        self.assertEqual(evs[-1]["type"], "done", evs[-1])
        pts = [e for e in evs if e["type"] == "point" and e["series"] == "after" and e["fid"] == "fan_turn_boots"]
        p = pts[-1]["point"]
        self.assertEqual(p["n"], 300)
        # 같은 편집 테이블로 CLI(--force-fantasy) 실행
        data, _ = st.load_table(sb.effects)
        for e in data["fantasies"]:
            if e["id"] == "fan_turn_boots":
                e["effects"][0]["value"] = type(old)(1)     # 서버도 원래 숫자 형식(float)을 따른다 (v4 AC-R1)
        ed_path = os.path.join(sb.tmp, "edited.json")
        with open(ed_path, "w", encoding="utf-8") as fp:
            json.dump(data, fp, ensure_ascii=False)
        out = os.path.join(sb.tmp, "cli")
        subprocess.run([sys.executable, os.path.join(ROOT, "matchup_sim.py"), "--effects", ed_path,
                        "--force-fantasy", "fan_turn_boots", "--runs", "300", "--seed", "srv",
                        "--set", "monsters.act_hp_growth=2.0", "--set", 'monsters.model="tier_avg"', "--set", "monsters.hp_base=600", "--out", out],
                       check=True, capture_output=True)
        with open(os.path.join(out, "runs.csv"), encoding="utf-8-sig") as fp:
            rows = list(csv.DictReader(fp))
        rec = sb.app.store.load(st.point_key(*self._key_args(sb, data, 600, ["fan_turn_boots"])))
        self.assertEqual("".join("1" if r["result"] == "win" else "0" for r in rows), rec["wins"][:300])
        self.assertEqual([int(r["reached_floor"]) for r in rows], rec["reached"][:300])
        self.assertEqual(sum(r["result"] == "win" for r in rows), p["wins"])

    def _key_args(self, sb, data, x, fids):
        import copy as cp_
        import matchup_sim as ms
        path, h = st.materialize_table(data, sb.app.tables_dir)
        cfg = cp_.deepcopy(sb.app.base_cfg)
        cfg["fantasy"]["effects_file"] = path
        ms.set_path(cfg, "monsters.hp_base", x)
        cfg["fantasy"]["forced"] = {"ids": list(fids), "at": "start"}
        return cfg, fids, "srv", h

    # --- AC-E2 (API 수준): 새 작업이 오면 이전 작업이 1초 안에 취소
    def test_e2_cancel_within_1s(self):
        sb = self.sb
        tab = {e["id"]: e for e in sb.app.table_data["fantasies"]}
        old = tab["fan_damage_slingshot"]["effects"][0]["value"]
        j1 = sb.job({"kind": "recompute", "edits": [{"fid": "fan_damage_slingshot", "effect": 0, "key": "value", "old": old, "new": 7}],
                     "fids": FIDS.split(","), "stages": [1000, 4000]})
        sb.events(j1, until=lambda e: e["type"] == "point")
        t0 = time.perf_counter()
        j2 = sb.job({"kind": "recompute", "edits": [{"fid": "fan_damage_slingshot", "effect": 0, "key": "value", "old": old, "new": 8}],
                     "fids": [], "x_values": [500], "stages": [100]})
        ev1 = sb.events(j1)
        t_cancel = time.perf_counter() - t0
        self.assertEqual(ev1[-1]["type"], "cancelled")
        print(f"\n  AC-E2: 이전 작업 취소까지 {t_cancel:.2f}s")
        self.assertLess(t_cancel, 1.0)
        ev2 = sb.events(j2)
        self.assertEqual(ev2[-1]["type"], "done")

    # --- AC-E4: 저장 → 새 서버 세션에서 불러오기 → old 일치면 복원, 다르면 충돌
    def test_e4_scenario_restore_and_conflict(self):
        sb = self.sb
        tab = {e["id"]: e for e in sb.app.table_data["fantasies"]}
        edits = [{"fid": "fan_damage_anchor", "effect": 0, "key": "value", "old": tab["fan_damage_anchor"]["effects"][0]["value"], "new": -15},
                 {"fid": "fan_rest_pillow", "effect": 0, "key": "value", "old": tab["fan_rest_pillow"]["effects"][0]["value"], "new": 90}]
        cfg_edits = [{"path": "player.skill", "old": 0.7, "new": 0.6}]
        s, j = sb.req("POST", "/api/scenarios", {"name": "닻 너프", "note": "t", "edits": edits, "cfg_edits": cfg_edits})
        self.assertEqual(s, 200)
        sb.stop()
        try:
            sb2 = Sandbox(reuse=sb.tmp)
            s, j = sb2.req("GET", "/api/scenarios/" + "닻_너프".encode("utf-8").hex() if False else "/api/scenarios/%EB%8B%BB_%EB%84%88%ED%94%84")
            self.assertEqual(s, 200, j)
            self.assertEqual(j["scenario"]["edits"], edits)
            self.assertEqual(j["scenario"]["cfg_edits"], cfg_edits)
            self.assertEqual(j["conflicts"], [])
            sb2.stop()
            # 원본 값을 바꾼 뒤(다른 사람이 Unity 에서 수정) 새 세션 → 충돌
            p = os.path.join(sb.src, "fan_damage_anchor.json")
            with open(p, "rb") as fp:
                b = fp.read()
            with open(p, "wb") as fp:
                fp.write(b.replace(b"-20.0", b"-25.0"))
            import_fantasies.main(["--src", sb.src, "--out", sb.effects, "--overrides", sb.ov, "--quiet"])
            sb3 = Sandbox(reuse=sb.tmp)
            s, j = sb3.req("GET", "/api/scenarios/%EB%8B%BB_%EB%84%88%ED%94%84")
            self.assertEqual([c["fid"] for c in j["conflicts"]], ["fan_damage_anchor"])
            sb3.stop()
            with open(p, "wb") as fp:
                fp.write(b)
            import_fantasies.main(["--src", sb.src, "--out", sb.effects, "--overrides", sb.ov, "--quiet"])
        finally:
            type(self).sb = Sandbox(reuse=sb.tmp)


@unittest.skipIf(sync_playwright is None, "playwright 미설치")
class ServerUI(unittest.TestCase):
    """AC-E2(첫 부분 결과 ≤ 전체의 20%), AC-E3(stale), UI 스모크 + 라이트·다크 스크린샷."""

    @classmethod
    def setUpClass(cls):
        os.makedirs(SHOTS, exist_ok=True)
        cls.sb = Sandbox(xs="400:800:200", runs="300", stages="300,1000,3000", adaptive="100,200")
        cls.pw = sync_playwright().start()
        ch = os.environ.get("VIEWER_BROWSER_CHANNEL", "msedge")
        cls.browser = cls.pw.chromium.launch(**({"channel": ch} if ch else {}))

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.pw.stop()
        cls.sb.stop()
        cls.sb.cleanup()

    def page(self, scheme="light", hash_="#f=fan_turn_boots,fan_damage_slingshot&t=curve&x=600"):
        ctx = self.browser.new_context(viewport={"width": 1400, "height": 1000}, color_scheme=scheme)
        pg = ctx.new_page()
        errs = []
        pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.goto(f"http://127.0.0.1:{self.sb.port}/{hash_}")
        pg.wait_for_function("window.__viewerReady === true")
        self.assertIn("서버 모드", pg.inner_text("#modeBadge"))
        return ctx, pg, errs

    def wait_job(self, pg, timeout=120000):
        pg.wait_for_function("window.__lastJob && window.__lastJob.end != null", timeout=timeout)
        return pg.evaluate("window.__lastJob")

    def edit(self, pg, fid, value):
        pg.click(f'#list .row[data-id="{fid}"] .fname')
        sel = f'#detail .editor[data-fid="{fid}"][data-key="value"] input.val'
        pg.fill(sel, str(value))
        pg.dispatch_event(sel, "change")

    def test_ui_smoke_edit_save_apply_revert(self):
        sb = self.sb
        src_before = read_all(sb.src)
        ctx, pg, errs = self.page()
        # 1) 수치 편집 → 부분 결과 → 완료
        self.edit(pg, "fan_turn_boots", 1)
        job = self.wait_job(pg)
        self.assertEqual(job["result"]["type"], "done")
        frac = (job["first"] - job["t0"]) / (job["end"] - job["t0"])
        print(f"\n  AC-E2: 첫 부분 결과 {job['first'] - job['t0']:.0f}ms / 전체 {job['end'] - job['t0']:.0f}ms = {frac * 100:.1f}%")
        self.assertLessEqual(frac, 0.20)
        self.assertIn("변경 1개", pg.inner_text("#chgCount"))
        # 수정 전 고스트: 기준선 + 편집한 환상 + (v4 §6.8) 선택한 다른 환상
        gh = pg.eval_on_selector_all('#chart path.ghost', "ps => ps.map(p => p.getAttribute('data-id'))")
        self.assertIn("__baseline___ghost", gh)
        self.assertIn("fan_turn_boots_ghost", gh)
        self.assertEqual(len(gh), 1 + len(pg.evaluate("window.__S.sel")))
        self.assertIn("수정 효과", pg.inner_text("#eq"))
        pg.screenshot(path=os.path.join(SHOTS, "server_edit_light.png"))
        # AC-E3: 재계산하지 않은 환상은 stale, 전체 재계산 후 사라짐
        pg.click('.tab[data-t="rank"]')
        n_stale = len(pg.query_selector_all("#rank .badge.stale"))
        self.assertGreater(n_stale, 50)
        pg.click('.tab[data-t="curve"]')
        # 2) 시나리오 저장
        pg.once("dialog", lambda d: d.accept("장화 너프"))
        pg.on("dialog", lambda d: d.accept(""))
        pg.click("#btnSave")
        pg.wait_for_timeout(500)
        self.assertTrue(os.path.exists(os.path.join(sb.scen, "장화_너프.json")))
        # 3) 미리보기 diff
        pg.click("#btnApply")
        pg.wait_for_selector(".modal pre")
        diff = pg.inner_text(".modal pre")
        self.assertIn('-', diff)
        self.assertIn("fan_turn_boots.json", pg.inner_text(".modal"))
        pg.screenshot(path=os.path.join(SHOTS, "server_apply_preview_light.png"))
        # 4) 반영 (fixtures 사본)
        pg.click("#applyGo")
        pg.wait_for_selector("#okClose")
        txt = pg.inner_text(".modal")
        self.assertIn("반영 완료", txt)
        self.assertIn("Import All Gameplay JSON", txt)
        self.assertIn("모든 값 일치", txt)
        pg.click("#okClose")
        changed = [fn for fn, b in read_all(sb.src).items() if b != src_before[fn]]
        self.assertEqual(changed, ["fan_turn_boots.json"])
        # 5) 복원
        pg.once("dialog", lambda d: d.accept())
        pg.click("#btnUnapply")
        pg.wait_for_timeout(800)
        after = read_all(sb.src)
        self.assertEqual(after, src_before)
        self.assertEqual(errs, [])
        ctx.close()

    def test_e3_full_recompute_clears_stale(self):
        ctx, pg, errs = self.page()
        self.edit(pg, "fan_damage_slingshot", 25)
        self.wait_job(pg)
        pg.click('.tab[data-t="rank"]')
        self.assertGreater(len(pg.query_selector_all("#rank .badge.stale")), 0)
        pg.evaluate("window.__lastJob = null")
        pg.click("#btnFull")
        self.wait_job(pg, timeout=300000)
        pg.wait_for_timeout(300)
        self.assertEqual(len(pg.query_selector_all("#rank .badge.stale")), 0)
        # 편집을 모두 되돌리면 원래 데이터 (stale 없음)
        pg.click("#btnRevertAll")
        self.assertEqual(len(pg.query_selector_all("#rank .badge.stale")), 0)
        self.assertEqual(errs, [])
        ctx.close()

    def test_dark_screenshot_and_trace(self):
        ctx, pg, errs = self.page("dark")
        self.edit(pg, "fan_damage_anchor", -10)
        self.wait_job(pg)
        pg.screenshot(path=os.path.join(SHOTS, "server_edit_dark.png"))
        pg.click('.tab[data-t="trace"]')
        pg.click("#trSuggest")
        pg.wait_for_selector(".seed", timeout=60000)
        pg.click(".seed")
        pg.wait_for_selector("#trB .ev", timeout=60000)
        self.assertTrue(pg.query_selector(".trace .ev.div") is not None or "끝까지 같음" in pg.inner_text("#trBody"))
        pg.screenshot(path=os.path.join(SHOTS, "server_trace_dark.png"))
        self.assertEqual(errs, [])
        ctx.close()


if __name__ == "__main__":
    unittest.main()
