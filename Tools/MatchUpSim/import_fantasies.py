#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
원본 환상 JSON(Assets/Data/Json/fantasies/*.json) → 시뮬레이터용 fantasy_effects.json

변환 규칙
---------
1) 원본 효과 하나하나를 (trigger.event, target, operation, mode, amount, condition) 패턴으로
   시뮬레이터 효과 타입에 매핑한다 (RULES). 환상 ID 로 분기하지 않는다.
2) 패턴으로 판단할 수 없는 환상(설명과 데이터가 어긋나거나, 시뮬레이터 추상화로는 의미가
   달라지는 경우)은 fantasy_effects.overrides.json 에 사람이 직접 근사를 적는다.
   overrides 항목이 있으면 자동 매핑 결과를 통째로 대체한다.
3) 환상의 fidelity:
   - 모든 원본 효과가 exact 로 매핑되면 exact
   - 하나라도 approx 면 approx
   - 매핑된 효과가 하나도 없으면 none,  일부만 매핑되면 approx ("일부 미모델링" 메모)

  python import_fantasies.py                 # 기본 경로로 생성
  python import_fantasies.py --src ../../Assets/Data/Json/fantasies --out fantasy_effects.json
  python import_fantasies.py --template      # 69종 전부 fidelity none 인 템플릿 생성
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
DEFAULT_SRC = os.path.normpath(os.path.join(HERE, "..", "..", "Assets", "Data", "Json", "fantasies"))
DEFAULT_OUT = os.path.join(HERE, "fantasy_effects.json")
DEFAULT_OVERRIDES = os.path.join(HERE, "fantasy_effects.overrides.json")


def _num(a):
    return float(a) if isinstance(a, (int, float)) else None


def _expr(a):
    return a.get("expression") if isinstance(a, dict) else None


def _cmp(cond):
    """condition.comparison → (left_var, op, right_value_or_var)"""
    c = (cond or {}).get("comparison")
    if not c:
        return None
    left = (c.get("left") or {}).get("variable")
    right = c.get("right")
    right = right.get("variable") if isinstance(right, dict) else right
    return left, c.get("operator"), right


def _duration_first_turn(e):
    d = e.get("duration") or {}
    return d.get("turns") == 1


# 표현식 "(A+B)*k", "A*k", "A/k" → (변수 목록, 연산, k)
_EXPR_MUL = re.compile(r"^\(?([A-Za-z0-9_+]+)\)?\s*\*\s*([0-9.]+)$")
_EXPR_DIV = re.compile(r"^([A-Za-z0-9_]+)\s*/\s*([0-9.]+)$")
_EXPR_FLOORDIV = re.compile(r"^floor\(([A-Za-z0-9_]+)\s*/\s*([0-9.]+)\)\s*\*\s*([0-9.]+)$")

# 원본 표현식 변수 → 시뮬레이터 per 값
PER_VARS = {
    ("ExtraMatchCount", "EraserCount"): "items_held",
    ("ConsumableCount",): "items_held",
    ("ItemUseCount",): "items_used_battle",
    ("HP",): "hp",
    ("BattleDigit8Count",): "digit8",
    ("RemainingMoves",): "unused_moves",
    ("ConsecutiveDigitRunCount",): "consecutive_pairs",
}


def parse_expr(ex):
    m = _EXPR_FLOORDIV.match(ex)
    if m:
        return {"var": (m.group(1),), "div": float(m.group(2)), "mul": float(m.group(3))}
    m = _EXPR_MUL.match(ex)
    if m:
        return {"var": tuple(m.group(1).split("+")), "mul": float(m.group(2))}
    m = _EXPR_DIV.match(ex)
    if m:
        return {"var": (m.group(1),), "div": float(m.group(2))}
    if re.fullmatch(r"[A-Za-z0-9_]+", ex):
        return {"var": (ex,), "mul": 1.0}
    return None


def per_of(px):
    return PER_VARS.get(tuple(px["var"])) if px else None


# ---------------------------------------------------------------------------
# 원본 연결(src) — 시뮬 효과의 숫자 키가 원본 JSON 의 어느 값에서 왔는지 (명세 v2 §5.4)
#   field: amount | chance.percent | amount.expression
#   transform (원본→시뮬): identity | percent_div_100 | expr_mul | expr_div | pct_scale_gt1
# 매핑 규칙마다 명시적으로 단다. 달지 않은 숫자 키는 --report-unlinked 로 확인한다.
# ---------------------------------------------------------------------------
def SA(key):
    return {"field": "amount", "sim_key": key, "transform": "identity"}


def SC(key):
    return {"field": "chance.percent", "sim_key": key, "transform": "percent_div_100"}


def SX(key, transform):
    return {"field": "amount.expression", "sim_key": key, "transform": transform}


def SP(key):
    return {"field": "amount", "sim_key": key, "transform": "pct_scale_gt1"}


# ---------------------------------------------------------------------------
# 매핑 규칙: 원본 효과 1개 → ([시뮬 효과...], fidelity, 메모) 또는 None(매핑 불가)
# 시뮬 효과의 "_src" 는 convert() 가 파일·효과 인덱스를 채워 "src" 로 바꾼다.
# ---------------------------------------------------------------------------
def map_effect(e):
    ev = (e.get("trigger") or {}).get("event", "")
    tg = e.get("target") or {}
    op = e.get("operation", "")
    mode = e.get("mode", "")
    amt = e.get("amount")
    n = _num(amt)
    ex = _expr(amt)
    px = parse_expr(ex) if ex else None
    cmpc = _cmp(e.get("condition"))
    actor, stat = tg.get("actor"), tg.get("stat")
    key, system, prop, formula = tg.get("key"), tg.get("system"), tg.get("property"), tg.get("formula")
    chance = (e.get("chance") or {}).get("percent")

    # --- 장식/표시 전용
    if key == "cosmetic":
        return [], "exact", "장식 효과(전투 영향 없음)"
    # --- 획득 가능 여부 (조합/변환 전용 환상)
    if key == "availability" and op == "exclude":
        return [{"_available": False}], "exact", "보상/상점 풀에서 제외"
    # --- 조합
    if op == "combine_fantasies" and isinstance(e.get("options"), list):
        return [{"type": "combine_into", "from": list(e["options"])}], "exact", "재료 환상이 모두 모이면 조합"

    # --- 이동 횟수
    if system == "battle" and prop == "movement_limit" and op == "modify_value" and mode == "add" and n is not None:
        if ev == "turn_start":
            return [{"type": "moves_per_turn_add", "value": n, "_src": [SA("value")]}], "exact", ""
        if ev == "battle_start":
            return [{"type": "battle_start_moves", "value": n, "_src": [SA("value")]}], "approx", "전투 시작 시 이동 +N 을 첫 턴 임시 이동으로 해석"
    if system == "shop" and prop == "movement_limit" and mode == "add" and n is not None:
        return [{"type": "shop_moves_add", "value": n, "_src": [SA("value")]}], "exact", ""

    # --- 타수
    if formula == "player.hits" and op == "modify_value" and mode == "add":
        eff = {"type": "hits_add"}
        fid = "exact"
        notes = []
        if n is not None:
            eff["value"] = n
            eff["_src"] = [SA("value")]
        elif px and per_of(px) in ("items_held", "consecutive_pairs"):
            eff["per"] = per_of(px)
            if "div" in px:
                eff["divisor"] = px["div"]
                eff["_src"] = [SX("divisor", "expr_div")]
            fid = "approx"
            notes.append("상자 숫자는 시뮬레이터의 기본 피해/몬스터 1타 피해 숫자로 근사"
                         if eff["per"] == "consecutive_pairs" else "")
        else:
            return None
        if ev == "turn_even":
            eff["when"] = {"turn_mod": [2, 0]}
        elif _duration_first_turn(e) or ev == "turn_1":
            eff["when"] = {"turn_eq": 1}
        if cmpc and cmpc[0] == "player_base_damage_same_digits":
            eff["when"] = {"base_same_digits": bool(cmpc[2])}
            fid = "approx"
            notes.append("조건은 굴린 기본 피해로만 판정 (조건을 맞추려는 조작은 미모델링)")
        elif cmpc:
            return None
        return [eff], fid, " ".join(x for x in notes if x)

    # --- 내가 주는 피해
    if ev == "deal_damage" and actor == "monster" and op == "modify_value" and mode == "add" and n is not None:
        return [{"type": "dmg_flat", "value": n, "_src": [SA("value")]}], "exact", "타격당 피해 가산"
    if ev == "deal_damage" and actor == "player" and stat == "health" and mode == "add" and n is not None:
        return [{"type": "heal_on_deal", "value": n, "_src": [SA("value")]}], "exact", "타격당 회복"
    if ev == "turn_end" and key == "damage" and op == "modify_value" and mode == "add":
        eff = {"type": "end_turn_dmg"}
        fid = "exact"
        note = ""
        if n is not None:
            eff["value"] = n
            eff["_src"] = [SA("value")]
        elif px and per_of(px) in ("items_held", "items_used_battle", "hp", "digit8"):
            eff["value"] = px.get("mul", 1.0)
            eff["per"] = per_of(px)
            if "mul" in px:
                eff["_src"] = [SX("value", "expr_mul")]
            if eff["per"] == "digit8":
                fid, note = "approx", "8의 개수는 내 기본 피해와 몬스터 1타 피해 숫자만 셈"
        else:
            return None
        if cmpc:
            if cmpc[0] == "current_turn" and cmpc[1] == "==":
                eff["when"] = {"turn_eq": int(cmpc[2])}
            else:
                return None
        return [eff], fid, note
    if ev == "turn_end" and actor == "monster" and mode == "multiply" and n is not None:
        if cmpc and set(cmpc[::2]) == {"player_base_damage", "monster_base_damage"} and cmpc[1] == "==":
            return ([{"type": "dmg_final_mult", "value": n, "condition": "base_eq_monster_dmg", "_src": [SA("value")]}], "approx",
                    "기본 피해 비교는 시뮬레이터의 내 기본 피해 vs 몬스터 1타 피해. 맞추려는 조작은 미모델링")
        return None

    # --- 기본 피해 상자 변형
    if key == "player_number" and op == "digit_min" and n is not None:
        return ([{"type": "base_dmg_transform", "op": "digit_min", "value": n, "_src": [SA("value")]}], "approx",
                "내 기본 피해 상자 숫자에만 적용")
    if key == "monster_number" and op == "digit_max" and n is not None:
        return ([{"type": "monster_dmg_digit_max", "value": n, "_src": [SA("value")]}], "approx", "몬스터 1타 피해 숫자에만 적용")
    if key == "player_base_damage" and op == "set_first_digit" and n is not None:
        return ([{"type": "base_dmg_transform", "op": "first_digit", "value": n, "_src": [SA("value")]}], "approx",
                "힘 피해 상자는 시뮬레이터에 없음. 기본 피해 상자에만 적용")

    # --- 받는 피해
    if ev == "take_damage" and tg.get("value") == "incoming_damage" and op == "modify_value":
        if mode == "add" and n is not None and not cmpc:
            return [{"type": "dmg_taken_flat", "value": n, "_src": [SA("value")]}], "exact", "타격당 받는 피해 가감"
        if mode == "multiply" and n is not None:
            if not cmpc:
                return [{"type": "dmg_taken_mult", "value": n, "_src": [SA("value")]}], "exact", ""
            if cmpc[0] == "monster_base_damage" and cmpc[1] == ">=" and cmpc[2] == "player_base_damage":
                return ([{"type": "dmg_taken_mult", "value": n, "condition": "monster_dmg_ge_player_base",
                          "_src": [SA("value")]}],
                        "approx", "기본 피해 비교는 몬스터 1타 피해 vs 내 기본 피해 (시뮬레이터 단위)")
    if ev == "take_damage" and actor == "attacker" and op == "modify_value" and n is not None:
        if mode == "add":
            return [{"type": "reflect_on_hit", "value": n, "_src": [SA("value")]}], "exact", "피격(타격)마다 적에게 고정 피해"
        if mode == "multiply":
            pct = n / 100.0 if n > 1 else n
            return ([{"type": "reflect_on_hit", "pct": pct, "_src": [SP("pct")]}], "approx",
                    f"원본 amount {n:g} 를 반사 비율 {pct:g} 로 해석")
    if ev == "take_damage" and actor == "player" and stat == "health" and px and "div" in px and "mul" in px:
        if px["var"] == ("IncomingDamageAmount",):
            return [{"type": "heal_on_take", "per": px["div"], "value": px["mul"],
                     "_src": [SX("per", "expr_div"), SX("value", "expr_mul")]}], "exact", ""

    # --- 몬스터 힘
    if actor == "monster" and stat == "strength" and mode == "add" and n is not None:
        eff = {"type": "monster_str_add", "value": n, "_src": [SA("value")]}
        if _duration_first_turn(e) or ev == "turn_1":
            eff["when"] = {"turn_eq": 1}
        return [eff], "approx", "힘 1 = 1타당 피해 1 (시뮬레이터 단위)"
    if ev.startswith("turn_") and ev[5:].isdigit() and actor == "player" and stat == "strength" and n is not None:
        return ([{"type": "player_str_add", "value": n, "when": {"turn_eq": int(ev[5:])}, "_src": [SA("value")]}], "approx",
                "힘 1 = 1타당 피해 +1 (시뮬레이터 단위)")
    if ev == "enemy_strength_gain" and actor == "player" and stat == "strength":
        return [{"type": "mirror_enemy_str", "value": 1}], "approx", "적이 얻은 힘만큼 1타당 피해 증가"
    if system == "battle" and prop == "enemy_acts_first" and op == "enable":
        return [{"type": "enemy_acts_first", "value": 1}], "exact", ""

    # --- 소모품
    if ev == "battle_start" and key in ("eraser", "extra_match") and mode == "add" and n is not None:
        return [{"type": "battle_temp_items", "value": n, "_src": [SA("value")]}], "approx", "임시 소모품 = 이번 전투 한정 추가 이동"
    if ev == "acquire_item" and key == "item" and mode == "add" and n is not None:
        return [{"type": "item_gain_bonus", "value": n, "_src": [SA("value")]}], "exact", ""
    if ev == "use_item" and key == "last_used_item" and chance:
        return [{"type": "item_use_refund_chance", "value": chance / 100.0, "_src": [SC("value")]}], "exact", ""
    if system == "reward" and prop == "item_chance" and mode == "multiply" and n is not None:
        return [{"type": "item_drop_mult", "value": n, "_src": [SA("value")]}], "exact", ""

    # --- 회복
    if ev == "battle_end" and actor == "player" and stat == "health" and mode == "add" and n is not None:
        return [{"type": "heal_per_battle", "value": n, "_src": [SA("value")]}], "exact", ""
    if ev in ("on_acquire", "acquire") and actor == "player" and stat == "health" and mode == "add":
        if n is not None:
            return [{"type": "on_acquire_heal", "value": n, "_src": [SA("value")]}], "exact", ""
        if px and px["var"] == ("HP",):
            return [{"type": "on_acquire_heal", "pct": px["mul"], "_src": [SX("pct", "expr_mul")]}], "exact", ""
    if ev == "turn_end" and actor == "player" and stat == "health" and px and per_of(px) == "unused_moves":
        return ([{"type": "heal_per_unused_move", "value": px["mul"], "_src": [SX("value", "expr_mul")]}], "approx",
                "시뮬레이터는 처치 가능해지면 이동을 멈추므로 사실상 전투 마지막 턴에만 회복")
    if ev == "lethal_damage" and key == "battle_rewind":
        return ([{"type": "revive_once", "value": n or 1, **({"_src": [SA("value")]} if n is not None else {})}],
                "approx", "사망 시 전투 시작 상태로 되감고 다시 싸움")
    if ev == "rest" and actor == "player" and stat == "health" and mode == "multiply" and n is not None:
        return [{"type": "rest_heal_mult", "value": n, "_src": [SA("value")]}], "exact", ""
    if system == "rest" and prop == "use_count" and mode == "add" and n is not None:
        return [{"type": "rest_extra_uses", "value": n, "_src": [SA("value")]}], "exact", ""
    if key == "rest_fantasy_alternative" and op == "enable":
        return ([{"type": "rest_alt_fantasy", "grade": "white"}], "approx",
                "체력이 policy.rest_below_hp 이상이면 회복 대신 환상을 고름")

    # --- 상점
    if ev == "shop_enter" and actor == "player" and stat == "health" and mode == "add" and n is not None:
        return [{"type": "shop_enter_heal", "value": n, "_src": [SA("value")]}], "exact", ""
    if system == "shop" and prop == "price" and mode == "multiply" and n is not None:
        return [{"type": "shop_price_mult", "value": n, "_src": [SA("value")]}], "exact", ""

    # --- 환상 획득 관련
    if op == "duplicate_or_void_acquire":
        return ([{"type": "acquire_dup_or_void", "chance": (chance or 50) / 100.0,
                  **({"_src": [SC("chance")]} if chance else {})}], "exact",
                "복사본은 효과가 한 번 더 적용됨")
    if op == "replace_with_copy":
        return ([{"type": "on_acquire_copy_owned", "value": 1}], "approx",
                "보유 환상 중 무작위 1개의 복사본으로 바뀜 (시작 강제 포함이면 보유 환상이 없어 효과 없음)")
    if op == "copy_temporary" and ev == "battle_start":
        return [{"type": "battle_start_temp_copy", "value": 1}], "approx", "보유 환상 중 무작위 1개를 전투 동안 한 번 더 적용"

    return None


def convert(src_entry, overrides):
    fid = src_entry["id"]
    out = {
        "id": fid,
        "name": src_entry.get("designerName") or (src_entry.get("localization") or {}).get("name") or fid,
        "grade": src_entry["rarity"],
        "source_id": src_entry.get("sourceId"),
        "description": src_entry.get("designerNote", ""),
    }
    ov = overrides.get(fid)
    if ov is not None and "effects" in ov:
        # 효과까지 사람이 적은 항목: 자동 매핑을 통째로 대체
        out.update({k: v for k, v in ov.items() if not k.startswith("_") and k != "notes_extra"})
        out["mapping"] = "override"
        out.setdefault("available", True)
        if ov.get("notes_extra"):
            out["notes"] = " / ".join(x for x in (out.get("notes", ""), ov["notes_extra"]) if x)
        return out

    effects, fids, notes, unmapped = [], [], [], 0
    available = True
    for j, e in enumerate(src_entry.get("effects", [])):
        m = map_effect(e)
        if m is None:
            unmapped += 1
            continue
        effs, f, note = m
        for x in effs:
            if "_available" in x:
                available = x["_available"]
            else:
                srcs = x.pop("_src", None)
                if srcs:
                    full = [{"file": src_entry.get("_file", fid + ".json"), "effect": j, **sx} for sx in srcs]
                    x["src"] = full[0] if len(full) == 1 else full
                effects.append(x)
        fids.append(f)
        if note:
            notes.append(note)
    if not fids or (not effects and unmapped):
        fidelity = "none"
        notes.insert(0, "시뮬레이터 효과 타입으로 표현할 수 없음")
    elif unmapped:
        fidelity = "approx"
        notes.insert(0, f"원본 효과 {unmapped}개 미모델링")
    elif "approx" in fids:
        fidelity = "approx"
    else:
        fidelity = "exact"
    if ov and ov.get("notes_extra"):
        notes.append(ov["notes_extra"])
    out.update({"fidelity": fidelity, "effects": effects, "notes": " / ".join(dict.fromkeys(notes)),
                "available": available, "mapping": "auto+note" if ov else "auto"})
    return out


def annotate_combos(out_list):
    """조합 재료 환상에 '어느 조합의 재료인지' 메모를 붙인다 (데이터 기반)."""
    by_id = {x["id"]: x for x in out_list}
    for x in out_list:
        for ef in x["effects"]:
            if ef["type"] == "combine_into":
                for part in ef["from"]:
                    if part in by_id:
                        msg = f"{x['name']}({x['id']}) 조합 재료 — 조합은 모델링됨"
                        by_id[part]["notes"] = " / ".join(n for n in (by_id[part]["notes"], msg) if n)


# v4 F8.5: digits 모델 기준 충실도 재분류. keep = gauss 판정(fidelity)을 그대로 쓴다 (전투 밖 효과 등)
DIGITS_FIDELITY = {
    "dmg_taken_flat": ("exact", "받는 피해 고정 감소: 타격마다 적용, 0 하한"),
    "dmg_taken_mult": ("exact", "받는 피해 배율 (조건은 편집 후 값 D' ≥ P' 로 판정)"),
    "def_cut_add": ("exact", "받는 피해 비율 감소 (타격마다)"),
    "dmg_mult_add": ("exact", "피해 배율"),
    "dmg_flat": ("exact", "1타 피해 +값"),
    "dmg_final_mult": ("exact", "최종 배율 (조건 P' = D' 를 배분 정책이 평가)"),
    "hits_add": ("exact", "타수 증가 (연속 쌍은 최종 값 P', D' 로 판정)"),
    "end_turn_dmg": ("exact", "턴 종료 피해 (8 의 개수는 최종 값 P', D' 로 셈)"),
    "player_str_add": ("exact", "플레이어 힘 = 기본 피해 상자 자릿수 +1 (게임 규칙)"),
    "monster_str_add": ("exact", "몬스터 힘 = 피해 자릿수 증감 (게임 규칙)"),
    "mirror_enemy_str": ("exact", "적이 얻은 힘만큼 내 힘(자릿수)"),
    "str_block": ("exact", "몬스터 힘 증가 막기"),
    "enemy_acts_first": ("exact", "몬스터 선공"),
    "moves_per_turn_add": ("exact", "이동 한도 +N (모든 상자 공유)"),
    "battle_start_moves": ("exact", "첫 턴 이동 +N"),
    "heal_on_deal": ("exact", "타격마다 회복"),
    "heal_on_take": ("exact", "피격 시 회복"),
    "base_dmg_transform": ("approx", "기본 피해 상자 변형: 게임은 턴 시작(Player_Base_Damage)과 공식 구성(Player_Number) 두 시점이 있으나 "
                                     "시뮬레이터는 굴림 직후 1회 적용 후 배분"),
    "monster_dmg_digit_max": ("approx", "몬스터 피해 숫자 상한: 굴림 직후 적용 (게임은 공식 구성 시점, Monster_Number)"),
    "combo_same_dmg_stack": ("approx", "같은 피해 누적: 배분 정책이 '같은 피해 맞추기'를 노리지 않음"),
    "carry_unused_moves": ("approx", "남은 이동 이월: 유효 이동 수 K < 한도 M 일 때 남은 이동을 넘김(정책 근사)"),
    "heal_per_unused_move": ("approx", "남은 이동당 회복: 남은 이동 = M − 사용 이동 (정책 근사)"),
    "battle_temp_items": ("approx", "임시 소모품 = 이번 전투 한정 추가 이동 (성냥 추가·제거 아이템은 범위 밖, Q20)"),
    "item_use_refund_chance": ("approx", "소모품 = 추가 이동으로 근사"),
    "monster_skip_chance_add": ("approx", "몬스터 행동 건너뛰기 확률"),
}


def mark_surrogate(e):
    """v4.1 F10.2: 값 필드가 숫자 하나이고 조건(when/per/condition/chance)이 없는 효과 = 한계효과 근사 후보."""
    from sim_service import edits as ed
    for ef in e.get("effects", []):
        ef.pop("surrogate_candidate", None)
        if e.get("fidelity") == "none" or any(k in ef for k in ("when", "per", "condition", "chance")):
            continue
        keys = [k for k in ed.EFFECT_SCHEMA.get(ef["type"], {})
                if k in ef and isinstance(ef[k], (int, float)) and not isinstance(ef[k], bool)]
        if len(keys) == 1 and "chance" not in keys[0] and "chance" not in ef["type"]:   # 확률 효과 제외
            ef["surrogate_candidate"] = True
    return e


def digits_fidelity(e):
    """환상 하나의 digits 기준 충실도와 사유 (AC-D9). 판단이 어려운 효과는 approx 유지."""
    # gauss 에서 미모델링이어도 digits 엔진이 모든 효과 타입을 직접 다루면(예: carry_unused_moves) 그 판정을 쓴다
    digits_handles = bool(e.get("effects")) and all(
        DIGITS_FIDELITY.get(ef["type"], ("keep", ""))[0] != "keep" for ef in e["effects"])
    if not e.get("effects") or (e.get("fidelity") == "none" and not digits_handles):
        return e.get("fidelity", "none"), "gauss 판정 유지: " + (e.get("notes") or "효과 없음/미모델링")
    order = {"exact": 2, "approx": 1, "none": 0}
    best, why = "exact", []
    for ef in e["effects"]:
        f, r = DIGITS_FIDELITY.get(ef["type"], ("keep", ""))
        if f == "keep":
            f, r = e.get("fidelity", "approx"), "전투 밖·획득 효과 — gauss 판정 유지"
        if ef["type"] == "hits_add" and "base_same_digits" in (ef.get("when") or {}):
            f, r = "approx", "같은 숫자 조건은 굴린 기본 피해로 판정"
        if ef["type"] == "dmg_flat" and "base_same_digits" in (ef.get("when") or {}):
            f, r = "approx", "같은 숫자 조건은 굴린 기본 피해로 판정"
        why.append(f"{ef['type']}: {r}")
        if order[f] < order[best]:
            best = f
    return best, " / ".join(dict.fromkeys(why))


def build_table(src_entries, overrides, source_label="(메모리)"):
    """원본 환상 dict 목록(각 항목에 "_file") + overrides dict → fantasy_effects.json 형식 dict.
    파일을 읽지 않으므로 작업 사본(overlay)의 dry-run 임포트에도 쓴다."""
    overrides = {k: v for k, v in (overrides or {}).items() if not k.startswith("_")}
    out_list = [convert(d, overrides) for d in src_entries if d.get("enabled", True)]
    annotate_combos(out_list)
    for e in out_list:
        e["fidelity_digits"], e["notes_digits"] = digits_fidelity(e)
        mark_surrogate(e)
    out_list.sort(key=lambda x: ({"white": 0, "blue": 1, "red": 2}[x["grade"]], x.get("source_id") or 0, x["id"]))
    return {"version": 1, "source": source_label, "generated_at": datetime.now().isoformat(timespec="seconds"),
            "fantasies": out_list}


def unlinked_report(out_list):
    """원본 연결(src)이 없는 편집 가능 숫자 키 목록."""
    from sim_service import edits as ed
    rows = []
    for f in out_list:
        for i, ef in enumerate(f.get("effects", [])):
            for k in ed.EFFECT_SCHEMA.get(ef.get("type"), {}):
                if k not in ef or not isinstance(ef[k], (int, float)) or isinstance(ef[k], bool):
                    continue
                if ed.src_for(ef, k):
                    continue
                if f.get("mapping") == "override":
                    why = "overrides 에 직접 적은 값 (시뮬 전용, overrides 파일에 저장)"
                else:
                    why = "임포터가 상수로 넣었거나 원본 숫자 필드가 아님 (시나리오 전용)"
                rows.append((f["id"], f.get("name", ""), i, ef["type"], k, ef[k], why))
    return rows


def main(argv=None):
    ap = argparse.ArgumentParser(description="원본 환상 JSON → fantasy_effects.json")
    ap.add_argument("--src", default=DEFAULT_SRC, help="원본 fantasies 폴더")
    ap.add_argument("--out", default=DEFAULT_OUT)
    ap.add_argument("--overrides", default=DEFAULT_OVERRIDES)
    ap.add_argument("--template", action="store_true", help="모든 환상을 fidelity none 으로 채운 템플릿 생성")
    ap.add_argument("--report-unlinked", action="store_true", help="원본 연결(src)이 없는 편집 가능 숫자 키를 출력")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args(argv)

    files = sorted(glob.glob(os.path.join(args.src, "*.json")))
    if not files:
        print(f"원본 환상 JSON 을 찾을 수 없음: {args.src}", file=sys.stderr)
        return 1
    src = []
    for p in files:
        with open(p, encoding="utf-8-sig") as fp:
            d = json.load(fp)
        if d.get("enabled", True):
            d["_file"] = os.path.basename(p)
            src.append(d)

    overrides = {}
    if not args.template and os.path.exists(args.overrides):
        with open(args.overrides, encoding="utf-8-sig") as fp:
            overrides = {k: v for k, v in json.load(fp).items() if not k.startswith("_")}

    if args.template:
        out_list = [{"id": d["id"], "name": d.get("designerName", d["id"]), "grade": d["rarity"],
                     "source_id": d.get("sourceId"), "description": d.get("designerNote", ""),
                     "fidelity": "none", "effects": [], "notes": "", "available": True} for d in src]
        out_path = args.out if args.out != DEFAULT_OUT else os.path.join(HERE, "fantasy_effects.template.json")
    else:
        out_list = [convert(d, overrides) for d in src]
        annotate_combos(out_list)
        for e in out_list:
            e["fidelity_digits"], e["notes_digits"] = digits_fidelity(e)
            mark_surrogate(e)
        out_path = args.out
        unknown = set(overrides) - {d["id"] for d in src}
        if unknown:
            print(f"  ※ overrides 에만 있는 ID (원본 없음): {sorted(unknown)}")

    out_list.sort(key=lambda x: ({"white": 0, "blue": 1, "red": 2}[x["grade"]], x.get("source_id") or 0, x["id"]))
    data = {
        "version": 1,
        "source": os.path.relpath(args.src, HERE).replace("\\", "/") + " 에서 import_fantasies.py 로 생성",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "fantasies": out_list,
    }
    with open(out_path, "w", encoding="utf-8") as fp:
        json.dump(data, fp, ensure_ascii=False, indent=2)

    from collections import Counter
    c = Counter(x["fidelity"] for x in out_list)
    if not args.quiet:
        print(f"{out_path}: {len(out_list)}종 (exact {c['exact']}, approx {c['approx']}, none {c['none']})")
    if args.report_unlinked and not args.template:
        rows = unlinked_report(out_list)
        print(f"원본 연결이 없는 편집 가능 숫자 키 {len(rows)}개:")
        for fid, name, i, t, k, v, why in rows:
            print(f"  {fid:<28} {name:<8} effects[{i}] {t}.{k} = {v}  — {why}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
