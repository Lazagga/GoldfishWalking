# -*- coding: utf-8 -*-
"""v4 피해 자릿수 모델 (F8) AC-D0 ~ AC-D9 와 몬스터 기믹 (F9) AC-K0 ~ AC-K8.
(AC-D1 상자 이동 표는 test_v4_boxmoves.py, AC-K9 기믹 편집 반영은 test_v4_server.py)"""
import copy
import json
import math
import os
import random
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

import matchup_sim as ms  # noqa: E402
from sim_service import box_moves as bm  # noqa: E402
from sim_service import compute as cp  # noqa: E402
from sim_service import edits as ed  # noqa: E402
from sim_service import fight_digits as fd  # noqa: E402
from sim_service import monsters as mo  # noqa: E402
from sim_service import store as st  # noqa: E402

EFFECTS = os.path.join(ROOT, "fantasy_effects.json")
MTABLE = os.path.join(ROOT, "monster_table.json")


def cfg_of(dm="digits", g="off", skill=0.7, hp=None, scale=1.0):
    c = copy.deepcopy(ms.DEFAULT_CONFIG)
    ms.apply_fantasy_args(c, EFFECTS)
    c["monsters"].update({"model": "table", "table_file": MTABLE, "damage_model": dm, "gimmicks": g, "hp_scale": scale})
    c["player"]["skill"] = skill
    if hp:
        c["player"]["start_hp"] = hp
    return c


def mon_of(patterns=("2_Single",), hp=100000, sim=(), ai="static", strength=0, extra_patterns=None):
    pats = []
    for k in patterns:
        if isinstance(k, dict):
            pats.append(k)
            continue
        if k == "Skip":
            pats.append({"key": k, "kind": "skip", "multi": False, "str_units": 0, "source": "generic"})
            continue
        if k.startswith("Str_"):
            pats.append({"key": k, "kind": "str", "multi": False, "str_units": int(k[4:]), "source": "generic"})
            continue
        parts = k.split("_")
        multi = parts[1] == "Multi"
        pats.append({"key": k, "kind": "attack", "multi": multi, "dmg_digits": int(parts[0]),
                     "hit_digits": int(parts[2]) if multi else None, "str_units": 0, "source": "generic"})
    return {"id": "T", "act": 1, "tier": "easy", "hp": hp, "strength": strength, "ai": ai, "patterns": pats,
            "sim": list(sim)}


def battle(c, mon, seed="b", fids=(), hp=None):
    c0 = copy.deepcopy(c)
    c0["monsters"].update({"damage_model": "gauss", "gimmicks": "off", "model": "tier_avg"})
    ctx = ms.SimContext(c0)
    ctx.damage_model = "digits"
    ctx.pick_monster = lambda s, t, a: mon
    stt = ms.RunState(c, ctx.pool, ctx, seed)
    for f in fids:
        stt.acquire(ctx.grade_of[f], f, "forced")
    if hp:
        stt.hp = hp
    stt.trace, stt.battle_log = [], []
    stt.floor_pos = ("t", seed)
    stt.stats["battles"] = 1
    out = fd.fight_digits(c, stt, mon["tier"], mon["act"], ms.rng_for(seed, "ev"))
    return out, stt, [e for e in stt.trace if e["ev"] == "turn"]


def chi2_uniform(vals, lo, hi):
    k = hi - lo + 1
    cnt = [0] * k
    for v in vals:
        cnt[v - lo] += 1
    e = len(vals) / k
    return sum((x - e) ** 2 / e for x in cnt), k - 1


def chi2_crit(df, z=3.09):   # 상위 0.001 (Wilson–Hilferty 근사)
    return df * (1 - 2 / (9 * df) + z * math.sqrt(2 / (9 * df))) ** 3


