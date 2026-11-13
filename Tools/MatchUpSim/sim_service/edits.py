# -*- coding: utf-8 -*-
"""편집 모델 (명세 v2 §5): 효과 스키마·검증, 변경분 적용, 시나리오 파일.

변경분(edit) = {"fid", "effect"(환상 내 효과 인덱스), "key", "old", "new"}
설정 변경분(cfg_edit) = {"path", "old", "new"}
"""
from __future__ import annotations

import copy
import json
import math
import os
import re
from datetime import datetime

import matchup_sim as ms

# (min, max, 정수 여부, 단위, 최소 배제) — 키별. 타입마다 편집 가능한 숫자 키를 정의한다.
R = lambda lo, hi, integer=False, unit="", lo_excl=False: {"min": lo, "max": hi, "int": integer, "unit": unit,  # noqa: E731
                                                          "min_exclusive": lo_excl}
MULT = R(0, 10, unit="배", lo_excl=True)
PROB = R(0, 1, unit="확률")

EFFECT_SCHEMA = {
    "dmg_mult_add": {"value": R(-1, 10, unit="배율 가산")},
    "dmg_flat": {"value": R(-500, 2000, unit="피해/타")},
    "dmg_final_mult": {"value": MULT},
    "base_dmg_transform": {"value": R(0, 999), "odd_mult": MULT, "even_value": R(0, 999, True)},
    "hits_add": {"value": R(-5, 20, True, "타"), "divisor": R(1, 100, unit="개", lo_excl=False)},
    "combo_same_dmg_stack": {"value": R(0, 500, unit="피해")},
    "end_turn_dmg": {"value": R(0, 2000, unit="피해")},
    "player_str_add": {"value": R(-10, 50, unit="힘")},
    "mirror_enemy_str": {"value": R(0, 5, unit="배")},
    "moves_per_turn_add": {"value": R(-5, 20, True, "회")},
    "moves_per_turn_mult": {"value": R(0, 5, unit="배", lo_excl=True)},
    "battle_start_moves": {"value": R(0, 20, True, "회")},
    "carry_unused_moves": {"value": R(0, 1, True)},
    "battle_temp_items": {"value": R(0, 20, True, "개")},
    "item_use_refund_chance": {"value": PROB},
    "dmg_taken_flat": {"value": R(-500, 500, unit="피해/타")},
    "dmg_taken_mult": {"value": R(0, 5, unit="배", lo_excl=True)},
    "dmg_taken_delay": {"value": PROB},
    "def_cut_add": {"value": PROB},
    "monster_dmg_digit_max": {"value": R(0, 9, True, "숫자")},
    "monster_str_add": {"value": R(-50, 50, unit="힘")},
    "str_block": {"value": R(0, 20, True, "회")},
    "monster_skip_chance_add": {"value": PROB},
    "enemy_acts_first": {"value": R(0, 1, True)},
    "reflect_on_hit": {"value": R(0, 2000, unit="피해"), "pct": R(0, 5, unit="비율")},
    "heal_on_deal": {"value": R(0, 500, unit="체력")},
    "heal_on_take": {"per": R(1, 1000, unit="피해"), "value": R(0, 500, unit="체력")},
    "heal_per_unused_move": {"value": R(0, 200, unit="체력")},
    "revive_once": {"value": R(0, 5, True, "회")},
    "battle_start_temp_copy": {"value": R(0, 5, True, "개")},
    "heal_per_battle": {"value": R(0, 1000, unit="체력")},
    "item_drop_chance_add": {"value": R(-1, 1, unit="확률")},
    "item_drop_mult": {"value": MULT},
    "item_gain_bonus": {"value": R(0, 10, True, "개")},
    "rest_heal_mult": {"value": MULT},
    "rest_heal_add": {"value": R(0, 2000, unit="체력")},
    "rest_extra_uses": {"value": R(0, 10, True, "회")},
    "rest_alt_fantasy": {},
    "shop_price_mult": {"value": R(0, 5, unit="배", lo_excl=True)},
    "shop_enter_heal": {"value": R(0, 2000, unit="체력")},
    "shop_moves_add": {"value": R(0, 20, True, "회")},
    "shop_free_items": {"value": R(0, 20, True, "개")},
    "on_acquire_heal": {"value": R(0, 5000, unit="체력"), "pct": R(0, 5, unit="비율")},
    "acquire_dup_or_void": {"chance": PROB},
    "on_acquire_copy_owned": {"value": R(0, 5, True, "개")},
    "combine_into": {},
}
# 타입·키 조합별 특수 범위
SPECIAL = {
    ("end_turn_dmg", "value", "hp"): R(0, 2, unit="체력 비율"),
    ("base_dmg_transform", "value", "mult"): MULT,
    ("base_dmg_transform", "value", "digit_min"): R(0, 9, True, "숫자"),
    ("base_dmg_transform", "value", "first_digit"): R(0, 9, True, "숫자"),
    ("base_dmg_transform", "value", "zero_set"): R(0, 999, True, "피해"),
}
CFG_EDITABLE = {
    "player.skill": R(0, 1, unit="실력"),
    "player.start_hp": R(1, 2000, True, "체력"),
    "player.moves_per_turn": R(0, 20, True, "회"),
    "player.attack_gain_per_move": R(0, 3),
    "player.defense_cut_per_move": R(0, 1),
    "monsters.hp_base": R(1, 10000, unit="체력"),
    "monsters.act_hp_growth": R(0.1, 10, unit="배"),
    "items.drop_chance": PROB,
    "rewards.normal_battle.fantasy_chance": PROB,
}
assert set(EFFECT_SCHEMA) == ms.EFFECT_TYPES, set(EFFECT_SCHEMA) ^ ms.EFFECT_TYPES


