# -*- coding: utf-8 -*-
"""몬스터 전투 로그 (v4.5 F16): 표본 수집·히스토그램·재생.

- 지표 계산(chunk_metrics)은 전투마다 요약 레코드를 받아 몬스터별·분류별 상위 N개만 들고 있다. 청크끼리 같은 규칙으로 다시 N개를 골라 합치므로
  청크 크기와 무관하게 같은 표본이 나온다(정렬 키 끝에 (run, ord) 동률 규칙, 무작위 분류는 sha1 해시).
- 개별 로그를 저장하지 않는다. 표본의 위치(런 번호·그 런에서 몇 번째 전투)만 저장하고, 상세는 같은 시드로 다시 돌려(replay) 만든다.
- 시뮬레이션 의미를 바꾸지 않는다(트레이스·전투 기록의 부가 필드만 읽는다).
"""
from __future__ import annotations

import bisect
import hashlib
import math

import matchup_sim as ms

CATS = ("death", "max_hit", "taken", "long", "short", "win", "escape", "random")
CAT_LABEL = {"death": "사망", "max_hit": "최대 1타", "taken": "받은 피해", "long": "긴 전투", "short": "짧은 전투",
             "win": "승리(아슬아슬)", "escape": "도주·시간 초과", "random": "무작위"}
N_SAMPLES = 8
COMPACT = ("run", "ord", "act", "floor", "hp0", "hp1", "turns", "taken", "taken_cap", "max_hit", "outcome", "nfant")
HIST_STEPS = 8            # 1 옥타브를 8칸
HIST_MAX = 40 * HIST_STEPS
OUTLIER_DEFAULT = {"taken_ratio": 3.0, "max_hit_mult": 100.0}


def _h(seed, mid, run, ord_, tag=""):
    return int(hashlib.sha1(f"{seed}|{mid}|{run}|{ord_}{tag}".encode("utf-8")).hexdigest()[:12], 16)


def rec_keys(b, seed):
    """전투 레코드 → {분류: 정렬 키}. 키가 작을수록 앞선다. 동률은 (run, ord) 오름차순."""
    mid, run, o = b["monster"], b["run"], b["ord"]
    tie = (run, o)
    ks = {"max_hit": (-b["max_hit"],) + tie, "taken": (-b.get("taken_cap", b["taken"]),) + tie,
          "long": (-b["turns"],) + tie, "short": (b["turns"],) + tie, "random": (_h(seed, mid, run, o),) + tie}
    out = b["outcome"]
    if out == "death":
        ks["death"] = (_h(seed, mid, run, o, "d"),) + tie
    elif out == "win":
        ks["win"] = (b.get("hp1", 0),) + tie
    elif out in ("escape", "timeout"):
        ks["escape"] = (_h(seed, mid, run, o, "e"),) + tie
    return ks


def sample_add(samples, b, seed):
    """samples = {mid: {cat: [(key, compact)...]}} 에 전투 하나를 넣는다 (분류마다 상위 N 만 유지)."""
    cm = None
    for cat, key in rec_keys(b, seed).items():
        lst = samples.setdefault(b["monster"], {}).setdefault(cat, [])
        if len(lst) >= N_SAMPLES and key >= lst[-1][0]:
            continue
        if cm is None:
            cm = {k: b.get(k) for k in COMPACT}
        bisect.insort(lst, (key, cm), key=lambda x: x[0])
        if len(lst) > N_SAMPLES:
            lst.pop()


def samples_merge(parts):
    """청크별 samples 를 같은 규칙으로 합친다."""
    out = {}
    for p in parts:
        for mid, cats in (p or {}).items():
            for cat, lst in cats.items():
                out.setdefault(mid, {}).setdefault(cat, []).extend(lst)
    for mid, cats in out.items():
        for cat in cats:
            cats[cat].sort(key=lambda x: x[0])
            del cats[cat][N_SAMPLES:]
    return out


def samples_final(samples, mid):
    """저장·전송용: {분류: [compact ...]} (키 제거)."""
    return {cat: [rec for _, rec in lst] for cat, lst in (samples.get(mid) or {}).items()}


# ---------------------------------------------------------------------------
# 로그 눈금 히스토그램 (분위수를 청크끼리 합칠 수 있게)
# ---------------------------------------------------------------------------
def hist_bin(v):
    if v <= 0:
        return 0
    return min(HIST_MAX, 1 + int(math.log2(v) * HIST_STEPS))


def hist_add(h, v):
    b = hist_bin(v)
    h[b] = h.get(b, 0) + 1


def hist_quantile(h, q):
    n = sum(h.values())
    if not n:
        return None
    target, acc = q * n, 0
    for b in sorted(h):
        acc += h[b]
        if acc >= target:
            return 0 if b == 0 else round(2 ** ((b - 0.5) / HIST_STEPS), 2)
    return None


