# -*- coding: utf-8 -*-
"""피해 자릿수 모델 전투 (v4 F8) + 몬스터 기믹 (v4 F9).

monsters.damage_model = "digits" (monsters.model = "table" 필요). monsters.gimmicks = "on" 이면 기믹도 반영.
게임 규칙 출처: Assets/1Scripts/Battle/BattleController.cs (PrepareTurn, ResolveBattleRoutine,
ResolveMonsterActionRoutine), MonsterPatternRunner.cs, MonsterRuntime.cs, MonsterEffectExpressionEvaluator.cs.

턴 순서 (F9.1)
 1 준비: 페이즈 전이 → 이동 한도 → 환상 턴 시작 → 플레이어 기본 피해 굴림 → (기믹) 공격 조건·조준 숫자·디버프 상자·
   턴 시작 성냥 잠금·접미 조건 상자 → 패턴 선택 → 몬스터 피해·타수 굴림 → 상시 규칙 → 예약 효과
 2 배분: K ~ Binomial(M, skill), 상자별 reach(F8.3) 로 도달 값, 목적함수 최대 (생존 우선 → 처치 우선 → J)
 3 공식 평가: 디버프 → 공격 조건 → 몬스터의 플레이어 피해 규칙(숨은 숫자·접미·특수 숫자 0) / 몬스터: 조준 사격
 4 선공 5 플레이어 타격(몬스터 사망 시 중단) 6 턴 종료 환상 7 몬스터 행동 8 자폭 9 상태 피해 10 지속시간 11 카운트다운

난수: 롤마다 rng_for(run_seed, 막, 층, "dg", 턴, tag) — 기존 스트림을 쓰지 않는다 (AC-D0).
"""
from __future__ import annotations

import math
import random

import matchup_sim as ms

from . import box_moves as bm

VERSION = 2          # 2: 큰 상자는 이동 수별 최선 값 DP (메모리 폭주 수정)
BEAM_LIMIT = 100000


def dmin(d):
    return 1 if d <= 1 else 10 ** (d - 1)


def dmax(d):
    return 10 ** max(1, d) - 1


def ndig(v):
    return len(str(abs(int(v))))


# ---------------------------------------------------------------------------
# 표현식 평가기 (MonsterEffectExpressionEvaluator 와 같은 의미, F9.4)
# ---------------------------------------------------------------------------
def _norm(s):
    return (s or "").strip().replace("_", "").replace(" ", "").lower()


class Env:
    """평가기 입력: 몬스터 상태(m), 플레이어 hp/상태(p), 난수 함수."""
    __slots__ = ("m", "p", "dealt", "roll")

    def __init__(self, m, p, dealt=0, roll=None):
        self.m, self.p, self.dealt, self.roll = m, p, dealt, roll


def eval_value(expr, env):
    if expr is None:
        return 0.0
    if isinstance(expr, (int, float)):
        return float(expr)
    t = str(expr).strip()
    if not t:
        return 0.0
    try:
        return float(t)
    except ValueError:
        pass
    # 첫 번째 산술 연산자에서 자른다 (게임 평가기: 우선순위 없음, 왼쪽부터)
    for i in range(1, len(t)):
        c = t[i]
        if c in "+-*/":
            a, b = eval_value(t[:i], env), eval_value(t[i + 1:], env)
            if c == "+":
                return a + b
            if c == "-":
                return a - b
            if c == "*":
                return a * (b / 100.0 if b > 1 else b)
            return 0.0 if b == 0 else math.floor(a / b)
    m, p = env.m, env.p
    k = _norm(t)
    if k == "playerhpmulti2":
        pct = env.roll("hp_pct").randint(10, 99) if env.roll else 10
        m.special = {"value": pct, "digits": 2, "label": "HP %", "editable": False}
        return float(math.floor(p.hp * pct / 100.0))
    if k == "stargazingmulti3":
        return float(m.special["value"]) if m.special else 0.0
    if k == "cosmictreeheal":
        return 1.0
    if k == "damagedealt":
        return float(max(0, env.dealt))
    if k in ("damagetaken", "monsterdamagetakenthisbattle"):
        return float(m.cap_acc)
    if k == "damagecapbreakthreshold":
        return float(m.cap_until or 0)
    if k == "fortunestack":
        return float(m.fortune)
    if k in ("prophecystack", "prophetstack"):
        return float(m.prophecy)
    if k == "playerbleed":
        return float(p.bleed)
    if k in ("playerpoison", "playerpoision"):
        return float(p.poison)
    if k in ("playerhp", "hp"):
        return float(p.hp)
    if k == "specialboxvalue":
        return float(m.special["value"]) if m.special else 0.0
    if k == "heartqueenbox":
        # 게임 평가기에는 이 변수가 없어 0 이 된다 (조건 heart_queen_box == 0 이 항상 참 → 회전 중에도 사용 가능).
        # 시뮬레이터는 설계 의도대로 카운트다운 상자 값으로 해석한다 (README 불일치 보고).
        return float(m.countdown) if m.countdown is not None else 0.0
    if k == "strength":
        return float(m.strength)
    if k == "hprate":
        return m.hp / m.base_hp if m.base_hp > 0 else 1.0
    if k == "phase":
        return float(m.phase)
    if k == "random":
        return float(env.roll("rand").randint(0, 9)) if env.roll else 0.0
    if t.lower().startswith("digitcount(") and t.endswith(")"):
        return float(ndig(int(math.floor(eval_value(t[11:-1], env)))))
    return 0.0


def eval_cond(expr, env):
    t = (expr or "").strip()
    if not t:
        return True
    parts = t.split("&&")
    if len(parts) > 1:
        return all(eval_cond(x, env) for x in parts)
    for op in (">=", "<=", "==", "!=", ">", "<"):
        i = t.find(op)
        if i < 0:
            continue
        a, b = eval_value(t[:i], env), eval_value(t[i + len(op):], env)
        if op == ">=":
            return a >= b
        if op == "<=":
            return a <= b
        if op == "==":
            return abs(a - b) < 1e-6
        if op == "!=":
            return abs(a - b) >= 1e-6
        if op == ">":
            return a > b
        return a < b
    return eval_value(t, env) > 0