def key_schema(ef, key):
    t = ef.get("type")
    sub = ef.get("per") if t == "end_turn_dmg" else ef.get("op") if t == "base_dmg_transform" else None
    return SPECIAL.get((t, key, sub)) or EFFECT_SCHEMA.get(t, {}).get(key)


def schema_json():
    return {"effects": EFFECT_SCHEMA, "special": {"|".join(k): v for k, v in SPECIAL.items()}, "cfg": CFG_EDITABLE,
            "cfg_set": CFG_SET_ALLOWED, "monster": MONSTER_SCHEMA, "sim_reflected": SIM_REFLECTED}


def validate(sch, value):
    if sch is None:
        return "편집할 수 없는 키"
    if not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(value):
        return "숫자가 아님"
    if sch["int"] and float(value) != int(value):
        return "정수만 가능"
    if value < sch["min"] or (sch.get("min_exclusive") and value == sch["min"]):
        return f"최솟값 {'초과' if sch.get('min_exclusive') else ''} {sch['min']}"
    if value > sch["max"]:
        return f"최댓값 {sch['max']}"
    return None


def src_list(ef):
    s = ef.get("src")
    if not s:
        return []
    return s if isinstance(s, list) else [s]


def src_for(ef, key):
    for s in src_list(ef):
        if s.get("sim_key") == key:
            return s
    return None


def fantasy_edit_info(entry):
    keys = []
    for i, ef in enumerate(entry.get("effects", [])):
        for k in EFFECT_SCHEMA.get(ef.get("type"), {}):
            if k in ef and isinstance(ef[k], (int, float)) and not isinstance(ef[k], bool):
                sch = key_schema(ef, k)
                src = src_for(ef, k)
                keys.append({"effect": i, "key": k, "value": ef[k], "schema": sch,
                             "target": "source" if src else ("overrides" if entry.get("mapping") == "override" else "scenario"),
                             "src": src})
    return {"src_linked": any(k["target"] == "source" for k in keys), "editable_keys": keys}


def num_eq(a, b):
    try:
        return abs(float(a) - float(b)) <= 1e-9 * max(1.0, abs(float(a)), abs(float(b)))
    except (TypeError, ValueError):
        return a == b


