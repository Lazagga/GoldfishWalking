#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Match Up 밸런스 몬테카를로 시뮬레이터
=====================================

성냥개비 퍼즐 자체는 시뮬레이션할 수 없으므로, "성냥개비 1회 이동이 평균적으로
얼마나 이득을 주는가"를 확률 파라미터로 추상화해 런 전체(3막 x 15층)를 반복 실행한다.
결과는 하나의 결과 폴더(기본: sim_results/)에 CSV로 계속 누적된다.

빠른 사용법
-----------
  # 기본 설정으로 2000판
  python matchup_sim.py --runs 2000 --label baseline

  # 설정 파일 뽑아서 편집 후 사용
  python matchup_sim.py --dump-config balance_config.json
  python matchup_sim.py --config balance_config.json --runs 5000

  # 개별 값 덮어쓰기 (점 경로, 리스트는 인덱스)
  python matchup_sim.py --set player.start_hp=180 --set monsters.act_scale.1.hp=1.5

  # 파라미터 스윕 (조합 전체를 각각 한 배치로 실행, 같은 시드라 공정 비교 가능)
  python matchup_sim.py --sweep player.start_hp=120,150,180 --sweep player.skill=0.5,0.8

  # 목표 승률 탐색: 막별 체력 증가율마다 승률 10%가 되는 1막 기본 체력 찾기
  python matchup_sim.py --tune monsters.hp_base=20:400 --target 0.10 \
      --sweep monsters.act_hp_growth=1.2,1.5,1.8,2.1

결과 폴더 구성
--------------
  runs.csv         판 하나당 한 줄 (도달 층, 승패, 사망 원인, 막별 잔여 체력,
                   fantasies = 보유 환상 목록(획득 순서, | 구분) 등)
  tune_results.csv --tune 실행마다 찾은 값 한 줄
  batches.csv      배치 하나당 한 줄 (요약 통계 + 사용한 모든 파라미터 cfg.* 열)
  floor_reach.csv  배치 x 층(1~45)별 도달률 / 클리어률 (생존 곡선)
  configs/<batch_id>.json  배치에 쓴 설정 전체 스냅샷

모든 CSV는 batch_id로 서로 연결된다. 새 파라미터가 추가돼 열이 늘어나면
기존 파일을 열 합집합으로 자동 재작성하므로 과거 데이터가 사라지지 않는다.

환상 효과 모드
--------------
  fantasy.effect_mode = "grade" (기본) : 등급별 개수 x 등급 계수 (기존 동작 그대로)
  fantasy.effect_mode = "table"        : fantasy_effects.json 의 환상별 효과 사용
  --effects fantasy_effects.json 을 주면 따로 지정하지 않는 한 table 모드가 된다.

  # 특정 환상을 시작부터 보유 (보상/상점 후보에서는 자동 제외)
  python matchup_sim.py --effects fantasy_effects.json --force-fantasy fan_turn_boots

  # 환상별 승률 곡선 스캔 (fantasy_scan.py 로 위임)
  python matchup_sim.py --fantasy-scan --effects fantasy_effects.json \\
      --x monsters.hp_base=50:100:5 --fantasies all --runs 3000 --seed scan1 --workers 8
