# -*- coding: utf-8 -*-
"""몬스터별 지표 (명세 v2 F2): 평균 턴 수, 전투당 받는 피해, 이 몬스터에서의 사망 비율, 전투 중 최대 1타 피해,
조우 시 승률 (전투 승률 = 이 몬스터와의 전투에서 이긴 비율, 조우한 런 승률 = 이 몬스터를 만난 런이 클리어한 비율)."""
from __future__ import annotations

import json
import math
import os
from datetime import datetime

import matchup_sim as ms

from . import battlelog as bl_

MON_CHUNK_SCHEMA = 2     # 청크 결과의 모양(표본·히스토그램 추가). jobs 의 청크 캐시 키에 들어가 옛 청크가 섞이지 않게 한다 (SIM_VERSION 은 그대로)

# 기획 문서(보완 우선순위 S4·M3)의 목표 전투 턴 수
TURN_TARGETS = {"easy": [3, 4], "normal": [3, 4], "elite": [5, 6], "boss": [7, 9]}


def chunk_metrics(task):
    cfg, seed, start, end = task
    ctx = ms.SimContext(cfg)
    agg = {}
    samples = {}
    deaths = runs = wins = 0
    for i in range(start, end):
        log = []
        r = ms.simulate_run(cfg, f"{seed}-{i}", ctx=ctx, battle_log=log)
        runs += 1
        ords = {}
        for b in log:
            a = agg.setdefault(b["monster"], {"tier": b["tier"], "act": b["act"], "battles": 0, "turns": 0, "turns_sq": 0,
                                              "taken": 0, "deaths": 0, "max_hit_sum": 0, "max_hit_max": 0, "timeouts": 0})
            a["battles"] += 1
            a["turns"] += b["turns"]
            a["turns_sq"] += b["turns"] ** 2
            a["taken"] += b["taken"]
            a["max_hit_sum"] += b["max_hit"]
            a["max_hit_max"] = max(a["max_hit_max"], b["max_hit"])
            a.setdefault("escapes", 0)
            a["taken_cap"] = a.get("taken_cap", 0) + b.get("taken_cap", 0)
            a["hp0_sum"] = a.get("hp0_sum", 0) + b.get("hp0", 0)
            bl_.hist_add(a.setdefault("h_taken", {}), b["taken"])
            bl_.hist_add(a.setdefault("h_max", {}), b["max_hit"])
            if b["outcome"] == "death":
                a["deaths"] += 1
                if b["taken"] > 2 * max(1, b.get("hp0", 1)):
                    a["overkill_deaths"] = a.get("overkill_deaths", 0) + 1
            elif b["outcome"] == "escape":
                a["escapes"] += 1
            elif b["outcome"] == "timeout":
                a["timeouts"] += 1
            o = ords.get(b["monster"], 0)
            ords[b["monster"]] = o + 1
            bl_.sample_add(samples, {**b, "run": i, "ord": o}, seed)       # v4.5 F16: 표본 후보 (분류별 상위 N)
        won = r["result"] == "win"
        for mid in {b["monster"] for b in log}:      # 런 단위: 이 몬스터를 한 번이라도 만난 런
            a = agg[mid]
            a["runs_met"] = a.get("runs_met", 0) + 1
            a["runs_met_won"] = a.get("runs_met_won", 0) + won
        if r["result"] == "lose":
            deaths += 1
        wins += won
    return {"agg": agg, "deaths": deaths, "runs": runs, "wins": wins, "samples": samples}


def merge(parts):
    agg, deaths, runs, wins = {}, 0, 0, 0
    for p in parts:
        deaths += p["deaths"]
        runs += p["runs"]
        wins += p.get("wins", 0)
        for k, a in p["agg"].items():
            t = agg.setdefault(k, {**a, **{f: 0 for f in ("battles", "turns", "turns_sq", "taken", "deaths",
                                                             "max_hit_sum", "max_hit_max", "timeouts", "escapes",
                                                             "runs_met", "runs_met_won", "taken_cap", "hp0_sum", "overkill_deaths")},
                                           "h_taken": {}, "h_max": {}})
            for f in ("battles", "turns", "turns_sq", "taken", "deaths", "max_hit_sum", "timeouts", "escapes",
                      "runs_met", "runs_met_won", "taken_cap", "hp0_sum", "overkill_deaths"):
                t[f] += a.get(f, 0)
            for hk in ("h_taken", "h_max"):
                for bin_, n_ in (a.get(hk) or {}).items():
                    t[hk][bin_] = t[hk].get(bin_, 0) + n_
            t["max_hit_max"] = max(t["max_hit_max"], a["max_hit_max"])
    return agg, deaths, runs, wins


def rate_ci(k, n):
    """비율과 95% Wilson 구간 (반올림)."""
    if not n:
        return None, None
    p = k / n
    lo, hi = ms.wilson_ci(p, n)
    return round(p, 4), [round(lo, 4), round(hi, 4)]


