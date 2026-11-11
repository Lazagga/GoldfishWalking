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
"""
from __future__ import annotations

import argparse
import copy
import csv
import hashlib
import itertools
import json
import os
import random
import statistics
import sys
import time
from datetime import datetime

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
        # 플레이어 실력 0~1. 이동 1회의 기대 이득에 곱해진다.
        "skill": 0.7,
        # 공격 이동 1회: 기본 피해 x U(0, 2*gain) x skill 만큼 피해 증가 (평균 gain*skill)
        "attack_gain_per_move": 0.6,
        # 방어 이동 1회: 몬스터 1타 피해를 U(0, 2*cut) x skill 비율만큼 감소
        "defense_cut_per_move": 0.35,
        # 연타 공격일 때 방어 이동 1회로 타수를 0으로 만들 확률 (x skill)
        "zero_hits_chance": 0.25,
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
    },
    "sim": {
        "max_turns": 60,           # 한 전투 최대 턴 (넘으면 timeout 패배)
    },
}


# ---------------------------------------------------------------------------
# 설정 유틸
# ---------------------------------------------------------------------------
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
# 런 상태
# ---------------------------------------------------------------------------
class RunState:
    def __init__(self, cfg, pool):
        self.hp = cfg["player"]["start_hp"]
        self.fant = {g: 0 for g in GRADES}
        self.pool = pool
        self.owned = []          # 획득 순서 그대로 (효과 발동 순서)
        self.owned_set = set()
        self.matches = cfg["items"]["start_matches"]
        self.erasers = cfg["items"]["start_erasers"]
        self.normal_battles = 0
        self.stats = {
            "battles": 0, "elites": 0, "bosses_killed": 0, "rests": 0, "shops": 0,
            "turns": 0, "dmg_taken": 0, "hp_healed": 0, "hp_spent_shop": 0,
            "items_used": 0, "items_bought": 0, "fantasies_bought": 0,
        }

    def unowned(self, grade):
        return [f for f in self.pool[grade] if f not in self.owned_set]

    def gain_fantasy(self, grade, name):
        self.owned.append(name)
        self.owned_set.add(name)
        self.fant[grade] += 1


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


def choose_node(cfg, st, options, rng):
    pol = cfg["policy"]
    if pol["path"] == "random" or len(options) == 1:
        return rng.choice(options)
    hp = st.hp

    def score(n):
        t = n["type"]
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
# 휴식 / 상점
# ---------------------------------------------------------------------------
def do_rest(cfg, st, act, rng):
    R, skill = cfg["rest"], cfg["player"]["skill"]
    base = rng.randint(R["heal_min"], R["heal_max"]) * R["act_scale"][act - 1]
    heal = base
    for _ in range(R["moves"]):
        heal += base * skill * rng.uniform(0, 2 * R["edit_gain_per_move"])
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


def do_shop(cfg, st, rng):
    S, pol, F = cfg["shop"], cfg["policy"], cfg["fantasy"]
    keep = pol["shop_keep_hp"]
    moves = S["moves"]
    st.stats["shops"] += 1

    # 환상: 등급별 1개 진열, 높은 등급부터 고려
    for g in ("red", "blue", "white"):
        cands = st.unowned(g)
        if not cands:
            continue
        offer = rng.choice(cands)
        lo, hi = S["fantasy_price"][g]
        price = rng.randint(lo, hi)
        final = edit_price(cfg, price, moves, rng) if moves else price
        if st.hp - final >= keep:
            st.hp -= final
            st.gain_fantasy(g, offer)
            st.stats["hp_spent_shop"] += final
            st.stats["fantasies_bought"] += 1
            if final != price:
                moves = 0  # 편집한 상품을 샀으므로 이동 횟수 소진 (리셋 불가)
        # 못 샀으면 리셋 → 이동 횟수 환급

    # 아이템: 구매마다 가격 재굴림
    for _ in range(pol["max_items_per_shop"]):
        price = rng.randint(S["item_price_min"], S["item_price_max"])
        final = edit_price(cfg, price, moves, rng) if moves else price
        if st.hp - final < keep:
            break
        st.hp -= final
        st.stats["hp_spent_shop"] += final
        st.stats["items_bought"] += 1
        if rng.random() < 0.5:
            st.matches += 1
        else:
            st.erasers += 1
        if final != price:
            moves = 0


def give_rewards(cfg, st, tier, rng):
    g = TIER_GRADE[tier]
    cands = st.unowned(g)
    if cands:
        offered = rng.sample(cands, min(3, len(cands)))  # 3개 중 1개 선택 (효과가 추상화돼 있어 무작위 선택)
        st.gain_fantasy(g, rng.choice(offered))
    if rng.random() < cfg["items"]["drop_chance"]:
        st.matches += 1
    if rng.random() < cfg["items"]["drop_chance"]:
        st.erasers += 1


# ---------------------------------------------------------------------------
# 런 1회
# ---------------------------------------------------------------------------
def simulate_run(cfg, run_seed, pool=None):
    st = RunState(cfg, pool if pool is not None else load_fantasy_pool(cfg))
    hp_after = {1: "", 2: "", 3: ""}
    result, end_reason, end_act, end_floor, death_tier = "win", "clear", ACTS, FLOORS_PER_ACT, ""

    done = False
    for act in range(1, ACTS + 1):
        floors = generate_map(cfg, run_seed, act)
        options = [n["idx"] for n in floors[0]]
        for f in range(1, FLOORS_PER_ACT + 1):
            layer = floors[f - 1]
            node = choose_node(cfg, st, [layer[i] for i in options], rng_for(run_seed, act, f, "path"))
            rng = rng_for(run_seed, act, f, "event")
            ntype = node["type"]

            if ntype in ("battle", "elite", "boss"):
                if ntype == "battle":
                    tier = "easy" if st.normal_battles < cfg["monsters"]["easy_battles"] else "normal"
                    st.normal_battles += 1
                else:
                    tier = ntype
                st.stats["battles"] += 1
                if tier == "elite":
                    st.stats["elites"] += 1
                outcome = fight(cfg, st, tier, act, rng)
                if outcome != "win":
                    result, end_reason, end_act, end_floor, death_tier = "lose", outcome, act, f, tier
                    done = True
                    break
                if tier == "boss":
                    st.stats["bosses_killed"] += 1
                give_rewards(cfg, st, tier, rng)
            elif ntype == "rest":
                do_rest(cfg, st, act, rng)
            elif ntype == "shop":
                do_shop(cfg, st, rng)
            options = node["children"]
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
    pool = load_fantasy_pool(cfg)
    cfg_blob = json.dumps(cfg, sort_keys=True, ensure_ascii=False)
    digest = hashlib.sha1(f"{cfg_blob}|{master_seed}|{runs}|{time.time_ns()}".encode()).hexdigest()[:6]
    batch_id = f"{datetime.now():%Y%m%d-%H%M%S}-{digest}"

    t0 = time.perf_counter()
    rows = []
    for i in range(runs):
        run_seed = f"{master_seed}-{i}"  # 배치가 달라도 같은 i면 같은 시드 → 공정 비교
        r = simulate_run(cfg, run_seed, pool)
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


def tune(cfg, key, lo, hi, target, tol, max_evals, runs, master_seed, label, out_dir, desc, integer=True):
    """key 값을 [lo, hi] 안에서 이분 탐색해 승률이 target 에 가장 가까운 값을 찾는다.
    승률은 key 에 대해 단조(증가 또는 감소)라고 가정한다. 모든 평가 배치는 CSV에 누적된다."""
    evals = {}

    def evaluate(x):
        if x in evals:
            return evals[x][0]
        c = copy.deepcopy(cfg)
        set_path(c, key, x)
        d = "; ".join([p for p in [desc, f"{key}={x}"] if p])
        bid, s = run_batch(c, runs, master_seed, label or "tune", out_dir, d, quiet=True)
        evals[x] = (s["win_rate"], bid, s)
        print(f"    {key}={x:<8} 승률 {s['win_rate'] * 100:5.1f}%  평균 도달 {s['mean_reached_floor']}층")
        return s["win_rate"]

    rnd = (lambda v: int(round(v))) if integer else (lambda v: v)
    lo, hi = rnd(lo), rnd(hi)
    w_lo, w_hi = evaluate(lo), evaluate(hi)
    decreasing = w_lo >= w_hi
    lo_w, hi_w = (w_lo, w_hi) if decreasing else (w_hi, w_lo)
    in_range = hi_w <= target <= lo_w

    if in_range:
        a, b = lo, hi
        while len(evals) < max_evals:
            if integer and b - a <= 1:
                break
            mid = rnd((a + b) / 2)
            w = evaluate(mid)
            if abs(w - target) <= tol / 4:
                break
            if (w > target) == decreasing:
                a = mid
            else:
                b = mid

    best_x = min(evals, key=lambda x: (abs(evals[x][0] - target), x))
    best_w, best_bid, best_s = evals[best_x]
    row = {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "label": label,
        "fixed": desc,
        "tune_key": key,
        "target_win_rate": target,
        "found_value": best_x,
        "win_rate": best_w,
        "within_tol": abs(best_w - target) <= tol,
        "in_search_range": in_range,
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
    flag = "" if in_range else "  ※ 탐색 범위 안에 목표 승률이 없음"
    print(f"  → {key}={best_x} 승률 {best_w * 100:.1f}% (평가 {len(evals)}회){flag}")
    return row


def main(argv=None):
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
                    help="목표 승률이 되는 값을 이분 탐색, 예: monsters.hp_base=20:400 (스윕 조합마다 실행)")
    ap.add_argument("--target", type=float, default=0.10, help="--tune 목표 승률 (기본 0.10)")
    ap.add_argument("--tol", type=float, default=0.01, help="--tune 허용 오차 (기본 0.01 = ±1%%p)")
    ap.add_argument("--max-evals", type=int, default=12, help="--tune 조합당 최대 평가 배치 수")
    ap.add_argument("--float", action="store_true", help="--tune 값을 정수가 아닌 실수로 탐색")
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
    set_desc = []
    for item in args.set:
        k, v = item.split("=", 1)
        set_path(cfg, k.strip(), parse_value(v.strip()))
        set_desc.append(f"{k.strip()}={v.strip()}")

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
        print(f"목표 승률 {args.target * 100:.1f}% ±{args.tol * 100:.1f}%p 탐색: {tune_spec[0]} ∈ [{lo:g}, {hi:g}]")

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
                                "; ".join(desc), integer=not args.float))
        else:
            run_batch(c, args.runs, master_seed, args.label, args.out, "; ".join(desc))

    if tune_spec and len(results) > 1:
        print("\n=== 탐색 요약 ===")
        for r in results:
            mark = "" if r["within_tol"] else "  (오차 밖)"
            print(f"  {r['fixed'] or '-'} → {r['tune_key']}={r['found_value']} 승률 {r['win_rate'] * 100:.1f}%{mark}")


if __name__ == "__main__":
    main()
