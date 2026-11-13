# -*- coding: utf-8 -*-
"""한계효과 미리보기 학습 작업 (v4.1 F10.4, F10.10).

- 학습 격자의 각 θ 는 편집 오버레이로 만든 **일반 시뮬레이션 점**이다 → 점 캐시(data_hash 키)에 정상 저장되고,
  나중에 같은 값을 입력하면 실제 재계산이 캐시 적중으로 끝난다(AC-Y6). 근사값 자체는 캐시에 넣지 않는다.
- 최하위 우선순위: 인터랙티브 작업이 실행 대기(pending)하면 조각 단위로 멈추고(Cancelled), 끝난 뒤 이어서 한다.
  이미 계산한 접두는 캐시에 저장되므로 재개한 결과는 중단 없이 돌린 것과 같다(AC-Y9).
- 저장: <results>/surrogate/<환상ID>.<효과>.<키>.json, monster.<몬스터ID>.<필드>.json, monster.<ID>.<필드>.probe.json
- 무효화: strong_hash(몬스터·패턴·설정·보상 구조·피해 모델·기믹 + 몬스터 대상이면 같은 몬스터의 다른 필드),
  weak_hash(대상 필드를 가린 나머지 데이터). 대상 필드 자신의 값 변경은 무효화가 아니다.
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
import queue
import threading
import time

import matchup_sim as ms

from . import compute as cp
from . import edits as ed
from . import stats as S
from . import store as st
from . import surrogate as sg

BG_CHUNK = 50          # 학습은 작은 조각으로 돌려 1초 안에 양보한다


def _sha(obj):
    return hashlib.sha1(json.dumps(obj, sort_keys=True, ensure_ascii=False, default=str).encode("utf-8")).hexdigest()[:16]


def safe_name(s):
    return "".join(c if c.isalnum() or c in "._-" else "_" for c in str(s))


def model_path(app, kind, tid, field, probe=False):
    d = os.path.join(app.results, "surrogate")
    name = (f"monster.{tid}.{field}" if kind == "monster" else f"{tid}.{field}") + (".probe" if probe else "")
    return os.path.join(d, safe_name(name) + ".json")


# ---------------------------------------------------------------------------
# 상태 해시 (무효화)
# ---------------------------------------------------------------------------
def _cfg_digest(cfg):
    c = copy.deepcopy(cfg)
    c["fantasy"]["effects_file"] = ""
    c["fantasy"]["forced"] = {"ids": [], "at": "start"}
    if c["monsters"].get("table_file"):
        c["monsters"]["table_file"] = ""
    st.strip_v4_defaults(c)
    return _sha(c)


def _masked_table(table_data, kind, tid, field):
    t = copy.deepcopy(table_data)
    if kind == "fantasy":
        eff, key = field.split(".", 1)
        for e in t["fantasies"]:
            if e["id"] == tid and int(eff) < len(e.get("effects", [])):
                e["effects"][int(eff)][key] = None
    return st.table_hash(t)


def _masked_monsters(mdata, kind, tid, field):
    if mdata is None:
        return ""
    m = copy.deepcopy(mdata)
    if kind == "monster":
        for x in m["monsters"]:
            if x["id"] == tid:
                x[field] = None
    return st.monster_hash_of(m)


def state_hashes(app, kind, tid, field, edits=(), cfg_edits=(), cfg_set=None):
    """현재 상태(작업 사본 + 클라이언트 편집)의 strong/weak 해시. 대상 필드 편집은 제외한다."""
    own = [e for e in edits if not _is_target_edit(e, kind, tid, field)]
    f_edits = [e for e in own if e.get("target", "fantasy") == "fantasy"]
    m_edits = [e for e in own if e.get("target") in ("monster", "pattern", "gimmick")]
    table, c1, e1 = ed.apply_edits(app.table_data, f_edits)
    mdata = app.monster_data
    if m_edits and mdata is not None:
        mdata = ed.apply_monster_edits(mdata, m_edits)[0]
    cfg, _, _ = ed.apply_cfg_edits(ed.apply_cfg_set(app.base_cfg, cfg_set), list(cfg_edits or []))
    if kind == "fantasy":
        strong = _sha([_cfg_digest(cfg), _masked_monsters(mdata, kind, tid, field), app.x_key, app.seed])
        weak = _masked_table(table, kind, tid, field)
    else:
        # 몬스터 대상: 같은 몬스터의 다른 필드·패턴·설정 = 강한 무효, 다른 몬스터·환상 = 약한 경고
        mine = next((x for x in (mdata or {}).get("monsters", []) if x["id"] == tid), {})
        mine = {k: v for k, v in mine.items() if k not in (field, "src", "notes", "name", "warnings")}
        strong = _sha([_cfg_digest(cfg), mine, app.x_key, app.seed])
        weak = _sha([st.table_hash(table), _masked_monsters(mdata, kind, tid, field)])
    return strong, weak


def _is_target_edit(e, kind, tid, field):
    if kind == "fantasy":
        return e.get("target", "fantasy") == "fantasy" and e.get("fid") == tid and f"{e.get('effect')}.{e.get('key')}" == field
    return e.get("target") == "monster" and e.get("mid") == tid and e.get("key") == field


def status_for(app, model, edits=(), cfg_edits=(), cfg_set=None):
    """저장된 모델의 유효성: ok / weak(약한 경고) / invalid(강한 무효 → 근사 끔)."""
    strong, weak = state_hashes(app, model["kind"], model["id"], model["field"], edits, cfg_edits, cfg_set)
    if strong != model["strong_hash"]:
        return "invalid", "몬스터·패턴·설정·보상 구조(또는 같은 몬스터의 다른 필드)가 바뀜 — 다시 학습 필요"
    if weak != model["weak_hash"]:
        return "weak", "다른 환상·몬스터가 바뀌어 기준선이 달라졌을 수 있음 (앵커가 흡수)"
    return "ok", ""


# ---------------------------------------------------------------------------
# 후보
# ---------------------------------------------------------------------------
def fantasy_targets(app):
    out = []
    for e in app.table_data["fantasies"]:
        for i, ef in enumerate(e.get("effects", [])):
            if not ef.get("surrogate_candidate"):
                continue
            for k in ed.EFFECT_SCHEMA.get(ef["type"], {}):
                if k in ef and isinstance(ef[k], (int, float)) and not isinstance(ef[k], bool):
                    out.append({"kind": "fantasy", "id": e["id"], "field": f"{i}.{k}"})
    return out


def _fantasy_field(app, fid, field):
    e = next((x for x in app.table_data["fantasies"] if x["id"] == fid), None)
    if e is None:
        raise ValueError(f"환상 없음: {fid}")
    i, key = field.split(".", 1)
    ef = e["effects"][int(i)]
    if key not in ef:
        raise ValueError(f"효과 키 없음: {fid} {field}")
    return ef, int(i), key


def grid_for(app, t, k=6):
    if t["kind"] == "fantasy":
        ef, i, key = _fantasy_field(app, t["id"], t["field"])
        sch = ed.key_schema(ef, key) or {"min": -1e9, "max": 1e9}
        orig = ef[key]
        return orig, sg.theta_grid(orig, sch.get("min", -1e9), sch.get("max", 1e9), k, bool(sch.get("int")))
    m = next((x for x in (app.monster_data or {}).get("monsters", []) if x["id"] == t["id"]), None)
    if m is None:
        raise ValueError(f"몬스터 없음: {t['id']}")
    orig = int(m.get(t["field"]) or 0)
    if t["field"] == "hp":
        return orig, sg.theta_grid(orig, 1, 1000000, k, True, mode="monster_hp")
    smax = max(orig, 2)
    return orig, list(range(0, smax + 1))


def x_points(app, mode, x_sel=None):
    xs = list(app.x_values)
    if mode == "selected3" and xs:
        x0 = x_sel if x_sel in xs else xs[len(xs) // 2]
        i = xs.index(x0)
        return xs[max(0, i - 1): i + 2]
    return xs


def estimate(app, targets, k=6, n=None, xmode=None, x_sel=None):
    """예상 판 수와 시간(현재 처리율 기준)."""
    runs = 0
    for t in targets:
        _, grid = grid_for(app, t, k)
        if t["kind"] == "fantasy":
            runs += len(grid) * len(x_points(app, xmode or "all", x_sel)) * 2 * (n or 1000)
        else:
            runs += len(grid) * len(x_points(app, xmode or "selected3", x_sel)) * (n or 3000)
    rate = app.engine.rate or 400.0
    return {"runs": runs, "seconds": round(runs / rate, 1), "targets": len(targets), "note": "캐시 적중분은 더 빠름"}


# ---------------------------------------------------------------------------
# 학습 실행
# ---------------------------------------------------------------------------
class Trainer:
    """백그라운드 학습 스레드 (FIFO). 인터랙티브 작업이 대기 중이면 양보한다."""

    def __init__(self, app):
        self.app = app
        self.q = queue.Queue()
        self.current = None
        self.yields = 0
        self.thread = threading.Thread(target=self._loop, daemon=True)
        self.thread.start()

    def submit(self, kind, params):
        from .jobs import Job
        job = Job(kind, params)
        jm = self.app.jobs
        with jm.lock:
            jm.jobs[job.id] = job
        self.q.put(job)
        return job

    def _loop(self):
        while True:
            job = self.q.get()
            self.current = job
            if job.cancelled:
                job.finish("cancelled")
                continue
            job.emit("started", kind=job.kind, background=True)
            try:
                fn = TRAIN_KINDS[job.kind]
                res = fn(self.app, job, self)
                job.finish("cancelled" if job.cancelled else "done", result=res)
            except cp.Cancelled:
                job.finish("cancelled")
            except Exception as e:  # noqa: BLE001
                import traceback
                job.finish("error", message=str(e), trace=traceback.format_exc()[-2000:])
            finally:
                self.current = None

    def ensure(self, job, reqs, n):
        """engine.ensure 를 최하위 우선순위로: 인터랙티브 작업이 기다리면 멈추고 끝난 뒤 이어서."""
        jm = self.app.jobs
        while True:
            if job.cancelled:
                raise cp.Cancelled()
            while jm.pending > 0 or (jm.current is not None and not jm.current.done):
                time.sleep(0.05)
                if job.cancelled:
                    raise cp.Cancelled()
            if not jm.run_lock.acquire(timeout=0.2):
                continue
            try:
                if jm.pending > 0:
                    continue
                return self.app.engine.ensure(reqs, n, cancel=lambda: jm.pending > 0 or job.cancelled, chunk=BG_CHUNK)
            except cp.Cancelled:
                if job.cancelled:
                    raise
                self.yields += 1
                job.emit("yield", n_yields=self.yields)
            finally:
                jm.run_lock.release()


def _base_state(app, p):
    return list(p.get("edits") or []), list(p.get("cfg_edits") or []), p.get("cfg_set") or {}


def fit_target(app, job, tr, t, k=6, n=None, xmode=None, x_sel=None, base=((), (), None)):
    from .jobs import prepare
    edits0, cfg_edits, cfg_set = base
    edits0 = [e for e in edits0 if not _is_target_edit(e, t["kind"], t["id"], t["field"])]
    orig, grid = grid_for(app, t, k)
    xs = x_points(app, xmode or ("all" if t["kind"] == "fantasy" else "selected3"), x_sel)
    n = int(n or (1000 if t["kind"] == "fantasy" else 3000))
    discrete = t["kind"] == "monster" and t["field"] == "strength"
    reqs, plan = [], []
    for th in grid:
        if t["kind"] == "fantasy":
            ef, i, key = _fantasy_field(app, t["id"], t["field"])
            e = {"fid": t["id"], "effect": i, "key": key, "old": ef[key], "new": ed.like_type(ef[key], th)}
        else:
            if app.base_cfg["monsters"].get("model") != "table" and (cfg_set or {}).get("monsters.model") != "table":
                raise ValueError("몬스터 근사는 monsters.model = table 에서만 (tier_avg 는 몬스터 편집이 곡선에 반영되지 않음)")
            m = next(x for x in app.monster_data["monsters"] if x["id"] == t["id"])
            e = {"target": "monster", "mid": t["id"], "key": t["field"], "old": m[t["field"]], "new": int(th)}
        edits = edits0 + ([] if th == orig else [e])
        cfg, h = prepare(app, edits, cfg_edits, cfg_set)
        for x in xs:
            c = copy.deepcopy(cfg)
            ms.set_path(c, app.x_key, x)
            rb = cp.make_req(c, [], app.seed, h, tag=(th, x, "base"))
            reqs.append(rb)
            ra = cp.make_req(c, [t["id"]], app.seed, h, tag=(th, x, "arm")) if t["kind"] == "fantasy" else None
            if ra:
                reqs.append(ra)
            plan.append((th, x, rb, ra))
    job.emit("plan", target=t, grid=grid, x=xs, n=n, points=len(reqs))
    recs = tr.ensure(job, reqs, n)
    data = {}
    base0 = {x: recs[rb["key"]] for th, x, rb, ra in plan if th == orig}
    for th, x, rb, ra in plan:
        b = recs[rb["key"]]
        if t["kind"] == "fantasy":
            d = S.paired_delta(recs[ra["key"]], b, n)
            w = b["wins"][:n].count("1") / n
        else:
            d = S.paired_delta(b, base0[x], n) if x in base0 else {"delta": 0.0, "delta_se": 0.0}
            w = base0[x]["wins"][:n].count("1") / n if x in base0 else b["wins"][:n].count("1") / n
        data.setdefault(x, []).append((th, d["delta"], d["delta_se"], w))
    model = sg.fit(data, n, orig, discrete=discrete)
    strong, weak = state_hashes(app, t["kind"], t["id"], t["field"], edits0, cfg_edits, cfg_set)
    model.update({"kind": t["kind"], "id": t["id"], "field": t["field"], "strong_hash": strong, "weak_hash": weak,
                  "fit_base_hash": _sha([strong, weak]), "seed": app.seed, "seeds": [0, n - 1], "x_key": app.x_key,
                  "cfg_set": cfg_set, "cfg_edits": cfg_edits, "base_edits": edits0,
                  "baseline": {str(x): base0[x]["wins"][:n].count("1") / n for x in base0},
                  "fitted_at": time.strftime("%Y-%m-%dT%H:%M:%S")})
    if t["kind"] == "monster":
        model["encounter"] = encounter_rates(app, t["id"], xs, cfg_edits, cfg_set, edits0, n_runs=min(n, 400))
        for x, r in model["encounter"].items():
            if r == 0 and x in model["x"]:
                model["x"][x]["status"] = "영향 없음"
                model["x"][x]["reason"] = "이 몬스터를 만나지 않음 (접촉률 0)"
        if all(r == 0 for r in model["encounter"].values()):
            model["status"], model["ok"] = "영향 없음", False
    path = model_path(app, t["kind"], t["id"], t["field"])
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path + ".tmp", "w", encoding="utf-8") as fp:
        json.dump(model, fp, ensure_ascii=False)
    os.replace(path + ".tmp", path)
    job.emit("model", target=t, status=model["status"])
    return {"target": t, "status": model["status"], "path": os.path.basename(path)}


def encounter_rates(app, mid, xs, cfg_edits, cfg_set, edits0, n_runs=400):
    """접촉률: 전투 시작 기록(battle_log)으로 그 몬스터를 만난 판의 비율 (점 캐시 레코드는 바꾸지 않음)."""
    from .jobs import prepare
    cfg, _ = prepare(app, edits0, cfg_edits, cfg_set)
    out = {}
    for x in xs:
        c = copy.deepcopy(cfg)
        ms.set_path(c, app.x_key, x)
        ctx = ms.SimContext(c)
        met = 0
        for i in range(n_runs):
            log = []
            ms.simulate_run(c, f"{app.seed}-{i}", ctx=ctx, battle_log=log)
            met += any(b["monster"] == mid for b in log)
        out[str(x)] = met / n_runs
    return out


def job_fit(app, job, tr):
    p = job.params
    base = _base_state(app, p)
    targets = p.get("targets") or fantasy_targets(app)
    out = []
    for t in targets:
        if job.cancelled:
            raise cp.Cancelled()
        out.append(fit_target(app, job, tr, t, int(p.get("k", 6)), p.get("n"), p.get("x_points"), p.get("x_sel"), base))
    return {"fitted": out}


def job_probe_fit(app, job, tr):
    """몬스터 단독 지표 모델 (F10.10-2): 체력 격자 8점 구간 선형 / 기본 힘 정수 표. n = 2000."""
    from . import monsters as mo
    from .jobs import prepare
    p = job.params
    mid, field = p["mid"], p.get("field", "hp")
    edits0, cfg_edits, cfg_set = _base_state(app, p)
    cfg, _ = prepare(app, [e for e in edits0 if e.get("target", "fantasy") == "fantasy"], cfg_edits, cfg_set)
    mdata = app.monster_data
    m = next(x for x in mdata["monsters"] if x["id"] == mid)
    orig = int(m.get(field) or 0)
    grid = sg.theta_grid(orig, 1, 1000000, 8, True, mode="monster_hp") if field == "hp" else list(range(0, max(orig, 2) + 1))
    n = int(p.get("n", 2000))
    rows = []
    for th in grid:
        if job.cancelled:
            raise cp.Cancelled()
        while app.jobs.pending > 0 or (app.jobs.current is not None and not app.jobs.current.done):
            time.sleep(0.05)
        mm = dict(m, **{field: int(th)})
        r = mo.probe(cfg, mm, n, "probe", [])
        rows.append([th, r["avg_turns"], r["avg_taken"], r["death_rate"], r["kill_rate"]])
    model = {"kind": "monster_probe", "id": mid, "field": field, "grid": grid, "rows": rows, "n": n, "theta0": orig,
             "discrete": field == "strength", "fitted_at": time.strftime("%Y-%m-%dT%H:%M:%S")}
    strong, weak = state_hashes(app, "monster", mid, field, edits0, cfg_edits, cfg_set)
    model.update({"strong_hash": strong, "weak_hash": weak})
    path = model_path(app, "monster", mid, field, probe=True)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fp:
        json.dump(model, fp, ensure_ascii=False)
    return {"path": os.path.basename(path), "rows": len(rows)}


TRAIN_KINDS = {"surrogate_fit": job_fit, "surrogate_probe": job_probe_fit}


# ---------------------------------------------------------------------------
# 읽기 / 기록
# ---------------------------------------------------------------------------
def load_model(app, kind, tid, field, probe=False):
    path = model_path(app, kind, tid, field, probe)
    try:
        with open(path, encoding="utf-8") as fp:
            return json.load(fp)
    except (OSError, ValueError):
        return None


def list_models(app):
    d = os.path.join(app.results, "surrogate")
    out = []
    if os.path.isdir(d):
        for fn in sorted(os.listdir(d)):
            if fn.endswith(".json"):
                try:
                    with open(os.path.join(d, fn), encoding="utf-8") as fp:
                        out.append(json.load(fp))
                except (OSError, ValueError):
                    pass
    return out


def audit_path(app):
    return os.path.join(app.results, "surrogate_audit.jsonl")


def append_audit(app, rec):
    keep = ("kind", "id", "field", "theta", "theta_anchor", "x", "pred", "actual", "status", "model_fitted_at")
    row = {k: rec.get(k) for k in keep}
    row["at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    os.makedirs(app.results, exist_ok=True)
    with open(audit_path(app), "a", encoding="utf-8") as fp:
        fp.write(json.dumps(row, ensure_ascii=False) + "\n")
    return row


def read_audit(app, limit=500):
    try:
        with open(audit_path(app), encoding="utf-8") as fp:
            lines = fp.readlines()[-limit:]
    except OSError:
        return []
    out = []
    for ln in lines:
        try:
            out.append(json.loads(ln))
        except ValueError:
            pass
    return out
