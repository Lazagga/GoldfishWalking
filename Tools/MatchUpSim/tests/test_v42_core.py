# -*- coding: utf-8 -*-
"""v4.2 F11 코어 (M27): 몬스터 체력 = 원본 JSON, 기본 설정 변경, 구버전 호환.

AC-H1 JSON 체력 그대로 / AC-H2 기본 설정·쓰이지 않는 키 경고 / AC-H3 키 호환(행 단위 동일은 test_identity)
AC-H5 시작 체력 단조 / AC-H11 캐시 키 / Q47 몬스터 테이블 없음·오래됨
테스트는 원본 몬스터 폴더(tests/fixtures/monsters)를 임시 폴더에 복사해서만 고친다.
"""
import copy
import glob
import json
import os
import shutil
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

import import_monsters as im  # noqa: E402
import matchup_sim as ms  # noqa: E402
from sim_service import fight_digits as fd  # noqa: E402
from sim_service import store as st  # noqa: E402

EFFECTS = os.path.join(ROOT, "fantasy_effects.json")
MTABLE = os.path.join(ROOT, "monster_table.json")
FIX_MON = os.path.join(HERE, "fixtures", "monsters")
FIX_PAT = os.path.join(HERE, "fixtures", "patterns")


def default_cfg():
    c = copy.deepcopy(ms.DEFAULT_CONFIG)
    ms.apply_fantasy_args(c, EFFECTS)
    return c


def battle_hp(cfg, mon):
    """그 몬스터와 싸울 때 전투에 쓰인 몬스터 체력 (trace 의 battle 이벤트)."""
    ctx = ms.SimContext(cfg)
    ctx.pick_monster = lambda s, tier, act: mon
    stt = ms.RunState(cfg, ctx.pool, ctx, "h1")
    stt.trace, stt.battle_log = [], []
    stt.floor_pos = (int(mon["act"]), 1)
    stt.stats["battles"] = 1
    fn = fd.fight_digits if cfg["monsters"]["damage_model"] == "digits" else ms.fight_table
    fn(cfg, stt, mon["tier"], int(mon["act"]), ms.rng_for("h1", mon["id"]))
    return [e for e in stt.trace if e["ev"] == "battle"][0]["mhp"]


