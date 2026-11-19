# -*- coding: utf-8 -*-
"""v2 AC-S2 / AC-F5 / AC-F7(결과 부분): 속도 개선·옵션 추가 후에도 기본 설정의 모든 판 결과가
v1 코드(tests/_matchup_sim_v1.py)와 같아야 한다.

환경 변수 IDENTITY_SEEDS 로 시드 수를 바꿀 수 있다 (기본 2000 = 명세 값).
"""
import copy
import os
import sys
import unittest


def _legacy(mod):
    """v4.1 까지의 기본 설정 (v4.2 에서 기본이 table+digits 로 바뀜). v1 원본 모듈에는 해당 키가 없다."""
    import copy as _c
    cfg = _c.deepcopy(mod.DEFAULT_CONFIG)
    if hasattr(mod, "LEGACY_MONSTERS"):
        cfg["monsters"].update(mod.LEGACY_MONSTERS)
    if "rewards" in cfg:      # v1 원본 모듈에는 rewards 설정이 없다 (보상 = 환상 확정)
        cfg["rewards"]["normal_battle"]["mode"] = "fantasy"      # v4.4 부터 기본 획득 방식이 ember — v1 과 같은 환상 확정 보상으로 비교
    return cfg

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)

import matchup_sim as ms  # noqa: E402
import _matchup_sim_v1 as v1  # noqa: E402

EFFECTS = os.path.join(ROOT, "fantasy_effects.json")
N = int(os.environ.get("IDENTITY_SEEDS", "2000"))

# (이름, effects 사용 여부, hp_base, 강제 포함 목록들)
CASES = [
    ("grade74", False, 74, [[], ["W05"], ["B03", "R02"]]),
    ("table660", True, 660, [[], ["fan_fantasy_leo"], ["fan_start_stamp", "fan_damage_slingshot"]]),
    ("table300", True, 300, [[], ["fan_turn_boots"], ["fan_acquire_blueprint", "fan_rest_coffee"]]),
]


def _identity_effects():
    """v1 과의 동일성 비교용 효과 테이블: 천칭자리는 뺀다. F22-A 이후 천칭자리는 평가형 한 규칙(zero_else_mult)이고 복수 보유해도 중첩되지 않아(D5)
    v1(보유 수만큼 반복)과 일부러 다르다 — 값 자체는 test_v45_policy_libra 가 검사한다."""
    import json
    import tempfile
    with open(EFFECTS, encoding="utf-8") as fp:
        tab = json.load(fp)
    for f in tab["fantasies"]:
        if f["id"] == "fan_damage_libra":
            f["available"] = False
    p = os.path.join(tempfile.mkdtemp(), "fe_identity.json")
    with open(p, "w", encoding="utf-8") as fp:
        json.dump(tab, fp)
    return p


_LEGACY = []


def cfg_for(mod, table, hp, forced):
    cfg = _legacy(mod)
    cfg["monsters"]["act_hp_growth"] = 2.0
    cfg["monsters"]["hp_base"] = hp
    if table:
        if not _LEGACY:
            _LEGACY.append(_identity_effects())
        cfg["fantasy"]["effects_file"] = _LEGACY[0]
        cfg["fantasy"]["effect_mode"] = "table"
    cfg["fantasy"]["forced"] = {"ids": list(forced), "at": "start"}
    return cfg


def compare(testcase, n=N, extra=None, trace=False):
    """모든 사례에서 행 dict 가 v1 과 같은지. extra(cfg) 로 새 옵션의 기본값을 명시적으로 넣어 볼 수 있다.
    v1 은 반올림(round)을 쓰므로(F22-D 이후 현행은 버림) 비교하는 동안만 LEGACY_ROUNDING 을 켠다."""
    ms.LEGACY_ROUNDING = True
    try:
        _compare(testcase, n, extra, trace)
    finally:
        ms.LEGACY_ROUNDING = False


def _compare(testcase, n=N, extra=None, trace=False):
    for name, table, hp, forced_sets in CASES:
        for forced in forced_sets:
            c_old = cfg_for(v1, table, hp, forced)
            c_new = cfg_for(ms, table, hp, forced)
            if extra:
                extra(c_new)
            ctx_old, ctx_new = v1.SimContext(c_old), ms.SimContext(c_new)
            for i in range(n):
                seed = f"id-{i}"
                a = v1.simulate_run(c_old, seed, ctx=ctx_old)
                kw = {"trace": []} if trace else {}
                b = ms.simulate_run(c_new, seed, ctx=ctx_new, **kw)
                b = {k: b[k] for k in a}   # 기존(v1) 키만 비교 — v3 에서 통계 키가 추가됨 (명세 AC-S2)
                if a != b:
                    diff = {k: (a.get(k), b.get(k)) for k in set(a) | set(b) if a.get(k) != b.get(k)}
                    testcase.fail(f"{name} forced={forced} seed={seed}: {diff}")


class IdentityWithV1(unittest.TestCase):
    def test_rows_identical(self):
        compare(self)


if __name__ == "__main__":
    unittest.main()
