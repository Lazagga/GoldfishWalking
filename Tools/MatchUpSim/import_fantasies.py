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
# 매핑 규칙: 원본 효과 1개 → ([시뮬 효과...], fidelity, 메모) 또는 None(매핑 불가)
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
            return [{"type": "moves_per_turn_add", "value": n}], "exact", ""
        if ev == "battle_start":
            return [{"type": "battle_start_moves", "value": n}], "approx", "전투 시작 시 이동 +N 을 첫 턴 임시 이동으로 해석"
    if system == "shop" and prop == "movement_limit" and mode == "add" and n is not None:
        return [{"type": "shop_moves_add", "value": n}], "exact", ""

    # --- 타수
    if formula == "player.hits" and op == "modify_value" and mode == "add":
        eff = {"type": "hits_add"}
        fid = "exact"
        notes = []
        if n is not None:
            eff["value"] = n
        elif px and per_of(px) in ("items_held", "consecutive_pairs"):
            eff["per"] = per_of(px)
            if "div" in px:
                eff["divisor"] = px["div"]
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
        return [{"type": "dmg_flat", "value": n}], "exact", "타격당 피해 가산"
    if ev == "deal_damage" and actor == "player" and stat == "health" and mode == "add" and n is not None:
        return [{"type": "heal_on_deal", "value": n}], "exact", "타격당 회복"
    if ev == "turn_end" and key == "damage" and op == "modify_value" and mode == "add":
        eff = {"type": "end_turn_dmg"}
        fid = "exact"
        note = ""
        if n is not None:
            eff["value"] = n
        elif px and per_of(px) in ("items_held", "items_used_battle", "hp", "digit8"):
            eff["value"] = px.get("mul", 1.0)
            eff["per"] = per_of(px)
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
            return ([{"type": "dmg_final_mult", "value": n, "condition": "base_eq_monster_dmg"}], "approx",
                    "기본 피해 비교는 시뮬레이터의 내 기본 피해 vs 몬스터 1타 피해. 맞추려는 조작은 미모델링")
        return None

    # --- 기본 피해 상자 변형
    if key == "player_number" and op == "digit_min" and n is not None:
        return ([{"type": "base_dmg_transform", "op": "digit_min", "value": n}], "approx",
                "내 기본 피해 상자 숫자에만 적용")
    if key == "monster_number" and op == "digit_max" and n is not None:
        return ([{"type": "monster_dmg_digit_max", "value": n}], "approx", "몬스터 1타 피해 숫자에만 적용")
    if key == "player_base_damage" and op == "set_first_digit" and n is not None:
        return ([{"type": "base_dmg_transform", "op": "first_digit", "value": n}], "approx",
                "힘 피해 상자는 시뮬레이터에 없음. 기본 피해 상자에만 적용")

    # --- 받는 피해
    if ev == "take_damage" and tg.get("value") == "incoming_damage" and op == "modify_value":
        if mode == "add" and n is not None and not cmpc:
            return [{"type": "dmg_taken_flat", "value": n}], "exact", "타격당 받는 피해 가감"
        if mode == "multiply" and n is not None:
            if not cmpc:
                return [{"type": "dmg_taken_mult", "value": n}], "exact", ""
            if cmpc[0] == "monster_base_damage" and cmpc[1] == ">=" and cmpc[2] == "player_base_damage":
                return ([{"type": "dmg_taken_mult", "value": n, "condition": "monster_dmg_ge_player_base"}],
                        "approx", "기본 피해 비교는 몬스터 1타 피해 vs 내 기본 피해 (시뮬레이터 단위)")
    if ev == "take_damage" and actor == "attacker" and op == "modify_value" and n is not None:
        if mode == "add":
            return [{"type": "reflect_on_hit", "value": n}], "exact", "피격(타격)마다 적에게 고정 피해"
        if mode == "multiply":
            pct = n / 100.0 if n > 1 else n
            return ([{"type": "reflect_on_hit", "pct": pct}], "approx",
                    f"원본 amount {n:g} 를 반사 비율 {pct:g} 로 해석")
    if ev == "take_damage" and actor == "player" and stat == "health" and px and "div" in px and "mul" in px:
        if px["var"] == ("IncomingDamageAmount",):
            return [{"type": "heal_on_take", "per": px["div"], "value": px["mul"]}], "exact", ""

    # --- 몬스터 힘
    if actor == "monster" and stat == "strength" and mode == "add" and n is not None:
        eff = {"type": "monster_str_add", "value": n}
        if _duration_first_turn(e) or ev == "turn_1":
            eff["when"] = {"turn_eq": 1}
        return [eff], "approx", "힘 1 = 1타당 피해 1 (시뮬레이터 단위)"
    if ev.startswith("turn_") and ev[5:].isdigit() and actor == "player" and stat == "strength" and n is not None:
        return ([{"type": "player_str_add", "value": n, "when": {"turn_eq": int(ev[5:])}}], "approx",
                "힘 1 = 1타당 피해 +1 (시뮬레이터 단위)")
    if ev == "enemy_strength_gain" and actor == "player" and stat == "strength":
        return [{"type": "mirror_enemy_str", "value": 1}], "approx", "적이 얻은 힘만큼 1타당 피해 증가"
    if system == "battle" and prop == "enemy_acts_first" and op == "enable":
        return [{"type": "enemy_acts_first", "value": 1}], "exact", ""

    # --- 소모품
    if ev == "battle_start" and key in ("eraser", "extra_match") and mode == "add" and n is not None:
        return [{"type": "battle_temp_items", "value": n}], "approx", "임시 소모품 = 이번 전투 한정 추가 이동"
    if ev == "acquire_item" and key == "item" and mode == "add" and n is not None:
        return [{"type": "item_gain_bonus", "value": n}], "exact", ""
    if ev == "use_item" and key == "last_used_item" and chance:
        return [{"type": "item_use_refund_chance", "value": chance / 100.0}], "exact", ""
    if system == "reward" and prop == "item_chance" and mode == "multiply" and n is not None:
        return [{"type": "item_drop_mult", "value": n}], "exact", ""

    # --- 회복
    if ev == "battle_end" and actor == "player" and stat == "health" and mode == "add" and n is not None:
        return [{"type": "heal_per_battle", "value": n}], "exact", ""
    if ev in ("on_acquire", "acquire") and actor == "player" and stat == "health" and mode == "add":
        if n is not None:
            return [{"type": "on_acquire_heal", "value": n}], "exact", ""
        if px and px["var"] == ("HP",):
            return [{"type": "on_acquire_heal", "pct": px["mul"]}], "exact", ""
    if ev == "turn_end" and actor == "player" and stat == "health" and px and per_of(px) == "unused_moves":
        return ([{"type": "heal_per_unused_move", "value": px["mul"]}], "approx",
                "시뮬레이터는 처치 가능해지면 이동을 멈추므로 사실상 전투 마지막 턴에만 회복")
    if ev == "lethal_damage" and key == "battle_rewind":
        return [{"type": "revive_once", "value": n or 1}], "approx", "사망 시 전투 시작 상태로 되감고 다시 싸움"
    if ev == "rest" and actor == "player" and stat == "health" and mode == "multiply" and n is not None:
        return [{"type": "rest_heal_mult", "value": n}], "exact", ""
    if system == "rest" and prop == "use_count" and mode == "add" and n is not None:
        return [{"type": "rest_extra_uses", "value": n}], "exact", ""
    if key == "rest_fantasy_alternative" and op == "enable":
        return ([{"type": "rest_alt_fantasy", "grade": "white"}], "approx",
                "체력이 policy.rest_below_hp 이상이면 회복 대신 환상을 고름")

    # --- 상점
    if ev == "shop_enter" and actor == "player" and stat == "health" and mode == "add" and n is not None:
        return [{"type": "shop_enter_heal", "value": n}], "exact", ""
    if system == "shop" and prop == "price" and mode == "multiply" and n is not None:
        return [{"type": "shop_price_mult", "value": n}], "exact", ""

    # --- 환상 획득 관련
    if op == "duplicate_or_void_acquire":
        return ([{"type": "acquire_dup_or_void", "chance": (chance or 50) / 100.0}], "exact",
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
    for e in src_entry.get("effects", []):
        m = map_effect(e)
        if m is None:
            unmapped += 1
            continue
        effs, f, note = m
        for x in effs:
            if "_available" in x:
                available = x["_available"]
            else:
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


def main(argv=None):
    ap = argparse.ArgumentParser(description="원본 환상 JSON → fantasy_effects.json")
    ap.add_argument("--src", default=DEFAULT_SRC, help="원본 fantasies 폴더")
    ap.add_argument("--out", default=DEFAULT_OUT)
    ap.add_argument("--overrides", default=DEFAULT_OVERRIDES)
    ap.add_argument("--template", action="store_true", help="모든 환상을 fidelity none 으로 채운 템플릿 생성")
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
    print(f"{out_path}: {len(out_list)}종 (exact {c['exact']}, approx {c['approx']}, none {c['none']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
