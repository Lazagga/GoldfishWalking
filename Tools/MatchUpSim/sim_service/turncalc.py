# -*- coding: utf-8 -*-
"""v4.5 F21 턴 피해 분해 — 한 턴의 '내가 준 피해'와 '내가 받은 피해'가 어떻게 만들어졌는지를 출처별로 적는다.

fight_digits 의 전투 루프는 트레이스를 켰을 때만 이 모듈을 부른다(시뮬 경로는 그대로, 상태·난수를 건드리지 않음).
여기 함수는 전부 순수 함수다: 전투가 기록해 둔 입력(`ctx`)과 환상 효과 목록(`matchup_sim.fx_contributors` 모양)만 받는다.

- 단계 목록(순차 증감): 적용 순서대로 `전 → 후`를 적는다. 합이 `최종 − 기본`.
- 제거 시 차이(ablate): 같은 입력에서 출처(환상) 하나만 빼고 같은 공식을 다시 계산한 값과의 차이.
- 초과 피해: 체력을 넘은 양을 치명 타격의 단계 증감 비율로 출처에 나누고(`over.by`), 초과를 줄인 출처(`over.reduced`)와
  제거 시 차이(`over.ablate`)도 적는다.
- 표에 없는 요인은 이름 붙은 `extra` 항목으로 적고, 그래도 남는 차이는 `미분류`(unclassified)로 보인다 — 0 이어야 한다(AC-T2).
"""
from __future__ import annotations

NAMES = {"move": "성냥 이동", "item": "아이템", "base": "굴림"}


def _plain(e):
    return not (e.get("when") or e.get("per"))


def ssum(idx, t, excl=None):
    """Fx.sum 과 같은 값: when·per 가 없는 효과의 value × 개수 합 (value 기본 1)."""
    return sum(e.get("value", 1) * e["count"] for e in idx.get(t, ()) if _plain(e) and e["fid"] != excl)


def _ents(idx, t, excl=None):
    return [e for e in idx.get(t, ()) if e["fid"] != excl]


def _fids(entries, wf=None):
    """[[fid, 개수, 가중치]] — 같은 환상은 합친다. 가중치 = 그 환상이 이 단계에 더한 양의 크기(순차 증감을 출처별로 나눌 때)."""
    out = {}
    for e in entries:
        w = wf(e) if wf else e.get("value", 1) * e["count"]
        o = out.setdefault(e["fid"], [e["fid"], 0, 0.0])
        o[1] += e["count"]
        o[2] += abs(w)
    return [[f, c, round(w, 6)] for f, c, w in out.values()]


def _trunc(x):
    """소수점 버림 (F22-D) — matchup_sim.trunc 와 같은 식 (이 모듈은 시뮬 모듈을 가져오지 않는다)."""
    return int(x + 1e-9) if x >= 0 else -int(-x + 1e-9)


def _fx_src(t, entries, wf=None):
    return {"kind": "fx", "type": t, "fids": _fids(entries, wf)}