# ---------------------------------------------------------------------------
# 상태
# ---------------------------------------------------------------------------
class Mon:
    __slots__ = ("hp", "base_hp", "strength", "base_strength", "stun", "shield", "cap", "cap_until", "cap_acc",
                 "fortune", "prophecy", "phase", "special", "countdown", "scheduled", "timed", "uses",
                 "reactive", "reacted", "hidden", "found", "once_used", "dead")

    def __init__(self, hp, strength):
        self.hp = self.base_hp = hp
        self.strength = self.base_strength = strength
        self.stun = 0
        self.shield = 0
        self.cap = 0
        self.cap_until = None
        self.cap_acc = 0
        self.fortune = self.prophecy = 0
        self.phase = 1
        self.special = None        # {"value", "digits", "label", "editable"}
        self.countdown = None
        self.scheduled = []        # (턴, 효과)
        self.timed = []
        self.uses = {}
        self.reactive = set()
        self.reacted = set()
        self.hidden = ()
        self.found = set()
        self.once_used = False
        self.dead = False

    def apply_damage(self, amount):
        """MonsterRuntime.ApplyDamage: 1타 상한 → 방어막 → 체력. 실제 체력 피해를 돌려준다."""
        if amount > 0 and self.cap > 0:
            amount = min(amount, self.cap)
        if amount > 0 and self.shield > 0:
            b = min(amount, self.shield)
            self.shield -= b
            amount -= b
        self.hp -= amount
        actual = amount if amount > 0 else 0
        if actual > 0 and self.cap > 0 and self.cap_until:
            self.cap_acc += actual
        return actual

    def sim_hit(self, amount, cap, shield):
        """apply_damage 를 상태 변경 없이 계산 (배분 평가용). 반환: (피해, 남은 방어막)."""
        if amount > 0 and cap > 0:
            amount = min(amount, cap)
        if amount > 0 and shield > 0:
            b = min(amount, shield)
            shield -= b
            amount -= b
        return (amount if amount > 0 else 0), shield


class PState:
    __slots__ = ("hp", "bleed", "poison", "pbleed", "ppoison", "debuff")

    def __init__(self, hp):
        self.hp = hp
        self.bleed = self.poison = self.pbleed = self.ppoison = 0
        self.debuff = None     # {"op": "minus"|"divide", "digits", "expires", "value"}


def binom(rng, n, p):
    if p >= 1:
        return n
    if p <= 0:
        return 0
    return sum(1 for _ in range(n) if rng.random() < p)


def pick_segments(rng, masks, n):
    """상자의 세그먼트 중 n 개를 무작위로 잠금 (자릿수별 비트마스크 튜플)."""
    segs = [(i, b) for i, m in enumerate(masks) for b in (1, 2, 4, 8, 16, 32, 64) if m & b]
    if n <= 0 or not segs:
        return tuple(0 for _ in masks)
    chosen = rng.sample(segs, min(n, len(segs)))
    out = [0] * len(masks)
    for i, b in chosen:
        out[i] |= b
    return tuple(out)


# ---------------------------------------------------------------------------
# 배분 (F8.4)
# ---------------------------------------------------------------------------
def prune(reach, better, feat=None, keep_all=False):
    """reach = {값: 최소 이동}. 특징이 같은 값끼리 (이동 수 오름차순) 파레토 프런트만 남긴다.
    better = +1 이면 큰 값이 좋음, -1 이면 작은 값이 좋음."""
    if keep_all:
        return sorted(((v, c) for v, c in reach.items()), key=lambda x: (x[1], -better * x[0]))
    groups = {}
    for v, c in reach.items():
        groups.setdefault(feat(v) if feat else None, []).append((v, c))
    out = []
    for items in groups.values():
        items.sort(key=lambda x: (x[1], -better * x[0]))
        best = None
        for v, c in items:
            if best is None or better * v > better * best:
                out.append((v, c))
                best = v
    return out


def allocate(boxes, K, evaluate):
    """boxes = [(name, [(값, 이동)])], 합계 이동 ≤ K 인 모든 조합 중 evaluate(dict) 의 키가 최대인 조합.
    evaluate 는 비교 가능한 키(튜플)를 돌려준다. 반환: (값 dict, 키, 사용 이동, 후보 수)."""
    names = [b[0] for b in boxes]
    opts = [b[1] for b in boxes]
    best, best_key, best_cost, n = None, None, 0, 0
    cur = {}

    def rec(i, used):
        nonlocal best, best_key, best_cost, n
        if i == len(opts):
            n += 1
            k = evaluate(cur)
            if best_key is None or k > best_key:
                best, best_key, best_cost = dict(cur), k, used
            return
        for v, c in opts[i]:
            if used + c > K:
                continue
            cur[names[i]] = v
            rec(i + 1, used + c)
        cur.pop(names[i], None)

    rec(0, 0)
    return best, best_key, best_cost, n


def objective(dealt, taken, hp, mhp, kill_first, w, extra_pen=0.0, heal=0, doom=False):
    """결정적 목적함수 키 (클수록 좋음). 생존 우선 → 처치 우선 → J."""
    if doom:
        taken = float("inf")
    alive = taken < hp
    kill = kill_first and dealt >= mhp
    J = w * (dealt - heal) / max(1, mhp) - (1 - w) * (taken if taken != float("inf") else 1e9) / max(1, hp) - extra_pen
    if not alive:
        return (0, 0, -taken, J)
    if kill:
        return (1, 1, -taken, J)
    return (1, 0, J, -taken)


# ---------------------------------------------------------------------------
# 전투
# ---------------------------------------------------------------------------
UNUSED_PARAMS = ("player.defense_cut_per_move", "player.attack_gain_per_move", "monsters.str_amount",
                 "monsters.tiers", "player.base_dmg_min", "player.base_dmg_max", "player.zero_hits_chance")


def policy_of(cfg):
    P = (cfg["player"].get("policy") or {})
    return {"w": float(P.get("attack_weight", 0.5)), "escape_pen": float(P.get("escape_penalty", 0.3)),
            "reset_at": int(P.get("reset_at_strength", 2)), "react_pen": P.get("react_penalty", "auto")}