class Digits(unittest.TestCase):
    # --- AC-D0
    def test_d0_gauss_unchanged_and_cache_keys(self):
        c = ms.legacy_config()
        c2 = copy.deepcopy(c)
        del c2["monsters"]["gimmicks"]
        del c2["player"]["policy"]
        self.assertEqual(st.point_key(c, [], "s", "h"), st.point_key(c2, [], "s", "h"))   # 기본값은 키에서 빠짐
        c3 = copy.deepcopy(c)
        c3["monsters"]["gimmicks"] = "on"
        self.assertNotEqual(st.point_key(c, [], "s", "h"), st.point_key(c3, [], "s", "h"))
        # 몬스터 테이블에 v4 필드(sim·effects 등)가 생겨도 gauss 결과는 같다
        with open(MTABLE, encoding="utf-8") as fp:
            tab = json.load(fp)
        old = copy.deepcopy(tab)
        for m in old["monsters"]:
            for k in ("sim", "gimmick_report", "fidelity_digits", "fidelity_gimmicks", "gimmick_tier"):
                m.pop(k, None)
            for p in m["patterns"]:
                for k in ("effects", "condition", "dynamic", "heal", "self_destruct", "dmg_editable"):
                    p.pop(k, None)
        import tempfile
        d = tempfile.mkdtemp()
        po = os.path.join(d, "old.json")
        with open(po, "w", encoding="utf-8") as fp:
            json.dump(old, fp)
        ca, cb = cfg_of("gauss"), cfg_of("gauss")
        cb["monsters"]["table_file"] = po
        xa, xb = ms.SimContext(ca), ms.SimContext(cb)
        for i in range(150):
            self.assertEqual(ms.simulate_run(ca, f"g{i}", ctx=xa), ms.simulate_run(cb, f"g{i}", ctx=xb))
        # digits 행에는 gauss 행에 없는 키(escapes)만 추가된다
        rd = ms.simulate_run(cfg_of(), "g0")
        rg = ms.simulate_run(cfg_of("gauss"), "g0")
        self.assertEqual(set(rd) - set(rg), {"escapes"})

    # --- AC-D2
    def test_d2_rolls(self):
        c = cfg_of(skill=0.0, hp=10 ** 9)
        mon = mon_of(("2_Single", "2_Multi_1"))
        base, md, mh = [], [], []
        for i in range(90):
            _, _, tr = battle(c, mon, f"r{i}", hp=10 ** 9)
            for t in tr:
                base.append(t["base"])
                if t["pattern"] == "2_Single":
                    md.append(t["mon_dmg"])
                    self.assertEqual(t["hits"], 1)
                else:
                    mh.append(t["hits"])
        self.assertGreaterEqual(len(base), 5000)
        self.assertTrue(all(10 <= v <= 99 for v in base + md))
        self.assertTrue(all(1 <= v <= 9 for v in mh))
        for vals, lo, hi in ((base, 10, 99), (md, 10, 99), (mh, 1, 9)):
            x2, df = chi2_uniform(vals, lo, hi)
            self.assertLess(x2, chi2_crit(df), (lo, hi, x2))
        # 몬스터 힘 +1 → 자릿수 +1
        _, _, tr = battle(c, mon_of(("2_Single",), strength=1), "s1", hp=10 ** 9)
        self.assertTrue(all(100 <= t["mon_dmg"] <= 999 for t in tr))
        # 같은 시드의 기준선·환상 팔: 같은 턴의 롤이 같다
        _, _, a = battle(c, mon, "pair", hp=10 ** 9)
        _, _, b = battle(c, mon, "pair", fids=["fan_damage_anchor"], hp=10 ** 9)
        n = min(len(a), len(b))
        self.assertGreater(n, 10)
        self.assertEqual([(t["base"], t["mon_dmg"], t["hits"]) for t in a[:n]], [(t["base"], t["mon_dmg"], t["hits"]) for t in b[:n]])

    # --- AC-D3
    def test_d3_effective_moves(self):
        mon = mon_of(("2_Single",))
        for skill, check in ((0.0, lambda t: t["K"] == 0 and t["base_edit"] == t["base"] and t["mon_dmg_edit"] == t["mon_dmg"]),
                             (1.0, lambda t: t["K"] == t["moves"])):
            _, _, tr = battle(cfg_of(skill=skill), mon, "k", hp=10 ** 9)
            self.assertTrue(tr and all(check(t) for t in tr), skill)
        ks, ms_ = [], []
        for i in range(60):
            _, _, tr = battle(cfg_of(skill=0.5), mon, f"k{i}", hp=10 ** 9)
            ks += [t["K"] for t in tr]
            ms_ += [t["moves"] for t in tr]
        n = len(ks)
        mean, exp = sum(ks) / n, sum(ms_) * 0.5 / n
        se = math.sqrt(sum(m * 0.25 for m in ms_)) / n
        self.assertLess(abs(mean - exp), 4 * se)

    # --- AC-D4
    def test_d4_allocation_optimal(self):
        rng = random.Random(5)
        for trial in range(150):
            P, D, H = rng.randint(10, 99), rng.randint(10, 99), rng.randint(1, 9)
            K = rng.randint(0, 3)
            hp, mhp = rng.randint(20, 400), rng.randint(20, 300)
            w = 0.5
            pr, dr, hr = bm.reach(2, P, K), bm.reach(2, D, K), bm.reach(1, H, K)

            def ev(v):
                return fd.objective(v["P"], v["D"] * v["H"], hp, mhp, True, w)
            boxes = [("P", fd.prune(pr, +1)), ("D", fd.prune(dr, -1)), ("H", fd.prune(hr, -1))]
            got, key, used, n = fd.allocate(boxes, K, ev)
            # 전수 열거 (가지치기 없음)
            best = None
            for pv, pc in pr.items():
                for dv, dc in dr.items():
                    for hv, hc in hr.items():
                        if pc + dc + hc <= K:
                            k = ev({"P": pv, "D": dv, "H": hv})
                            best = k if best is None or k > best else best
            self.assertEqual(key, best, (P, D, H, K))
            self.assertLessEqual(used, K)
        # 생존 우선: 살 수 있는 후보가 있으면 처치 가능해도 죽는 후보를 고르지 않는다
        a = fd.objective(dealt=100, taken=200, hp=150, mhp=90, kill_first=False, w=0.9)
        b = fd.objective(dealt=10, taken=100, hp=150, mhp=90, kill_first=False, w=0.9)
        self.assertGreater(b, a)
        # 처치 우선 (선공일 때): 처치 후보 중 받는 피해 최소
        k1 = fd.objective(dealt=95, taken=50, hp=150, mhp=90, kill_first=True, w=0.1)
        k2 = fd.objective(dealt=80, taken=0, hp=150, mhp=90, kill_first=True, w=0.1)
        self.assertGreater(k1, k2)

    # --- AC-D5
    def test_d5_taken_flat(self):
        mon = mon_of(("2_Multi_1",))
        c = cfg_of(skill=0.0)
        with open(EFFECTS, encoding="utf-8") as fp:
            tab = {e["id"]: e for e in json.load(fp)["fantasies"]}
        one = -sum(ef["value"] for ef in tab["fan_damage_anchor"]["effects"] if ef["type"] == "dmg_taken_flat")
        two = one - sum(ef["value"] for ef in tab["fan_damage_poinsettia"]["effects"] if ef["type"] == "dmg_taken_flat")
        self.assertGreater(two, one)                               # 두 효과는 합산 (닻 + 포인세티아)
        for fids, cut in ((["fan_damage_anchor"], one), (["fan_damage_anchor", "fan_damage_poinsettia"], two)):
            _, _, tr = battle(c, mon, "flat", fids=fids, hp=10 ** 9)
            for t in tr:
                self.assertEqual(t["taken"], max(0, t["mon_dmg"] - cut) * t["hits"], t)
            if cut >= 10:
                self.assertTrue(any(t["mon_dmg"] < cut and t["taken"] == 0 for t in tr))   # 0 하한

    # --- AC-D6
    def test_d6_pattern_edit(self):
        c = cfg_of(skill=0.7, hp=10 ** 7)
        m2 = mon_of(("2_Single",), hp=400, ai="static")
        m3 = mon_of(("3_Single",), hp=400, ai="static")
        a = mo.probe(c, m2, 400, "p6")
        b = mo.probe(c, m3, 400, "p6")
        ra = a["avg_taken"] / a["avg_turns"]
        rb = b["avg_taken"] / b["avg_turns"]
        self.assertTrue(6 < rb / ra < 14, (ra, rb))          # 기대 비율 549.5/54.5 ≈ 10 근처
        self.assertFalse(ed.sim_reflected(cfg_of("gauss"))["digits"])   # gauss: 시뮬 미반영
        self.assertTrue(ed.sim_reflected(c)["digits"])

    # --- AC-D7
    def test_d7_reproducible_workers(self):
        c = cfg_of(g="on", scale=0.5)
        th = st.table_hash(json.load(open(EFFECTS, encoding="utf-8")))
        outs = []
        for w in (1, 3):
            import tempfile
            store = st.PointStore(tempfile.mkdtemp())
            eng = cp.Engine(store, w)
            try:
                req = cp.make_req(c, [], "d7", th)
                eng.ensure([req], 500)
                outs.append(store.load(req["key"]))
            finally:
                eng.close()
        self.assertEqual(outs[0]["wins"], outs[1]["wins"])
        self.assertEqual(outs[0]["reached"], outs[1]["reached"])
        r1 = ms.simulate_run(c, "same")
        self.assertEqual(r1, ms.simulate_run(c, "same"))

    # --- AC-D8
    def test_d8_errors_warnings(self):
        c = cfg_of()
        c["monsters"]["model"] = "tier_avg"
        with self.assertRaises(ValueError):
            ms.SimContext(c)
        c = cfg_of("gauss", "on")
        with self.assertRaises(ValueError):
            ms.SimContext(c)
        msgs = []
        bad = ms.warn_unused_digits(cfg_of(), ["player.defense_cut_per_move", "monsters.hp_scale",
                                               "monsters.tiers.easy.str_amount"], out=msgs.append)
        self.assertEqual(bad, ["player.defense_cut_per_move", "monsters.tiers.easy.str_amount"])
        self.assertEqual(len(msgs), 2)
        self.assertEqual(ms.warn_unused_digits(cfg_of("gauss"), ["player.defense_cut_per_move"], out=msgs.append), [])

    # --- AC-D9
    def test_d9_fidelity_table(self):
        tab = json.load(open(EFFECTS, encoding="utf-8"))["fantasies"]
        self.assertEqual(len(tab), 69)
        self.assertTrue(all(e.get("fidelity_digits") in ("exact", "approx", "none") and e.get("notes_digits") for e in tab))
        appr = [e for e in tab if e["fidelity_digits"] == "approx"]
        self.assertTrue(appr and all(e["notes_digits"] for e in appr))
        up = [e for e in tab if e["fidelity"] == "approx" and e["fidelity_digits"] == "exact"]
        self.assertGreaterEqual(len(up), 5)