# ───────────── 내가 준 피해 ─────────────
def dealt_chain(idx, c, excl=None):
    """한 번 타격의 피해 (환상 부분): 기본 숫자 → 배율 → 고정 피해 → 최종 배율. 반환 dict: 중간값과 단계."""
    Pp = c["Pp"]
    mult_e = [e for e in _ents(idx, "dmg_mult_add", excl) if _plain(e)]
    mult = 1.0 + ssum(idx, "dmg_mult_add", excl)
    m1 = _trunc(Pp * mult)
    flat_e = _ents(idx, "dmg_flat", excl)
    fl_plain = sum(e.get("value", 0) * e["count"] * (c["act"] if e.get("act_scaling") else 1) for e in flat_e if not e.get("when"))
    fl_on, fl_off = [], []
    for e in flat_e:
        if e.get("when"):
            (fl_on if c["when_ok"](e["when"], c["turn"], c["Pv"]) else fl_off).append(e)
    flat = fl_plain + sum(e.get("value", 0) * e["count"] for e in fl_on)
    one_raw = m1 + flat
    one = max(0, one_raw)
    fm, fin_on, fin_off = 1.0, [], []
    for e in _ents(idx, "dmg_final_mult", excl):
        if e.get("condition") == "base_eq_monster_dmg" and Pp != c["d_eff"]:
            fin_off.append(e)
            continue
        fm *= e["value"] ** e["count"]
        fin_on.append(e)
    d = int(one * fm)
    flat_src = [e for e in flat_e if not e.get("when")] + fl_on
    steps = []
    if mult_e:
        steps.append({"k": "mult", "src": _fx_src("dmg_mult_add", mult_e), "from": Pp, "to": m1})
    if flat_src:
        steps.append({"k": "flat", "src": _fx_src("dmg_flat", flat_src, lambda e: e.get("value", 0) * (c["act"] if e.get("act_scaling") else 1) * e["count"]),
                      "from": m1, "to": m1 + flat})
    if one_raw < 0:
        steps.append({"k": "clamp", "src": {"kind": "floor"}, "from": one_raw, "to": 0})
    if fin_on:
        steps.append({"k": "final", "src": _fx_src("dmg_final_mult", fin_on, lambda e: e["value"] - 1), "from": one, "to": d})
    off = [{"type": "dmg_flat", "fid": e["fid"], "when": e.get("when")} for e in fl_off] + \
          [{"type": "dmg_final_mult", "fid": e["fid"], "when": {"condition": e.get("condition")}} for e in fin_off]
    return {"d": d, "steps": steps, "cond_off": off, "after_final": d}