"""
from __future__ import annotations

import argparse
import copy
import csv
import hashlib
import itertools
import json
import math
import os
import random
import statistics
import sys
import time
from datetime import datetime

# 시뮬레이션 의미가 바뀌는 수정(같은 입력에서 결과가 달라지는 수정)마다 올린다. 스캔 캐시 키에 들어간다.
SIM_VERSION = 1

ACTS = 3
FLOORS_PER_ACT = 15
TOTAL_FLOORS = ACTS * FLOORS_PER_ACT
GRADES = ("white", "blue", "red")
TIER_GRADE = {"easy": "white", "normal": "white", "elite": "blue", "boss": "red"}
NODE_TO_TIER = {"elite": "elite", "boss": "boss"}  # battle -> easy/normal 은 런타임에 결정
SPECIAL_NODES = ("elite", "rest", "shop")  # 연속 등장 금지

# ---------------------------------------------------------------------------
# 기본 설정 — 수치는 모두 "임시값"이다. 실제 데이터로 보정해서 쓰면 된다.
# ---------------------------------------------------------------------------
DEFAULT_CONFIG = {
    "player": {
        "start_hp": 150,
        # 턴마다 시드로 굴리는 기본 피해 상자 값의 범위 (2자리 상자)
        "base_dmg_min": 10,
        "base_dmg_max": 45,
        "moves_per_turn": 2,
        # 플레이어 실력 0~1. gauss: 이동 1회의 기대 이득에 곱해진다.
        #   digits(v4): "이동 1회가 쓸모 있게 쓰일 확률" — 유효 이동 수 K ~ Binomial(이동 한도, skill)
        "skill": 0.7,
        # 공격 이동 1회: 기본 피해 x U(0, 2*gain) x skill 만큼 피해 증가 (평균 gain*skill)
        "attack_gain_per_move": 0.6,
        # 방어 이동 1회: 몬스터 1타 피해를 U(0, 2*cut) x skill 비율만큼 감소
        "defense_cut_per_move": 0.35,
        # 연타 공격일 때 방어 이동 1회로 타수를 0으로 만들 확률 (x skill)
        "zero_hits_chance": 0.25,
        # digits 모델 이동 배분 정책 (v4 F8.4). 기본값이면 점 캐시 키에 넣지 않는다 (기존 캐시 유지)
        "policy": {"attack_weight": 0.5, "escape_penalty": 0.3, "reset_at_strength": 2, "react_penalty": "auto"},
    },
    "monsters": {
        # 초반 N번의 일반 전투는 easy 몬스터
        "easy_battles": 3,
        # 체력 모델
        #   ratio : 체력 = hp_base x tier_hp_ratio[등급] x act_hp_growth^(막-1)
        #           (tiers.*.hp_mean, act_scale.*.hp 는 무시)
        #   manual: 체력 = tiers[등급].hp_mean x act_scale[막].hp
        "hp_model": "ratio",
        "hp_base": 80,                 # 1막 일반 몬스터 평균 체력
        "tier_hp_ratio": {"easy": 0.6, "normal": 1, "elite": 3, "boss": 5},
        "act_hp_growth": 1.8,          # 막이 오를 때마다 곱해지는 체력 배율
        # 1막 기준 등급별 수치. dmg_mean 은 "1타당" 평균 피해.
        "tiers": {
            "easy":   {"hp_mean": 50,  "hp_cv": 0.15, "dmg_mean": 7,  "dmg_cv": 0.3,
                       "multi_chance": 0.10, "multi_hits_max": 2,
                       "str_chance": 0.00, "str_amount": 2, "skip_chance": 0.15},
            "normal": {"hp_mean": 80,  "hp_cv": 0.15, "dmg_mean": 10, "dmg_cv": 0.3,
                       "multi_chance": 0.25, "multi_hits_max": 3,
                       "str_chance": 0.10, "str_amount": 2, "skip_chance": 0.08},
            "elite":  {"hp_mean": 150, "hp_cv": 0.15, "dmg_mean": 13, "dmg_cv": 0.3,
                       "multi_chance": 0.30, "multi_hits_max": 3,
                       "str_chance": 0.15, "str_amount": 3, "skip_chance": 0.05},
            "boss":   {"hp_mean": 300, "hp_cv": 0.10, "dmg_mean": 16, "dmg_cv": 0.25,
                       "multi_chance": 0.35, "multi_hits_max": 4,
                       "str_chance": 0.20, "str_amount": 3, "skip_chance": 0.03},
        },
        # 막별 배율 (index 0 = 1막). hp 는 manual 모델에서만 사용, dmg 는 항상 사용.
        # 몬스터 모델: table = monster_table.json 의 실제 몬스터, 체력은 원본 JSON 그대로 (v4.2 F11 기본)
        #   tier_avg = 등급별 평균 몬스터 (v1~v4.1 기본, 구버전 호환 전용 — LEGACY_MONSTERS 참고)
        "model": "table",
        "table_file": "monster_table.json",   # 상대 경로는 현재 폴더 → 이 스크립트 폴더 순으로 찾는다
        "select": "independent",       # table 모델의 몬스터 선택: independent | shuffle_bag
        # table 모델의 일반 전투 몬스터 배정
        #   game: 게임 MonsterSelector 규칙 — encounter_rules.fixed 의 (막, 방) 은 고정 몬스터,
        #         easy_rooms 의 방은 그 막의 easy 중 무작위, 나머지 일반 전투는 그 막의 easy + normal 중 무작위
        #   tier: (v4 이전) 막마다 처음 easy_battles 번은 easy, 이후 normal 만
        #   방 번호(room)는 게임의 roomIndex 와 같은 0부터 (시뮬 층 f = room + 1)
        "encounter": "game",
        "encounter_rules": {"fixed": [{"act": 1, "room": 0, "id": "Mob_10101_Fairy"}],
                            "easy_rooms": [{"act": 1, "rooms": [1, 2]}]},
        "hp_scale": 1.0,               # table 모델에서 모든 몬스터 체력에 곱하는 배율 (1 = JSON 그대로, 승률 맞추기·민감도용)
        "damage_model": "digits",      # digits(v4.2 기본: 자릿수 굴림 + 상자 안 성냥 이동, model=table 필요) | gauss(등급 평균 피해)
        "gimmicks": "on",              # on(v4.2 기본: 몬스터 기믹, digits 에서만) | off
        "act_scale": [
            {"hp": 1.0, "dmg": 1.0},
            {"hp": 1.9, "dmg": 1.7},
            {"hp": 3.2, "dmg": 2.4},
        ],
    },
    "fantasy": {
        # 환상 1개당 추상화된 효과 (곱연산이 아니라 합산)
        "dmg_bonus": {"white": 0.03, "blue": 0.10, "red": 0.20},
        "def_bonus": {"white": 0.02, "blue": 0.04, "red": 0.08},
        "def_cap": 0.6,
        # 등급별 풀 크기 (총 69종 가정, 다 모으면 더 안 나옴). list_file 이 없을 때
        # W01.., B01.., R01.. 형태의 임시 이름으로 풀을 만든다.
        "pool": {"white": 40, "blue": 20, "red": 9},
        # 실제 환상 목록 JSON 경로 (선택). [{"id":..,"name":..,"grade":..}, ...] 형태,
        # grade 는 white/blue/red, 백색/청색/적색, common/rare/legendary 등을 인식한다.
        "list_file": "",
        # grade: 위의 등급 계수 사용 (기존 동작) / table: effects_file 의 환상별 효과 사용
        "effect_mode": "grade",
        "effects_file": "",
        # 강제 포함: ids 의 환상을 at 시점에 보유. at = "start" 또는 {"floor": 전체 층 번호(1~45)}
        "forced": {"ids": [], "at": "start"},
        # 제외(banned): 보상·상점·휴식 후보와 조합 결과에서 뺀다 (v3). forced 와 겹치면 오류
        "banned": {"ids": []},
    },
    "items": {
        "drop_chance": 0.5,       # 전투 보상으로 여분 성냥 / 지우개 각각 등장 확률
        "start_matches": 0,
        "start_erasers": 0,
    },
    "rest": {
        "heal_min": 20,
        "heal_max": 60,
        "moves": 2,
        "edit_gain_per_move": 0.4,
        "act_scale": [1.0, 1.3, 1.6],
    },
    "shop": {
        "moves": 2,
        "item_price_min": 10,
        "item_price_max": 99,
        # 등급별 환상 가격 상자 초기값 범위 (2/3/4자리)
        "fantasy_price": {"white": [10, 99], "blue": [100, 299], "red": [1000, 1999]},
        # 가격 편집 1회: 가격 x U(0, 2*discount) x skill 만큼 인하
        "discount_per_move": 0.3,
        # 가격 편집 1회로 맨 앞자리를 통째로 지울 확률 (x skill). 예: 158 -> 58
        "digit_drop_chance": 0.3,
    },
    "map": {
        "weights": {"battle": 4, "elite": 3, "rest": 2, "shop": 1},
        "min_nodes": 1,
        "max_nodes": 3,
        "fixed_battle_floors": 2,
        "forced_shop_floor": 14,
    },
    "policy": {
        "path": "greedy",          # greedy | random
        "rest_below_hp": 90,       # 이 체력 미만이면 휴식 선호
        "elite_above_hp": 140,     # 이 체력 이상이면 엘리트 선호, 미만이면 회피
        "shop_above_hp": 130,      # 이 체력 이상이면 상점 선호
        "shop_keep_hp": 90,        # 구매 후 최소 남길 체력
        "max_items_per_shop": 2,
        "offense_bias": 0.6,       # 위험하지 않을 때 이동을 공격에 쓸 확률
        "danger_ratio": 0.3,       # 예상 피격 >= 현재 체력 x 이 값이면 방어 우선 + 아이템 사용
        "use_items": "danger",     # danger | always | never
        "max_items_per_turn": 1,
        # 보상 3개 중 1개 선택 방식: random(기본) | greedy_value | softmax_value
        "fantasy_pick": "random",
        "value_table": {},            # 환상 ID → 가치 (greedy/softmax 용). 비어 있으면 value_table_file 사용
        "value_table_file": "",
        "softmax_temp": 0.02,         # softmax_value 온도 (가치 단위 = Δ승률)
    },
    "rewards": {
        # 일반 전투 보상 구조 (v2 F5). fantasy = 환상 확정(기본, v1 동작)
        #   chance: fantasy_chance 확률로만 환상 / choice: 체력 < policy.rest_below_hp 면 회복,
        #   아니면 환상(후보 없으면 아이템 2개)
        #   ember: 불씨 획득 시스템 (v3 §7, 게임 미반영 변경안 — 시뮬레이터 전용)
        "normal_battle": {"mode": "fantasy", "fantasy_chance": 1.0, "heal_amount": 40},
        # 불씨: 일반 전투 승리마다 불씨 1개, slot_size 개가 모이면 백색 환상 3택1.
        #   blue_mode  replace = 불씨가 확률 blue_chance 로 푸른색 / extra = 하얀 불씨 + 확률로 푸른 불씨 추가
        #   blue_reward offer = 푸른 불씨가 든 슬롯은 후보 중 min(푸른 수, blue_offer_cap)개가 청색 / direct = 청색 즉시 획득
        "ember": {"slot_size": 3, "blue_chance": 0.10, "blue_mode": "replace", "blue_reward": "offer",
                  "blue_offer_cap": 1, "offer_size": 3},
    },
    "sim": {
        "max_turns": 60,           # 한 전투 최대 턴 (넘으면 timeout 패배)
    },
}


# ---------------------------------------------------------------------------
# 설정 유틸
# ---------------------------------------------------------------------------

# v4.1 까지의 기본 몬스터 설정 (구버전 호환, v4.2 F11.2). 이 값을 명시하면 변경 전 코드와 결과가 같다 (AC-H3).
LEGACY_MONSTERS = {"model": "tier_avg", "table_file": "", "damage_model": "gauss", "gimmicks": "off"}
# table 모델에서 전투 체력에 쓰이지 않는 키 (v4.2 F11.3)
TABLE_UNUSED = ("monsters.hp_base", "monsters.act_hp_growth", "monsters.tier_hp_ratio", "monsters.hp_model",
                "monsters.tiers.*.hp_mean", "monsters.tiers.*.hp_cv", "monsters.act_scale.*.hp")


def legacy_config(**monsters):
    """v4.1 까지의 기본 설정 (tier_avg + gauss + 기믹 끔). 구버전 결과 재현·회귀 테스트용."""
    cfg = copy.deepcopy(DEFAULT_CONFIG)
    cfg["monsters"].update(LEGACY_MONSTERS)
    cfg["monsters"].update(monsters)
    return cfg


def normalize_models(cfg):
    """tier_avg(평균 몬스터)는 gauss 피해만 지원한다 → tier_avg 를 고르면 피해 모델을 구버전 값(gauss, 기믹 끔)으로 맞춘다.
    (digits·기믹은 table 에서만 동작하므로 유효한 설정의 결과는 바뀌지 않는다.) cfg 를 그대로 돌려준다."""
    M = cfg["monsters"]
    if M.get("model") == "tier_avg":
        M["damage_model"] = LEGACY_MONSTERS["damage_model"]
        M["gimmicks"] = LEGACY_MONSTERS["gimmicks"]
    return cfg


def resolve_table_file(path):
    """monsters.table_file 경로 해석: 절대 경로 / 현재 폴더 / 이 스크립트 폴더. 없으면 임포터 안내와 함께 오류 (Q47)."""
    if not path:
        raise ValueError("monsters.model=table 에는 monsters.table_file 이 필요함")
    cands = [path] if os.path.isabs(path) else [path, os.path.join(os.path.dirname(os.path.abspath(__file__)), path)]
    for c in cands:
        if os.path.exists(c):
            return c
    raise ValueError(f"몬스터 테이블 {path} 이 없음 — 먼저 `python import_monsters.py` 를 실행하세요 "
                     "(구버전 평균 몬스터는 --set monsters.model=\"tier_avg\")")

def deep_merge(base, over):
    for k, v in over.items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            deep_merge(base[k], v)
        else:
            base[k] = copy.deepcopy(v)
    return base


def parse_value(s):
    try:
        return json.loads(s)
    except (json.JSONDecodeError, ValueError):
        return s


def get_path(cfg, path, default=None):
    """'a.b.0.c' 경로의 값 (없으면 default). 목록 인덱스는 숫자 조각."""
    cur = cfg
    for part in path.split("."):
        if isinstance(cur, list):
            try:
                cur = cur[int(part)]
            except (ValueError, IndexError):
                return default
        elif isinstance(cur, dict) and part in cur:
            cur = cur[part]
        else:
            return default
    return cur


def set_path(cfg, path, value):
    keys = path.split(".")
    cur = cfg
    for k in keys[:-1]:
        if isinstance(cur, list):
            cur = cur[int(k)]
        else:
            if k not in cur:
                raise KeyError(f"알 수 없는 설정 키: {path}")
            cur = cur[k]
    last = keys[-1]
    if isinstance(cur, list):
        cur[int(last)] = value
    else:
        if last not in cur:
            raise KeyError(f"알 수 없는 설정 키: {path}")
        cur[last] = value


def flatten(obj, prefix=""):
    out = {}
    if isinstance(obj, dict):
        for k, v in obj.items():
            out.update(flatten(v, f"{prefix}{k}."))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            out.update(flatten(v, f"{prefix}{i}."))
    else:
        out[prefix[:-1]] = obj
    return out


def rng_for(*parts):
    """시드/막/층/목적 키 조합으로 독립 난수 스트림 (게임의 시드 고정 방식 흉내)."""
    return random.Random("|".join(str(p) for p in parts))


_GRADE_ALIASES = {
    "white": "white", "w": "white", "common": "white", "normal": "white", "백색": "white", "흰색": "white", "0": "white",
    "blue": "blue", "b": "blue", "rare": "blue", "elite": "blue", "청색": "blue", "파란색": "blue", "1": "blue",
    "red": "red", "r": "red", "legendary": "red", "epic": "red", "boss": "red", "적색": "red", "빨간색": "red", "2": "red",
}


def load_fantasy_pool(cfg):
    """등급별 환상 이름 목록. list_file 이 있으면 그걸 읽고, 없으면 임시 이름을 만든다."""
    F = cfg["fantasy"]
    path = F.get("list_file") or ""
    if not path:
        return {g: [f"{g[0].upper()}{i + 1:02d}" for i in range(F["pool"][g])] for g in GRADES}

    with open(path, encoding="utf-8-sig") as fp:
        data = json.load(fp)
    if isinstance(data, dict):
        for key in ("fantasies", "items", "list", "data"):
            if isinstance(data.get(key), list):
                data = data[key]
                break
        else:
            data = list(data.values())
    pool = {g: [] for g in GRADES}
    skipped = 0
    for e in data:
        if not isinstance(e, dict):
            skipped += 1
            continue
        name = e.get("name") or e.get("displayName") or e.get("id")
        raw = str(e.get("grade", e.get("rarity", e.get("tier", "")))).strip().lower()
        g = _GRADE_ALIASES.get(raw)
        if not name or not g:
            skipped += 1
            continue
        pool[g].append(str(name))
    if skipped:
        print(f"  (환상 목록: 이름/등급을 못 읽은 항목 {skipped}개 건너뜀)")
    return pool


# ---------------------------------------------------------------------------
# 환상 효과 테이블 (effect_mode = "table")
# ---------------------------------------------------------------------------
FIDELITIES = ("exact", "approx", "none")

# 시뮬레이터가 이해하는 효과 타입. 새 타입을 추가하면 여기와 README 의 표를 같이 고친다.
# (환상 ID 로 분기하는 코드는 쓰지 않는다. 모든 효과는 이 타입들의 조합으로만 표현한다.)
EFFECT_TYPES = {
    # 전투 — 내 피해
    "dmg_mult_add", "dmg_flat", "dmg_final_mult", "base_dmg_transform", "hits_add",
    "combo_same_dmg_stack", "end_turn_dmg", "player_str_add", "mirror_enemy_str",
    # 전투 — 이동/소모품
    "moves_per_turn_add", "moves_per_turn_mult", "battle_start_moves", "carry_unused_moves",
    "battle_temp_items", "item_use_refund_chance",
    # 전투 — 받는 피해 / 몬스터
    "dmg_taken_flat", "dmg_taken_mult", "dmg_taken_delay", "def_cut_add", "monster_dmg_digit_max",
    "monster_str_add", "str_block", "monster_skip_chance_add", "enemy_acts_first",
    "reflect_on_hit", "heal_on_deal", "heal_on_take", "heal_per_unused_move", "revive_once",
    "battle_start_temp_copy",
    # 전투 밖
    "heal_per_battle", "item_drop_chance_add", "item_drop_mult", "item_gain_bonus",
    "rest_heal_mult", "rest_heal_add", "rest_extra_uses", "rest_alt_fantasy",
    "shop_price_mult", "shop_enter_heal", "shop_moves_add", "shop_free_items",
    "on_acquire_heal", "acquire_dup_or_void", "on_acquire_copy_owned", "combine_into",
}
# 같은 타입끼리 곱으로 합치는 타입 (나머지는 합산)
PRODUCT_TYPES = {"moves_per_turn_mult", "rest_heal_mult", "shop_price_mult", "item_drop_mult"}
# when 조건 (턴 번호 등)을 지원하는 타입
WHEN_KEYS = {"turn_eq", "turn_ge", "turn_mod", "base_same_digits"}

_TABLE_CACHE = {}


def file_sha1(path):
    with open(path, "rb") as fp:
        return hashlib.sha1(fp.read()).hexdigest()


def load_effects_table(path):
    """fantasy_effects.json 을 읽어 {id: entry} (파일 순서 유지) 와 파일 해시를 돌려준다."""
    path = os.path.abspath(path)
    key = (path, os.path.getmtime(path))
    if key in _TABLE_CACHE:
        return _TABLE_CACHE[key]
    with open(path, encoding="utf-8-sig") as fp:
        data = json.load(fp)
    table = {}
    for e in data.get("fantasies", []):
        fid = e["id"]
        g = _GRADE_ALIASES.get(str(e.get("grade", "")).lower())
        if g is None:
            raise ValueError(f"{fid}: 등급을 알 수 없음 ({e.get('grade')})")
        fid_fidelity = e.get("fidelity")
        if fid_fidelity not in FIDELITIES:
            raise ValueError(f"{fid}: fidelity 는 exact/approx/none 중 하나여야 함 ({fid_fidelity})")
        for ef in e.get("effects", []):
            if ef.get("type") not in EFFECT_TYPES:
                raise ValueError(f"{fid}: 알 수 없는 효과 타입 {ef.get('type')}")
            bad = set(ef.get("when", {})) - WHEN_KEYS
            if bad:
                raise ValueError(f"{fid}: 알 수 없는 when 키 {sorted(bad)}")
        if fid in table:
            raise ValueError(f"환상 ID 중복: {fid}")
        table[fid] = dict(e, grade=g)
    result = (table, file_sha1(path))
    _TABLE_CACHE[key] = result
    return result


class SimContext:
    """배치 하나에서 판마다 공유하는 읽기 전용 정보 (풀, 효과 테이블)."""

    def __init__(self, cfg, pool=None):
        F = cfg["fantasy"]
        self.mode = F.get("effect_mode", "grade")
        if self.mode not in ("grade", "table"):
            raise ValueError(f"fantasy.effect_mode 는 grade 또는 table: {self.mode}")
        self.table = {}
        self.effects_hash = ""
        if F.get("effects_file"):
            self.table, self.effects_hash = load_effects_table(F["effects_file"])
        if self.mode == "table" and not self.table:
            raise ValueError("table 모드에는 fantasy.effects_file 이 필요함")

        if pool is not None:
            self.pool = pool
        elif self.mode == "table":
            # 획득 불가(available=false) 환상은 보상/상점 풀에서 빠진다 (조합 전용 등). 강제 포함은 가능.
            self.pool = {g: [fid for fid, e in self.table.items()
                             if e["grade"] == g and e.get("available", True)] for g in GRADES}
        else:
            self.pool = load_fantasy_pool(cfg)

        self.map_key = json.dumps(cfg["map"], sort_keys=True)
        RW = (cfg.get("rewards") or {}).get("normal_battle") or {}
        self.normal_reward = {"mode": RW.get("mode", "fantasy"), "fantasy_chance": RW.get("fantasy_chance", 1.0),
                              "heal_amount": RW.get("heal_amount", 40)}
        if self.normal_reward["mode"] not in ("fantasy", "chance", "choice", "ember"):
            raise ValueError("rewards.normal_battle.mode 는 fantasy/chance/choice/ember: " + str(self.normal_reward["mode"]))
        self.ember_on = self.normal_reward["mode"] == "ember"
        pol = cfg["policy"]
        self.pick_mode = pol.get("fantasy_pick", "random")
        if self.pick_mode not in ("random", "greedy_value", "softmax_value"):
            raise ValueError("policy.fantasy_pick 은 random/greedy_value/softmax_value: " + str(self.pick_mode))
        self.value_table = dict(pol.get("value_table") or {})
        if not self.value_table and pol.get("value_table_file"):
            with open(pol["value_table_file"], encoding="utf-8") as fp:
                vt = json.load(fp)
            self.value_table = vt.get("values", vt)
        if self.pick_mode != "random" and not self.value_table:
            print(f"  ※ policy.fantasy_pick={self.pick_mode} 인데 가치표가 없어 random 으로 대체")
            self.pick_mode = "random"
        self.monsters = None
        Mc = cfg["monsters"]
        self.damage_model = Mc.get("damage_model", "gauss")
        if self.damage_model not in ("gauss", "digits"):
            raise ValueError(f"monsters.damage_model 은 gauss 또는 digits: {self.damage_model}")
        if Mc.get("gimmicks", "off") not in ("off", "on"):
            raise ValueError(f"monsters.gimmicks 는 off 또는 on: {Mc.get('gimmicks')}")
        if self.damage_model == "digits" and Mc.get("model", "tier_avg") != "table":
            raise ValueError("monsters.damage_model=digits 에는 monsters.model=table 이 필요함 (tier_avg 와 함께 쓸 수 없음)")
        if Mc.get("gimmicks", "off") == "on" and self.damage_model != "digits":
            raise ValueError("monsters.gimmicks=on 은 monsters.damage_model=digits 에서만 쓸 수 있음")
        if self.damage_model == "digits" and self.mode != "table":
            raise ValueError("monsters.damage_model=digits 에는 fantasy.effect_mode=table 이 필요함")
        if Mc.get("model", "tier_avg") == "table":
            self._load_monsters(cfg)
        self.grade_of = {}
        for g in GRADES:
            for name in self.pool[g]:
                self.grade_of[name] = g
        self.banned = set((F.get("banned") or {}).get("ids") or [])
        if self.banned:
            # 풀에서 제외 (등급 조회는 남겨 둠). 비어 있으면 풀 객체를 그대로 써서 결과가 현행과 같다
            self.pool = {g: [n for n in self.pool[g] if n not in self.banned] for g in GRADES}
        E = (cfg.get("rewards") or {}).get("ember") or {}
        self.ember = {"slot_size": int(E.get("slot_size", 3)), "blue_chance": float(E.get("blue_chance", 0.10)),
                      "blue_mode": E.get("blue_mode", "replace"), "blue_reward": E.get("blue_reward", "offer"),
                      "blue_offer_cap": int(E.get("blue_offer_cap", 1)), "offer_size": int(E.get("offer_size", 3))}
        if self.ember["slot_size"] < 1 or not 0 <= self.ember["blue_chance"] <= 1 or self.ember["offer_size"] < 1 \
                or self.ember["blue_mode"] not in ("replace", "extra") or self.ember["blue_reward"] not in ("offer", "direct") \
                or self.ember["blue_offer_cap"] < 0:
            raise ValueError(f"rewards.ember 설정 오류: {self.ember}")
        for fid, e in self.table.items():
            self.grade_of.setdefault(fid, e["grade"])

        # 조합: 재료가 모두 모이면 재료를 없애고 결과 환상을 얻는다
        self.combos = [(fid, list(ef["from"])) for fid, e in self.table.items()
                       for ef in e.get("effects", []) if ef["type"] == "combine_into"]

        forced = F.get("forced") or {}
        self.forced_ids = list(forced.get("ids") or [])
        for fid in self.forced_ids:
            if fid not in self.grade_of:
                raise ValueError(f"강제 포함 환상을 찾을 수 없음: {fid}")
            if fid in self.banned:
                raise ValueError(f"강제 포함과 제외(banned)가 겹침: {fid}")
        at = forced.get("at", "start")
        if at == "start":
            self.forced_floor = 0
        elif isinstance(at, dict) and "floor" in at:
            self.forced_floor = int(at["floor"])
            if not 1 <= self.forced_floor <= TOTAL_FLOORS:
                raise ValueError(f"fantasy.forced.at.floor 는 1~{TOTAL_FLOORS}: {self.forced_floor}")
        else:
            raise ValueError(f"fantasy.forced.at 형식 오류: {at}")

        if self.mode == "table":
            missing = [n for g in GRADES for n in self.pool[g] if n not in self.table]
            if missing:
                print(f"  ※ 효과 테이블에 없는 환상 {len(missing)}개는 효과 없음(none)으로 취급: {missing[:5]}...")


def _ctx_load_monsters(self, cfg):
    """monster_table.json (import_monsters.py 산출물) 을 읽어 (막, 등급) 별 풀을 만든다."""
    M = cfg["monsters"]
    path = resolve_table_file(M.get("table_file") or "")
    with open(path, encoding="utf-8-sig") as fp:
        data = json.load(fp)
    self.monsters = {}
    self.monster_by_id = {}
    for m in data.get("monsters", []):
        if not m.get("enabled", True):
            continue
        self.monsters.setdefault((int(m["act"]), m["tier"]), []).append(m)
        self.monster_by_id[m["id"]] = m
    # 게임 규칙의 일반 전투 풀 = 그 막의 easy + normal (대체 전, 원래 등급 그대로)
    self.battle_pool = {act: list(self.monsters.get((act, "easy"), [])) + list(self.monsters.get((act, "normal"), []))
                        for act in range(1, ACTS + 1)}
    self.monster_encounter = M.get("encounter", "game")
    if self.monster_encounter not in ("game", "tier"):
        raise ValueError(f"monsters.encounter 는 game/tier: {self.monster_encounter}")
    rules = self.encounter_rules = M.get("encounter_rules") or {}
    for r in rules.get("fixed") or ():
        if r.get("id") not in self.monster_by_id and self.monster_encounter == "game":
            raise ValueError(f"monsters.encounter_rules.fixed: 몬스터 테이블에 없는(또는 꺼진) ID {r.get('id')}")
    for act in range(1, ACTS + 1):
        for tier in ("easy", "normal", "elite", "boss"):
            if not self.monsters.get((act, tier)):
                # 쉬운 몬스터가 없는 막은 일반 몬스터로 대체
                alt = self.monsters.get((act, "normal" if tier == "easy" else tier))
                if not alt:
                    raise ValueError(f"monster_table: {act}막 {tier} 몬스터가 없음")
                self.monsters[(act, tier)] = alt
    self.monster_select = M.get("select", "independent")
    if self.monster_select not in ("independent", "shuffle_bag"):
        raise ValueError(f"monsters.select 는 independent/shuffle_bag: {self.monster_select}")


def _ctx_pick_from(self, st, pool, act, key):
    rng = rng_for(st.run_seed, "monster", act, key, st.stats["battles"])  # 이벤트 난수와 분리
    if self.monster_select == "independent":
        return rng.choice(pool)
    bags = st.__dict__.setdefault("_monster_bags", {})
    bag = bags.get((act, key))
    if not bag:
        bag = list(pool)
        rng.shuffle(bag)
        bags[(act, key)] = bag
    return bag.pop()


def _ctx_pick_monster(self, st, tier, act):
    nxt = st.__dict__.pop("_next_monster", None)     # 게임 규칙으로 이미 정한 일반 전투 몬스터
    if nxt is not None:
        return nxt
    return _ctx_pick_from(self, st, self.monsters[(act, tier)], act, tier)


def _ctx_pick_encounter(self, st, act, room):
    """게임 MonsterSelector 규칙의 일반 전투 몬스터 (room = 게임 roomIndex, 0부터)."""
    rules = self.encounter_rules
    for r in rules.get("fixed") or ():
        if int(r.get("act", 0)) == act and int(r.get("room", -1)) == room:
            return self.monster_by_id[r["id"]]
    for r in rules.get("easy_rooms") or ():
        if int(r.get("act", 0)) == act and room in [int(x) for x in r.get("rooms") or ()]:
            return _ctx_pick_from(self, st, self.monsters[(act, "easy")], act, "easy")
    return _ctx_pick_from(self, st, self.battle_pool[act] or self.monsters[(act, "normal")], act, "battle")


def _ctx_new_monster_state(self, mon):
    return {"i": 0, "uses": {}}


def _ctx_monster_intent(self, mon, state, rng, extra_skip):
    """패턴 AI: static = 순서대로 순환(사용 불가 패턴은 건너뜀), random = 사용 가능한 것 중 무작위.
    반환: (kind, multi, str_units)."""
    pats = mon["patterns"]
    ok = [k for k, p in enumerate(pats) if p.get("max_uses") is None or state["uses"].get(p["key"], 0) < p["max_uses"]]
    if extra_skip > 0 and rng.random() < extra_skip:
        return "skip", False, 0
    if not ok:
        return "attack", False, 0   # 사용 가능한 패턴 없음 → 2_Single 대체 (게임 규칙)
    if mon.get("ai") == "random":
        k = rng.choice(ok)
    else:
        n = len(pats)
        k = next((j % n for j in range(state["i"], state["i"] + n) if j % n in ok), ok[0])
        state["i"] = k + 1
    p = pats[k]
    state["uses"][p["key"]] = state["uses"].get(p["key"], 0) + 1
    return p["kind"], bool(p.get("multi")), int(p.get("str_units", 1))


SimContext._load_monsters = _ctx_load_monsters
SimContext.pick_monster = _ctx_pick_monster
SimContext.pick_encounter = _ctx_pick_encounter
SimContext.new_monster_state = _ctx_new_monster_state
SimContext.monster_intent = _ctx_monster_intent


def _when_ok(when, turn, base):
    if not when:
        return True
    if "turn_eq" in when and turn != when["turn_eq"]:
        return False
    if "turn_ge" in when and turn < when["turn_ge"]:
        return False
    if "turn_mod" in when:
        m, r = when["turn_mod"]
        if turn % m != r:
            return False
    if "base_same_digits" in when:
        s = str(abs(int(base)))
        if (len(s) > 1 and len(set(s)) == 1) != bool(when["base_same_digits"]):
            return False
    return True


class Fx:
    """보유 환상(개수 포함)의 효과를 타입별로 모은 것. 획득할 때마다 add() 로 늘린다."""

    __slots__ = ("table", "by_type", "s", "p")

    def __init__(self, table, counts=None, order=()):
        self.table = table
        self.by_type, self.s, self.p = {}, {}, {}
        for fid in order:
            c = (counts or {}).get(fid, 0)
            if c > 0:
                self.add(fid, c)

    def add(self, fid, c=1):
        for ef in self.table.get(fid, {}).get("effects", ()):
            t = ef["type"]
            self.by_type.setdefault(t, []).append((ef, c))
            if ef.get("when") or ef.get("per"):
                continue
            if t in PRODUCT_TYPES:
                self.p[t] = self.p.get(t, 1.0) * ef.get("value", 1.0) ** c
            else:
                self.s[t] = self.s.get(t, 0) + ef.get("value", 1) * c
        return self

    def copy(self):
        o = Fx(self.table)
        o.by_type = {k: list(v) for k, v in self.by_type.items()}
        o.s, o.p = dict(self.s), dict(self.p)
        return o

    def sum(self, t):
        return self.s.get(t, 0)

    def prod(self, t):
        return self.p.get(t, 1.0)

    def has(self, t):
        return t in self.by_type

    def items(self, t):
        return self.by_type.get(t, ())


class LazyRng:
    """처음 쓸 때만 시드를 만드는 난수 (시드 생성 비용 절약)."""

    __slots__ = ("parts", "_r")

    def __init__(self, *parts):
        self.parts, self._r = parts, None

    def __getattr__(self, name):
        if self._r is None:
            self._r = rng_for(*self.parts)
        return getattr(self._r, name)


# ---------------------------------------------------------------------------
# 런 상태
# ---------------------------------------------------------------------------
class RunState:
    def __init__(self, cfg, pool, ctx=None, run_seed=""):
        self.hp = cfg["player"]["start_hp"]
        self.fant = {g: 0 for g in GRADES}
        self.pool = pool
        self.owned = []          # 획득 순서 그대로 (효과 발동 순서). 풀에서 새로 얻은 환상만 기록
        self.owned_set = set()   # 한 번이라도 얻은 환상 → 보상/상점 후보에서 제외
        self.matches = cfg["items"]["start_matches"]
        self.erasers = cfg["items"]["start_erasers"]
        self.normal_battles = 0
        self.stats = {
            "battles": 0, "elites": 0, "bosses_killed": 0, "rests": 0, "shops": 0,
            "turns": 0, "dmg_taken": 0, "hp_healed": 0, "hp_spent_shop": 0,
            "items_used": 0, "items_bought": 0, "fantasies_bought": 0,
        }
        self.escapes = 0         # v4: 카운트다운 도주 (보상 없이 진행)
        # table 모드 전용
        self.ctx = ctx
        self.run_seed = run_seed
        self.table_mode = ctx is not None and ctx.mode == "table"
        self.counts = {}         # 현재 보유 개수 (복사본 포함, 조합 재료는 0이 됨)
        self.copies = 0          # 복사/중복으로 생긴 추가 개수
        self.voided = 0          # 획득 무효 횟수 (사자자리 등)
        self.acquire_n = 0
        self.fx = Fx(ctx.table) if self.table_mode else None
        self.src = {"reward": 0, "shop": 0, "forced": 0}   # 출처별 획득 수 (휴식 대체 획득은 reward 로 셈)
        self.ember = {"white": 0, "blue": 0, "slots": 0, "blue_offers": 0, "blue_picked": 0, "blue_wasted": 0}
        self.slot = []           # 불씨 슬롯 (색 목록), 층·막을 넘어 유지
        self.pos = (0, 0)        # (막, 층) — 불씨 난수 스트림용
        self.normal_wins = 0
        self.fbf = None          # 층별 보유 환상 수 기록 list (요청 시)
        self.trace = None        # 트레이스 모드면 이벤트 list (F7)
        self.battle_log = None   # 몬스터별 지표 수집 시 list (F2)

    def unowned(self, grade):
        return [f for f in self.pool[grade] if f not in self.owned_set]

    def gain_fantasy(self, grade, name):
        self.owned.append(name)
        self.owned_set.add(name)
        self.fant[grade] += 1
        self.counts[name] = self.counts.get(name, 0) + 1
        if self.fx is not None:
            self.fx.add(name, 1)

    # --- table 모드 ---
    def refresh_fx(self):
        if self.table_mode:
            order = list(dict.fromkeys(self.owned + [k for k in self.counts if k not in self.owned_set]))
            self.fx = Fx(self.ctx.table, self.counts, order)

    def fx_rng(self, *parts):
        """효과 전용 난수 스트림. 이벤트 스트림을 건드리지 않아 짝지은 비교가 덜 흔들린다."""
        return LazyRng(self.run_seed, "fx", *parts)

    def acquire(self, grade, name, source="reward"):
        """환상 획득. grade 모드에서는 gain_fantasy 와 같다."""
        skey = source if source in self.src else "reward"
        if not self.table_mode:
            self.gain_fantasy(grade, name)
            self.src[skey] += 1
            return
        self.acquire_n += 1
        if self.trace is not None:
            self.trace.append({"ev": "acquire", "fid": name, "source": source, "hp": self.hp})
        rng = self.fx_rng("acquire", name)  # 이름 기준: 앞선 획득 이력이 달라도 같은 환상이면 같은 난수
        dup = False
        if source != "forced":
            for ef, c in self.fx.items("acquire_dup_or_void"):
                if rng.random() < ef.get("chance", 0.5):
                    dup = True
                else:
                    self.voided += 1
                    if self.trace is not None:
                        self.trace.append({"ev": "acquire_void", "fid": name})
                    self.owned_set.add(name)  # 이번 획득 기회는 소모 (같은 보상에서 다시 나오지 않음)
                    return
        self.gain_fantasy(grade, name)
        self.src[skey] += 1
        rebuild = False
        if dup:
            self.counts[name] += 1
            self.copies += 1
            self.fx.add(name, 1)
        entry = self.ctx.table.get(name, {})
        for ef in entry.get("effects", ()):
            t = ef["type"]
            if t == "on_acquire_heal":
                heal = round(ef.get("value", 0) + ef.get("pct", 0) * max(self.hp, 0))
                self.hp += heal
                self.stats["hp_healed"] += heal
            elif t == "on_acquire_copy_owned":
                others = [k for k in self.owned if k != name and self.counts.get(k, 0) > 0]
                if others:
                    pick = rng.choice(others)
                    self.counts[name] -= 1
                    self.counts[pick] += 1
                    self.copies += 1
                    rebuild = True
        # 조합
        for result, parts in self.ctx.combos:
            if result not in self.owned_set and result not in self.ctx.banned \
                    and all(self.counts.get(p, 0) > 0 for p in parts):
                for p in parts:
                    self.counts[p] = 0
                self.gain_fantasy(self.ctx.grade_of[result], result)
                rebuild = True
        if rebuild:
            self.refresh_fx()


# ---------------------------------------------------------------------------
# 맵 생성
# ---------------------------------------------------------------------------
def weighted_pick(rng, weights):
    total = sum(weights.values())
    r = rng.random() * total
    acc = 0.0
    for k, w in weights.items():
        acc += w
        if r < acc:
            return k
    return k


def generate_map(cfg, run_seed, act):
    M = cfg["map"]
    rng = rng_for(run_seed, act, "map")
    floors = []
    for f in range(1, FLOORS_PER_ACT + 1):
        if f == FLOORS_PER_ACT:
            cols = [1]
        else:
            n = rng.randint(M["min_nodes"], M["max_nodes"])
            cols = sorted(rng.sample([0, 1, 2], n))
        floors.append([{"idx": i, "col": c, "type": None, "children": [], "parents": []}
                       for i, c in enumerate(cols)])

    # 인접 노드끼리만 연결, 고립 노드 방지
    for f in range(FLOORS_PER_ACT - 1):
        cur, nxt = floors[f], floors[f + 1]
        for a in cur:
            a["children"] = [b["idx"] for b in nxt if abs(a["col"] - b["col"]) <= 1]
            if not a["children"]:
                nearest = min(nxt, key=lambda b: abs(a["col"] - b["col"]))
                a["children"].append(nearest["idx"])
        for b in nxt:
            if not any(b["idx"] in a["children"] for a in cur):
                nearest = min(cur, key=lambda a: abs(a["col"] - b["col"]))
                nearest["children"].append(b["idx"])
        for a in cur:
            for j in a["children"]:
                nxt[j]["parents"].append(a["idx"])

    # 노드 타입
    shop_seen = False
    for f in range(1, FLOORS_PER_ACT + 1):
        layer = floors[f - 1]
        for node in layer:
            if f == FLOORS_PER_ACT:
                node["type"] = "boss"
                continue
            if f <= M["fixed_battle_floors"]:
                node["type"] = "battle"
                continue
            parent_types = {floors[f - 2][p]["type"] for p in node["parents"]} if f > 1 else set()
            allowed = {k: w for k, w in M["weights"].items()
                       if not (k in SPECIAL_NODES and k in parent_types)}
            node["type"] = weighted_pick(rng, allowed)
        if f == M["forced_shop_floor"] and not shop_seen:
            cand = [n for n in layer if not any(floors[f - 2][p]["type"] == "shop" for p in n["parents"])]
            rng.choice(cand or layer)["type"] = "shop"
        if any(n["type"] == "shop" for n in layer):
            shop_seen = True
    return floors


# --- 맵 캐시 (v2 S2): 맵은 (run_seed, 막, 맵 설정)에만 의존하므로 프로세스 안에서 재사용한다.
# 노드는 (idx, type, children) 튜플로 압축해 저장하고, LRU 상한으로 메모리를 묶는다.
MAP_CACHE_MAX = 24000          # 막 단위 항목 수 (시드 8000개분). 항목당 약 3KB → 워커당 약 70MB 이내
_MAP_CACHE = {}


def compact_map(floors):
    return tuple(tuple((n["idx"], n["type"], tuple(n["children"])) for n in layer) for layer in floors)


def get_map(cfg, run_seed, act, map_key=None):
    """generate_map 과 같은 맵을 압축 튜플로 돌려준다 (결과 동일, 캐시 사용)."""
    if map_key is None:
        map_key = json.dumps(cfg["map"], sort_keys=True)
    key = (map_key, run_seed, act)
    m = _MAP_CACHE.get(key)
    if m is None:
        m = compact_map(generate_map(cfg, run_seed, act))
        if len(_MAP_CACHE) >= MAP_CACHE_MAX:
            # 가장 오래 넣은 항목부터 제거 (dict 삽입 순서). 같은 시드를 연달아 쓰는 접근 패턴에 맞춘 단순 FIFO.
            for k in list(_MAP_CACHE)[: MAP_CACHE_MAX // 4]:
                del _MAP_CACHE[k]
        _MAP_CACHE[key] = m
    return m


def choose_node(cfg, st, options, rng):
    """options: 압축 노드 튜플 (idx, type, children). rng 는 선택지가 2개 이상일 때만 쓰인다."""
    pol = cfg["policy"]
    if pol["path"] == "random" or len(options) == 1:
        return rng.choice(options)
    hp = st.hp

    def score(n):
        t = n[1]
        if t == "rest":
            s = 3.0 if hp < pol["rest_below_hp"] else 0.5
        elif t == "elite":
            s = 2.0 if hp >= pol["elite_above_hp"] else -1.0
        elif t == "shop":
            s = 2.5 if hp >= pol["shop_above_hp"] else 0.0
        else:
            s = 1.0
        return s + rng.random() * 0.01

    return max(options, key=score)


# ---------------------------------------------------------------------------
# 전투
# ---------------------------------------------------------------------------
def fight(cfg, st, tier, act, rng):
    P, pol, F = cfg["player"], cfg["policy"], cfg["fantasy"]
    t = cfg["monsters"]["tiers"][tier]
    sc = cfg["monsters"]["act_scale"][act - 1]
    skill = P["skill"]

    M = cfg["monsters"]
    if M.get("hp_model", "manual") == "ratio":
        hp_mean = M["hp_base"] * M["tier_hp_ratio"][tier] * M["act_hp_growth"] ** (act - 1)
    else:
        hp_mean = t["hp_mean"] * sc["hp"]
    mhp = max(1, round(rng.gauss(hp_mean, hp_mean * t["hp_cv"])))
    mstr = 0
    dmg_mult = 1.0 + sum(F["dmg_bonus"][g] * st.fant[g] for g in GRADES)
    def_cut = min(F["def_cap"], sum(F["def_bonus"][g] * st.fant[g] for g in GRADES))

    for turn in range(1, cfg["sim"]["max_turns"] + 1):
        st.stats["turns"] += 1
        # --- 몬스터 의도 (화면에 보이는 수식)
        r = rng.random()
        per_hit, hits = 0, 0
        if r < t["skip_chance"]:
            kind = "skip"
        elif r < t["skip_chance"] + t["str_chance"]:
            kind = "str"
        else:
            kind = "attack"
            dm = t["dmg_mean"] * sc["dmg"]
            per_hit = max(1, round(rng.gauss(dm, dm * t["dmg_cv"]))) + mstr
            if rng.random() < t["multi_chance"]:
                hits = rng.randint(2, max(2, t["multi_hits_max"]))
            else:
                hits = 1

        def incoming():
            return max(0, round(per_hit * (1 - def_cut))) * hits if kind == "attack" else 0

        # --- 플레이어 수식 (타수 1 고정)
        base = rng.randint(P["base_dmg_min"], P["base_dmg_max"])
        pdmg = float(base)
        moves = P["moves_per_turn"]

        # --- 아이템 = 추가 이동
        inv = st.matches + st.erasers
        if inv and pol["use_items"] != "never":
            inc = incoming()
            if pol["use_items"] == "always" or (inc > 0 and inc >= st.hp * pol["danger_ratio"]):
                n = min(inv, pol["max_items_per_turn"])
                for _ in range(n):
                    if st.erasers and (inc > 0 or not st.matches):
                        st.erasers -= 1
                    else:
                        st.matches -= 1
                moves += n
                st.stats["items_used"] += n

        # --- 성냥개비 이동 배분
        for _ in range(moves):
            if pdmg * dmg_mult >= mhp:
                break  # 이미 처치 가능 → 몬스터는 행동하지 못함
            inc = incoming()
            if inc == 0:
                do_def = False
            elif inc >= st.hp or inc >= st.hp * pol["danger_ratio"]:
                do_def = True
            else:
                do_def = rng.random() >= pol["offense_bias"]
            if do_def:
                if hits > 1 and rng.random() < P["zero_hits_chance"] * skill:
                    hits = 0
                else:
                    cut = min(1.0, skill * rng.uniform(0, 2 * P["defense_cut_per_move"]))
                    per_hit = max(0, round(per_hit * (1 - cut)))
            else:
                pdmg += base * skill * rng.uniform(0, 2 * P["attack_gain_per_move"])

        # --- 턴 처리: 플레이어 → 몬스터
        mhp -= max(0, round(pdmg * dmg_mult))
        if mhp <= 0:
            return "win"
        if kind == "str":
            mstr += t["str_amount"]
        elif kind == "attack":
            d = incoming()
            st.hp -= d
            st.stats["dmg_taken"] += d
            if st.hp <= 0:
                return "death"
    return "timeout"


# ---------------------------------------------------------------------------
# 전투 (table 모드) — fight() 와 같은 골격에 환상별 효과를 끼워 넣은 것.
# grade 모드 결과를 바꾸지 않도록 별도 함수로 둔다.
# ---------------------------------------------------------------------------
def _digits_map(n, fn):
    n = int(n)
    return int("".join(str(fn(int(d))) for d in str(abs(n)))) if n else 0


def transform_base(base, fx):
    for ef, c in fx.items("base_dmg_transform"):
        op, v = ef["op"], ef.get("value", 0)
        for _ in range(c):
            if op == "mult":
                base = int(base * v)
            elif op == "digit_min":
                base = _digits_map(base, lambda d: max(d, int(v)))
            elif op == "first_digit":
                s = str(int(base))
                base = int(str(int(v)) + s[1:]) if base > 0 else int(v)
            elif op == "odd_even":
                base = int(base * ef.get("odd_mult", 2)) if base % 2 else int(ef.get("even_value", 0))
            elif op == "zero_set":
                base = int(v) if base == 0 else base
            else:
                raise ValueError(f"base_dmg_transform op 알 수 없음: {op}")
    return base


def _consecutive_pairs(*nums):
    n = 0
    for x in nums:
        s = str(abs(int(x)))
        n += sum(1 for a, b in zip(s, s[1:]) if int(b) == int(a) + 1)
    return n


def fx_contributors(st, extra=None):
    """트레이스용: 효과 타입별로 어느 환상이 어떤 값을 주는지 (보유 개수 반영)."""
    out = {}
    order = list(dict.fromkeys(st.owned))
    pairs = [(fid, st.counts.get(fid, 0)) for fid in order] + ([(extra, 1)] if extra else [])
    for fid, c in pairs:
        if c <= 0:
            continue
        for ef in st.ctx.table.get(fid, {}).get("effects", ()):
            d = {k: v for k, v in ef.items() if k not in ("type", "src")}
            out.setdefault(ef["type"], []).append({"fid": fid, "count": c, **d})
    return out


def fight_table(cfg, st, tier, act, rng):
    P, pol, F = cfg["player"], cfg["policy"], cfg["fantasy"]
    t = cfg["monsters"]["tiers"][tier]
    sc = cfg["monsters"]["act_scale"][act - 1]
    skill = P["skill"]
    M = cfg["monsters"]
    frng = st.fx_rng("battle", st.stats["battles"])
    tr = st.trace  # None 이면 트레이스 끔 (핫 루프에서는 이 지역 변수만 검사)

    fx = st.fx
    temp_copy = None
    # 도장류: 전투 시작 시 보유 환상 하나의 임시 복사본
    if fx.has("battle_start_temp_copy"):
        cands = [k for k in st.owned if st.counts.get(k, 0) > 0 and not any(
            ef["type"] == "battle_start_temp_copy" for ef in st.ctx.table.get(k, {}).get("effects", ()))]
        if cands:
            temp_copy = frng.choice(cands)
            fx = fx.copy().add(temp_copy, 1)

    mon = None
    if M.get("model", "tier_avg") == "table":
        mon = st.ctx.pick_monster(st, tier, act)
        mhp0 = max(1, round(mon["hp"] * M.get("hp_scale", 1.0)))
    else:
        if M.get("hp_model", "manual") == "ratio":
            hp_mean = M["hp_base"] * M["tier_hp_ratio"][tier] * M["act_hp_growth"] ** (act - 1)
        else:
            hp_mean = t["hp_mean"] * sc["hp"]
        mhp0 = max(1, round(rng.gauss(hp_mean, hp_mean * t["hp_cv"])))

    # --- 전투 동안 변하지 않는 값 (v2 S5: 루프 밖으로). 난수 소비 순서는 v1 과 같다.
    dmg_mult = 1.0 + fx.sum("dmg_mult_add")
    def_cut = min(F["def_cap"], fx.sum("def_cut_add"))
    flat_plain = sum(ef.get("value", 0) * c * (act if ef.get("act_scaling") else 1)
                     for ef, c in fx.items("dmg_flat") if not ef.get("when"))
    flat_when = [(ef, c) for ef, c in fx.items("dmg_flat") if ef.get("when")]
    taken_flat = fx.sum("dmg_taken_flat")
    taken_mult = [(ef.get("condition"), ef["value"] ** c) for ef, c in fx.items("dmg_taken_mult")]
    delay_frac = min(1.0, fx.sum("dmg_taken_delay"))
    moves_base = P["moves_per_turn"] * fx.prod("moves_per_turn_mult") + fx.sum("moves_per_turn_add")
    start_moves = int(fx.sum("battle_start_moves"))
    skip_chance = t["skip_chance"] + fx.sum("monster_skip_chance_add")
    str_chance_hi = skip_chance + t["str_chance"]
    dm = t["dmg_mean"] * sc["dmg"]
    dm_sd = dm * t["dmg_cv"]
    multi_chance, multi_max = t["multi_chance"], max(2, t["multi_hits_max"])
    str_amount = t["str_amount"]
    str_add = list(fx.items("monster_str_add"))
    digit_max = [int(ef["value"]) for ef, c in fx.items("monster_dmg_digit_max")]
    has_transform = fx.has("base_dmg_transform")
    pstr_list = list(fx.items("player_str_add"))
    hits_plain = sum(int(ef.get("value", 0)) * c for ef, c in fx.items("hits_add")
                     if not ef.get("when") and not ef.get("per"))
    hits_other = [(ef, c) for ef, c in fx.items("hits_add") if ef.get("when") or ef.get("per")]
    final_list = [(ef.get("condition"), ef["value"] ** c) for ef, c in fx.items("dmg_final_mult")]
    etd_list = [(ef.get("when"), ef.get("per"), ef.get("value", 0), c) for ef, c in fx.items("end_turn_dmg")]
    has_combo = fx.has("combo_same_dmg_stack")
    combo_step = int(fx.sum("combo_same_dmg_stack"))
    heal_deal = int(fx.sum("heal_on_deal"))
    heal_unused = fx.sum("heal_per_unused_move")
    carry_on = bool(fx.sum("carry_unused_moves"))
    reflect = [(ef.get("value", 0), ef.get("pct", 0), c) for ef, c in fx.items("reflect_on_hit")]
    heal_take = [(ef.get("per", 100), ef.get("value", 0), c) for ef, c in fx.items("heal_on_take")]
    enemy_first = fx.sum("enemy_acts_first") > 0
    mirror_str = fx.sum("mirror_enemy_str")
    refund_chance = min(1.0, fx.sum("item_use_refund_chance"))
    revives = int(fx.sum("revive_once"))
    has_etd = bool(etd_list)
    use_items, danger, max_items = pol["use_items"], pol["danger_ratio"], pol["max_items_per_turn"]
    offense_bias = pol["offense_bias"]
    zero_hits_p = P["zero_hits_chance"] * skill
    def_span, att_span = 2 * P["defense_cut_per_move"], 2 * P["attack_gain_per_move"]
    bmin, bmax = P["base_dmg_min"], P["base_dmg_max"]
    max_turns = cfg["sim"]["max_turns"]
    stats = st.stats
    hp_start, items_start = st.hp, (st.matches, st.erasers)
    taken0 = stats["dmg_taken"]
    if tr is not None:
        tr.append({"ev": "battle", "tier": tier, "act": act, "monster": mon["id"] if mon else f"{tier}(평균)",
                   "mhp": mhp0, "hp": st.hp, "temp_copy": temp_copy, "fx": fx_contributors(st, temp_copy)})

    def per_hit_in(kind, per_hit, mon_base, base):
        if kind != "attack":
            return 0
        v = max(0, round(per_hit * (1 - def_cut)) + taken_flat)
        for cond, factor in taken_mult:
            if cond == "monster_dmg_ge_player_base" and not mon_base >= base:
                continue
            v = int(v * factor)
        return v

    mon_str0 = (mon.get("strength") or 0) * str_amount if mon is not None else 0   # 몬스터 기본 힘 (원본은 모두 0)
    while True:
        mhp = mhp0
        mstr = mon_str0
        pstr = 0              # 내 힘 (1 = 1타당 피해 +1, 몬스터 힘과 같은 단위)
        str_blocks = int(fx.sum("str_block"))
        temp_items = int(fx.sum("battle_temp_items"))
        items_used_battle = 0
        carry = 0
        bleed = 0             # 지연된 받는 피해
        prev_hit, combo = None, 0
        outcome = "timeout"
        max_hit = 0
        taken_turn = 0
        mon_state = st.ctx.new_monster_state(mon) if mon is not None else None

        def monster_acts(kind, per_hit, hits, mon_base, base, str_gain):
            """몬스터 행동. 반환: 'death' / 'win'(반사로 처치) / None"""
            nonlocal mstr, pstr, str_blocks, bleed, mhp, taken_turn
            if kind == "str":
                if str_blocks > 0:
                    str_blocks -= 1
                else:
                    mstr += str_gain
                    pstr += str_gain * mirror_str
            elif kind == "attack":
                d = per_hit_in(kind, per_hit, mon_base, base)
                for _ in range(hits):
                    if d <= 0:
                        break
                    now = d - int(d * delay_frac)
                    bleed += d - now
                    st.hp -= now
                    stats["dmg_taken"] += now
                    taken_turn += now
                    for rv, rp, c in reflect:
                        mhp -= int((rv + rp * d) * c)
                    for hper, hv, c in heal_take:
                        h = int(d // hper) * hv * c
                        st.hp += h
                        stats["hp_healed"] += h
                    if st.hp <= 0:
                        return "death"
                if mhp <= 0:
                    return "win"
            return None

        for turn in range(1, max_turns + 1):
            stats["turns"] += 1
            taken_turn = 0
            # --- 몬스터 의도
            per_hit, hits = 0, 0
            str_gain = str_amount
            if mon is None:
                r = rng.random()
                if r < skip_chance:
                    kind = "skip"
                elif r < str_chance_hi:
                    kind = "str"
                else:
                    kind = "attack"
                    str_mod = sum(ef.get("value", 0) * c for ef, c in str_add
                                  if _when_ok(ef.get("when"), turn, 0)) if str_add else 0
                    per_hit = max(0, max(1, round(rng.gauss(dm, dm_sd))) + mstr + str_mod)
                    for v in digit_max:
                        per_hit = _digits_map(per_hit, lambda d, v=v: min(d, v))
                    if rng.random() < multi_chance:
                        hits = rng.randint(2, multi_max)
                    else:
                        hits = 1
            else:
                kind, multi, str_units = st.ctx.monster_intent(mon, mon_state, rng, skip_chance - t["skip_chance"])
                str_gain = str_amount * str_units
                if kind == "attack":
                    str_mod = sum(ef.get("value", 0) * c for ef, c in str_add
                                  if _when_ok(ef.get("when"), turn, 0)) if str_add else 0
                    per_hit = max(0, max(1, round(rng.gauss(dm, dm_sd))) + mstr + str_mod)
                    for v in digit_max:
                        per_hit = _digits_map(per_hit, lambda d, v=v: min(d, v))
                    hits = rng.randint(2, multi_max) if multi else 1
            mon_base = per_hit
            if per_hit > max_hit:
                max_hit = per_hit

            # --- 내 수식
            base = rng.randint(bmin, bmax)
            if has_transform:
                base = transform_base(base, fx)

            # 내 힘 증가: when 이 없으면 전투 첫 턴 시작 시 1회, 있으면 조건이 맞는 턴 시작 시
            for ef, c in pstr_list:
                if (ef.get("when") and _when_ok(ef["when"], turn, base)) or (not ef.get("when") and turn == 1):
                    pstr += ef.get("value", 0) * c

            p_hits = 1 + hits_plain
            for ef, c in hits_other:
                if not _when_ok(ef.get("when"), turn, base):
                    continue
                per = ef.get("per")
                if per == "items_held":
                    p_hits += int((st.matches + st.erasers + temp_items) // ef.get("divisor", 10)) * c
                elif per == "consecutive_pairs":
                    p_hits += _consecutive_pairs(base, mon_base) * c
                else:
                    p_hits += int(ef.get("value", 0)) * c
            flat = flat_plain + pstr + sum(ef.get("value", 0) * c for ef, c in flat_when
                                           if _when_ok(ef["when"], turn, base))
            final_mult = 1.0
            for cond, factor in final_list:
                if cond == "base_eq_monster_dmg" and base != mon_base:
                    continue
                final_mult *= factor

            def end_turn_dmg():
                total = 0
                for w, per, v, c in etd_list:
                    if not _when_ok(w, turn, base):
                        continue
                    if per == "items_held":
                        v *= st.matches + st.erasers + temp_items
                    elif per == "items_used_battle":
                        v *= items_used_battle
                    elif per == "hp":
                        v *= max(0, st.hp)
                    elif per == "digit8":
                        v *= (str(base) + str(mon_base)).count("8")
                    total += v * c
                return int(total)

            pdmg = float(base)
            etd = end_turn_dmg() if has_etd else 0

            moves = int(moves_base) + carry + (start_moves if turn == 1 else 0)
            carry = 0

            # --- 아이템 = 추가 이동 (임시 소모품 먼저)
            n_items = 0
            inv = st.matches + st.erasers + temp_items
            if inv and use_items != "never":
                inc = per_hit_in(kind, per_hit, mon_base, base) * hits
                if use_items == "always" or (inc > 0 and inc >= st.hp * danger):
                    n_items = n = min(inv, max_items)
                    for _ in range(n):
                        if temp_items:
                            temp_items -= 1
                        elif st.erasers and (inc > 0 or not st.matches):
                            st.erasers -= 1
                            if refund_chance and frng.random() < refund_chance:
                                st.erasers += 1
                        else:
                            st.matches -= 1
                            if refund_chance and frng.random() < refund_chance:
                                st.matches += 1
                    moves += n
                    stats["items_used"] += n
                    items_used_battle += n

            # --- 성냥개비 이동 배분
            used = n_att = 0
            for _ in range(moves):
                one = max(0, round(pdmg * dmg_mult) + flat)
                if int(one * final_mult) * p_hits + etd >= mhp:
                    break
                used += 1
                inc = per_hit_in(kind, per_hit, mon_base, base) * hits
                if inc == 0:
                    do_def = False
                elif inc >= st.hp or inc >= st.hp * danger:
                    do_def = True
                else:
                    do_def = rng.random() >= offense_bias
                if do_def:
                    if hits > 1 and rng.random() < zero_hits_p:
                        hits = 0
                    else:
                        cut = min(1.0, skill * rng.uniform(0, def_span))
                        per_hit = max(0, round(per_hit * (1 - cut)))
                else:
                    n_att += 1
                    pdmg += base * skill * rng.uniform(0, att_span)
            unused = moves - used
            mhp_before, hp_before = mhp, st.hp
            etd_real = 0
            res = None

            if enemy_first:
                res = monster_acts(kind, per_hit, hits, mon_base, base, str_gain)

            if res is None:
                # --- 내 공격 (타수만큼, 0 이하 피해는 타격으로 치지 않음)
                one = max(0, round(pdmg * dmg_mult) + flat)
                for _ in range(p_hits):
                    d = int(one * final_mult)
                    if has_combo:
                        if prev_hit is not None and d == prev_hit:
                            combo += combo_step
                        else:
                            combo = 0
                        prev_hit = d
                        d += combo
                    if d <= 0:
                        continue
                    mhp -= d
                    if heal_deal:
                        st.hp += heal_deal
                        stats["hp_healed"] += heal_deal
                # --- 내 턴 종료
                if has_etd:
                    etd_real = end_turn_dmg()
                    mhp -= etd_real
                h = int(heal_unused * unused)
                if h:
                    st.hp += h
                    stats["hp_healed"] += h
                if carry_on:
                    carry = unused
                if mhp <= 0:
                    res = "win"
                elif bleed:  # 지연된 피해는 전투가 이어질 때만 (처치하면 사라짐)
                    st.hp -= bleed
                    stats["dmg_taken"] += bleed
                    taken_turn += bleed
                    bleed = 0
                    if st.hp <= 0:
                        res = "death"
                if res is None and not enemy_first:
                    res = monster_acts(kind, per_hit, hits, mon_base, base, str_gain)
            if tr is not None:
                tr.append({"ev": "turn", "t": turn, "intent": kind, "mon_dmg": mon_base, "hits": hits,
                           "base": base, "moves": moves, "att": n_att, "def": used - n_att, "items": n_items,
                           "p_hits": p_hits, "flat": flat, "final_mult": final_mult,
                           "dealt": mhp_before - mhp, "etd": etd_real, "taken": taken_turn,
                           "hp_change": st.hp - hp_before, "hp": st.hp, "mhp": mhp, "end": res})
            if res:
                outcome = res
                break

        if st.battle_log is not None:
            st.battle_log.append({"monster": mon["id"] if mon else tier, "tier": tier, "act": act,
                                  "turns": turn, "taken": stats["dmg_taken"] - taken0, "outcome": outcome,
                                  "max_hit": int(max_hit), "floor": (getattr(st, "floor_pos", None) or (None, None))[1]})
        if outcome == "death" and revives > 0:
            # 게자리류: 전투 시작 시점으로 되감기 (전투당 횟수 제한)
            revives -= 1
            st.hp = hp_start
            st.matches, st.erasers = items_start
            if tr is not None:
                tr.append({"ev": "rewind"})
            continue
        if tr is not None:
            tr.append({"ev": "battle_end", "outcome": outcome, "hp": st.hp, "turns": turn})
        return outcome


# ---------------------------------------------------------------------------
# 휴식 / 상점
# ---------------------------------------------------------------------------
def do_rest(cfg, st, act, rng):
    R, skill = cfg["rest"], cfg["player"]["skill"]
    fx = st.fx
    if fx is not None:
        # 커피류: 체력이 충분하면 회복 대신 미보유 환상 1개
        for ef, c in fx.items("rest_alt_fantasy"):
            g = ef.get("grade", "white")
            cands = st.unowned(g)
            if cands and st.hp >= cfg["policy"]["rest_below_hp"]:
                st.acquire(g, rng.choice(cands), "rest")
                st.stats["rests"] += 1
                return
    uses = 1 + (int(fx.sum("rest_extra_uses")) if fx is not None else 0)
    for _ in range(uses):
        base = rng.randint(R["heal_min"], R["heal_max"]) * R["act_scale"][act - 1]
        heal = base
        for _ in range(R["moves"]):
            heal += base * skill * rng.uniform(0, 2 * R["edit_gain_per_move"])
        if fx is not None:
            heal = heal * fx.prod("rest_heal_mult") + fx.sum("rest_heal_add")
        heal = round(heal)
        st.hp += heal
        st.stats["hp_healed"] += heal
    st.stats["rests"] += 1


def edit_price(cfg, price, moves, rng):
    S, skill = cfg["shop"], cfg["player"]["skill"]
    p = price
    for _ in range(moves):
        if p >= 10 and rng.random() < S["digit_drop_chance"] * skill:
            p = p % (10 ** (len(str(int(p))) - 1))  # 맨 앞자리 제거
        else:
            p = p * (1 - skill * rng.uniform(0, 2 * S["discount_per_move"]))
    return max(1, round(p))


def gain_items(st, matches=0, erasers=0):
    bonus = int(st.fx.sum("item_gain_bonus")) if st.fx is not None else 0
    if matches:
        st.matches += matches + bonus
    if erasers:
        st.erasers += erasers + bonus


def do_shop(cfg, st, rng):
    S, pol, F = cfg["shop"], cfg["policy"], cfg["fantasy"]
    fx = st.fx
    keep = pol["shop_keep_hp"]
    moves = S["moves"]
    price_mult = 1.0
    st.stats["shops"] += 1
    if fx is not None:
        h = int(fx.sum("shop_enter_heal"))
        st.hp += h
        st.stats["hp_healed"] += h
        moves += int(fx.sum("shop_moves_add"))
        price_mult = fx.prod("shop_price_mult")

    def final_price(price, moves):
        final = edit_price(cfg, price, moves, rng) if moves else price
        edited = final != price
        if price_mult != 1.0:
            final = max(1, round(final * price_mult))
        return final, edited

    # 환상: 등급별 1개 진열, 높은 등급부터 고려
    for g in ("red", "blue", "white"):
        cands = st.unowned(g)
        if not cands:
            continue
        offer = rng.choice(cands)
        lo, hi = S["fantasy_price"][g]
        price = rng.randint(lo, hi)
        final, edited = final_price(price, moves)
        if st.hp - final >= keep:
            st.hp -= final
            st.acquire(g, offer, "shop")
            st.stats["hp_spent_shop"] += final
            st.stats["fantasies_bought"] += 1
            if edited:
                moves = 0  # 편집한 상품을 샀으므로 이동 횟수 소진 (리셋 불가)
        # 못 샀으면 리셋 → 이동 횟수 환급

    # 무료 소모품 (끈끈이장갑류)
    free = int(fx.sum("shop_free_items")) if fx is not None else 0
    for _ in range(free):
        st.stats["items_bought"] += 1
        if rng.random() < 0.5:
            gain_items(st, matches=1)
        else:
            gain_items(st, erasers=1)

    # 아이템: 구매마다 가격 재굴림
    for _ in range(pol["max_items_per_shop"]):
        price = rng.randint(S["item_price_min"], S["item_price_max"])
        final, edited = final_price(price, moves)
        if st.hp - final < keep:
            break
        st.hp -= final
        st.stats["hp_spent_shop"] += final
        st.stats["items_bought"] += 1
        if rng.random() < 0.5:
            gain_items(st, matches=1)
        else:
            gain_items(st, erasers=1)
        if edited:
            moves = 0


def pick_offered(cfg, st, offered, rng):
    """보상 3개 중 1개 선택 (policy.fantasy_pick). random 은 v1 과 같은 난수 소비."""
    mode = st.ctx.pick_mode
    if mode == "random":
        return rng.choice(offered)
    vt = st.ctx.value_table
    if mode == "greedy_value":
        return max(offered, key=lambda f: vt.get(f, 0.0))  # 동점이면 먼저 제시된 것
    temp = max(1e-9, float(cfg["policy"].get("softmax_temp", 0.02)))
    vals = [vt.get(f, 0.0) for f in offered]
    top = max(vals)
    w = [math.exp((v - top) / temp) for v in vals]
    r = rng.random() * sum(w)
    acc = 0.0
    for f, x in zip(offered, w):
        acc += x
        if r < acc:
            return f
    return offered[-1]


def ember_reward(cfg, st, rng):
    """불씨 획득 (v3 §7). 색은 전용 난수 스트림 LazyRng(run_seed, "ember", 막, 층) — 이벤트·효과 스트림을 건드리지 않는다.
    슬롯이 완성되면 이벤트 난수(rng)로 후보를 뽑아 현행 보상과 같은 방식으로 환상을 얻는다."""
    E, em = st.ctx.ember, st.ember
    erng = LazyRng(st.run_seed, "ember", st.pos[0], st.pos[1])
    got = []
    if E["blue_mode"] == "replace":
        got.append("blue" if erng.random() < E["blue_chance"] else "white")
    else:
        got.append("white")
        if erng.random() < E["blue_chance"]:
            got.append("blue")
    for c in got:
        em[c] += 1
        st.slot.append(c)
    if st.trace is not None:
        st.trace.append({"ev": "ember", "colors": got, "slot": list(st.slot)})
    size = E["slot_size"]
    while len(st.slot) >= size:
        done, st.slot = st.slot[:size], st.slot[size:]   # 넘친 불씨는 다음 슬롯으로 이월
        em["slots"] += 1
        nb = done.count("blue")
        white = st.unowned("white")
        blue = st.unowned("blue") if nb else []
        offered, pick = [], None
        if nb and not blue:
            em["blue_wasted"] += 1      # 청색 후보가 없어 백색으로 채움
        if nb and blue and E["blue_reward"] == "direct":
            pick = rng.choice(blue)
            offered = [pick]
            em["blue_offers"] += 1
        else:
            c = min(nb, E["blue_offer_cap"], len(blue))
            if c:
                offered += rng.sample(blue, c)
                em["blue_offers"] += 1
            k = min(E["offer_size"] - len(offered), len(white))
            if k > 0:
                offered += rng.sample(white, k)
            if offered:
                pick = pick_offered(cfg, st, offered, rng)
        if st.trace is not None:
            st.trace.append({"ev": "slot_done", "embers": done, "offered": offered, "pick": pick})
        if pick is not None:
            g = st.ctx.grade_of[pick]
            if g == "blue":
                em["blue_picked"] += 1
            st.acquire(g, pick, "reward")


def give_rewards(cfg, st, tier, rng):
    fx = st.fx
    chance = cfg["items"]["drop_chance"]
    if fx is not None:
        h = int(fx.sum("heal_per_battle"))
        st.hp += h
        st.stats["hp_healed"] += h
        chance = min(1.0, (chance + fx.sum("item_drop_chance_add")) * fx.prod("item_drop_mult"))
    g = TIER_GRADE[tier]
    cands = st.unowned(g)
    take_fantasy = True
    RW = st.ctx.normal_reward
    if tier in ("easy", "normal"):
        st.normal_wins += 1
    if RW["mode"] != "fantasy" and tier in ("easy", "normal"):
        if RW["mode"] == "ember":
            take_fantasy = False
            ember_reward(cfg, st, rng)
        elif RW["mode"] == "chance":
            take_fantasy = rng.random() < RW.get("fantasy_chance", 1.0)
        elif RW["mode"] == "choice":
            if st.hp < cfg["policy"]["rest_below_hp"]:
                take_fantasy = False
                heal = int(RW.get("heal_amount", 40))
                st.hp += heal
                st.stats["hp_healed"] += heal
                if st.trace is not None:
                    st.trace.append({"ev": "reward_choice", "pick": "heal", "amount": heal})
            elif not cands:
                take_fantasy = False
                gain_items(st, matches=1, erasers=1)
                if st.trace is not None:
                    st.trace.append({"ev": "reward_choice", "pick": "items"})
    if cands and take_fantasy:
        offered = rng.sample(cands, min(3, len(cands)))  # 3개 중 1개 선택 (policy.fantasy_pick)
        pick = pick_offered(cfg, st, offered, rng)
        if st.trace is not None:
            st.trace.append({"ev": "reward", "offered": offered, "pick": pick})
        st.acquire(g, pick, "reward")
    if rng.random() < chance:
        gain_items(st, matches=1)
    if rng.random() < chance:
        gain_items(st, erasers=1)


# ---------------------------------------------------------------------------
# 런 1회
# ---------------------------------------------------------------------------
def simulate_run(cfg, run_seed, pool=None, ctx=None, trace=None, battle_log=None, fbf=None):
    """판 1회. trace 에 list 를 주면 이벤트 로그를 채운다(F7). battle_log 에 list 를 주면 전투별 기록(F2).
    fbf 에 list 를 주면 층마다 그 층을 마친 뒤의 보유 환상 수를 채운다(v3 §7.4)."""
    if ctx is None:
        ctx = SimContext(cfg, pool)
    st = RunState(cfg, ctx.pool, ctx, run_seed)
    st.trace = trace
    st.battle_log = battle_log
    ember_on = ctx.ember_on
    hp_after = {1: "", 2: "", 3: ""}
    result, end_reason, end_act, end_floor, death_tier = "win", "clear", ACTS, FLOORS_PER_ACT, ""
    fight_fn = fight_table if st.table_mode else fight
    if ctx.damage_model == "digits":
        from sim_service.fight_digits import fight_digits as fight_fn  # noqa: F811

    def give_forced():
        for fid in ctx.forced_ids:
            if fid not in st.counts:  # 이미 얻은 적이 있으면 건너뜀 (획득 무효로 놓친 것은 지급)
                st.acquire(ctx.grade_of[fid], fid, "forced")

    if ctx.forced_ids and ctx.forced_floor == 0:
        give_forced()

    done = False
    for act in range(1, ACTS + 1):
        floors = get_map(cfg, run_seed, act, ctx.map_key)
        options = [n[0] for n in floors[0]]
        for f in range(1, FLOORS_PER_ACT + 1):
            layer = floors[f - 1]
            if ctx.forced_ids and ctx.forced_floor == (act - 1) * FLOORS_PER_ACT + f:
                give_forced()
            if len(options) == 1:
                node = layer[options[0]]  # 선택지 1개: path 난수를 만들지 않음 (그 스트림은 다른 곳에서 안 씀)
            else:
                node = choose_node(cfg, st, [layer[i] for i in options], rng_for(run_seed, act, f, "path"))
            rng = rng_for(run_seed, act, f, "event")
            ntype = node[1]
            if ember_on:
                st.pos = (act, f)
            if trace is not None:
                trace.append({"ev": "node", "act": act, "floor": f, "type": ntype, "hp": st.hp})

            if ntype in ("battle", "elite", "boss"):
                if ntype == "battle":
                    if ctx.monsters is not None and getattr(ctx, "monster_encounter", "tier") == "game":
                        # 게임 규칙: 몬스터를 먼저 정하고 그 몬스터의 등급으로 싸운다
                        mon_ = ctx.pick_encounter(st, act, f - 1)
                        st._next_monster = mon_
                        tier = mon_["tier"]
                    elif ctx.monsters is not None:
                        # 몬스터 테이블 모델: 막마다 처음 easy_battles 번이 쉬운 몬스터 (막마다 easy 몬스터가 있으므로)
                        k = st.__dict__.setdefault("_normal_by_act", {})
                        tier = "easy" if k.get(act, 0) < cfg["monsters"]["easy_battles"] else "normal"
                        k[act] = k.get(act, 0) + 1
                    else:
                        tier = "easy" if st.normal_battles < cfg["monsters"]["easy_battles"] else "normal"
                    st.normal_battles += 1
                else:
                    tier = ntype
                st.stats["battles"] += 1
                if tier == "elite":
                    st.stats["elites"] += 1
                st.floor_pos = (act, f)
                outcome = fight_fn(cfg, st, tier, act, rng)
                if outcome == "escape":      # 카운트다운 도주: 승리와 같은 종료, 보상 없음 (사용자 확인 Q24)
                    st.escapes += 1
                    options = node[2]
                    if fbf is not None:
                        fbf.append(len(st.owned))
                    continue
                if outcome != "win":
                    result, end_reason, end_act, end_floor, death_tier = "lose", outcome, act, f, tier
                    done = True
                    break
                if tier == "boss":
                    st.stats["bosses_killed"] += 1
                give_rewards(cfg, st, tier, rng)
            elif ntype == "rest":
                hp0 = st.hp
                do_rest(cfg, st, act, rng)
                if trace is not None:
                    trace.append({"ev": "rest", "heal": st.hp - hp0, "hp": st.hp})
            elif ntype == "shop":
                hp0, nf = st.hp, len(st.owned)
                do_shop(cfg, st, rng)
                if trace is not None:
                    trace.append({"ev": "shop", "hp_spent": hp0 - st.hp, "bought": st.owned[nf:], "hp": st.hp})
            options = node[2]
            if fbf is not None:
                fbf.append(len(st.owned))
        if done:
            break
        hp_after[act] = st.hp

    reached = (end_act - 1) * FLOORS_PER_ACT + end_floor
    row = {
        "result": result,
        "end_reason": end_reason,
        "end_act": end_act,
        "end_floor_in_act": end_floor,
        "reached_floor": reached,
        "floors_cleared": reached if result == "win" else reached - 1,
        "death_tier": death_tier,
        "final_hp": max(st.hp, 0) if result == "win" else st.hp,
        "hp_after_act1": hp_after[1],
        "hp_after_act2": hp_after[2],
        "hp_after_act3": hp_after[3],
        "fant_white": st.fant["white"],
        "fant_blue": st.fant["blue"],
        "fant_red": st.fant["red"],
        "items_left": st.matches + st.erasers,
    }
    row.update(st.stats)
    # v3 추가 통계 (기존 키의 값은 바꾸지 않는다)
    row["fantasies_reward"], row["fantasies_shop"], row["fantasies_forced"] = st.src["reward"], st.src["shop"], st.src["forced"]
    em = st.ember
    row["embers_white"], row["embers_blue"], row["slots_done"] = em["white"], em["blue"], em["slots"]
    row["blue_offers"], row["blue_picked"], row["blue_wasted"] = em["blue_offers"], em["blue_picked"], em["blue_wasted"]
    row["normal_wins"] = st.normal_wins
    row["acquires"] = st.acquire_n
    if ctx.damage_model == "digits":
        row["escapes"] = st.escapes
    if st.table_mode:
        row["fantasy_copies"] = st.copies
        row["fantasy_voided"] = st.voided
    row["fantasies"] = "|".join(st.owned)  # 획득 순서, 마지막 열
    return row


# ---------------------------------------------------------------------------
# CSV 누적
# ---------------------------------------------------------------------------
def append_rows(path, rows):
    """헤더가 같으면 append, 새 열이 생기면 합집합 헤더로 파일 재작성."""
    if not rows:
        return
    new_fields = list(rows[0].keys())
    for r in rows[1:]:
        for k in r:
            if k not in new_fields:
                new_fields.append(k)

    if not os.path.exists(path) or os.path.getsize(path) == 0:
        with open(path, "w", newline="", encoding="utf-8-sig") as fp:
            w = csv.DictWriter(fp, fieldnames=new_fields, restval="")
            w.writeheader()
            w.writerows(rows)
        return

    with open(path, newline="", encoding="utf-8-sig") as fp:
        header = next(csv.reader(fp), [])

    if all(k in header for k in new_fields):
        with open(path, "a", newline="", encoding="utf-8-sig") as fp:
            csv.DictWriter(fp, fieldnames=header, restval="").writerows(rows)
        return

    merged = header + [k for k in new_fields if k not in header]
    with open(path, newline="", encoding="utf-8-sig") as fp:
        old = list(csv.DictReader(fp))
    tmp = path + ".tmp"
    with open(tmp, "w", newline="", encoding="utf-8-sig") as fp:
        w = csv.DictWriter(fp, fieldnames=merged, restval="")
        w.writeheader()
        w.writerows(old)
        w.writerows(rows)
    os.replace(tmp, path)


def quantile(sorted_vals, q):
    if not sorted_vals:
        return ""
    i = min(len(sorted_vals) - 1, max(0, round(q * (len(sorted_vals) - 1))))
    return sorted_vals[i]


def summarize(rows):
    n = len(rows)
    floors = sorted(r["reached_floor"] for r in rows)
    wins = [r for r in rows if r["result"] == "win"]
    losses = [r for r in rows if r["result"] == "lose"]
    s = {
        "win_rate": round(len(wins) / n, 4),
        "mean_reached_floor": round(statistics.fmean(floors), 2),
        "median_reached_floor": quantile(floors, 0.5),
        "p10_reached_floor": quantile(floors, 0.1),
        "p90_reached_floor": quantile(floors, 0.9),
        "death_act1_rate": round(sum(r["end_act"] == 1 for r in losses) / n, 4),
        "death_act2_rate": round(sum(r["end_act"] == 2 for r in losses) / n, 4),
        "death_act3_rate": round(sum(r["end_act"] == 3 for r in losses) / n, 4),
        "timeout_rate": round(sum(r["end_reason"] == "timeout" for r in losses) / n, 4),
    }
    for tier in ("easy", "normal", "elite", "boss"):
        s[f"death_by_{tier}_rate"] = round(sum(r["death_tier"] == tier for r in losses) / n, 4)
    for a in (1, 2):
        vals = [r[f"hp_after_act{a}"] for r in rows if r[f"hp_after_act{a}"] != ""]
        s[f"mean_hp_after_act{a}"] = round(statistics.fmean(vals), 1) if vals else ""
    s["mean_final_hp_win"] = round(statistics.fmean(r["final_hp"] for r in wins), 1) if wins else ""
    s["mean_fantasies"] = round(statistics.fmean(r["fant_white"] + r["fant_blue"] + r["fant_red"] for r in rows), 2)
    s["mean_turns_per_battle"] = round(sum(r["turns"] for r in rows) / max(1, sum(r["battles"] for r in rows)), 2)
    return s


def floor_reach_rows(batch_id, rows):
    n = len(rows)
    out = []
    for f in range(1, TOTAL_FLOORS + 1):
        reach = sum(r["reached_floor"] >= f for r in rows)
        clear = sum(r["floors_cleared"] >= f for r in rows)
        out.append({
            "batch_id": batch_id, "floor": f,
            "act": (f - 1) // FLOORS_PER_ACT + 1, "floor_in_act": (f - 1) % FLOORS_PER_ACT + 1,
            "reached": reach, "reach_rate": round(reach / n, 4),
            "cleared": clear, "clear_rate": round(clear / n, 4),
        })
    return out


# ---------------------------------------------------------------------------
# 배치 실행
# ---------------------------------------------------------------------------
def run_batch(cfg, runs, master_seed, label, out_dir, overrides_desc, quiet=False):
    os.makedirs(os.path.join(out_dir, "configs"), exist_ok=True)
    ctx = SimContext(cfg)
    cfg_blob = json.dumps(cfg, sort_keys=True, ensure_ascii=False)
    digest = hashlib.sha1(f"{cfg_blob}|{master_seed}|{runs}|{time.time_ns()}".encode()).hexdigest()[:6]
    batch_id = f"{datetime.now():%Y%m%d-%H%M%S}-{digest}"

    t0 = time.perf_counter()
    rows = []
    for i in range(runs):
        run_seed = f"{master_seed}-{i}"  # 배치가 달라도 같은 i면 같은 시드 → 공정 비교
        r = simulate_run(cfg, run_seed, ctx=ctx)
        rows.append({"batch_id": batch_id, "run": i, "run_seed": run_seed, **r})
    elapsed = time.perf_counter() - t0

    summary = summarize(rows)
    batch_row = {
        "batch_id": batch_id,
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "label": label,
        "overrides": overrides_desc,
        "runs": runs,
        "master_seed": master_seed,
        **summary,
        **{f"cfg.{k}": v for k, v in flatten(cfg).items()},
    }

    append_rows(os.path.join(out_dir, "runs.csv"), rows)
    append_rows(os.path.join(out_dir, "batches.csv"), [batch_row])
    append_rows(os.path.join(out_dir, "floor_reach.csv"), floor_reach_rows(batch_id, rows))
    with open(os.path.join(out_dir, "configs", f"{batch_id}.json"), "w", encoding="utf-8") as fp:
        json.dump(cfg, fp, ensure_ascii=False, indent=2)

    if quiet:
        return batch_id, summary
    print(f"[{batch_id}] {label or '-'} {overrides_desc or ''}".rstrip())
    print(f"  {runs}판 / {elapsed:.1f}s | 승률 {summary['win_rate']*100:.1f}% | "
          f"평균 도달 {summary['mean_reached_floor']}층 (중앙 {summary['median_reached_floor']}, "
          f"p10 {summary['p10_reached_floor']}, p90 {summary['p90_reached_floor']})")
    print(f"  막별 사망률 1막 {summary['death_act1_rate']*100:.1f}% / 2막 {summary['death_act2_rate']*100:.1f}% / "
          f"3막 {summary['death_act3_rate']*100:.1f}% | 보스 사망 {summary['death_by_boss_rate']*100:.1f}% | "
          f"timeout {summary['timeout_rate']*100:.1f}%")
    return batch_id, summary


def wilson_ci(p, n, z=1.96):
    """승률 p (n판) 의 95% Wilson 구간."""
    if not n:
        return (0.0, 1.0)
    den = 1 + z * z / n
    c = (p + z * z / (2 * n)) / den
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return (max(0.0, c - h), min(1.0, c + h))


def tune_search(evaluate, lo, hi, target, tol, max_evals, integer=True, cancel=None):
    """[lo, hi] 이분 탐색 (지표가 단조라고 가정). evaluate(x) → 지표 값.
    반환: (evals {x: 값}, best_x, in_range, stop) — stop = 목표 도달 | 정수 간격 1 | 최대 평가 수 | 범위 밖 | 취소.
    CLI(--tune)와 뷰어 패널(서버)이 같이 쓴다 → 같은 시드·판 수면 같은 결과 (v4.2 AC-H8)."""
    evals = {}

    def ev(x):
        if cancel is not None and cancel():
            raise TuneCancelled()
        if x not in evals:
            evals[x] = evaluate(x)
        return evals[x]

    rnd = (lambda v: int(round(v))) if integer else (lambda v: round(v, 6))
    lo, hi = rnd(lo), rnd(hi)
    w_lo, w_hi = ev(lo), ev(hi)
    decreasing = w_lo >= w_hi
    lo_w, hi_w = (w_lo, w_hi) if decreasing else (w_hi, w_lo)
    in_range = hi_w <= target <= lo_w
    stop = "범위 밖 (범위 안에 해 없음)"
    if in_range:
        a, b = lo, hi
        stop = "최대 평가 수"
        while len(evals) < max_evals:
            if integer and b - a <= 1:
                stop = "정수 간격 1"
                break
            mid = rnd((a + b) / 2)
            if mid in (a, b):
                stop = "더 나눌 수 없음"
                break
            w = ev(mid)
            if abs(w - target) <= tol / 4:
                stop = "목표 도달 (허용 오차의 1/4 이내)"
                break
            if (w > target) == decreasing:
                a = mid
            else:
                b = mid
    best_x = min(evals, key=lambda x: (abs(evals[x] - target), x))
    return evals, best_x, in_range, stop


class TuneCancelled(Exception):
    pass


def scaled_hp_table(cfg, scale):
    """monsters.hp_scale = scale 일 때의 몬스터별·막×등급별 환산 체력 (JSON 체력 × scale, 반올림). 읽기만 한다 (AC-H8)."""
    path = resolve_table_file(cfg["monsters"].get("table_file") or "")
    with open(path, encoding="utf-8-sig") as fp:
        mons = [m for m in json.load(fp).get("monsters", []) if m.get("enabled", True)]
    rows = [{"id": m["id"], "name": m.get("name", m["id"]), "act": int(m["act"]), "tier": m["tier"], "hp": m["hp"],
             "scaled": max(1, round(m["hp"] * scale))} for m in mons]
    groups = {}
    for r in rows:
        groups.setdefault((r["act"], r["tier"]), []).append(r)
    order = {"easy": 0, "normal": 1, "elite": 2, "boss": 3}
    summary = [{"act": a, "tier": t, "n": len(v), "hp_mean": round(statistics.fmean(r["hp"] for r in v), 1),
                "scaled_mean": round(statistics.fmean(r["scaled"] for r in v), 1),
                "scaled_min": min(r["scaled"] for r in v), "scaled_max": max(r["scaled"] for r in v)}
               for (a, t), v in sorted(groups.items(), key=lambda kv: (kv[0][0], order.get(kv[0][1], 9)))]
    return {"scale": scale, "summary": summary, "monsters": rows}


def print_tune_extras(cfg, key, best_x, out=print):
    """--tune 결과에 덧붙이는 표 (v4.2 F11.6). 몬스터 JSON·설정·시나리오는 쓰지 않는다."""
    if key == "monsters.hp_scale" and cfg["monsters"].get("model") == "table":
        t = scaled_hp_table(cfg, best_x)
        out(f"  등급·막별 환산 체력 (JSON 체력 × {best_x:g}, 반올림 — 반영은 몬스터 탭에서 직접):")
        for r in t["summary"]:
            out(f"    {r['act']}막 {r['tier']:<6} {r['n']}종: 평균 {r['hp_mean']:g} → {r['scaled_mean']:g} "
                f"({r['scaled_min']}~{r['scaled_max']})")
        out("  몬스터별 (id\t이름\t막\t등급\t현재 체력\t환산 체력):")
        for r in t["monsters"]:
            out(f"    {r['id']}\t{r['name']}\t{r['act']}\t{r['tier']}\t{r['hp']}\t{r['scaled']}")
        return t
    if key == "player.start_hp":
        out(f"  필요한 시작 체력: {best_x} (현재 {get_path(cfg, key)}) — GameBootstrap.startingHealth 는 자동으로 바꾸지 않음")
    return None


def tune(cfg, key, lo, hi, target, tol, max_evals, runs, master_seed, label, out_dir, desc, integer=True,
         metric="win_rate"):
    """key 값을 [lo, hi] 안에서 이분 탐색해 지표(metric, 기본 승률)가 target 에 가장 가까운 값을 찾는다.
    지표는 key 에 대해 단조(증가 또는 감소)라고 가정한다. 모든 평가 배치는 CSV에 누적된다.
    metric 예: win_rate, mean_fantasies, mean_reached_floor (summarize() 의 키).
    v4.2: 찾은 점의 승률 95% CI·종료 조건, monsters.hp_scale 이면 환산 체력 표를 출력한다 (파일은 out_dir 의 CSV 만 쓴다)."""
    batches = {}

    def evaluate(x):
        c = copy.deepcopy(cfg)
        set_path(c, key, x)
        d = "; ".join([p for p in [desc, f"{key}={x}"] if p])
        bid, s = run_batch(c, runs, master_seed, label or "tune", out_dir, d, quiet=True)
        if metric not in s:
            raise KeyError(f"알 수 없는 지표: {metric} (가능: {', '.join(k for k in s if isinstance(s[k], (int, float)))})")
        batches[x] = (bid, s)
        print(f"    {key}={x:<8} {metric} {s[metric]:.4g}  승률 {s['win_rate'] * 100:5.1f}%  평균 도달 {s['mean_reached_floor']}층")
        return s[metric]

    evals, best_x, in_range, stop = tune_search(evaluate, lo, hi, target, tol, max_evals, integer)
    best_w = evals[best_x]
    best_bid, best_s = batches[best_x]
    ci = wilson_ci(best_s["win_rate"], runs)
    row = {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "label": label,
        "fixed": desc,
        "tune_key": key,
        "target_metric": metric,
        "target_win_rate": target if metric == "win_rate" else "",
        "target_value": target,
        "found_value": best_x,
        "metric_value": best_w,
        "win_rate": best_s["win_rate"],
        "win_rate_ci_lo": round(ci[0], 4),
        "win_rate_ci_hi": round(ci[1], 4),
        "within_tol": abs(best_w - target) <= tol,
        "in_search_range": in_range,
        "stop_reason": stop,
        "mean_reached_floor": best_s["mean_reached_floor"],
        "death_act1_rate": best_s["death_act1_rate"],
        "death_act2_rate": best_s["death_act2_rate"],
        "death_act3_rate": best_s["death_act3_rate"],
        "runs_per_eval": runs,
        "evaluations": len(evals),
        "master_seed": master_seed,
        "batch_id": best_bid,
    }
    append_rows(os.path.join(out_dir, "tune_results.csv"), [row])
    flag = "" if in_range else "  ※ 범위 안에 해 없음 (탐색 범위 안에 목표 승률이 없음)"
    print(f"  → {key}={best_x} {metric} {best_w:.4g} (승률 {best_s['win_rate'] * 100:.1f}% "
          f"[95% CI {ci[0] * 100:.1f}~{ci[1] * 100:.1f}%], {runs}판 x 평가 {len(evals)}회, 종료: {stop}){flag}")
    print_tune_extras(cfg, key, best_x)
    return row


DIGITS_UNUSED = ("player.defense_cut_per_move", "player.attack_gain_per_move", "monsters.str_amount",
                 "player.base_dmg_min", "player.base_dmg_max", "player.zero_hits_chance", "monsters.tiers")


def _key_match(k, u):
    import fnmatch
    return k == u or k.startswith(u + ".") or fnmatch.fnmatch(k, u)


def warn_unused(cfg, keys, out=print):
    """쓰이지 않는 파라미터 경고: digits 모델(AC-D8) + table 모델의 평균 몬스터 체력 키(v4.2 AC-H2)."""
    bad = warn_unused_digits(cfg, keys, out)
    M = cfg["monsters"]
    if M.get("model", "tier_avg") == "table":
        unused = list(TABLE_UNUSED) + (["monsters.easy_battles"] if M.get("encounter", "game") == "game" else [])
        for k in keys:
            if k not in bad and any(_key_match(k, u) for u in unused):
                bad.append(k)
                out(f"  ※ 경고: {k} 는 monsters.model=table 에서 쓰이지 않음 (구버전 tier_avg 전용, 결과에 영향 없음)")
    return bad


def warn_stale_monster_table(cfg, out=print):
    """table 모델이 원본 몬스터 폴더와 어긋난 monster_table.json 을 쓰면 경고 (v4.2 Q47). 경고 문구 또는 None."""
    M = cfg["monsters"]
    if M.get("model") != "table":
        return None
    try:
        path = resolve_table_file(M.get("table_file") or "")
        import import_monsters
        msg = import_monsters.stale_warning(path)
    except Exception:   # noqa: BLE001 — 경고만, 실패해도 실행은 계속
        return None
    if msg:
        out(f"  ※ 경고: {msg}")
    return msg


def warn_unused_digits(cfg, keys, out=print):
    """digits 모델에서 쓰이지 않는 파라미터를 X축·--set 에 쓰면 경고 (AC-D8). 경고 목록을 돌려준다."""
    if cfg["monsters"].get("damage_model", "gauss") != "digits":
        return []
    bad = [k for k in keys if any(k == u or k.startswith(u + ".") or (u == "monsters.str_amount" and k.endswith(".str_amount"))
                                  for u in DIGITS_UNUSED)]
    for k in bad:
        out(f"  ※ 경고: {k} 는 damage_model=digits 에서 쓰이지 않음 (결과에 영향 없음)")
    return bad


def apply_fantasy_args(cfg, effects=None, effect_mode=None, force=None, force_at=None):
    """--effects / --effect-mode / --force-fantasy / --force-at 을 설정에 반영."""
    if effects:
        cfg["fantasy"]["effects_file"] = os.path.abspath(effects)
        if effect_mode is None:
            effect_mode = "table"
    if effect_mode:
        cfg["fantasy"]["effect_mode"] = effect_mode
    if force:
        ids = [x.strip() for x in force.split(",") if x.strip()]
        cfg["fantasy"]["forced"] = {"ids": ids, "at": "start" if not force_at else {"floor": int(force_at)}}


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if "--fantasy-scan" in argv:
        import fantasy_scan
        argv.remove("--fantasy-scan")
        return fantasy_scan.main(argv)

    ap = argparse.ArgumentParser(description="Match Up 밸런스 몬테카를로 시뮬레이터")
    ap.add_argument("--runs", type=int, default=2000, help="배치당 판 수 (기본 2000)")
    ap.add_argument("--seed", default=None, help="마스터 시드 (생략 시 현재 시각)")
    ap.add_argument("--config", help="설정 JSON (기본값 위에 덮어씀)")
    ap.add_argument("--set", action="append", default=[], metavar="KEY=VALUE",
                    help="설정 덮어쓰기, 예: player.start_hp=180")
    ap.add_argument("--sweep", action="append", default=[], metavar="KEY=V1,V2,...",
                    help="파라미터 스윕, 여러 개 주면 모든 조합 실행")
    ap.add_argument("--label", default="", help="배치 메모 (batches.csv label 열)")
    ap.add_argument("--out", default="sim_results", help="결과 CSV 폴더 (기본 sim_results)")
    ap.add_argument("--dump-config", metavar="PATH", help="기본 설정을 JSON으로 저장하고 종료")
    ap.add_argument("--tune", metavar="KEY=LO:HI",
                    help="목표 승률이 되는 값을 이분 탐색, 예: monsters.hp_scale=0.5:2 (몬스터 체력 배율, 환산 체력 표 출력) / player.start_hp=50:600 (스윕 조합마다 실행, 몬스터 JSON 은 쓰지 않음)")
    ap.add_argument("--target", type=float, default=0.10, help="--tune 목표값 (기본 0.10 = 승률 10%%)")
    ap.add_argument("--target-metric", default="win_rate",
                    help="--tune 목표 지표 (win_rate | mean_fantasies | mean_reached_floor ...)")
    ap.add_argument("--tol", type=float, default=0.01, help="--tune 허용 오차 (기본 0.01 = ±1%%p)")
    ap.add_argument("--max-evals", type=int, default=12, help="--tune 조합당 최대 평가 배치 수")
    ap.add_argument("--float", action="store_true", help="--tune 값을 정수가 아닌 실수로 탐색")
    ap.add_argument("--preset", action="append", default=[], help="설정 프리셋 JSON (예: presets/ember_v1.json), --config 뒤에 덮어씀")
    ap.add_argument("--ban-fantasy", metavar="ID[,ID...]", help="풀에서 제외할 환상 (제외 기준선)")
    ap.add_argument("--effects", help="환상 효과 테이블 JSON (주면 기본으로 table 모드)")
    ap.add_argument("--effect-mode", choices=["grade", "table"], help="환상 효과 모드")
    ap.add_argument("--force-fantasy", metavar="ID[,ID...]", help="런 시작부터 보유할 환상")
    ap.add_argument("--force-at", type=int, metavar="FLOOR", help="강제 포함 시점(전체 층 번호 1~45, 생략 시 시작)")
    ap.add_argument("--fantasy-scan", action="store_true", help="환상별 승률 곡선 스캔 (fantasy_scan.py --help 참고)")
    args = ap.parse_args(argv)

    if args.dump_config:
        with open(args.dump_config, "w", encoding="utf-8") as fp:
            json.dump(DEFAULT_CONFIG, fp, ensure_ascii=False, indent=2)
        print(f"기본 설정 저장: {args.dump_config}")
        return

    cfg = copy.deepcopy(DEFAULT_CONFIG)
    if args.config:
        with open(args.config, encoding="utf-8") as fp:
            deep_merge(cfg, json.load(fp))
    for pth in args.preset:
        with open(pth, encoding="utf-8") as fp:
            deep_merge(cfg, {k: v for k, v in json.load(fp).items() if not k.startswith("_")})
    apply_fantasy_args(cfg, args.effects, args.effect_mode, args.force_fantasy, args.force_at)
    if args.ban_fantasy:
        cfg["fantasy"]["banned"] = {"ids": [x.strip() for x in args.ban_fantasy.split(",") if x.strip()]}
    set_desc = []
    if args.force_fantasy:
        set_desc.append(f"forced={args.force_fantasy}")
    for item in args.set:
        k, v = item.split("=", 1)
        set_path(cfg, k.strip(), parse_value(v.strip()))
        set_desc.append(f"{k.strip()}={v.strip()}")
    normalize_models(cfg)
    warn_stale_monster_table(cfg)
    warn_unused(cfg, [i.split("=", 1)[0].strip() for i in args.set + args.sweep]
                       + ([args.tune.split("=", 1)[0].strip()] if args.tune else []))

    sweeps = []
    for item in args.sweep:
        k, vs = item.split("=", 1)
        sweeps.append((k.strip(), [parse_value(v.strip()) for v in vs.split(",")]))

    master_seed = args.seed if args.seed is not None else datetime.now().strftime("%Y%m%d%H%M%S")
    combos = list(itertools.product(*[vals for _, vals in sweeps])) if sweeps else [()]
    print(f"마스터 시드 {master_seed} | 배치 {len(combos)}개 x {args.runs}판 → {os.path.abspath(args.out)}")

    tune_spec = None
    if args.tune:
        k, rng_s = args.tune.split("=", 1)
        lo, hi = (float(v) for v in rng_s.split(":"))
        tune_spec = (k.strip(), lo, hi)
        print(f"목표 {args.target_metric}={args.target:g} ±{args.tol:g} 탐색: {tune_spec[0]} ∈ [{lo:g}, {hi:g}]")

    results = []
    for combo in combos:
        c = copy.deepcopy(cfg)
        desc = list(set_desc)
        for (k, _), v in zip(sweeps, combo):
            set_path(c, k, v)
            desc.append(f"{k}={v}")
        if tune_spec:
            print(f"[{'; '.join(desc) or '기본 설정'}]")
            results.append(tune(c, tune_spec[0], tune_spec[1], tune_spec[2], args.target, args.tol,
                                args.max_evals, args.runs, master_seed, args.label, args.out,
                                "; ".join(desc), integer=not args.float and not isinstance(get_path(c, tune_spec[0]), float),
                                metric=args.target_metric))
        else:
            run_batch(c, args.runs, master_seed, args.label, args.out, "; ".join(desc))

    if tune_spec and len(results) > 1:
        print("\n=== 탐색 요약 ===")
        for r in results:
            mark = "" if r["within_tol"] else "  (오차 밖)"
            print(f"  {r['fixed'] or '-'} → {r['tune_key']}={r['found_value']} {r['target_metric']} {r['metric_value']:.4g}{mark}")


if __name__ == "__main__":
    main()