def apply_edits(table_data, edits):
    """변경분을 효과 테이블(dict, fantasy_effects.json 형식)에 적용한 사본과 충돌 목록을 돌려준다."""
    data = copy.deepcopy(table_data)
    by_id = {e["id"]: e for e in data["fantasies"]}
    conflicts, errors = [], []
    for ed in edits:
        if ed.get("target", "fantasy") != "fantasy":
            continue      # 몬스터·패턴 편집은 apply_monster_edits 가 처리
        e = by_id.get(ed.get("fid"))
        if e is None:
            conflicts.append({**ed, "reason": "환상 없음"})
            continue
        effs = e.get("effects", [])
        i = ed.get("effect")
        if not isinstance(i, int) or not 0 <= i < len(effs) or ed.get("key") not in effs[i]:
            conflicts.append({**ed, "reason": "효과/키 없음"})
            continue
        ef = effs[i]
        if not num_eq(ef[ed["key"]], ed.get("old")):
            conflicts.append({**ed, "reason": f"현재 값 {ef[ed['key']]} ≠ old {ed.get('old')}", "current": ef[ed["key"]]})
            continue
        err = validate(key_schema(ef, ed["key"]), ed.get("new"))
        if err:
            errors.append({**ed, "reason": err})
            continue
        ef[ed["key"]] = like_type(ef[ed["key"]], ed["new"])
    return data, conflicts, errors


def like_type(old, new):
    """원래 값의 숫자 형식(float/int)을 따른다: 뷰어(JS)는 1.0 을 1 로 보내므로, 그대로 두면
    같은 값의 JSON 편집(임포트 결과 1.0)과 정규 해시가 달라진다 (AC-R1)."""
    if isinstance(new, bool) or isinstance(old, bool):
        return new
    if isinstance(old, float) and isinstance(new, int):
        return float(new)
    if isinstance(old, int) and isinstance(new, float) and new.is_integer():
        return int(new)
    return new


# 몬스터·패턴 숫자 필드 (v3 F2). 자릿수 허용 범위는 원본 규칙 확인 전이라 제한하지 않고 4 초과만 경고한다 (§13 Q14).
MONSTER_SCHEMA = {
    "hp": R(1, 1000000, True, "체력"),
    "strength": R(-3, 99, True, "힘"),
    "digits": {**R(1, 99, True, "자릿수"), "warn_above": 4},
    "hits": {**R(1, 99, True, "자릿수"), "warn_above": 4},
    "n": R(-9, 99, True, "힘"),
}
PATTERN_FIELD = {"digits": "dmg_digits", "hits": "hit_digits", "n": "str_units"}
# gauss 피해 모델에서 실제로 시뮬레이션에 쓰이는 필드 (자릿수는 digits 모델에서만 쓰임 → "시뮬 미반영")
SIM_REFLECTED = {"hp": True, "strength": True, "n": True, "digits": False, "hits": False}
SIM_REFLECTED_DIGITS = {"hp": True, "strength": True, "n": True, "digits": True, "hits": True}
# 기믹 값 (v4 F9.6, AC-K9): monster_table.monsters[].sim[gi][key], src 로 원본 패시브 필드에 연결
GIMMICK_SCHEMA = {
    "init": R(0, 9, True, "카운트다운 시작 값"),
    "value": R(1, 1000000, True, "1타 피해 상한"),
    "rate": R(0, 1, False, "흡혈 비율"),
    "multiplier": R(1, 99, True, "조준 사격 배수"),
}


def sim_reflected(cfg):
    """피해 모델별 '시뮬 반영' 필드 (패턴 자릿수는 digits 에서만 반영)."""
    dm = (cfg or {}).get("monsters", {}).get("damage_model", "gauss")
    return SIM_REFLECTED_DIGITS if dm == "digits" else SIM_REFLECTED


def pattern_key(p):
    if p.get("source") != "generic":
        return p["key"]
    if p["kind"] == "str":
        return f"Str_{p['str_units']}"
    return f"{p['dmg_digits']}_Multi_{p['hit_digits']}" if p.get("multi") else f"{p['dmg_digits']}_Single"