def fidelity_for(cfg, m):
    """피해 모델·기믹 스위치에 맞는 몬스터 충실도 (v4)."""
    M = cfg["monsters"]
    if M.get("damage_model", "gauss") != "digits":
        return m.get("fidelity", "approx")
    if M.get("gimmicks", "off") == "on":
        return m.get("fidelity_gimmicks", m.get("fidelity_digits", "none"))
    return m.get("fidelity_digits", "none")


def warning_for(cfg, m):
    if not m.get("gimmicks"):
        return ""
    M = cfg["monsters"]
    if M.get("damage_model") == "digits" and M.get("gimmicks") == "on":
        bad = [r for r in m.get("gimmick_report", []) if r["fidelity"] != "exact"]
        return ("근사 기믹: " + "; ".join(f"{r['gimmick']}({r['fidelity']}) {r['reason']}" for r in bad)) if bad else ""
    return "미모델링 기믹: " + ", ".join(m["gimmicks"])


def run_metrics(cfg, seed, n, pool=None, chunk=250, monster_table=None):
    tasks = [(cfg, seed, s, min(n, s + chunk)) for s in range(0, n, chunk)]
    parts = pool.map(chunk_metrics, tasks) if pool is not None else [chunk_metrics(t) for t in tasks]
    return build_result(cfg, *merge(parts), monster_table=monster_table, samples=bl_.samples_merge([p.get("samples") for p in parts]),
                        seed=seed)


def build_result(cfg, agg, deaths, runs, wins, monster_table=None, samples=None, with_samples=True, outlier=None, seed=None):
    """merge() 결과 → 몬스터별 지표 행. 서버 작업(monster_metrics)도 같은 함수를 쓴다.
    samples: battlelog.samples_merge 결과(없으면 표본 없음). with_samples=False 면 행에 samples_stage='pending'(앞 단계 이벤트용)."""
    ol = {**bl_.OUTLIER_DEFAULT, **(outlier or {})}
    info = {}
    if monster_table:
        info = {m["id"]: m for m in monster_table.get("monsters", [])}
    rows = []
    for mid, a in agg.items():
        b = a["battles"]
        mean = a["turns"] / b
        var = max(0.0, a["turns_sq"] / b - mean * mean) * b / max(1, b - 1)
        se = math.sqrt(var / b) if b > 1 else 0.0
        m = info.get(mid, {})
        fid = fidelity_for(cfg, m) if m else "approx"
        tgt = TURN_TARGETS.get(a["tier"])
        verdict = None
        if tgt:
            lo, hi = mean - 1.96 * se, mean + 1.96 * se
            verdict = "길다" if lo > tgt[1] else "짧다" if hi < tgt[0] else "범위 내" if lo >= tgt[0] and hi <= tgt[1] else "불확실"
        rows.append({
            "id": mid, "name": m.get("name", mid), "act": a["act"], "tier": a["tier"], "hp": m.get("hp"),
            "fidelity": fid, "gimmicks": m.get("gimmicks", []),
            "warning": warning_for(cfg, m),
            "battles": b, "avg_turns": round(mean, 3), "turns_ci": [round(mean - 1.96 * se, 3), round(mean + 1.96 * se, 3)],
            "turn_target": tgt, "turn_verdict": verdict,
            "avg_taken": round(a["taken"] / b, 2), "death_rate_in_battle": round(a["deaths"] / b, 4),
            "death_share": round(a["deaths"] / max(1, deaths), 4), "timeouts": a["timeouts"],
            "max_hit_avg": round(a["max_hit_sum"] / b, 2), "max_hit_max": a["max_hit_max"],
            "escapes": a.get("escapes", 0),
            # 조우 시 승률: 전투 승리 = 사망·도주(카운트다운)·시간 초과가 아닌 전투
            "battle_wins": b - a["deaths"] - a.get("escapes", 0) - a["timeouts"],
            "battle_win_rate": rate_ci(b - a["deaths"] - a.get("escapes", 0) - a["timeouts"], b)[0],
            "battle_win_ci": rate_ci(b - a["deaths"] - a.get("escapes", 0) - a["timeouts"], b)[1],
            "runs_met": a.get("runs_met", 0),
            "run_win_rate_met": rate_ci(a.get("runs_met_won", 0), a.get("runs_met", 0))[0],
            "run_win_ci_met": rate_ci(a.get("runs_met_won", 0), a.get("runs_met", 0))[1],
            # v4.5 F16.5: 이상치 대응 열 (기존 열의 정의는 그대로, 끝에 추가)
            "avg_taken_cap": round(a.get("taken_cap", 0) / b, 2),
            "taken_p50": bl_.hist_quantile(a.get("h_taken") or {}, 0.5), "taken_p90": bl_.hist_quantile(a.get("h_taken") or {}, 0.9),
            "max_hit_p50": bl_.hist_quantile(a.get("h_max") or {}, 0.5), "max_hit_p90": bl_.hist_quantile(a.get("h_max") or {}, 0.9),
            "overkill_share": round(a.get("overkill_deaths", 0) / a["deaths"], 4) if a["deaths"] else None,
            "hp0_mean": round(a.get("hp0_sum", 0) / b, 1),
        })
        row = rows[-1]
        row["outlier"] = bool((row["avg_taken_cap"] > 0 and row["avg_taken"] >= ol["taken_ratio"] * row["avg_taken_cap"])
                              or (row["hp0_mean"] > 0 and row["max_hit_max"] >= ol["max_hit_mult"] * row["hp0_mean"]))
        if with_samples:
            row["samples"] = bl_.samples_final(samples or {}, mid)
        else:
            row["samples_stage"] = "pending"
    rows.sort(key=lambda r: (r["act"], ["easy", "normal", "elite", "boss"].index(r["tier"]), r["name"]))
    out = {"runs": runs, "deaths": deaths, "wins": wins, "win_rate": round(wins / max(1, runs), 4), "monsters": rows}
    if seed is not None:
        out["seed"] = seed
    return out