def hits_chain(idx, c, excl=None):
    """타수: 기본 1 + hits_add(항상·조건·per) + 연속쌍."""
    n, steps, off = 1, [], []
    plain = [e for e in _ents(idx, "hits_add", excl) if _plain(e)]
    if plain:
        add = sum(int(e.get("value", 0)) * e["count"] for e in plain)
        steps.append({"src": _fx_src("hits_add", plain), "from": n, "to": n + add})
        n += add
    pairs_c = []
    for e in _ents(idx, "hits_add", excl):
        if _plain(e):
            continue
        if not c["when_ok"](e.get("when"), c["turn"], c["Pv"]):
            off.append({"type": "hits_add", "fid": e["fid"], "when": e.get("when")})
            continue
        per = e.get("per")
        if per == "items_held":
            add = int(c["inv0"] // e.get("divisor", 10)) * e["count"]
        elif per == "consecutive_pairs":
            pairs_c.append(e)
            continue
        else:
            add = int(e.get("value", 0)) * e["count"]
        if add:
            steps.append({"src": _fx_src("hits_add", [e]), "from": n, "to": n + add})
            n += add
    if pairs_c:
        add = c["pairs"] * sum(e["count"] for e in pairs_c)
        steps.append({"src": _fx_src("hits_add", pairs_c, lambda e: e["count"]), "from": n, "to": n + add, "per": "consecutive_pairs"})
        n += add
    return {"n": n, "steps": steps, "cond_off": off}


# ───────────── 내가 받은 피해 ─────────────
def taken_chain(idx, c, excl=None):
    """몬스터 한 번 타격이 나에게 주는 피해: 자릿수 상한 → 조준 → 방어 → 고정 감소 → 조건부 배율."""
    D = c["D"]
    caps = [int(e["value"]) for e in _ents(idx, "monster_dmg_digit_max", excl)]
    dm = c["digits_map"]
    eff = (lambda v: v) if not caps else (lambda v: dm(v, lambda d: min(d, min(caps))))
    steps, off = [], []
    per = eff(D)
    if per != D or caps:
        steps.append({"k": "digit_cap", "src": _fx_src("monster_dmg_digit_max", _ents(idx, "monster_dmg_digit_max", excl), lambda e: 0), "from": D, "to": per})
    if c.get("aim") is not None and c["amul"] > 1:
        if str(c["aim"]) in c["aim_s"]:
            new = int(per * c["amul"])
            steps.append({"k": "aim", "src": {"kind": "monster", "sim": "aimed_shot"}, "from": per, "to": new})
            per = new
    def_e = [e for e in _ents(idx, "def_cut_add", excl) if _plain(e)]
    cut = min(c["def_cap"], ssum(idx, "def_cut_add", excl))
    a = _trunc(per * (1 - cut))
    if def_e:
        steps.append({"k": "def", "src": _fx_src("def_cut_add", def_e), "from": per, "to": a})
    tf_e = [e for e in _ents(idx, "dmg_taken_flat", excl) if _plain(e)]
    tf = ssum(idx, "dmg_taken_flat", excl)
    raw = a + tf
    if tf_e:
        steps.append({"k": "flat", "src": _fx_src("dmg_taken_flat", tf_e), "from": a, "to": raw})
    v = max(0, raw)
    if raw < 0:
        steps.append({"k": "clamp", "src": {"kind": "floor"}, "from": raw, "to": 0})
    for e in _ents(idx, "dmg_taken_mult", excl):
        if e.get("condition") == "monster_dmg_ge_player_base" and not eff(D) >= c["P"]:
            off.append({"type": "dmg_taken_mult", "fid": e["fid"], "when": {"condition": e.get("condition")}})
            continue
        nv = int(v * e["value"] ** e["count"])
        steps.append({"k": "mult", "src": _fx_src("dmg_taken_mult", [e], lambda e: e["value"] - 1), "from": v, "to": nv})
        v = nv
    return {"per": v, "steps": steps, "cond_off": off, "eff_d": eff(D)}


def delay_frac(idx, excl=None):
    return min(1.0, ssum(idx, "dmg_taken_delay", excl))


# ───────────── 초과 피해 ─────────────
def split_over(over, pos, neg):
    """over 를 pos(양수 기여: [(키, 값)])의 비율로 나눈다(합 = over, 큰 나머지 순 보정). neg 는 초과를 줄인 것 [(키, 크기)] — 같은 비율 기준."""
    over = int(round(over))
    tot = sum(v for _, v in pos if v > 0)
    if over <= 0 or tot <= 0:
        return [], []
    raw = [(k, over * v / tot) for k, v in pos if v > 0]
    base = [(k, int(x)) for k, x in raw]
    rest = over - sum(n for _, n in base)
    order = sorted(range(len(raw)), key=lambda i: -(raw[i][1] - base[i][1]))
    base = [list(b) for b in base]
    for i in order[:rest]:
        base[i][1] += 1
    by = [{"src": k, "n": n} for k, n in base if n > 0]
    red = [{"src": k, "n": int(round(over * v / tot))} for k, v in neg if v > 0]
    return by, [r for r in red if r["n"] > 0]


def _src_key(src, fid=None):
    if src.get("kind") == "fx":
        return fid
    if src.get("kind") == "monster":
        return "mon:" + src.get("sim", "")
    return src.get("kind", "")


def _contrib_list(steps, base_key="base_roll", base_val=0):
    """단계 증감을 출처 키별 (양수 목록, 음수 목록) 으로. 환상 단계는 가중치로 환상별로 나눈다."""
    pos, neg = [(base_key, base_val)], []
    for s in steps:
        delta = s["to"] - s["from"]
        if not delta:
            continue
        src = s["src"]
        parts = []
        if src.get("kind") == "fx":
            ws = [f[2] for f in src["fids"]]
            tw = sum(ws) or len(ws)
            for f in src["fids"]:
                parts.append((f[0], delta * ((f[2] or 1) if sum(ws) else 1) / tw))
        else:
            parts.append((_src_key(src), delta))
        for k, v in parts:
            (pos if v > 0 else neg).append((k, abs(v)))
    return pos, neg


# ───────────── 조립 ─────────────
def _unclassified(total, parts):
    r = total - parts
    return [{"k": "unclassified", "amount": r}] if r else []


def build(ctx):
    """한 턴의 calc. ctx 는 fight_digits 가 모은 입력·결과 (아래 키 참고)."""
    idx = ctx["idx"]
    out = {"dealt": _dealt(ctx, idx), "taken": _taken(ctx, idx)}
    out["cond_off"] = out["dealt"].pop("_off") + out["taken"].pop("_off")
    out["sources"] = {"dealt": _sources(out["dealt"], idx), "taken": _sources(out["taken"], idx)}
    out["approx"] = bool(ctx.get("approx"))
    return _norm(out)


def _norm(o):
    """값이 정수인 실수(62.0)는 정수로 — JSON·화면에서 깔끔하게 (가중치 w 는 그대로 둔다)."""
    if isinstance(o, float):
        return int(o) if o.is_integer() else round(o, 6)
    if isinstance(o, dict):
        return {k: _norm(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_norm(v) for v in o]
    return o


def _dealt(c, idx):
    Pe = c.get("Pe", c["Pp"])      # 평가형 변환(천칭자리) 후의 값 — 배율 단계는 이 값에서 시작한다 (F22-A)
    cc = {"Pp": Pe, "act": c["act"], "turn": c["turn"], "Pv": c["Pv"], "d_eff": c["d_eff"], "when_ok": c["when_ok"]}
    hc = {"turn": c["turn"], "Pv": c["Pv"], "inv0": c["inv0"], "pairs": c["pairs"], "when_ok": c["when_ok"]}
    ch = dealt_chain(idx, cc)
    steps = []
    roll_t = [e for e in _ents(idx, "base_dmg_transform") if e.get("op") != "zero_else_mult"]
    eval_t = [e for e in _ents(idx, "base_dmg_transform") if e.get("op") == "zero_else_mult"]
    if c["P0"] != c["Pv"]:
        steps.append({"k": "transform", "src": _fx_src("base_dmg_transform", roll_t, lambda e: 0), "from": c["P0"], "to": c["Pv"]})
    if c["Pp"] != c["Pv"]:
        steps.append({"k": "move", "src": {"kind": "move", "n": c["used"], "items": c["n_items"]}, "from": c["Pv"], "to": c["Pp"]})
    if eval_t and Pe != c["Pp"]:
        steps.append({"k": "eval", "src": _fx_src("base_dmg_transform", eval_t[:1], lambda e: 0), "from": c["Pp"], "to": Pe})
    steps += ch["steps"]
    if c["d1"] != ch["d"] or c["rules"]:
        steps.append({"k": "rule", "src": {"kind": "monster", "sim": "+".join(c["rules"]) or "rule"}, "from": ch["d"], "to": c["d1"]})
    hh = hits_chain(idx, hc)
    n_nom = c["hits"]
    out = {"base": c["P0"], "roll": {"digits": c["dP"], "player_strength": c["pstr"]}, "steps": steps, "per_hit": c["d1"],
           "hits": {"base": 1, "steps": hh["steps"], "n": n_nom}, "_off": [dict(o, side="dealt") for o in ch["cond_off"] + hh["cond_off"]]}
    if hh["n"] != n_nom:
        out["hits"]["steps"].append({"src": {"kind": "unknown"}, "from": hh["n"], "to": n_nom})
    # 합계: 적용 순서 타격 → 한도·방어막 → 턴 끝 피해·반사·회복
    ex = []
    applied = c["hit_log"]
    nominal = c["d1"] * n_nom
    unapplied = (n_nom - len(applied)) * c["d1"]
    if unapplied:
        ex.append({"k": "unapplied", "amount": -unapplied, "why": c["dealt_stop"]})
    combo = sum(h["d"] - c["d1"] for h in applied)
    if combo:
        ex.append({"k": "combo", "amount": combo, "src": _fx_src("combo_same_dmg_stack", _ents(idx, "combo_same_dmg_stack"), lambda e: 0)})
    cap = sum(h["cap"] for h in applied)
    shield = sum(h["shield"] for h in applied)
    if cap:
        ex.append({"k": "cap", "amount": -cap, "src": {"kind": "monster", "sim": "cap_per_hit"}})
    if shield:
        ex.append({"k": "shield", "amount": -shield, "src": {"kind": "monster", "sim": "shield"}})
    for i, amt in c["etd_parts"]:
        ex.append({"k": "etd", "amount": amt, "src": {"kind": "fx", "type": "end_turn_dmg", "fids": [[c["etd_fids"][i], 1, amt]]}})
    for fid, amt in c["refl"].items():
        ex.append({"k": "reflect", "amount": amt, "src": {"kind": "fx", "type": "reflect_on_hit", "fids": [[fid, 1, amt]]}})
    for h in c["m_heals"]:
        ex.append({"k": "heal", "amount": -h["amount"], "src": {"kind": "monster", "sim": h["why"]}})
    known = nominal + sum(e["amount"] for e in ex)
    ex += _unclassified(c["dealt"], known)
    out["extra"] = ex
    out["total"] = c["dealt"]
    out["raw"] = c["dealt"]
    # 초과
    over = int(round(max(0, c["dealt"] - c["mhp_before"]))) if c["m_dead"] else 0
    pos, neg = _contrib_list(steps, "base_roll", c["P0"])
    for e in ex:
        if e["k"] in ("combo", "etd", "reflect") and e["amount"] > 0:
            src = e["src"]
            pos.append((src["fids"][0][0] if src.get("kind") == "fx" and src["fids"] else e["k"], e["amount"]))
    by, red = split_over(over, pos, neg)
    out["over"] = {"n": over, "by": by, "reduced": red, "ablate": []}
    # 제거 시 차이: 그 출처만 뺀 같은 계산의 (한 번 타격 × 타수)
    abl, oab = [], []
    nom = c["d1"] * n_nom
    for fid in _all_fids(steps, hh["steps"]):
        c2 = dealt_chain(idx, cc, fid)
        h2 = hits_chain(idx, hc, fid)
        d2 = c2["d"] if not (c["d1"] != ch["d"] or c["rules"]) else _rules_scale(c, ch["d"], c2["d"])
        nom2 = d2 * (h2["n"] + (n_nom - hh["n"]))
        delta = nom - nom2
        abl.append({"src": fid, "without": c["dealt"] - delta, "delta": delta})
        if over or c["dealt"] > c["mhp_before"] - 1:
            oab.append({"src": fid, "without_over": max(0, c["dealt"] - delta - c["mhp_before"]) if c["m_dead"] else 0,
                        "delta": over - (max(0, c["dealt"] - delta - c["mhp_before"]) if c["m_dead"] else 0)})
    out["ablate"] = abl
    out["over"]["ablate"] = [o for o in oab if o["delta"]]
    return out


def _rules_scale(c, d_pre, d2_pre):
    """기믹 규칙(0 처리·디버프 등)이 걸린 턴: 규칙 이후 값 d1 을 규칙 이전 값 비율로 환산 (근사). 규칙이 0 으로 만들면 0 그대로."""
    if not d_pre:
        return c["d1"]
    return int(c["d1"] * d2_pre / d_pre) if c["d1"] else 0


def _all_fids(*step_lists):
    seen, out = set(), []
    for steps in step_lists:
        for s in steps:
            for f in s["src"].get("fids", ()):
                if f[0] not in seen:
                    seen.add(f[0])
                    out.append(f[0])
    return out


def _taken(c, idx):
    if not c["attack"]:
        total = c["taken"]
        ex = [{"k": "status", "amount": c["tk"]["status"]}] if c["tk"]["status"] else []
        for lab, r in c["tk"]["direct"]:
            ex.append({"k": "direct", "amount": r, "label": lab})
        if c["tk"]["delayed_paid"]:
            ex.append({"k": "delayed_paid", "amount": c["tk"]["delayed_paid"]})
        ex += _unclassified(total, sum(e["amount"] for e in ex))
        over = max(0, total - c["hp_before"]) if c["res"] == "death" else 0
        by = [{"src": ex[0]["k"] if ex else "unknown", "n": over}] if over else []
        return {"base": 0, "steps": [], "per_hit": 0, "hits": {"base": 0, "n": 0}, "extra": ex, "total": total, "raw": total,
                "over": {"n": over, "by": by, "reduced": [], "ablate": []}, "ablate": [], "roll": c["roll"], "_off": []}
    tc = {"D": c["Dfin"], "P": c.get("Pe", c["Pp"]), "digits_map": c["digits_map"], "aim": c["aim"], "amul": c["amul"], "aim_s": c["aim_s"], "def_cap": c["def_cap"]}
    ch = taken_chain(idx, tc)
    steps = []
    if c["Dp0"] != c["D"]:
        steps.append({"k": "move", "src": {"kind": "move", "n": c["used"], "items": c["n_items"]}, "from": c["D"], "to": c["Dp0"]})
    if c["reroll"] is not None and c["reroll"] != c["Dp0"]:
        steps.append({"k": "reroll", "src": {"kind": "monster", "sim": "strength_reset"}, "from": c["Dp0"], "to": c["reroll"]})
    steps += ch["steps"]
    if ch["per"] != c["per_in"]:
        steps.append({"k": "rule", "src": {"kind": "unknown"}, "from": ch["per"], "to": c["per_in"]})
    df = delay_frac(idx)
    tk = c["tk"]
    n_nom, n_app = c["Hp"], tk["n"]
    nominal = c["per_in"] * n_nom
    ex = []
    unapplied = c["per_in"] * (n_nom - n_app)
    if unapplied:
        ex.append({"k": "unapplied", "amount": -unapplied, "why": tk["why"]})
    if tk["deferred"]:
        ex.append({"k": "delay", "amount": -tk["deferred"], "src": _fx_src("dmg_taken_delay", _ents(idx, "dmg_taken_delay"))})
    if tk["delayed_paid"]:
        ex.append({"k": "delayed_paid", "amount": tk["delayed_paid"]})
    if tk["status"]:
        ex.append({"k": "status", "amount": tk["status"]})
    for lab, r in tk["direct"]:
        ex.append({"k": "direct", "amount": r, "label": lab})
    known = nominal + sum(e["amount"] for e in ex)
    ex += _unclassified(c["taken"], known)
    out = {"base": c["D"], "roll": c["roll"], "steps": steps, "per_hit": c["per_in"],
           "hits": {"base": c["H"], "steps": ([{"src": {"kind": "move", "n": c["used"]}, "from": c["H"], "to": c["Hp"]}] if c["Hp"] != c["H"] else []), "n": n_nom, "applied": n_app},
           "extra": ex, "total": c["taken"], "raw": c["taken"], "_off": [dict(o, side="taken") for o in ch["cond_off"]]}
    over = int(round(max(0, c["taken"] - c["hp_before"]))) if c["res"] == "death" else 0
    if over and tk["death_in"] == "hit":
        pos, neg = _contrib_list(steps, "base_roll", c["D"])
        pos = [(k, v) for k, v in pos]
        by, red = split_over(over, pos, neg)
    elif over:
        by, red = [{"src": tk["death_in"], "n": over}], []
    else:
        by, red = [], []
    out["over"] = {"n": over, "by": by, "reduced": red, "ablate": []}
    abl, oab = [], []
    now = c["per_in"] - int(c["per_in"] * df)
    for fid in _all_fids(steps, [{"src": {"fids": [[f] for f in _delay_fids(idx)]}}]):
        c2 = taken_chain(idx, tc, fid)
        df2 = delay_frac(idx, fid)
        now2 = c2["per"] - int(c2["per"] * df2)
        delta = (now - now2) * n_app          # 그 출처가 있어서 더/덜 받은 양 (음수 = 덜 받음)
        abl.append({"src": fid, "without": c["taken"] - delta, "delta": delta})
        if over:
            o2 = max(0, c["taken"] - delta - c["hp_before"])
            oab.append({"src": fid, "without_over": o2, "delta": over - o2})
    out["ablate"] = abl
    out["over"]["ablate"] = [o for o in oab if o["delta"]]
    return out


def _delay_fids(idx):
    return list(dict.fromkeys(e["fid"] for e in idx.get("dmg_taken_delay", ())))


def _sources(side, idx):
    """출처 요약 — 값이 0 이 아닌 모든 출처를 하나도 빼지 않고 (순차 증감, 제거 시 차이, 초과 기여)."""
    S = {}

    def get(key, kind, fid=None, label=None):
        return S.setdefault(key, {"key": key, "kind": kind, "fid": fid, "label": label, "seq": 0, "ablate": None, "over": 0, "over_reduced": 0, "count": 0, "types": []})
    for s in side.get("steps", ()):
        src, delta = s["src"], s["to"] - s["from"]
        if src.get("kind") == "fx":
            ws = [f[2] for f in src["fids"]]
            tw = sum(ws)
            for f in src["fids"]:
                o = get(f[0], "fx", f[0])
                o["count"] = max(o["count"], f[1])
                if src["type"] not in o["types"]:
                    o["types"].append(src["type"])
                o["seq"] += delta * (f[2] / tw) if tw else delta / len(src["fids"])
        else:
            key = _src_key(src)
            o = get(key, src.get("kind"), None, src.get("sim"))
            o["seq"] += delta
    for e in side.get("extra", ()):
        src = e.get("src")
        if src and src.get("kind") == "fx":
            for f in src["fids"]:
                o = get(f[0], "fx", f[0])
                if src["type"] not in o["types"]:
                    o["types"].append(src["type"])
                o["seq"] += e["amount"] / len(src["fids"])
        else:
            o = get("x:" + e["k"], "extra", None, e["k"])
            o["seq"] += e["amount"]
    for hs in side.get("hits", {}).get("steps", ()):
        src = hs["src"]
        if src.get("kind") == "fx":
            for f in src["fids"]:
                o = get(f[0], "fx", f[0])
                if src["type"] not in o["types"]:
                    o["types"].append(src["type"])
    for a in side.get("ablate", ()):
        get(a["src"], "fx", a["src"])["ablate"] = a["delta"]
    ov = side.get("over", {})
    for b in ov.get("by", ()):
        k = b["src"]
        get(k, "fx" if k in S and S[k]["kind"] == "fx" else ("base" if k == "base_roll" else "extra"), k if k in S else None, k)["over"] += b["n"]
    for r in ov.get("reduced", ()):
        get(r["src"], "fx", r["src"])["over_reduced"] += r["n"]
    for a in ov.get("ablate", ()):
        get(a["src"], "fx", a["src"])["over_ablate"] = a["delta"]
    rows = [v for v in S.values() if v["seq"] or v["ablate"] or v["over"] or v["over_reduced"] or v["kind"] == "fx"]
    rows.sort(key=lambda r: -abs(r["ablate"] if r["ablate"] is not None else r["seq"]))
    return rows


def round_parts(parts, total):
    """실수 목록 parts 를 합이 정수 total 이 되게 정수로 (내림 + 큰 나머지 순 보정)."""
    base = [int(x) for x in parts]
    rest = int(total) - sum(base)
    order = sorted(range(len(parts)), key=lambda i: -(parts[i] - base[i]))
    for i in order[:max(0, rest)]:
        base[i] += 1
    return base