class Gimmicks(unittest.TestCase):
    # --- AC-K0
    def test_k0_switch(self):
        c_on, c_off = cfg_of(g="on", scale=0.5), cfg_of(g="off", scale=0.5)
        with self.assertRaises(ValueError):
            ms.SimContext(cfg_of("gauss", "on"))
        # off 이면 sim 사양이 있어도 digits 만 켠 결과와 같다 (사양을 지운 테이블과 비교)
        with open(MTABLE, encoding="utf-8") as fp:
            tab = json.load(fp)
        for m in tab["monsters"]:
            m["sim"] = []
            for p in m["patterns"]:
                for k in ("effects", "condition", "dynamic", "heal", "self_destruct"):
                    p.pop(k, None)
        import tempfile
        pth = os.path.join(tempfile.mkdtemp(), "m.json")
        json.dump(tab, open(pth, "w", encoding="utf-8"))
        c_strip = copy.deepcopy(c_off)
        c_strip["monsters"]["table_file"] = pth
        xa, xb = ms.SimContext(c_off), ms.SimContext(c_strip)
        for i in range(60):
            self.assertEqual(ms.simulate_run(c_off, f"k{i}", ctx=xa), ms.simulate_run(c_strip, f"k{i}", ctx=xb))
        xo = ms.SimContext(c_on)
        diff = sum(ms.simulate_run(c_on, f"k{i}", ctx=xo)["reached_floor"] != ms.simulate_run(c_off, f"k{i}", ctx=xa)["reached_floor"]
                   for i in range(60))
        self.assertGreater(diff, 0)

    # --- AC-K1
    def test_k1_state(self):
        c = cfg_of(g="on", skill=0.0)
        ls = {"kind": "lifesteal", "rate": 0.5}
        # 몬스터 체력 변화 = −(내가 준 피해 = 기본 피해, 실력 0) + floor(몬스터가 준 피해 × 0.5)
        _, _, tr = battle(c, mon_of(("2_Single",), hp=100000, sim=[ls]), "ls2", hp=10 ** 9)
        mhp = 100000
        for t in tr:
            exp = mhp - (t["base_edit"]) + math.floor(t["taken"] * 0.5)
            self.assertEqual(t["mhp"], exp, t)
            mhp = t["mhp"]
        # 출혈은 한 턴 뒤 한 번 들어오고 사라짐, 중독은 유지
        bleed = {"key": "B", "kind": "skip", "source": "pattern",
                 "effects": [{"op": "add_status", "target": "player", "type": "bleed", "amount": 7, "timing": "immediate"},
                             {"op": "add_status", "target": "player", "type": "poison", "amount": 3, "timing": "immediate"}],
                 "max_uses": 1}
        _, _, tr = battle(c, mon_of((bleed, "Skip"), sim=[], ai="static"), "bp", hp=10 ** 6)
        self.assertEqual([t["taken"] for t in tr[:4]], [0, 10, 3, 3])   # 1턴: 대기, 2턴: 출혈7+중독3, 이후 중독만
        # ApplyDamage 순서: 1타 상한 → 방어막 → 체력
        m = fd.Mon(100, 0)
        m.cap, m.shield = 30, 20
        self.assertEqual(m.apply_damage(50), 10)
        self.assertEqual((m.hp, m.shield), (90, 0))

    # --- AC-K2
    def test_k2_countdown_phase(self):
        c = cfg_of(g="on", skill=0.0)
        cd = {"kind": "countdown", "init": 3, "editable": False, "amount": 1, "on_zero": "escape"}
        out, _, tr = battle(c, mon_of(("Skip",) if False else (mon_of()["patterns"][0],), sim=[cd]), "cd", hp=10 ** 9)
        self.assertEqual(out, "escape")
        self.assertEqual(len(tr), 3)
        doom = {"key": "Doom", "kind": "skip", "source": "pattern", "condition": "heart_queen_box==0",
                "effects": [{"op": "deal_damage", "target": "player", "amount": 9999, "timing": "immediate"}]}
        cd2 = {"kind": "countdown", "init": 5, "editable": False, "amount": 1, "on_zero": "pattern", "pattern": "Doom"}
        out, _, tr = battle(c, mon_of(("2_Single", doom), sim=[cd2]), "hq", hp=5000)
        self.assertEqual(out, "death")
        self.assertEqual(len(tr), 5)
        self.assertNotIn("Doom", [t["pattern"] for t in tr])      # 조건(카운트다운 0)이 아니면 회전에서 건너뜀
        ph = {"kind": "phase_two", "hp_rate": 0.5, "split_all": True, "move_limit": 7}
        _, _, tr = battle(cfg_of(g="on", skill=1.0), mon_of(("2_Single",), hp=600, sim=[ph]), "ph", hp=10 ** 9)
        thr = math.floor(600 * 0.5)
        mhp = 600
        for t in tr:
            self.assertEqual(t["phase"], 2 if mhp <= thr else 1)
            if mhp <= thr:
                self.assertEqual(t["moves"], 7)
            mhp = t["mhp"]

    # --- AC-K3
    def test_k3_pattern_selection(self):
        c = cfg_of(g="on", skill=0.0)
        once = {"key": "Once", "kind": "attack", "multi": False, "dmg_digits": 1, "max_uses": 1, "source": "pattern"}
        _, _, tr = battle(c, mon_of(("2_Single", once, "Str_1")), "st", hp=10 ** 9)
        seq = [t["pattern"] for t in tr[:7]]
        self.assertEqual(seq[:3], ["2_Single", "Once", "Str_1"])
        self.assertEqual(seq[3:6], ["2_Single", "Str_1", "Str_1"])   # 턴5: Once 사용 불가 → 다음(Str_1)
        cond = {"key": "Low", "kind": "attack", "multi": False, "dmg_digits": 1, "condition": "hprate<=0.0", "source": "pattern"}
        _, _, tr = battle(c, mon_of(("2_Single", cond, "2_Multi_1"), ai="random"), "rd", hp=10 ** 9)
        pats = [t["pattern"] for t in tr]
        self.assertNotIn("Low", pats)
        self.assertEqual(set(pats), {"2_Single", "2_Multi_1"})

    # --- AC-K4
    def test_k4_expressions(self):
        m = fd.Mon(1000, 2)
        m.hp = 300
        m.fortune, m.prophecy, m.cap_acc, m.countdown = 40, 7, 410, 0
        p = fd.PState(150)
        p.bleed, p.poison = 12, 5

        e = fd.Env(m, p, 31, lambda tag: random.Random(1))
        p.hp = 150
        cases = [("DamageDealt", 31), ("DamageDealt*0.5", 15.5), ("PlayerHP*0.3", 45), ("PlayerHP*30", 45),
                 ("10/3", 3), ("5/0", 0), ("1+2*3", 1 + 2 * 0.03), ("FortuneStack", 40), ("ProphetStack", 7),
                 ("PlayerBleed", 12), ("PlayerPoison", 5), ("CosmictreeHeal", 1), ("DigitCount(123)", 3),
                 ("hprate", 0.3), ("strength", 2), ("damage_taken", 410), ("unknown_var", 0), ("3", 3)]
        for ex, want in cases:
            self.assertAlmostEqual(fd.eval_value(ex, e), want, places=6, msg=ex)
        self.assertTrue(0 <= fd.eval_value("Random", e) <= 9)
        for ex, want in (("hprate<=0.4", True), ("HPRate<=0.5 && Phase==1", True), ("HPRate<=0.5 && Phase==2", False),
                         ("damage_taken>=400", True), ("heart_queen_box==0", True), ("", True)):
            self.assertEqual(fd.eval_cond(ex, e), want, ex)
        m.countdown = 2
        self.assertFalse(fd.eval_cond("heart_queen_box==0", e))

    # --- AC-K5
    def test_k5_structure(self):
        r = random.Random(3)
        masks = bm.masks_of(88, 2)
        for n in range(0, 6):
            lk = fd.pick_segments(r, masks, n)
            self.assertEqual(sum(bin(x).count("1") for x in lk), n)
            self.assertTrue(all(lk[i] & ~masks[i] == 0 for i in range(2)))
        c = cfg_of(g="on", skill=1.0)
        _, _, tr = battle(c, mon_of(("2_Single",), sim=[{"kind": "player_immovable"}]), "go", hp=10 ** 9)
        self.assertTrue(all(t["base_edit"] == t["base"] for t in tr))
        _, _, tr = battle(c, mon_of(("2_Single",), sim=[{"kind": "lock_monster_damage"}]), "sc", hp=10 ** 9)
        self.assertTrue(all(t["mon_dmg_edit"] == t["mon_dmg"] for t in tr))
        # 분할: 결과 값이 분할 reach 안에 있어야 한다
        _, _, tr = battle(c, mon_of(("2_Single",), sim=[{"kind": "split_player"}]), "sp", hp=10 ** 9)
        for t in tr:
            self.assertIn(t["base_edit"], bm.reach(2, t["base"], t["K"], split=True))

    # --- AC-K6
    def test_k6_aimed_shot(self):
        sim = [{"kind": "aimed_shot", "multiplier": 3}]
        _, _, tr = battle(cfg_of(g="on", skill=0.0), mon_of(("2_Single",), sim=sim), "aim", hp=10 ** 9)
        for t in tr:
            hit = str(t["aim"]) in str(t["base"]) + "1"
            self.assertEqual(t["taken"], t["mon_dmg"] * (3 if hit else 1), t)
        # 정책: 실력 1 이면 조준 숫자를 피하는 비율이 실력 0 보다 높다
        def rate(skill):
            n = hit = 0
            for i in range(40):
                _, _, tr = battle(cfg_of(g="on", skill=skill), mon_of(("2_Single",), sim=sim), f"a{i}", hp=3000)
                for t in tr:
                    n += 1
                    hit += str(t["aim"]) in str(t["base_edit"]) + "1"
            return hit / n
        self.assertLess(rate(1.0), rate(0.0) - 0.03)

    # --- AC-K7
    def test_k7_hidden_suffix(self):
        sim = [{"kind": "hidden_digits", "count": 2, "ratio": 0.5}]
        c = cfg_of(g="on", skill=0.0)
        found_any = False
        for i in range(20):
            _, stt, tr = battle(c, mon_of(("2_Single",), sim=sim), f"h{i}", hp=10 ** 9)
            mhp = 100000
            for t in tr:
                d = mhp - t["mhp"]
                mhp = t["mhp"]
                self.assertIn(d, (0, t["base"] // 2, t["base"]))
                found_any |= d == t["base"] // 2 and d > 0
        self.assertTrue(found_any)
        sf = [{"kind": "suffix", "digits": 2}]
        hits = 0
        for i in range(30):
            _, _, tr = battle(cfg_of(g="on", skill=0.0), mon_of(("2_Single",), sim=sf), f"s{i}", hp=10 ** 9)
            mhp = 100000
            for t in tr:
                d = mhp - t["mhp"]
                mhp = t["mhp"]
                if d:
                    hits += 1
                    self.assertEqual(t["base"] % 100, t["special"] % 100)
        # 실력 1 이면 맞추려고 성냥을 옮긴다 → 0 이 아닌 피해가 더 자주
        hits1 = 0
        for i in range(30):
            _, _, tr = battle(cfg_of(g="on", skill=1.0), mon_of(("2_Single",), sim=sf), f"s{i}", hp=10 ** 9)
            mhp = 100000
            for t in tr:
                hits1 += (mhp - t["mhp"]) > 0
                mhp = t["mhp"]
        self.assertGreater(hits1, hits)

    # --- AC-K8
    def test_k8_report(self):
        tab = json.load(open(MTABLE, encoding="utf-8"))["monsters"]
        self.assertEqual(len(tab), 39)
        by = {m["id"]: m for m in tab}
        for m in tab:
            self.assertIn(m["fidelity_gimmicks"], ("exact", "approx", "none"))
            self.assertTrue(all(r["reason"] for r in m["gimmick_report"]))
        self.assertIn("사용자 결정", next(r["reason"] for r in by["Mob_20104_Magician"]["gimmick_report"] if r["gimmick"] == "decoy"))
        self.assertEqual(by["Mob_30107_Shadow"]["fidelity_gimmicks"], "approx")
        self.assertEqual(by["Mob_10101_Fairy"]["fidelity_digits"], "exact")
        self.assertEqual(sum(m["fidelity_digits"] == "exact" for m in tab), 5)


if __name__ == "__main__":
    unittest.main()