def meta_of(cfg, seed, n):
    return {"generated_at": datetime.now().isoformat(timespec="seconds"), "seed": seed, "runs": n,
            "monster_model": cfg["monsters"].get("model"), "damage_model": cfg["monsters"].get("damage_model"),
            "hp_scale": cfg["monsters"].get("hp_scale"), "turn_targets": TURN_TARGETS,
            "gimmicks": cfg["monsters"].get("gimmicks", "off"),
            "note": ("피해 크기는 등급 평균(gauss) — 원본 자릿수 미사용. 기믹 미모델링 몬스터는 경고 표시."
                     if cfg["monsters"].get("damage_model", "gauss") != "digits" else
                     "digits: 자릿수 굴림 + 상자 안 성냥 이동(정책). 기믹 " + cfg["monsters"].get("gimmicks", "off"))}


def write(result, cfg, seed, n, path):
    data = {"meta": meta_of(cfg, seed, n), **result}
    with open(path, "w", encoding="utf-8") as fp:
        json.dump(data, fp, ensure_ascii=False, indent=1)
    return data


def probe(cfg, mon, n=2000, seed="probe", fids=()):
    """몬스터 1종과의 단독 전투 지표 (v3 F2 monster_probe). 기준 상태 = 시작 체력·설정된 실력·환상 없음(fids 로 지정 가능).
    런 맥락(누적 체력·환상 보유)이 없는 지표다. 같은 시드·설정이면 결과가 같다."""
    import copy
    c = copy.deepcopy(cfg)
    c["fantasy"]["forced"] = {"ids": [], "at": "start"}
    c0 = copy.deepcopy(c)             # 몬스터 테이블 파일 없이도 단독 전투를 돌릴 수 있게 (digits 검사 우회)
    c0["monsters"]["damage_model"], c0["monsters"]["gimmicks"], c0["monsters"]["model"] = "gauss", "off", "tier_avg"
    ctx = ms.SimContext(c0)
    ctx.damage_model = c["monsters"].get("damage_model", "gauss")
    if ctx.mode != "table":
        raise ValueError("monster_probe 는 table 효과 모드에서만 동작")
    ctx.pick_monster = lambda st, tier, act: mon
    ctx.new_monster_state = lambda m: {"i": 0, "uses": {}}
    if ctx.monsters is None:
        ctx.monsters = {}
    c["monsters"]["model"] = "table"
    turns = taken = kills = deaths = 0
    hist = {}
    for i in range(n):
        st = ms.RunState(c, ctx.pool, ctx, f"{seed}-{i}")
        st.battle_log = []
        for f in fids:
            st.acquire(ctx.grade_of[f], f, "forced")
        st.stats["battles"] = 1
        st.floor_pos = ("probe", i)
        fight_fn = ms.fight_table
        if c["monsters"].get("damage_model", "gauss") == "digits":
            from .fight_digits import fight_digits as fight_fn
        out = fight_fn(c, st, mon["tier"], int(mon["act"]), ms.rng_for(seed, "probe", mon["id"], i))
        b = st.battle_log[-1]
        turns += b["turns"]
        taken += b["taken"]
        kills += out == "win"
        deaths += out == "death"
        hist[b["turns"]] = hist.get(b["turns"], 0) + 1
    return {"id": mon["id"], "n": n, "damage_model": c["monsters"].get("damage_model", "gauss"),
            "gimmicks": c["monsters"].get("gimmicks", "off"), "fidelity": fidelity_for(c, mon),
            "avg_turns": round(turns / n, 4), "avg_taken": round(taken / n, 3),
            "kill_rate": round(kills / n, 4), "death_rate": round(deaths / n, 4), "hp": mon["hp"],
            "turn_target": TURN_TARGETS.get(mon["tier"]), "turn_hist": dict(sorted(hist.items())),
            "note": "단독 전투 지표 — 런 맥락(누적 체력·환상 보유) 없음"}