def fight_digits(cfg, st, tier, act, rng):
    """반환: "win" | "death" | "timeout" | "escape" (카운트다운 도주 — 보상 없이 진행, 사용자 확인 Q24)."""
    P, F = cfg["player"], cfg["fantasy"]
    M_ = cfg["monsters"]
    G = M_.get("gimmicks", "off") == "on"
    pol = policy_of(cfg)
    w = pol["w"]
    skill = float(P["skill"])
    tr = st.trace
    floor_pos = getattr(st, "floor_pos", (act, st.stats["battles"]))
    seed = st.run_seed
    frng = st.fx_rng("battle", st.stats["battles"])

    fx = st.fx
    temp_copy = None
    if fx.has("battle_start_temp_copy"):
        cands = [k for k in st.owned if st.counts.get(k, 0) > 0 and not any(
            ef["type"] == "battle_start_temp_copy" for ef in st.ctx.table.get(k, {}).get("effects", ()))]
        if cands:
            temp_copy = frng.choice(cands)
            fx = fx.copy().add(temp_copy, 1)

    mon = st.ctx.pick_monster(st, tier, act)
    mhp0 = max(1, round(mon["hp"] * M_.get("hp_scale", 1.0)))
    specs = {}
    if G:
        for s in mon.get("sim") or ():
            specs.setdefault(s["kind"], []).append(s)
    sp = lambda k: (specs.get(k) or [None])[0]  # noqa: E731
    pats = mon["patterns"]

    # --- 환상 효과 (전투 동안 고정)
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
    skip_add = fx.sum("monster_skip_chance_add")
    str_add = list(fx.items("monster_str_add"))
    digit_max = [int(ef["value"]) for ef, c in fx.items("monster_dmg_digit_max")]
    has_transform = fx.has("base_dmg_transform")
    pstr_list = list(fx.items("player_str_add"))
    hits_plain = sum(int(ef.get("value", 0)) * c for ef, c in fx.items("hits_add") if not ef.get("when") and not ef.get("per"))
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
    polc = cfg["policy"]
    use_items, danger, max_items = polc["use_items"], polc["danger_ratio"], polc["max_items_per_turn"]
    max_turns = cfg["sim"]["max_turns"]
    stats = st.stats
    hp_start, items_start = st.hp, (st.matches, st.erasers)
    taken0 = stats["dmg_taken"]
    # 환상이 숫자 내용에 반응하면 가지치기 특징에 넣는다 (F8.5)
    feat_pairs = any(ef.get("per") == "consecutive_pairs" for ef, c in hits_other)
    feat_8 = any(per == "digit8" for _, per, _, _ in etd_list)
    feat_same = any("base_same_digits" in (ef.get("when") or {}) for ef, c in
                    list(fx.items("dmg_flat")) + hits_other + list(fx.items("player_str_add")))
    joint_pd = any(cond in ("base_eq_monster_dmg",) for cond, _ in final_list) or \
        any(cond == "monster_dmg_ge_player_base" for cond, _ in taken_mult)

    if tr is not None:
        tr.append({"ev": "battle", "tier": tier, "act": act, "monster": mon["id"], "mhp": mhp0, "hp": st.hp,
                   "temp_copy": temp_copy, "fx": ms.fx_contributors(st, temp_copy), "model": "digits",
                   "gimmicks": G})

    attempt = 0
    while True:
        def roll(turn, tag, _a=attempt):
            parts = (seed, floor_pos[0], floor_pos[1], "dg", turn, tag) + ((_a,) if _a else ())
            return ms.rng_for(*parts)

        m = Mon(mhp0, int(mon.get("strength") or 0))
        p = PState(st.hp)
        cap = sp("cap_per_hit")
        if cap:
            m.cap = int(cap["value"])
            m.cap_until = cap.get("until_taken")
        cd = sp("countdown")
        if cd:
            m.countdown = int(cd["init"])
        if sp("hidden_digits"):
            hr = roll(0, "hidden")
            a = hr.randint(0, 9)
            b = hr.randint(0, 8)
            if b >= a:
                b += 1
            m.hidden = (a, b)
        rx = sp("reactive_boxes")
        if rx:
            rr = roll(0, "react")
            cands = list(rx["boxes"])
            gs, per = int(rx["group"]), int(rx["per_group"])
            for g0 in range(0, len(cands), gs):
                grp = cands[g0:g0 + gs]
                avail = list(range(len(grp)))
                for _ in range(min(per, len(grp))):
                    k = rr.randint(0, len(avail) - 1)
                    m.reactive.add(grp[avail[k]])
                    avail.pop(k)
        pstr = 0
        str_blocks = int(fx.sum("str_block"))
        temp_items = int(fx.sum("battle_temp_items"))
        items_used_battle = 0
        carry = 0
        delayed = 0
        prev_hit, combo = None, 0
        outcome = "timeout"
        max_hit = 0
        last_moves = 0
        struct_next = {}          # 다음 턴 구조 효과 (분할·잠금)
        turn = 0

        def env(dealt=0, t=0):
            p.hp = st.hp
            return Env(m, p, dealt, (lambda tag: roll(t, "x" + tag)) if t else None)

        def usable(pt, t):
            mu = pt.get("max_uses")
            if mu is not None and m.uses.get(pt["key"], 0) >= mu:
                return False
            if G and pt.get("condition"):
                return eval_cond(pt["condition"], env(0, t))
            return True

        def select_pattern(t):
            n = len(pats)
            if mon.get("ai") == "random":
                ok = [pt for pt in pats if usable(pt, t)]
                if ok:
                    return ok[roll(t, "pat").randint(0, len(ok) - 1)]
            s0 = (t - 1) % n
            for off in range(n):
                pt = pats[(s0 + off) % n]
                if usable(pt, t):
                    return pt
            return {"key": "2_Single", "kind": "attack", "multi": False, "dmg_digits": 2, "hit_digits": None}

        for turn in range(1, max_turns + 1):
            stats["turns"] += 1
            p.hp = st.hp
            # ---- 1. 턴 준비
            ph2 = sp("phase_two")
            if ph2 and m.phase == 1 and m.hp <= math.floor(m.base_hp * float(ph2["hp_rate"])):
                m.phase = 2
                m.special = None
            # 이동 한도
            M = int(moves_base) + carry + (start_moves if turn == 1 else 0)
            carry = 0
            if ph2 and m.phase == 2 and ph2.get("move_limit") is not None and int(ph2["move_limit"]) >= 0:
                M = int(ph2["move_limit"])
            sh = sp("moves_decay")
            if sh:      # 그림자 (사용자 규칙 Q25): 매 턴 이동 횟수 1 씩 감소
                M = max(0, M - int(sh.get("per_turn", 1)) * (turn - 1))
            # 환상: 내 힘
            for ef, c in pstr_list:
                if (ef.get("when") and ms._when_ok(ef["when"], turn, 0)) or (not ef.get("when") and turn == 1):
                    pstr += ef.get("value", 0) * c
            # 플레이어 기본 피해: 자릿수 2 + 힘
            dP = 2 + max(0, int(pstr))
            P0 = roll(turn, "pbase").randint(dmin(dP), dmax(dP))
            Pv = ms.transform_base(P0, fx) if has_transform else P0
            Pv = max(0, int(Pv))
            dPb = max(dP, ndig(Pv))
            # 공격 조건 (지휘자·피리 부는 사나이)
            cond = None
            fc = sp("formula_condition")
            if fc:
                cr = roll(turn, "cond")
                if fc["type"] == "DigitCount":
                    cond = {"type": "DigitCount", "value": cr.randint(int(fc["value_min"]), max(int(fc["value_min"]), int(fc["value_max"]))),
                            "count": cr.randint(int(fc["count_min"]), max(int(fc["count_min"]), int(fc["count_max"]))),
                            "editable": bool(fc.get("count_editable"))}
                else:
                    ops = fc.get("operators") or ["=="]
                    cond = {"type": "Compare", "value": cr.randint(int(fc["value_min"]), int(fc["value_max"])),
                            "op": ops[cr.randint(0, len(ops) - 1)]}
            # 조준 사격
            aim = None
            am = sp("aimed_shot")
            if am and float(am["multiplier"]) > 1:
                aim = roll(turn, "aim").randint(0, 9)
            # 디버프 상자
            if p.debuff is not None:
                if p.debuff["expires"] is not None and turn > p.debuff["expires"]:
                    p.debuff = None
                else:
                    dd = p.debuff["digits"]
                    p.debuff["value"] = roll(turn, "debuff").randint(max(1, dmin(dd)), dmax(dd))
            # 턴 시작 성냥 잠금
            n_lock = sum(int(s["count"]) for s in specs.get("lock_matches") or () if s["timing"] == "turn_start")
            if turn == 1:
                n_lock += sum(int(s["count"]) for s in specs.get("lock_matches") or () if s["timing"] == "battle_start")
            Pmasks = bm.masks_of(Pv, dPb)
            locks = pick_segments(roll(turn, "lock"), Pmasks, n_lock) if n_lock else None
            # 접미 조건 상자 (고래 1페이즈)
            sf = sp("suffix")
            if sf and m.phase == 1:
                nd = int(sf["digits"])
                m.special = {"value": roll(turn, "suffix").randint(0 if nd <= 1 else 10 ** (nd - 1), 10 ** nd - 1),
                             "digits": nd, "label": "TARGET", "editable": False}
            # 패턴 선택
            stunned = m.stun > 0
            pt = select_pattern(turn)
            kind = pt.get("kind", "attack")
            if not G and kind not in ("attack", "str"):
                kind = "skip"
            mod = sum(ef.get("value", 0) * c for ef, c in str_add if ms._when_ok(ef.get("when"), turn, 0)) if str_add else 0
            D = H = 0
            dD = hD = 0
            heal_box = None
            if not stunned and kind == "attack":
                dyn = pt.get("dynamic") if G else None
                dD = max(1, int(pt.get("dmg_digits") or 2) + m.strength + int(mod))
                if dyn:
                    D = max(0, int(math.floor(eval_value(dyn, env(0, turn)))))
                    dD = max(1, int(pt.get("dmg_digits") or 1), ndig(D))
                else:
                    D = roll(turn, "mdmg").randint(dmin(dD), dmax(dD))
                for v in digit_max:
                    D = ms._digits_map(D, lambda d, v=v: min(d, v))
                if pt.get("multi"):
                    hD = max(1, int(pt.get("hit_digits") or 1))
                    H = roll(turn, "mhit").randint(dmin(hD), dmax(hD))
                else:
                    H, hD = 1, 1
            if G and not stunned and pt.get("heal") and pt["heal"].get("editable"):
                hd = max(1, int(math.floor(eval_value(pt["heal"].get("expr") if pt["heal"].get("expr") is not None
                                                      else pt["heal"].get("amount"), env(0, turn)))))
                heal_box = {"digits": hd, "value": roll(turn, "heal").randint(dmin(hd), dmax(hd))}
            # 상시 규칙 + 예약 효과 → 구조 제약
            p_split = bool(sp("split_player")) or (ph2 is not None and m.phase == 2 and ph2.get("split_all"))
            m_split = ph2 is not None and m.phase == 2 and ph2.get("split_all")
            p_movable = not bool(sp("player_immovable"))
            m_dmg_locked = bool(sp("lock_monster_damage"))
            m_movable = True
            locked_digits = ()
            if sp("strength_reset") and sp("strength_reset").get("lock_all") and m.once_used:
                p_movable = False
            for (tt, ef) in [x for x in m.scheduled if x[0] <= turn]:
                m.scheduled.remove((tt, ef))
                _apply_effect(ef, m, p, st, env, turn, roll, 0, None, struct_next, Pv, 1, stats)
            st_now = struct_next.pop(turn, {})
            if st_now.get("split_player"):
                p_split = True
            if st_now.get("split_self"):
                m_split = True
            if st_now.get("lock_player"):
                p_movable = False
            if st_now.get("lock_self"):
                m_movable = False
            if st_now.get("box_lock"):
                locked_digits = tuple(range(min(dPb, int(st_now["box_lock"]))))
            # ---- 2. 배분
            p_hits = 1 + hits_plain
            for ef, c in hits_other:
                if not ms._when_ok(ef.get("when"), turn, Pv):
                    continue
                per = ef.get("per")
                if per == "items_held":
                    p_hits += int((st.matches + st.erasers + temp_items) // ef.get("divisor", 10)) * c
                elif per == "consecutive_pairs":
                    pass        # 최종 값으로 평가
                else:
                    p_hits += int(ef.get("value", 0)) * c
            pairs_c = sum(c for ef, c in hits_other if ef.get("per") == "consecutive_pairs" and ms._when_ok(ef.get("when"), turn, Pv))
            flat = flat_plain + sum(ef.get("value", 0) * c for ef, c in flat_when if ms._when_ok(ef["when"], turn, Pv))
            # 아이템 = 추가 이동 (gauss 와 같은 정책)
            n_items = 0
            inv = st.matches + st.erasers + temp_items
            if inv and use_items != "never" and kind == "attack":
                inc = max(0, D + taken_flat) * H
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
                    M += n
                    stats["items_used"] += n
                    items_used_battle += n
            K = binom(roll(turn, "skill"), M, skill)
            amul = float(am["multiplier"]) if (am and aim is not None) else 1.0
            lib = G and any(ef.get("op") == "librarian_skill" for ef in pt.get("effects") or ())
            zero_sp = G and sp("zero_special_digits") and m.special
            zero_set = set(str(m.special["value"])) if zero_sp else set()
            hidden = m.hidden if G else ()

            def p_feat(v):
                s = str(v)
                f = []
                if aim is not None:
                    f.append(str(aim) in s)
                if hidden:
                    f.append(tuple(h in m.found and str(h) in s for h in hidden))
                    f.append(len(set(s) - {str(h) for h in hidden if h in m.found}))
                if sf and m.phase == 1 and m.special:
                    nd = int(sf["digits"])
                    f.append(v % (10 ** nd) == m.special["value"] % (10 ** nd))
                if cond and cond["type"] == "DigitCount":
                    f.append(s.count(str(cond["value"])))
                if cond and cond["type"] == "Compare":
                    f.append(None)      # 값 자체로 판정 → 가지치기 안 함(아래 keep_all)
                if zero_set:
                    f.append(int("".join("0" if ch in zero_set else ch for ch in s) or "0"))
                if feat_pairs:
                    f.append(ms._consecutive_pairs(v))
                if feat_8:
                    f.append(s.count("8"))
                if feat_same:
                    f.append(len(s) > 1 and len(set(s)) == 1)
                return tuple(f)

            boxes = []
            p_keep_all = joint_pd or lib or bool(cond and cond["type"] == "Compare") or bool(zero_set)
            pr = bm.reach_best(dPb, Pv, K if p_movable else 0, +1, split=p_split, locked=locks, locked_digits=locked_digits,
                               movable=p_movable)
            boxes.append(("P", prune(pr, +1, p_feat, keep_all=p_keep_all)))
            if kind == "attack" and not stunned:
                d_ok = m_movable and not m_dmg_locked and pt.get("dmg_editable", True)
                dr = bm.reach_best(dD, D, K if d_ok else 0, -1, split=m_split, movable=d_ok)
                d_feat = (lambda v: (ms._consecutive_pairs(v) if feat_pairs else 0, str(v).count("8") if feat_8 else 0))
                boxes.append(("D", prune(dr, -1, d_feat, keep_all=joint_pd)))
                if pt.get("multi"):
                    hr_ = bm.reach_best(hD, H, K if m_movable else 0, -1, split=m_split, movable=m_movable)
                    boxes.append(("H", prune(hr_, -1)))
            if heal_box:
                hb = bm.reach_best(heal_box["digits"], heal_box["value"], K if m_movable else 0, -1, split=m_split, movable=m_movable)
                boxes.append(("HB", prune(hb, -1)))
            if p.debuff is not None:
                db = bm.reach_best(p.debuff["digits"], p.debuff["value"], K if p_movable else 0, -1, split=p_split, movable=p_movable)
                if p.debuff["op"] == "divide":
                    db = {v: c for v, c in db.items() if v != 0}      # 0 으로 나누기 무효 → 닫을 수 없음
                boxes.append(("X", prune(db, -1)))
            if m.countdown is not None and cd.get("editable", True):
                cr_ = bm.reach(1, m.countdown, K, movable=True)
                cr_ = {v: c for v, c in cr_.items() if int(cd.get("min", 0)) <= v <= int(cd.get("max", 9))}
                boxes.append(("CD", prune(cr_, +1)))
            if cond and cond["type"] == "DigitCount" and cond["editable"]:
                cc = bm.reach(1, cond["count"], K, movable=True)
                boxes.append(("C", prune(cc, +1, lambda v: v)))

            hp_now = st.hp
            mhp_now = m.hp

            def player_per_hit(vals, real=False):
                Pp = vals["P"]
                one = max(0, round(Pp * dmg_mult) + flat)
                fm = 1.0
                for cnd, factor in final_list:
                    if cnd == "base_eq_monster_dmg" and Pp != vals.get("D", D):
                        continue
                    fm *= factor
                d = int(one * fm)
                if not G:
                    return d
                return _player_rules(d, Pp, vals, real)

            def _player_rules(d, Pp, vals, real):
                # 디버프 (빼기·나누기)
                if p.debuff is not None:
                    x = vals.get("X", p.debuff["value"])
                    d = d - x if p.debuff["op"] == "minus" else (d // x if x else 0)
                    d = max(0, d)
                # 공격 조건
                if cond:
                    if cond["type"] == "DigitCount":
                        cnt = str(Pp).count(str(cond["value"])) + str(p_hits).count(str(cond["value"]))
                        if p.debuff is not None:
                            cnt += str(vals.get("X", p.debuff["value"])).rjust(p.debuff["digits"], "0").count(str(cond["value"]))
                        if cnt != vals.get("C", cond["count"]):
                            d = 0
                    else:
                        base = int(max(0, round(Pp * dmg_mult) + flat))
                        op = cond["op"]
                        ok = base < cond["value"] if op == "<" else base > cond["value"] if op == ">" else base == cond["value"]
                        if not ok:
                            d = 0
                # 숨은 숫자 (발견 전에는 플레이어가 기대값으로 판단)
                if hidden:
                    s = str(abs(Pp))
                    ratio = float(sp("hidden_digits")["ratio"])
                    if real:
                        fnd = [h for h in hidden if str(h) in s]
                        for h in fnd:
                            m.found.add(h)
                        d = int(math.floor(d * min(1.0, len(fnd) * ratio)))
                    else:
                        known = [h for h in hidden if h in m.found]
                        unk = [h for h in hidden if h not in m.found]
                        exp_found = sum(1 for h in known if str(h) in s)
                        if unk:
                            free = len(set(s) - {str(h) for h in known})
                            exp_found += len(unk) * min(1.0, free / max(1, 10 - len(known)))
                        d = d * min(1.0, exp_found * ratio)
                # 접미 조건 (1페이즈)
                if sf and m.phase == 1:
                    nd = int(sf["digits"])
                    if not m.special or Pp % (10 ** nd) != m.special["value"] % (10 ** nd):
                        d = 0
                # 특수 상자 숫자 0 처리
                if zero_set and Pp > 0:
                    z = int("".join("0" if ch in zero_set else ch for ch in str(Pp)) or "0")
                    d = int(math.floor(d * z / Pp))
                return d

            def per_hit_in(vals):
                per = vals.get("D", D)
                if aim is not None and amul > 1:
                    s = str(vals["P"]) + str(p_hits) + (str(vals.get("X", p.debuff["value"])) if p.debuff else "")
                    if str(aim) in s:
                        per = int(per * amul)
                v = max(0, round(per * (1 - def_cut)) + taken_flat)
                for cnd, factor in taken_mult:
                    if cnd == "monster_dmg_ge_player_base" and not vals.get("D", D) >= vals["P"]:
                        continue
                    v = int(v * factor)
                return v

            react_cost = 0.0
            if m.reactive:
                avg_now = (dmin(max(1, dD)) + dmax(max(1, dD))) / 2 if dD else 50
                avg_up = (dmin(dD + 1) + dmax(dD + 1)) / 2 if dD else 500
                react_cost = (1 - w) * (avg_up - avg_now) / max(1, hp_now) if pol["react_pen"] == "auto" else float(pol["react_pen"])
            direct_exp = 0
            if G and not stunned:
                for ef in pt.get("effects") or ():
                    if ef.get("op") == "deal_damage" and ef.get("target") == "player" and ef.get("timing", "immediate") == "immediate":
                        direct_exp += _direct_estimate(ef, m, hp_now)
            # 상태 피해 (이번 턴 끝에 받음)
            status_now = p.bleed + p.poison

            def evaluate(vals):
                d1 = player_per_hit(vals)
                hits = p_hits + (ms._consecutive_pairs(vals["P"], vals.get("D", D)) * pairs_c if pairs_c else 0)
                dealt, shield = 0, m.shield
                hp_left = mhp_now
                for _ in range(hits):
                    if d1 <= 0 or hp_left <= 0:
                        break
                    a, shield = m.sim_hit(d1, m.cap, shield)
                    dealt += a
                    hp_left -= a
                taken = 0
                if kind == "attack" and not stunned:
                    taken = per_hit_in(vals) * vals.get("H", H)
                    if lib:
                        taken += (vals["P"] + p_hits) / 2.0
                taken += direct_exp + status_now
                heal = vals.get("HB", 0) if heal_box else 0
                pen = 0.0
                doom = False
                if m.countdown is not None:
                    c1 = vals.get("CD", m.countdown) - 1
                    if c1 <= 0:
                        if cd.get("on_zero") == "escape":
                            pen += pol["escape_pen"]
                        else:
                            doom = True
                    elif cd.get("editable", True) and max(bm.reach(1, c1, max(0, int(moves_base))) or {c1: 0}) - 1 <= 0:
                        pen += pol["escape_pen"] * 0.5 if cd.get("on_zero") == "escape" else 0.5
                if m.reactive:
                    for name, box in (("P", "player.damage"), ("D", "monster.damage"), ("H", "monster.hits")):
                        if box in m.reactive and box not in m.reacted and name in vals:
                            base_v = {"P": Pv, "D": D, "H": H}[name]
                            if vals[name] != base_v:
                                pen += react_cost
                return objective(dealt, taken, hp_now, mhp_now, not enemy_first, w, pen, heal, doom)

            beam = False
            prod = 1
            for _, o in boxes:
                prod *= max(1, len(o))
            if prod > BEAM_LIMIT:      # F8.4-5: 후보가 너무 많으면 상자마다 앞쪽(적은 이동·좋은 값) 후보만 남김
                beam = True
                keep = max(2, int(BEAM_LIMIT ** (1.0 / len(boxes))))
                boxes = [(nm, o[:keep]) for nm, o in boxes]
                st.beam_turns = getattr(st, "beam_turns", 0) + 1     # 행 키는 바꾸지 않는다
            vals, key, used, ncand = allocate(boxes, K, evaluate)
            Pp = vals["P"]
            Dp = vals.get("D", D)
            Hp = vals.get("H", H)
            if p.debuff is not None and "X" in vals:
                p.debuff["value"] = vals["X"]
            if m.countdown is not None and "CD" in vals:
                m.countdown = vals["CD"]
            if cond and "C" in vals:
                cond["count"] = vals["C"]
            if heal_box and "HB" in vals:
                heal_box["value"] = vals["HB"]
            if m.reactive:
                for name, box in (("P", "player.damage"), ("D", "monster.damage"), ("H", "monster.hits")):
                    if box in m.reactive and box not in m.reacted and name in vals and vals[name] != {"P": Pv, "D": D, "H": H}[name]:
                        m.reacted.add(box)
                        m.strength += int(rx.get("strength", 1))
            unused = M - used
            last_moves = used
            # CosmicTree: 힘 초기화 (1회, 플레이어 판단)
            sr = sp("strength_reset")
            if sr and not m.once_used and m.strength - m.base_strength >= pol["reset_at"]:
                m.once_used = True
                m.strength = m.base_strength
                if tr is not None:
                    tr.append({"ev": "strength_reset", "t": turn})
            # ---- 3. 공식 평가 (실제)
            vals_real = dict(vals)
            d1 = player_per_hit(vals_real, real=True)
            hits = p_hits + (ms._consecutive_pairs(Pp, Dp) * pairs_c if pairs_c else 0)
            mon_vals = {"P": Pp, "D": Dp, "X": vals.get("X")}
            per_in = per_hit_in(mon_vals) if (kind == "attack" and not stunned) else 0
            if Dp > max_hit:
                max_hit = Dp

            def end_turn_dmg():
                total = 0
                for wh, per, v, c in etd_list:
                    if not ms._when_ok(wh, turn, Pp):
                        continue
                    if per == "items_held":
                        v *= st.matches + st.erasers + temp_items
                    elif per == "items_used_battle":
                        v *= items_used_battle
                    elif per == "hp":
                        v *= max(0, st.hp)
                    elif per == "digit8":
                        v *= (str(Pp) + str(Dp)).count("8")
                    total += v * c
                return int(total)

            mhp_before, hp_before = m.hp, st.hp
            taken_turn = 0
            res = None
            etd_real = 0

            def monster_acts():
                nonlocal pstr, str_blocks, delayed, taken_turn, res
                if m.dead:
                    return None
                if stunned:
                    m.stun = max(0, m.stun - 1)
                    return None
                skip = skip_add > 0 and frng.random() < skip_add
                if skip:
                    return None
                total = 0
                if kind == "attack":
                    for _ in range(Hp):
                        if per_in <= 0:
                            break
                        now = per_in - int(per_in * delay_frac)
                        delayed += per_in - now
                        st.hp -= now
                        stats["dmg_taken"] += now
                        taken_turn += now
                        total += now
                        for rv, rp, c in reflect:
                            m.hp -= int((rv + rp * per_in) * c)
                        for hper, hv, c in heal_take:
                            h = int(per_in // hper) * hv * c
                            st.hp += h
                            stats["hp_healed"] += h
                        if st.hp <= 0:
                            return "death"
                    if G and total == 0 and sp("zero_damage_str_down"):
                        m.strength += int(sp("zero_damage_str_down")["amount"])
                    ls = sp("lifesteal")
                    if ls and total > 0:
                        m.hp += int(math.floor(total * float(ls["rate"])))
                    if m.hp <= 0:
                        return "win"
                elif kind == "str" and not (G and pt.get("source") == "pattern"):
                    gain = int(pt.get("str_units", 1))
                    if gain > 0 and str_blocks > 0:
                        str_blocks -= 1
                    else:
                        m.strength += gain
                        pstr += gain * mirror_str
                if G:
                    for ef in pt.get("effects") or ():
                        if ef.get("timing", "immediate") == "next_turn":
                            m.scheduled.append((turn + 1, ef))
                            continue
                        r = _apply_effect(ef, m, p, st, env, turn, roll, total, heal_box, struct_next, Pp, p_hits, stats)
                        if r:
                            taken_turn += r
                        if st.hp <= 0:
                            return "death"
                    m.uses[pt["key"]] = m.uses.get(pt["key"], 0) + 1
                    if pt.get("self_destruct"):
                        m.dead = True
                        m.hp = min(m.hp, 0)
                        return "win"
                else:
                    m.uses[pt["key"]] = m.uses.get(pt["key"], 0) + 1
                return None

            if enemy_first:
                res = monster_acts()
            if res is None:
                for _ in range(hits):
                    d = d1
                    if has_combo:
                        if prev_hit is not None and d == prev_hit:
                            combo += combo_step
                        else:
                            combo = 0
                        prev_hit = d
                        d += combo
                    if d <= 0:
                        continue
                    m.apply_damage(d)
                    if heal_deal:
                        st.hp += heal_deal
                        stats["hp_healed"] += heal_deal
                    if m.hp <= 0:
                        break
                if has_etd:
                    etd_real = end_turn_dmg()
                    m.hp -= etd_real
                h = int(heal_unused * unused)
                if h:
                    st.hp += h
                    stats["hp_healed"] += h
                if carry_on:
                    carry = unused
                if m.hp <= 0:
                    res = "win"
                elif delayed:
                    st.hp -= delayed
                    stats["dmg_taken"] += delayed
                    taken_turn += delayed
                    delayed = 0
                    if st.hp <= 0:
                        res = "death"
                if res is None and not enemy_first:
                    res = monster_acts()
            # ---- 9. 상태 피해
            if res is None and G:
                sd = p.bleed + p.poison
                if sd > 0:
                    st.hp -= sd
                    stats["dmg_taken"] += sd
                    taken_turn += sd
                p.bleed = 0
                p.bleed += p.pbleed
                p.poison += p.ppoison
                p.pbleed = p.ppoison = 0
                if st.hp <= 0:
                    res = "death"
            # ---- 10. 지속시간
            if res is None:
                for tm in list(m.timed):
                    tm[1] -= 1
                    if tm[1] <= 0:
                        m.strength -= tm[0]
                        m.timed.remove(tm)
            # ---- 11. 카운트다운
            if res is None and m.countdown is not None:
                m.countdown -= int(cd.get("amount", 1))
                if m.countdown <= 0:
                    m.countdown = 0
                    if cd.get("on_zero") == "escape":
                        res = "escape"
                    else:
                        tgt = next((x for x in pats if x["key"] == cd.get("pattern")), None)
                        for ef in (tgt or {}).get("effects") or ():
                            r = _apply_effect(ef, m, p, st, env, turn, roll, 0, None, struct_next, Pp, p_hits, stats)
                            if r:
                                taken_turn += r
                        if st.hp <= 0:
                            res = "death"
                        elif m.hp <= 0:
                            res = "win"
            if tr is not None:
                tr.append({"ev": "turn", "t": turn, "intent": kind, "pattern": pt.get("key"), "mon_dmg": D, "mon_dmg_edit": Dp,
                           "hits": H, "hits_edit": Hp, "base": Pv, "base_edit": Pp, "moves": M, "K": K, "used": used,
                           "items": n_items, "p_hits": hits, "cand": ncand, "beam": beam, "dealt": mhp_before - m.hp, "etd": etd_real,
                           "taken": taken_turn, "hp_change": st.hp - hp_before, "hp": st.hp, "mhp": m.hp, "end": res,
                           "aim": aim, "special": (m.special or {}).get("value"), "countdown": m.countdown,
                           "phase": m.phase, "mstr": m.strength})
            if res:
                outcome = res
                break

        if st.battle_log is not None:
            st.battle_log.append({"monster": mon["id"], "tier": tier, "act": act, "turns": turn,
                                  "floor": (getattr(st, "floor_pos", None) or (None, None))[1],
                                  "taken": stats["dmg_taken"] - taken0, "outcome": outcome, "max_hit": int(max_hit)})
        if outcome == "death" and revives > 0:
            revives -= 1
            attempt += 1
            st.hp = hp_start
            st.matches, st.erasers = items_start
            if tr is not None:
                tr.append({"ev": "rewind"})
            continue
        if tr is not None:
            tr.append({"ev": "battle_end", "outcome": outcome, "hp": st.hp, "turns": turn})
        return outcome


def _direct_estimate(ef, m, hp):
    """배분 평가용: 이번 턴 직접 피해의 기대값 (deal_damage)."""
    k = _norm(ef.get("expr") or "")
    hits = 3 if k == "stargazingmulti3" else max(1, int(ef.get("hits") or 1))
    if ef.get("expr") is None:
        return float(ef.get("amount") or 0) * hits
    if k == "playerhpmulti2":
        return hp * 0.545
    if k == "stargazingmulti3":
        return (m.special["value"] if m.special else 0) * 3
    if "playerhp" in k:
        return hp * 0.3
    return 0.0


def _apply_effect(ef, m, p, st, envf, turn, roll, dealt, heal_box, struct_next, Pp, p_hits, stats):
    """패턴 효과 하나 (MonsterPatternRunner.ApplyEffect). 플레이어가 받은 직접 피해를 돌려준다."""
    op = ef.get("op")
    typ = _norm(ef.get("type"))
    tgt = ef.get("target") or "self"
    e = envf(dealt, turn)
    if ef.get("expr") is not None:
        val = int(math.floor(eval_value(ef["expr"], e)))
    elif ef.get("amount") is not None:
        val = int(math.floor(float(ef["amount"])))
    else:
        val = int(ef.get("duration") or 0)
    if op == "split_box":      # 예약(next_turn) 효과: 실행된 턴(다음 턴)에만 적용 (지속시간 1턴으로 근사)
        struct_next.setdefault(turn, {})["split_player" if tgt == "player" else "split_self"] = True
        return 0
    if op == "lock_box":
        cur = struct_next.setdefault(turn, {})
        cur["lock_player" if tgt == "player" else "lock_self"] = True
        return 0
    if op == "heal":
        if heal_box is not None and tgt != "player":
            val = heal_box["value"]
        if tgt == "player":
            st.hp += max(0, val)
        else:
            m.hp += max(0, val)
        return 0
    if op == "deal_damage":
        if _norm(ef.get("expr") or "") == "playerformularandomnumber":
            val = Pp
        hits = 3 if _norm(ef.get("expr") or "") == "stargazingmulti3" else max(1, int(ef.get("hits") or 1))
        if tgt == "self":
            m.apply_damage(val)
            return 0
        tot = 0
        for _ in range(hits):
            a = max(0, val)
            st.hp -= a
            stats["dmg_taken"] += a
            tot += a
        return tot
    if op == "librarian_skill":
        nums = [Pp, p_hits]
        a = max(0, nums[roll(turn, "lib").randint(0, len(nums) - 1)])
        st.hp -= a
        stats["dmg_taken"] += a
        return a
    if op == "create_formula_box":
        n = max(1, int(ef.get("repeat") or 1))
        if _norm(ef.get("expr") or "") == "random":
            rr = roll(turn, "box")
            v = 0
            for _ in range(n):
                v = v * 10 + rr.randint(0, 9)
        else:
            v = max(0, min(9, val))
        if ef.get("mode") == "append" and n == 1:
            if m.special is None:
                m.special = {"value": v, "digits": 1, "label": ef.get("label"), "editable": False}
            else:
                m.special = dict(m.special, value=m.special["value"] * 10 + v, digits=m.special["digits"] + 1)
        else:
            m.special = {"value": v, "digits": n, "label": ef.get("label"), "editable": False}
        return 0
    if op == "remove_status":
        _set_buff(m, p, typ, 0)
        if typ == "shield":
            m.cap = 0
        return 0
    if op == "add_status":
        if typ in ("minusbox", "dividebox"):
            dur = ef.get("duration")
            p.debuff = {"op": "minus" if typ == "minusbox" else "divide", "digits": max(1, val),
                        "expires": (turn + int(dur)) if dur else None, "value": 1}
            return 0
        if typ == "boxlock":
            struct_next.setdefault(turn, {})["box_lock"] = max(1, val)
            return 0
        if typ == "strength":
            m.strength += val
        elif typ == "stun":
            m.stun += val
        elif typ == "shield":
            m.shield = max(0, m.shield + val)
        elif typ == "fortunestack":
            m.fortune = max(0, m.fortune + val)
        elif typ in ("prophecystack", "prophetstack"):
            m.prophecy = max(0, m.prophecy + val)
        elif typ == "bleed":
            p.pbleed = max(0, p.pbleed + val)
        elif typ == "poison":
            p.ppoison = max(0, p.ppoison + val)
        elif typ == "phase2":
            m.phase = 2
        return 0
    if op == "set_status":
        _set_buff(m, p, typ, val)
        return 0
    if op == "multiply_stat":
        k = max(0, val)
        if typ == "strength":
            m.strength *= k
        elif typ == "shield":
            m.shield *= k
        elif typ == "fortunestack":
            m.fortune *= k
        elif typ in ("prophecystack", "prophetstack"):
            m.prophecy *= k
        elif typ == "bleed":
            p.bleed = max(0, p.bleed * k)
        elif typ == "poison":
            p.poison = max(0, p.poison * k)
        return 0
    return 0


def _set_buff(m, p, typ, val):
    if typ == "strength":
        m.strength = val
    elif typ == "stun":
        m.stun = val
    elif typ == "shield":
        m.shield = max(0, val)
    elif typ == "fortunestack":
        m.fortune = max(0, val)
    elif typ in ("prophecystack", "prophetstack"):
        m.prophecy = max(0, val)
    elif typ == "bleed":
        p.pbleed = max(0, val)
    elif typ == "poison":
        p.ppoison = max(0, val)
    elif typ in ("phase", "phase2"):
        m.phase = max(1, val)