class Defaults(unittest.TestCase):
    def test_h2_default_model(self):
        M = ms.DEFAULT_CONFIG["monsters"]
        self.assertEqual((M["model"], M["damage_model"], M["gimmicks"]), ("table", "digits", "on"))
        self.assertEqual(M["hp_scale"], 1.0)
        self.assertTrue(ms.resolve_table_file(M["table_file"]))

    def test_h1_json_hp_exact(self):
        with open(MTABLE, encoding="utf-8") as fp:
            table = json.load(fp)
        src = {}
        for p in glob.glob(os.path.join(FIX_MON, "*.json")):
            with open(p, encoding="utf-8-sig") as fp:
                d = json.load(fp)
            src[d.get("dataName") or d.get("id")] = d["stats"]["health"]
        mons = [m for m in table["monsters"] if m.get("enabled", True)]
        self.assertEqual(len(mons), 39)
        self.assertEqual(sum(m["id"] in src for m in mons), 39)     # 원본 39종 모두 대조
        c1, c2 = default_cfg(), default_cfg()
        c2["monsters"]["hp_scale"] = 2.0
        c1["monsters"]["hp_base"] = 999          # 쓰이지 않는 키 — 체력에 영향 없어야 함
        c1["monsters"]["tiers"]["boss"]["hp_cv"] = 0.9
        for m in mons:
            if m["id"] in src:
                self.assertEqual(m["hp"], src[m["id"]], m["id"])
            self.assertEqual(battle_hp(c1, m), m["hp"], m["id"])
            self.assertEqual(battle_hp(c2, m), 2 * m["hp"], m["id"])

    def test_h2_unused_keys_do_not_change_results(self):
        a, b = default_cfg(), default_cfg()
        for k, v in (("monsters.hp_base", 5), ("monsters.act_hp_growth", 9.0), ("monsters.tier_hp_ratio.boss", 50),
                     ("monsters.hp_model", "manual"), ("monsters.act_scale.1.hp", 7.0)):
            ms.set_path(b, k, v)
        ctx_a, ctx_b = ms.SimContext(a), ms.SimContext(b)
        for i in range(8):
            ra = ms.simulate_run(a, f"h2-{i}", ctx=ctx_a)
            rb = ms.simulate_run(b, f"h2-{i}", ctx=ctx_b)
            self.assertEqual(ra, rb)

    def test_h2_warnings(self):
        msgs = []
        bad = ms.warn_unused(default_cfg(), ["monsters.hp_base", "monsters.tiers.boss.hp_cv", "monsters.act_scale.1.hp",
                                             "monsters.easy_battles", "player.start_hp", "monsters.hp_scale"],
                             out=msgs.append)
        self.assertEqual(set(bad), {"monsters.hp_base", "monsters.tiers.boss.hp_cv", "monsters.act_scale.1.hp",
                                    "monsters.easy_battles"})
        self.assertTrue(all("쓰이지 않음" in m for m in msgs))
        self.assertEqual(ms.warn_unused(ms.legacy_config(), ["monsters.hp_base"], out=msgs.append), [])

    def test_legacy_normalization(self):
        c = default_cfg()
        c["monsters"]["model"] = "tier_avg"
        ms.normalize_models(c)
        self.assertEqual((c["monsters"]["damage_model"], c["monsters"]["gimmicks"]), ("gauss", "off"))
        ms.SimContext(c)    # 오류 없이 만들어짐

    def test_h11_keys(self):
        new, old = default_cfg(), ms.legacy_config()
        ms.apply_fantasy_args(old, EFFECTS)
        self.assertNotEqual(st.point_key(new, [], 0, "h"), st.point_key(old, [], 0, "h"))
        # 구버전 설정의 키는 '기믹 키가 없던 시절' 키와 같다 (AC-H3: 이전 캐시 재사용)
        old2 = copy.deepcopy(old)
        del old2["monsters"]["gimmicks"]
        self.assertEqual(st.point_key(old, [], 0, "h"), st.point_key(old2, [], 0, "h"))


class StartHp(unittest.TestCase):
    def test_h5_start_hp_only_initial(self):
        c = default_cfg()
        c["player"]["start_hp"] = 77
        ctx = ms.SimContext(c)
        self.assertEqual(ms.RunState(c, ctx.pool, ctx, "x").hp, 77)

    def test_h5_monotonic(self):
        lo, hi = default_cfg(), default_cfg()
        lo["player"]["start_hp"], hi["player"]["start_hp"] = 50, 550
        n = 250
        w = []
        for c in (lo, hi):
            ctx = ms.SimContext(c)
            w.append(sum(ms.simulate_run(c, f"h5-{i}", ctx=ctx)["result"] == "win" for i in range(n)))
        self.assertLess(w[0], w[1])


class MonsterTableFile(unittest.TestCase):
    def test_missing_table_message(self):
        c = default_cfg()
        c["monsters"]["table_file"] = "no_such_monster_table.json"
        with self.assertRaises(ValueError) as cm:
            ms.SimContext(c)
        self.assertIn("import_monsters.py", str(cm.exception))

    def test_stale_warning(self):
        with tempfile.TemporaryDirectory() as tmp:
            mon, pat = os.path.join(tmp, "monsters"), os.path.join(tmp, "patterns")
            shutil.copytree(FIX_MON, mon)
            shutil.copytree(FIX_PAT, pat)
            out = os.path.join(tmp, "mt.json")
            im.main(["--monsters", mon, "--patterns", pat, "--out", out, "--quiet"])
            self.assertIsNone(im.stale_warning(out, mon, pat))
            f = sorted(glob.glob(os.path.join(mon, "*.json")))[0]
            with open(f, encoding="utf-8-sig") as fp:
                d = json.load(fp)
            d["stats"]["health"] += 1
            with open(f, "w", encoding="utf-8") as fp:
                json.dump(d, fp, ensure_ascii=False)
            self.assertIn("오래됨", im.stale_warning(out, mon, pat) or "")


if __name__ == "__main__":
    unittest.main()
