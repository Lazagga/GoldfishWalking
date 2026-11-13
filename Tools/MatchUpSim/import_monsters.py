#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
원본 몬스터·패턴 JSON → monster_table.json (명세 v2 F2)
=======================================================

  python import_monsters.py                    # 기본 경로 (Assets/Data/Json/monsters, patterns)
  python import_monsters.py --report           # 매핑 초안·모호한 규칙 보고

패턴 키 규칙 (Assets/Docs/DataImportGuide.md "Monster Pattern Key Rules"):
  {자릿수}_Single            → 단타, 피해 상자 자릿수
  {자릿수}_Multi_{타수자릿수} → 연타
  Str_{N}                   → 힘 +N
  그 밖                      → patterns/*.json 의 id 로 찾음. 없으면 2_Single 로 대체(경고)
AI: static = 순서대로 순환(사용 불가 패턴 건너뜀), random = 사용 가능한 것 중 무작위.

시뮬레이터 대응
  gauss (기본): 체력·패턴 종류·순서 = 원본, 피해 크기 = 등급 평균, 힘 = Str_N x str_amount, 기믹 미모델링 → fidelity
  digits (v4 F8): 피해 = 패턴 자릿수 + 몬스터 힘 자릿수의 균등 정수, 플레이어가 상자 안 성냥을 옮겨 값을 바꿈
                 → fidelity_digits (기믹이 없는 몬스터는 exact)
  digits + gimmicks=on (v4 F9): 패시브·패턴 효과·사용 조건을 선언형 사양(sim, 패턴 effects/condition)으로 옮겨 실행
                 → fidelity_gimmicks = 기믹별 충실도 중 가장 낮은 값, gimmick_report 에 기믹별 판정과 사유
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import re
import sys
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
DEFAULT_MON = os.path.join(REPO, "Assets", "Data", "Json", "monsters")
DEFAULT_PAT = os.path.join(REPO, "Assets", "Data", "Json", "patterns")
DEFAULT_OUT = os.path.join(HERE, "monster_table.json")

RX_SINGLE = re.compile(r"^(\d+)_Single$")
RX_MULTI = re.compile(r"^(\d+)_Multi_(\d+)$")
RX_STR = re.compile(r"^Str_(-?\d+)$")


def load_dir(path):
    out = []
    for p in sorted(glob.glob(os.path.join(path, "*.json"))):
        with open(p, encoding="utf-8-sig") as fp:
            d = json.load(fp)
        d["_file"] = os.path.basename(p)
        out.append(d)
    return out


def source_hash(mons, pats_list):
    """원본 몬스터·패턴 내용의 해시 (v4.2 Q47: monster_table.json 이 오래됐는지 판정). 파일 이름 순서로 정규화."""
    import hashlib
    blob = json.dumps([sorted(mons, key=lambda d: d.get("_file", "")), sorted(pats_list, key=lambda d: d.get("_file", ""))],
                      sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha1(blob.encode("utf-8")).hexdigest()[:16]


def stale_warning(table_path, mon_dir=DEFAULT_MON, pat_dir=DEFAULT_PAT):
    """monster_table.json 이 현재 원본과 다르면 경고 문구, 같거나 판정할 수 없으면 None (Q47)."""
    try:
        with open(table_path, encoding="utf-8-sig") as fp:
            recorded = json.load(fp).get("source_hash")
        if not recorded or not os.path.isdir(mon_dir):
            return None
        now = source_hash(load_dir(mon_dir), load_dir(pat_dir))
    except (OSError, ValueError):
        return None
    if now != recorded:
        return (f"몬스터 테이블이 오래됨: {os.path.basename(table_path)} 이후 원본 몬스터·패턴 JSON 이 바뀌었습니다 — "
                "`python import_monsters.py` 로 다시 만드세요")
    return None


def build_table(mons, pats_list):
    """원본 몬스터·패턴 dict 목록(각 항목에 "_file") → monster_table.json 형식 dict (파일을 읽지 않음)."""
    pats = {p["id"]: p for p in pats_list}
    out = [convert(m, pats) for m in mons]
    users = {}
    for m in out:
        for p in m["patterns"]:
            if p.get("source") == "pattern":
                if m["id"] not in users.setdefault(p["key"], []):
                    users[p["key"]].append(m["id"])
    return {"version": 2, "generated_at": datetime.now().isoformat(timespec="seconds"),
            "source": "Assets/Data/Json/monsters + patterns (import_monsters.py)",
            "source_hash": source_hash(mons, pats_list),
            "damage_model_supported": ["gauss", "digits"], "gimmicks_supported": True, "ambiguous_rules": AMBIGUOUS,
            "counts": {"monsters": len(mons), "patterns": len(pats)}, "pattern_users": users, "monsters": out}


def unlinked_report(data):
    """원본 연결(src)이 없는 몬스터·패턴 필드 목록."""
    rows = []
    for m in data["monsters"]:
        for f in ("hp", "strength"):
            if f not in m.get("src", {}):
                rows.append((m["id"], f, "원본에 필드 없음"))
        for k, p in enumerate(m["patterns"]):
            if not p.get("src"):
                why = "무행동/효과 전용 패턴 — 숫자 토큰 없음" if p.get("kind") != "attack" or p.get("source") != "generic" else "토큰 없음"
                rows.append((m["id"], f"patterns[{k}] {p['key']}", why))
    return rows


def tier_of(enc):
    g, d = enc.get("grade"), enc.get("difficulty")
    if g == "normal":
        return "easy" if d == "easy" else "normal"
    return g


def resolve_pattern(key, patterns, warnings):
    k = key.strip()
    m = RX_SINGLE.match(k)
    if m:
        return {"key": k, "kind": "attack", "multi": False, "dmg_digits": int(m.group(1)), "hit_digits": None,
                "str_units": 0, "source": "generic", "gimmicks": []}
    m = RX_MULTI.match(k)
    if m:
        return {"key": k, "kind": "attack", "multi": True, "dmg_digits": int(m.group(1)),
                "hit_digits": int(m.group(2)), "str_units": 0, "source": "generic", "gimmicks": []}
    m = RX_STR.match(k)
    if m:
        return {"key": k, "kind": "str", "multi": False, "dmg_digits": None, "hit_digits": None,
                "str_units": int(m.group(1)), "source": "generic", "gimmicks": []}
    p = patterns.get(k)
    if p is None:
        warnings.append(f"패턴 '{k}' 를 찾을 수 없어 2_Single 로 대체")
        return {"key": k, "kind": "attack", "multi": False, "dmg_digits": 2, "hit_digits": None, "str_units": 0,
                "source": "fallback", "gimmicks": ["패턴 없음 → 2_Single"]}
    att = p.get("attack")
    gimmicks = [f"{(e.get('trigger') or {}).get('event', '?')}:{e.get('operation', '?')}" for e in p.get("effects") or []]
    avail = p.get("availability") or {}
    if avail.get("condition"):
        gimmicks.append("사용 조건(condition) — 항상 사용 가능으로 근사")
    rec = {"key": k, "source": "pattern", "max_uses": avail.get("maxUsesPerBattle"), "gimmicks": gimmicks,
           "note": p.get("designerNote", ""), "_file": p.get("_file")}
    # v4 F9: 기믹 실행용 정규화 (digits + gimmicks=on 에서만 쓰임)
    effs = [norm_effect(e) for e in p.get("effects") or []]
    if effs:
        rec["effects"] = effs
    cond = norm_condition(avail.get("condition"))
    if cond:
        rec["condition"] = cond
    md = p.get("metadata") or {}
    if md.get("selfDestruct"):
        rec["self_destruct"] = True
    heal = next((e for e in effs if e["op"] == "heal" and e.get("target") != "player"), None)
    if heal and md.get("editableHeal"):
        rec["heal"] = {"editable": True, "expr": heal.get("expr"), "amount": heal.get("amount")}
    if not att:
        # 공격이 없는 패턴: 효과만 있으면 기믹, 아무것도 없으면 무행동
        str_units = 0
        for e in p.get("effects") or []:
            if (e.get("target") or {}).get("stat") == "strength" and isinstance(e.get("amount"), (int, float)):
                str_units += int(e["amount"])
        if str_units:
            rec.update({"kind": "str", "multi": False, "dmg_digits": None, "hit_digits": None, "str_units": str_units})
        else:
            rec.update({"kind": "skip", "multi": False, "dmg_digits": None, "hit_digits": None, "str_units": 0})
        return rec
    dmg = att.get("damage") or {}
    hits = att.get("hits") or {}
    multi = not (hits.get("fixed") == 1) if hits else False
    if dmg.get("initialValue") is not None:
        gimmicks.append(f"피해 초기값 표현식 {json.dumps(dmg['initialValue'], ensure_ascii=False)}")
        iv = dmg["initialValue"]
        rec["dynamic"] = iv.get("expression") if isinstance(iv, dict) else iv
    if dmg.get("editable") is False:
        rec["dmg_editable"] = False
    rec.update({"kind": "attack", "multi": bool(multi), "dmg_digits": dmg.get("digits"),
                "hit_digits": hits.get("digits") if multi else None, "str_units": 0})
    return rec


def norm_effect(e):
    """원본 패턴 효과 → 시뮬 효과 {op, target, type, amount|expr, timing, duration, repeat, mode, hits, label}."""
    tg = e.get("target") or {}
    out = {"op": e.get("operation"), "target": tg.get("actor") or tg.get("key") or "self",
           "timing": "next_turn" if (e.get("trigger") or {}).get("event") == "next_turn" else "immediate"}
    if e.get("type") is not None:
        out["type"] = e["type"]
    a = e.get("amount")
    if isinstance(a, dict):
        out["expr"] = a.get("expression")
    elif a is not None:
        out["amount"] = a
    d = e.get("duration")
    if isinstance(d, dict) and d.get("turns") is not None:
        out["duration"] = int(d["turns"])
    for k in ("repeat", "hitCount"):
        if e.get(k) is not None:
            out["repeat" if k == "repeat" else "hits"] = int(e[k])
    if e.get("mode"):
        out["mode"] = e["mode"]
    return out


def norm_condition(c):
    """availability.condition → 평가기 문자열 ("hprate<=0.4", "HPRate<=0.5 && Phase==1")."""
    if not c:
        return None
    if isinstance(c, str):
        return c
    if c.get("expression"):
        return c["expression"]
    cm = c.get("comparison")
    if cm:
        left = (cm.get("left") or {}).get("variable") or (cm.get("left") or {}).get("value")
        right = cm.get("right")
        if isinstance(right, dict):
            right = right.get("variable") or right.get("value")
        return f"{left}{cm.get('operator', '==')}{right}"
    return None


# 기믹별 시뮬 사양과 충실도 (v4 F9.3, 사용자 확인 Q24·Q25). tier: GA 상태형 / GB 구조형 / GC 의미 확인
def passive_specs(mon):
    out = []
    for pz in mon.get("passives") or []:
        op = pz.get("operation") or pz.get("type")
        fn = mon.get("_file")
        if op == "countdown":
            box, oz = pz.get("box") or {}, pz.get("onZero") or {}
            out.append({"kind": "countdown", "init": box.get("initialValue", 3), "min": box.get("minimum", 0),
                        "max": box.get("maximum", 9), "editable": box.get("editable", True),
                        "amount": (pz.get("decrease") or {}).get("amount", 1),
                        "on_zero": "escape" if oz.get("operation") == "end_battle" else "pattern",
                        "pattern": oz.get("pattern"), "tier": "GA",
                        "fidelity": "exact" if oz.get("operation") == "end_battle" else "approx",
                        "reason": ("특수 상자 값이 매 턴 1 감소, 0 이면 도주(승리와 같은 종료, 보상 없음 — 사용자 확인 Q24)"
                                   if oz.get("operation") == "end_battle" else
                                   "0 이면 지정 패턴 실행. 패턴 조건 heart_queen_box 는 게임 평가기에 없는 변수(항상 0) — "
                                   "시뮬은 카운트다운 값으로 해석(불일치 보고)"),
                        "src": {"init": {"kind": "monster", "file": fn, "path": ["passives", len(out), "box", "initialValue"],
                                         "transform": "identity"}}})
        elif op == "lock_random_player_matches":
            out.append({"kind": "lock_matches", "timing": pz.get("timing", "turn_start"), "count": pz.get("count", 1),
                        "tier": "GB", "fidelity": "exact",
                        "reason": "플레이어 기본 피해 상자의 성냥을 무작위로 잠금(tag=lock) — 잠긴 성냥은 이동 불가"})
        elif op == "aimed_shot":
            mult = pz.get("multiplier", 1)
            out.append({"kind": "aimed_shot", "multiplier": mult, "tier": "GB", "fidelity": "exact",
                        "reason": "매 턴 0~9 숫자, 플레이어 상자(피해·타수·디버프)에 있으면 몬스터 피해 × 배수"
                        + (" (배수 1 → 효과 없음, 게임과 같음)" if mult <= 1 else ""),
                        "src": {"multiplier": {"kind": "monster", "file": fn, "path": ["passives", len(out), "multiplier"],
                                               "transform": "identity"}}})
        elif op == "add_formula_decoy_digits":
            out.append({"kind": "decoy", "count": pz.get("count", 1), "tier": "GC", "fidelity": "approx",
                        "reason": "사용자 결정(Q25): 마술사 데코이 기믹은 반영하지 않음 — 몬스터 상자에 가짜 숫자가 없는 것으로 계산"})
        elif op == "limit_incoming_damage":
            until = pz.get("until")
            ut = None
            if until:
                ut = (until.get("comparison") or {}).get("right")
            out.append({"kind": "cap_per_hit", "value": pz.get("maximum"), "until_taken": ut, "tier": "GA",
                        "fidelity": "exact", "reason": "ApplyDamage: 1타 상한 → 방어막 → 체력" + (
                            f", 누적 {ut} 이상이면 해제 패턴 사용 가능" if ut else ""),
                        "src": {"value": {"kind": "monster", "file": fn, "path": ["passives", len(out), "maximum"],
                                          "transform": "identity"}}})
        elif op == "require_formula_condition":
            c = pz.get("configuration") or {}
            if c.get("Type") == "DigitCount":
                out.append({"kind": "formula_condition", "type": "DigitCount", "value_min": c.get("ValueMin", 0),
                            "value_max": c.get("ValueMax", 9), "count_min": c.get("CountMin", 0),
                            "count_max": c.get("CountMax", 9), "count_editable": c.get("CountEditable", False),
                            "tier": "GC", "fidelity": "exact",
                            "reason": "사용자 규칙(Q25): [숫자 V] × [개수 C] 상자, 플레이어 상자(피해·타수·디버프)의 V 개수가 C 와 "
                                      "같아야 피해. C 상자(1자리)는 성냥으로 편집 가능 — 코드 그대로 구현"})
            else:
                out.append({"kind": "formula_condition", "type": "Compare", "value_min": c.get("ValueMin", 10),
                            "value_max": c.get("ValueMax", 99), "operators": c.get("Operators") or ["<", ">"],
                            "tier": "GC", "fidelity": "exact",
                            "reason": "사용자 규칙(Q25): 턴 시작 시 [부등호][10~99] 제시, 플레이어 기본 피해(1타 공식 값)가 "
                                      "만족하지 않으면 피해 0 — 코드 그대로 구현"})
        elif op == "lock_box":
            tg = (pz.get("target") or {}).get("formula")
            out.append({"kind": "lock_monster_damage" if tg == "monster.damage" else "player_immovable",
                        "tier": "GB", "fidelity": "exact", "reason": f"{tg} 상자 편집 불가 (k = 0)"})
        elif op == "set_match_mobility":
            who = (pz.get("target") or {}).get("actor")
            if not pz.get("movable", True):
                out.append({"kind": "player_immovable" if who == "player" else "lock_monster_damage", "tier": "GB",
                            "fidelity": "exact", "reason": f"{who} 성냥 이동 불가 (k = 0)"})
        elif op == "react_to_box_edits":
            sel, re_ = pz.get("selection") or {}, pz.get("reaction") or {}
            out.append({"kind": "reactive_boxes", "boxes": pz.get("boxes") or [], "group": sel.get("groupSize", 1),
                        "per_group": sel.get("countPerGroup", 1), "strength": re_.get("strength", 1),
                        "once": re_.get("oncePerBox", True), "tier": "GB", "fidelity": "approx",
                        "reason": "반응 상자를 편집하면 힘 +1 (상자별 1회). 배분 정책은 힘 증가의 기대 비용을 벌점으로 근사"})
        elif op == "accumulate_lock_debuff":
            out.append({"kind": "moves_decay", "per_turn": 1, "tier": "GC", "fidelity": "approx",
                        "reason": "사용자 규칙(Q25): 잠금 디버프 대신 '매 턴 플레이어 이동 횟수 1 씩 감소'로 반영 "
                                  "(턴 t 의 이동 한도 = 기본 − (t−1), 0 하한)"})
        elif op == "lifesteal":
            out.append({"kind": "lifesteal", "rate": pz.get("ratio", 0), "tier": "GA", "fidelity": "exact",
                        "reason": "공격 후 floor(준 피해 × 비율) 회복",
                        "src": {"rate": {"kind": "monster", "file": fn, "path": ["passives", len(out), "ratio"],
                                         "transform": "identity"}}})
        elif op == "assign_hidden_digits":
            out.append({"kind": "hidden_digits", "count": pz.get("count", 2), "ratio": pz.get("damageRatioPerFound", 0.5),
                        "tier": "GB", "fidelity": "approx",
                        "reason": "서로 다른 숨은 숫자 2개, 포함 개수 × 비율(최대 1)만큼 피해. 발견 전 배분은 "
                                  "'포함될 기대 개수'로 판단(정책 근사)"})
        elif op == "split_player_boxes":
            out.append({"kind": "split_player", "tier": "GB", "fidelity": "exact",
                        "reason": "플레이어 상자 항상 분할 — 자릿수 사이 이동 불가 (사용자 규칙과 같음)"})
        elif op == "zero_player_special_digits":
            out.append({"kind": "zero_special_digits", "tier": "GB", "fidelity": "exact",
                        "reason": "별 상자에 든 숫자를 플레이어 기본 피해에서 0 으로 보고 비율만큼 피해 (BattleController 그대로)"})
        elif op == "react_to_zero_damage":
            out.append({"kind": "zero_damage_str_down", "amount": (pz.get("reaction") or {}).get("amount", -1),
                        "tier": "GA", "fidelity": "exact", "reason": "몬스터가 입힌 피해가 0 이면 힘 감소"})
        elif op == "once_per_battle_strength_reset":
            out.append({"kind": "strength_reset", "lock_all": pz.get("lockAllPlayerMatches", False), "tier": "GB",
                        "fidelity": "approx",
                        "reason": "플레이어가 1회 힘 초기화(이후 플레이어 성냥 전체 잠금). 사용 시점은 정책: 힘이 기본보다 "
                                  "player.policy.reset_at_strength 이상 높으면 사용"})
        elif op == "require_player_suffix":
            out.append({"kind": "suffix", "digits": pz.get("digits", 2), "tier": "GC", "fidelity": "exact",
                        "reason": "사용자 규칙(Q25): 1페이즈에 고래 상자 2자리 제시, 기본 피해 끝 2자리가 같을 때만 피해"})
        elif op == "phase_transition":
            ph = pz.get("phaseTwo") or {}
            out.append({"kind": "phase_two", "hp_rate": (pz.get("condition") or {}).get("healthRateAtMost", 0.5),
                        "split_all": ph.get("splitAllBoxes", False), "move_limit": ph.get("moveLimit"),
                        "tier": "GC", "fidelity": "exact",
                        "reason": "체력 ≤ floor(기본 × 비율) 이면 2페이즈: 모든 상자 분할, 이동 한도 덮어쓰기 (사용자 규칙과 같음)"})
        else:
            out.append({"kind": "unknown", "op": op, "tier": "GC", "fidelity": "none",
                        "reason": f"알 수 없는 패시브 {op} — 반영하지 않음"})
    return out


PATTERN_OP_FIDELITY = {
    "add_status": ("GA", "exact", "상태 추가 (힘·기절·출혈·중독·스택·방어막·디버프 상자·상자 잠금)"),
    "set_status": ("GA", "exact", "상태 설정"),
    "remove_status": ("GA", "exact", "상태 제거 (방어막이면 1타 상한도 해제)"),
    "multiply_stat": ("GA", "exact", "상태 곱"),
    "heal": ("GA", "exact", "회복 (편집 가능 회복 상자는 배분 대상)"),
    "deal_damage": ("GA", "exact", "직접 피해 (표현식, 환상 피해 감소 없음 — 게임과 같음)"),
    "split_box": ("GB", "approx", "다음 턴 상자 분할 — 지속시간이 없는 효과도 1턴으로 근사"),
    "lock_box": ("GB", "exact", "다음 턴 상자 잠금 (이동 불가)"),
    "create_formula_box": ("GA", "exact", "특수 상자 생성·숫자 추가"),
    "librarian_skill": ("GB", "exact", "플레이어 공식의 숫자(피해·타수 상자) 중 하나를 골라 직접 피해"),
}
FID_ORDER = {"exact": 2, "approx": 1, "none": 0}


def gimmick_report(mon_specs, pats):
    rows = [{"gimmick": s["kind"], "tier": s["tier"], "fidelity": s["fidelity"], "reason": s["reason"]} for s in mon_specs]
    seen = set()
    for p in pats:
        for e in p.get("effects") or []:
            k = (e["op"], e.get("type"))
            if k in seen:
                continue
            seen.add(k)
            t, f, why = PATTERN_OP_FIDELITY.get(e["op"], ("GC", "none", f"알 수 없는 패턴 효과 {e['op']}"))
            rows.append({"gimmick": f"{p['key']}:{e['op']}" + (f"({e.get('type')})" if e.get("type") else ""),
                         "tier": t, "fidelity": f, "reason": why})
        if p.get("condition") and ("cond", p["key"]) not in seen:
            seen.add(("cond", p["key"]))
            hq = "heart_queen_box" in p["condition"]
            rows.append({"gimmick": f"{p['key']}:사용 조건 {p['condition']}", "tier": "GA",
                         "fidelity": "approx" if hq else "exact",
                         "reason": "게임 평가기에 없는 변수 → 시뮬은 카운트다운 값으로 해석" if hq else "패턴 사용 조건 (표현식 평가기)"})
        if p.get("dynamic") and ("dyn", p["key"]) not in seen:
            seen.add(("dyn", p["key"]))
            rows.append({"gimmick": f"{p['key']}:동적 피해 {p['dynamic']}", "tier": "GA", "fidelity": "exact",
                         "reason": "피해 = 표현식 값, 자릿수 = 패턴 값"})
    return rows


def convert(mon, patterns):
    enc = mon.get("encounter") or {}
    warnings = []
    pats = [resolve_pattern(k, patterns, warnings) for k in (mon.get("ai") or {}).get("patterns") or []]
    if not pats:
        warnings.append("패턴 없음 → 2_Single")
        pats = [resolve_pattern("2_Single", patterns, warnings)]
    passives = [p.get("type") or p.get("operation") or "?" for p in mon.get("passives") or []]
    gimmicks = passives + sorted({g for p in pats for g in p["gimmicks"]})
    fidelity = "none" if gimmicks else "approx"
    specs = passive_specs(mon)
    rep_rows = gimmick_report(specs, pats)
    fid_digits = "exact" if not gimmicks else "none"
    fid_gim = min((r["fidelity"] for r in rep_rows), key=lambda f: FID_ORDER[f], default="exact")
    notes = ["체력·패턴 종류·순서는 원본, 피해 크기는 등급 평균(gauss)"]
    if gimmicks:
        notes.append("미모델링 기믹: " + ", ".join(gimmicks))
    fn = mon.get("_file", mon["id"] + ".json")
    src = {"hp": {"kind": "monster", "file": fn, "path": ["stats", "health"], "transform": "identity"}}
    if "strength" in (mon.get("stats") or {}):
        src["strength"] = {"kind": "monster", "file": fn, "path": ["stats", "strength"], "transform": "identity"}
    keys = (mon.get("ai") or {}).get("patterns") or []
    for k, p in enumerate(pats):
        if k >= len(keys):
            break
        if p["source"] == "generic":   # 토큰은 몬스터 파일의 ai.patterns[k] 문자열 안에 있다
            parts = {"digits": "dmg_digits", "hits": "hit_digits"} if p["kind"] == "attack" else {"n": "str_units"}
            p["src"] = {part: {"kind": "monster", "file": fn, "path": ["ai", "patterns", k], "transform": "token_digits",
                               "part": part} for part, field in parts.items() if p.get(field) is not None}
        elif p["source"] == "pattern" and p.get("_file"):
            p["src"] = {}
            if p.get("dmg_digits") is not None:
                p["src"]["digits"] = {"kind": "pattern", "file": p["_file"], "path": ["attack", "damage", "digits"],
                                      "transform": "identity"}
            if p.get("hit_digits") is not None:
                p["src"]["hits"] = {"kind": "pattern", "file": p["_file"], "path": ["attack", "hits", "digits"],
                                    "transform": "identity"}
    return {
        "src": src,
        "id": mon["id"], "name": mon.get("designerName", mon["id"]), "enabled": mon.get("enabled", True),
        "act": enc.get("act"), "tier": tier_of(enc), "grade": enc.get("grade"), "difficulty": enc.get("difficulty"),
        "hp": (mon.get("stats") or {}).get("health"), "strength": (mon.get("stats") or {}).get("strength", 0),
        "ai": (mon.get("ai") or {}).get("mode", "static"),
        "patterns": [{k: v for k, v in p.items() if k not in ("gimmicks", "_file")} for p in pats],
        "gimmicks": gimmicks, "fidelity": fidelity, "notes": " / ".join(notes), "warnings": warnings,
        # v4: 피해 모델별 충실도와 기믹 사양
        "fidelity_digits": fid_digits, "fidelity_gimmicks": fid_gim, "sim": specs, "gimmick_report": rep_rows,
        "gimmick_tier": max((r["tier"] for r in rep_rows), default=""),
    }


AMBIGUOUS = [
    "피해 크기: 원본은 패턴의 '자릿수'(예: 2_Single = 2자리 → 10~99)로 정해지지만, 플레이어가 성냥개비로 "
    "몬스터 숫자를 편집해 줄인다. 시뮬레이터의 방어 모델(이동 1회당 비율 감소)과 규모가 맞지 않아 "
    "damage_model=digits 는 방어 모델 재설계가 함께 필요하다.",
    "연타 타수: '{d}_Multi_{h}' 의 타수 자릿수 h=1 이면 1~9타인지, 실제 분포가 어떤지 확인 필요.",
    "힘: 기획 문서상 몬스터 힘은 다음 공격 피해의 '자릿수'를 늘린다 (Str_1 → 2자리가 3자리). "
    "v1 시뮬레이터는 '힘 1 = 1타당 피해 +str_amount' 로 근사한다.",
    "플레이어 힘: 기획 문서상 기본 피해 상자 자릿수 +1 (PlanningArchitecture.md). 환상의 힘 효과(종이학, 머그잔, 황소자리) 해석도 같이 바뀐다.",
    "패턴 사용 조건(availability.condition, 예: 체력 비율 ≤ 0.4)과 몬스터 패시브는 시뮬레이터가 다루지 않는다.",
    "쉬운(easy) 몬스터가 없는 막은 일반(normal) 몬스터로 대체한다.",
]


def main(argv=None):
    ap = argparse.ArgumentParser(description="원본 몬스터·패턴 JSON → monster_table.json")
    ap.add_argument("--monsters", default=DEFAULT_MON)
    ap.add_argument("--patterns", default=DEFAULT_PAT)
    ap.add_argument("--out", default=DEFAULT_OUT)
    ap.add_argument("--report", action="store_true", help="매핑 초안과 모호한 규칙 출력")
    ap.add_argument("--report-unlinked", action="store_true", help="원본 연결(src)이 없는 필드 출력")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args(argv)
    mons = load_dir(args.monsters)
    pats = {p["id"]: p for p in load_dir(args.patterns)}
    data = build_table(mons, list(pats.values()))
    out = data["monsters"]
    with open(args.out, "w", encoding="utf-8") as fp:
        json.dump(data, fp, ensure_ascii=False, indent=2)
    if not args.quiet:
        from collections import Counter
        c = Counter(m["fidelity"] for m in out)
        print(f"{args.out}: 몬스터 {len(mons)}종, 패턴 파일 {len(pats)}종 (approx {c['approx']}, none {c['none']})")
    if args.report_unlinked:
        rows = unlinked_report(data)
        print(f"원본 연결이 없는 몬스터·패턴 필드 {len(rows)}개:")
        for mid, f, why in rows:
            print(f"  {mid:<26} {f:<34} — {why}")
    if args.report:
        print("\n막·등급별 몬스터:")
        by = {}
        for m in out:
            by.setdefault((m["act"], m["tier"]), []).append(m)
        for k in sorted(by, key=lambda k: (k[0], ["easy", "normal", "elite", "boss"].index(k[1]))):
            print(f"  {k[0]}막 {k[1]:<6}: " + ", ".join(f"{m['name']}({m['hp']}, {m['ai']}, {m['fidelity']})" for m in by[k]))
        print("\n기믹이 있는 몬스터:")
        for m in out:
            if m["gimmicks"]:
                print(f"  {m['name']:<8} {', '.join(m['gimmicks'])}")
        warns = [(m["name"], w) for m in out for w in m["warnings"]]
        if warns:
            print("\n경고:")
            for n, w in warns:
                print(f"  {n}: {w}")
        print("\n결정이 필요한 규칙 (명세 v2 §11 Q1):")
        for i, a in enumerate(AMBIGUOUS, 1):
            print(f"  {i}. {a}")
    return data


if __name__ == "__main__":
    main()
