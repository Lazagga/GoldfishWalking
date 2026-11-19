# -*- coding: utf-8 -*-
"""v4.5 F22-C 플레이어 AI 효과 활용 점검 — 가지치기·빔 없이 모든 후보를 열거한 최적(oracle)과 실제 배분 정책의 선택을 비교한다.

환상마다 전투를 돌려 배분이 일어난 턴마다 두 목적함수 키를 비교하고, 다르면 불일치로 센다 (fight_digits.ORACLE 훅).
기본 실행은 스모크(환상당 N=ORACLE_N, 기본 200). 전체 점검은 ORACLE_N=2000 ORACLE_WRITE=1 로 돌려 sim_results/ai_oracle.json 을 만든다.
"""
import json
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)

from sim_service import fight_digits as fd  # noqa: E402
from test_v4_digits import battle, cfg_of, mon_of  # noqa: E402

N = int(os.environ.get("ORACLE_N", "200"))
TARGETS = {          # 상자 값·모양에 의존하는 효과를 가진 환상
    "fan_damage_libra": "천칭자리 (0 → 200 / ×0.5)",
    "fan_end_8ball": "8의 개수 (턴 종료 피해)",
    "fan_damage_virgo": "연속쌍 (타수)",
    "fan_damage_mirror": "같은 숫자 상자 (타수)",
    "fan_end_paperplane": "내 기본 피해 = 몬스터 1타 (최종 배율)",
    "fan_defend_paperboat": "몬스터 1타 ≥ 내 기본 피해 (받는 피해 배율)",
}


def collect(fids=(), n=N, ignore_rank=False, sim=(), seed="OR", mhp=6000, hp=3000):
    c = cfg_of(skill=1.0, hp=hp)
    c["player"]["moves_per_turn"] = 2
    log = []
    fd.ORACLE = {"log": log, "raw": [], "ignore_rank": ignore_rank}
    try:
        i = 0
        while len(log) < n and i < 4000:
            mon = mon_of(("2_Single", "2_Multi_1"), hp=mhp, sim=sim, ai="static")
            battle(c, mon, f"{seed}{i}", fids=fids, hp=hp)
            i += 1
    finally:
        fd.ORACLE = None
    return log[:n]


def rate(log):
    return sum(1 for e in log if not e["match"]) / max(1, len(log))


class Oracle(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.table = {}
        for fid in TARGETS:
            cls.table[fid] = collect((fid,))
        cls.table["(환상 없음)"] = collect(())
        cls.table["조준 사격 (몬스터)"] = collect((), sim=[{"kind": "aimed_shot", "multiplier": 3}], seed="OA")
        if os.environ.get("ORACLE_WRITE"):
            out = {"n": N, "rows": [{"id": k, "name": TARGETS.get(k, k), "turns": len(v), "mismatch": sum(1 for e in v if not e["match"]),
                                      "rate": round(rate(v), 4)} for k, v in cls.table.items()]}
            with open(os.path.join(ROOT, "sim_results", "ai_oracle.json"), "w", encoding="utf-8") as fp:
                json.dump(out, fp, ensure_ascii=False, indent=1)

    # --- AC-O1: 환상별 불일치율 표가 대상 환상을 모두 포함한다
    def test_o1_table_has_all_targets(self):
        for fid in TARGETS:
            self.assertGreaterEqual(len(self.table[fid]), min(N, 50), fid)
        print("\n  AI 효과 활용 점검 (불일치율, 턴 N=%d)" % N)
        for k, v in self.table.items():
            print(f"    {k:<24} {rate(v) * 100:5.2f}%  ({sum(1 for e in v if not e['match'])}/{len(v)})")

    # --- AC-O2: 천칭자리 불일치율 ≤ 1%, 가지치기를 F22-A 이전처럼(rank 무시) 하면 더 높다
    def test_o2_libra_matches_oracle_and_legacy_prune_does_not(self):
        self.assertLessEqual(rate(self.table["fan_damage_libra"]), 0.01)
        legacy = collect(("fan_damage_libra",), ignore_rank=True)
        self.assertGreater(rate(legacy), 0.01)
        self.assertGreater(rate(legacy), rate(self.table["fan_damage_libra"]))

    def test_o3_other_feature_fantasies_report(self):
        # 불일치율이 1% 를 넘는 환상은 가지치기 특징이 빠진 것 — 표에 이름이 남고, 여기서는 상한(5%)만 지킨다
        for fid in TARGETS:
            self.assertLessEqual(rate(self.table[fid]), 0.05, (fid, rate(self.table[fid])))

    def test_hook_off_by_default(self):
        self.assertIsNone(fd.ORACLE)


if __name__ == "__main__":
    unittest.main()