def apply_monster_edits(mtable, edits):
    """몬스터·패턴 숫자 편집을 몬스터 테이블 사본에 적용. 반환 (data, conflicts, errors)."""
    data = copy.deepcopy(mtable)
    by = {m["id"]: m for m in data.get("monsters", [])}
    conflicts, errors = [], []
    for e in edits:
        if e.get("target") == "gimmick":
            m = by.get(e.get("mid"))
            sims = (m or {}).get("sim") or []
            gi = e.get("gi", -1)
            sch = GIMMICK_SCHEMA.get(e.get("key"))
            if not m or not 0 <= gi < len(sims) or sch is None or e["key"] not in sims[gi]:
                conflicts.append({**e, "reason": "기믹 없음"})
                continue
            if not num_eq(sims[gi][e["key"]], e.get("old")):
                conflicts.append({**e, "reason": f"현재 값 ≠ old {e.get('old')}"})
                continue
            err = validate(sch, e.get("new"))
            if err:
                errors.append({**e, "reason": err})
                continue
            sims[gi][e["key"]] = like_type(sims[gi][e["key"]], e["new"])
            continue
        sch = MONSTER_SCHEMA.get(e.get("key"))
        targets = []
        if e.get("target") == "monster" and e.get("mid") in by:
            targets = [(by[e["mid"]], e["key"])]
        elif e.get("target") == "pattern" and e.get("mid") in by and 0 <= e.get("step", -1) < len(by[e["mid"]]["patterns"]):
            targets = [(by[e["mid"]]["patterns"][e["step"]], PATTERN_FIELD[e["key"]])]
        elif e.get("target") == "pattern" and "pid" in e:
            targets = [(p, PATTERN_FIELD[e["key"]]) for m in by.values() for p in m["patterns"] if p["key"] == e["pid"]]
        if not targets or sch is None:
            conflicts.append({**e, "reason": "몬스터/패턴 없음"})
            continue
        if any(not num_eq(t.get(f), e.get("old")) for t, f in targets):
            conflicts.append({**e, "reason": f"현재 값 ≠ old {e.get('old')}"})
            continue
        err = validate(sch, e.get("new"))
        if err:
            errors.append({**e, "reason": err})
            continue
        for t, f in targets:
            t[f] = int(e["new"])
            if "kind" in t:
                t["key"] = pattern_key(t)
    return data, conflicts, errors


# 숫자가 아닌 설정 전환 (획득 시스템 스위치 등). 값은 허용 목록 안에서만.
CFG_SET_ALLOWED = {
    "rewards.normal_battle.mode": ["fantasy", "chance", "choice", "ember"],
    "rewards.ember.blue_mode": ["replace", "extra"],
    "rewards.ember.blue_reward": ["offer", "direct"],
    "policy.fantasy_pick": ["random", "greedy_value", "softmax_value"],
    "monsters.select": ["independent", "shuffle_bag"],
    "monsters.encounter": ["game", "tier"],
    "monsters.damage_model": ["gauss", "digits"],     # v4 F8
    "monsters.gimmicks": ["off", "on"],               # v4 F9
    "monsters.model": ["tier_avg", "table"],
}
CFG_EDITABLE.update({
    "rewards.ember.slot_size": R(1, 12, True, "칸"),
    "rewards.ember.blue_chance": PROB,
    "rewards.ember.blue_offer_cap": R(0, 3, True, "개"),
    "monsters.hp_scale": R(0.05, 20, unit="배"),
})


def apply_cfg_set(cfg, cfg_set):
    c = copy.deepcopy(cfg)
    for path, v in (cfg_set or {}).items():
        if path not in CFG_SET_ALLOWED or v not in CFG_SET_ALLOWED[path]:
            raise ValueError(f"허용되지 않는 설정 전환: {path}={v!r}")
        ms.set_path(c, path, v)
    return c


def get_path(cfg, path):
    cur = cfg
    for k in path.split("."):
        cur = cur[int(k)] if isinstance(cur, list) else cur[k]
    return cur


def apply_cfg_edits(cfg, cfg_edits):
    c = copy.deepcopy(cfg)
    conflicts, errors = [], []
    for ed in cfg_edits:
        path = ed.get("path", "")
        sch = CFG_EDITABLE.get(path)
        try:
            cur = get_path(c, path)
        except (KeyError, IndexError, ValueError, TypeError):
            conflicts.append({**ed, "reason": "설정 키 없음"})
            continue
        if not num_eq(cur, ed.get("old")):
            conflicts.append({**ed, "reason": f"현재 값 {cur} ≠ old {ed.get('old')}", "current": cur})
            continue
        err = validate(sch, ed.get("new"))
        if err:
            errors.append({**ed, "reason": err})
            continue
        ms.set_path(c, path, ed["new"])
    return c, conflicts, errors


