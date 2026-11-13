# -*- coding: utf-8 -*-
"""시드 런 재생 (명세 v2 F7): 같은 시드를 기준선 / 환상 강제 포함으로 돌려 턴 로그와 처음 갈라진 지점을 만든다."""
from __future__ import annotations

import copy

import matchup_sim as ms

# 비교에 쓰는 필드 (fx 기여 목록·체력 변화 같은 파생 값은 제외)
PROJ = ("ev", "act", "floor", "type", "tier", "monster", "mhp", "t", "intent", "mon_dmg", "hits", "base",
        "moves", "att", "def", "dealt", "taken", "hp", "end", "outcome", "pick", "offered", "fid", "heal",
        "hp_spent", "bought")


def project(e):
    return tuple((k, e.get(k)) for k in PROJ if k in e)


def run_trace(cfg, seed_str, forced=()):
    c = copy.deepcopy(cfg)
    c["fantasy"]["forced"] = {"ids": list(forced), "at": (c["fantasy"].get("forced") or {}).get("at", "start")}
    tr = []
    row = ms.simulate_run(c, seed_str, trace=tr)
    return row, tr


def divergence(base_events, forced_events, forced_ids=()):
    """기준선과 강제 포함 로그에서 처음 갈라진 위치. 강제 포함 획득 이벤트 자체는 비교에서 뺀다.
    반환: {"base": i, "forced": j} (각 로그의 인덱스) 또는 None(끝까지 같음)."""
    fe = [(j, e) for j, e in enumerate(forced_events)
          if not (e.get("ev") == "acquire" and e.get("source") == "forced" and e.get("fid") in forced_ids)]
    be = list(enumerate(base_events))
    for (i, a), (j, b) in zip(be, fe):
        if project(a) != project(b):
            return {"base": i, "forced": j}
    if len(be) != len(fe):
        k = min(len(be), len(fe))
        return {"base": be[k][0] if k < len(be) else len(base_events),
                "forced": fe[k][0] if k < len(fe) else len(forced_events)}
    return None


def compare(cfg, seed_str, fid):
    forced = [fid] if isinstance(fid, str) else list(fid)
    row_b, tr_b = run_trace(cfg, seed_str, [])
    row_f, tr_f = run_trace(cfg, seed_str, forced)
    return {"seed": seed_str, "fid": fid, "base": {"row": row_b, "events": tr_b},
            "forced": {"row": row_f, "events": tr_f}, "divergence": divergence(tr_b, tr_f, forced)}


def suggest_seeds(rec_base, rec_f, master_seed, limit=8):
    """대표 시드 제안: 환상 승리, 환상 패배, 기준선과 결과가 갈린 시드."""
    n = min(rec_base["n"], rec_f["n"])
    wins, losses, diff_up, diff_down = [], [], [], []
    for i in range(n):
        b, f = rec_base["wins"][i] == "1", rec_f["wins"][i] == "1"
        (wins if f else losses).append(i)
        if f and not b:
            diff_up.append(i)
        elif b and not f:
            diff_down.append(i)
    s = lambda xs: [f"{master_seed}-{i}" for i in xs[:limit]]  # noqa: E731
    return {"win": s(wins), "lose": s(losses), "turned_win": s(diff_up), "turned_lose": s(diff_down)}