# ---------------------------------------------------------------------------
# 재생
# ---------------------------------------------------------------------------
def _segments(tr):
    """트레이스 → 시도(attempt) 구간 목록. battle_log 항목과 같은 순서(부활로 되감기하면 시도마다 항목 하나)."""
    segs, cur, battle_ev, start = [], None, None, 0
    for i, e in enumerate(tr):
        ev = e.get("ev")
        if ev == "battle":
            battle_ev, cur, start = e, {"battle": e, "turns": [], "start": i, "end": None}, i
        elif ev == "turn" and cur is not None:
            cur["turns"].append(e)
        elif ev in ("rewind", "battle_end") and cur is not None:
            cur["end"] = i
            segs.append(cur)
            cur = {"battle": battle_ev, "turns": [], "start": start, "end": None} if ev == "rewind" else None
    return segs


def replay(cfg, fantasies, mid, seed, run, ord_=None, expect=None, ctx=None):
    """한 판을 그대로 다시 돌려 그 몬스터의 ord 번째 전투 로그를 만든다. fantasies = {id: {"name","grade"}}.
    expect 가 있으면 turns·taken·max_hit·outcome·floor 를 비교해 replay_match 를 정한다."""
    tr, bl = [], []
    row = ms.simulate_run(cfg, f"{seed}-{run}", ctx=ctx, trace=tr, battle_log=bl)
    idx = [i for i, b in enumerate(bl) if b["monster"] == mid]
    k = int(ord_ or 0)
    if k < 0 or k >= len(idx):
        raise LookupError(f"그 런에 {mid} 전투가 {len(idx)}번뿐이라 ord={k} 이 없음")
    b = bl[idx[k]]
    seg = _segments(tr)[idx[k]]
    ev0 = tr[:seg["start"]]
    # 보유 환상: 이 전투 전의 acquire (획득 층 = 직전 node)
    owned, void, cur_node = [], [], None
    fx = {f["fid"] for lst in (seg["battle"].get("fx") or {}).values() for f in lst}
    for e in ev0:
        if e.get("ev") == "node":
            cur_node = (e.get("act"), e.get("floor"))
        elif e.get("ev") == "acquire":
            f = fantasies.get(e["fid"], {})
            owned.append({"n": len(owned) + 1, "fid": e["fid"], "name": f.get("name", e["fid"]), "grade": f.get("grade"),
                          "floor": list(cur_node) if cur_node else None, "source": e.get("source"), "fx": e["fid"] in fx})
        elif e.get("ev") == "acquire_void":
            void.append({"fid": e.get("fid"), "floor": list(cur_node) if cur_node else None})
    # 전투 전까지의 런 흐름
    timeline = []
    for e in ev0:
        t = e.get("ev")
        if t == "node":
            timeline.append({"act": e.get("act"), "floor": e.get("floor"), "type": e.get("type"), "hp": e.get("hp")})
        elif timeline and t in ("rest", "shop", "battle_end"):
            timeline[-1].update({k2: v for k2, v in e.items() if k2 != "ev"} | {"then": t})
    turns = []
    for t in seg["turns"]:
        t = dict(t)
        hp_before = t["hp"] - t["hp_change"]
        over = max(0, t["taken"] - max(hp_before, 0))
        t["hp_before"], t["taken_cap"] = hp_before, min(t["taken"], max(hp_before, 0))
        notes = list(t.get("notes") or [])
        if over and t.get("end") == "death":
            notes.append({"k": "overkill", "over": over})
        t["notes"], t["over"] = notes, over
        turns.append(t)
    res = {"mid": mid, "seed": f"{seed}-{run}", "run": {k2: row.get(k2) for k2 in ("result", "reached_floor", "end_act", "end_floor") if k2 in row},
           "battle": {"act": b["act"], "floor": b["floor"], "ord": k, "hp0": b["hp0"], "hp1": b["hp1"], "mhp0": seg["battle"].get("mhp"),
                      "turns": b["turns"], "taken": b["taken"], "taken_cap": b["taken_cap"], "max_hit": b["max_hit"], "outcome": b["outcome"],
                      "nfant": b["nfant"]},
           "owned": owned, "acquire_void": void, "items": {"matches": seg["battle"].get("matches"), "erasers": seg["battle"].get("erasers")},
           "turns": turns, "timeline": timeline, "replay_match": True}
    if expect:
        got = {"turns": b["turns"], "taken": b["taken"], "max_hit": b["max_hit"], "outcome": b["outcome"], "floor": b["floor"]}
        bad = {k2: {"expected": v, "replayed": got.get(k2)} for k2, v in expect.items() if k2 in got and got[k2] != v}
        res["replay_match"] = not bad
        if bad:
            res["mismatch"] = bad
    return res