# ---------------------------------------------------------------------------
# 시나리오
# ---------------------------------------------------------------------------
_SAFE = re.compile(r"[^0-9A-Za-z가-힣_\-]+")


def scenario_filename(name):
    slug = _SAFE.sub("_", (name or "").strip()).strip("_")[:60]
    if not slug:
        raise ValueError("시나리오 이름이 비어 있음")
    return slug + ".json"


def scenario_path(scen_dir, name):
    fn = scenario_filename(name)
    path = os.path.realpath(os.path.join(scen_dir, fn))
    if os.path.dirname(path) != os.path.realpath(scen_dir):
        raise ValueError("시나리오 경로 이탈")
    return path


def save_scenario(scen_dir, name, edits, cfg_edits, base_hash, note="", results=None, applied=None,
                  file_edits=None, cfg_set=None):
    os.makedirs(scen_dir, exist_ok=True)
    path = scenario_path(scen_dir, name)
    now = datetime.now().isoformat(timespec="seconds")
    created = now
    if os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as fp:
                created = json.load(fp).get("created_at", now)
        except (OSError, ValueError):
            pass
    data = {"schema": 2, "name": name, "note": note, "created_at": created, "updated_at": now,
            "base": {"data_hash": base_hash, "sim_version": ms.SIM_VERSION},
            "edits": edits, "cfg_edits": cfg_edits, "cfg_set": cfg_set or {}, "file_edits": file_edits or [],
            "applied": applied, "results": results}
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fp:
        json.dump(data, fp, ensure_ascii=False, indent=2)
    os.replace(tmp, path)
    return path, data


def list_scenarios(scen_dir):
    out = []
    if not os.path.isdir(scen_dir):
        return out
    for fn in sorted(os.listdir(scen_dir)):
        if fn.endswith(".json"):
            try:
                with open(os.path.join(scen_dir, fn), encoding="utf-8") as fp:
                    d = json.load(fp)
                out.append({"file": fn, "name": d.get("name", fn), "updated_at": d.get("updated_at"),
                            "edits": len(d.get("edits", [])), "cfg_edits": len(d.get("cfg_edits", [])),
                            "applied": bool(d.get("applied"))})
            except (OSError, ValueError):
                continue
    return out


def load_scenario(scen_dir, name):
    with open(scenario_path(scen_dir, name), encoding="utf-8") as fp:
        return json.load(fp)


def check_scenario(scen, table_data, cfg, monster_table=None, file_sha1=None):
    """현재 데이터·설정 위에 시나리오를 적용해 충돌을 표시한다. schema 1(v2 형식: target 없는 edits)도 읽는다.
    file_sha1(kind, id) → 현재 디스크 원본 sha1 (file_edits 의 base_sha1 과 비교)."""
    _, c1, e1 = apply_edits(table_data, scen.get("edits", []))
    _, c2, e2 = apply_cfg_edits(cfg, scen.get("cfg_edits", []))
    c3, e3 = [], []
    m_edits = [e for e in scen.get("edits", []) if e.get("target") in ("monster", "pattern", "gimmick")]
    if m_edits:
        if monster_table is None:
            c3 = [{**e, "reason": "몬스터 테이블 없음"} for e in m_edits]
        else:
            _, c3, e3 = apply_monster_edits(monster_table, m_edits)
    c4 = []
    for fe in scen.get("file_edits", []):
        try:
            cur = file_sha1(fe["kind"], fe["id"]) if file_sha1 else None
        except Exception as ex:  # noqa: BLE001
            cur = None
            c4.append({**{k: fe[k] for k in ("kind", "id")}, "reason": str(ex)})
            continue
        if cur != fe.get("base_sha1"):
            c4.append({"kind": fe["kind"], "id": fe["id"], "reason": "원본 파일이 편집 시작 때와 다름(base_sha1 불일치)"})
    return {"conflicts": c1 + c2 + c3 + c4, "errors": e1 + e2 + e3}
