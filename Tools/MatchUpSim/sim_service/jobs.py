# -*- coding: utf-8 -*-
"""작업 큐 (명세 v2 §4.1, §6.3): 한 번에 작업 하나. 새 작업이 오면 진행 중인 작업을 취소한다.
작업은 이벤트 목록을 쌓고, 서버는 그것을 SSE 로 흘려보낸다 (재접속하면 처음부터 다시 받음)."""
from __future__ import annotations

import copy
import itertools
import threading
import time
import traceback

import matchup_sim as ms

from . import compute as cp
from . import edits as ed
from . import stats as S
from . import store as st

BASE = "__baseline__"
PROGRESS_LOG = True      # 서버 콘솔에 진행 상황을 ~10초마다 한 줄 찍는다 (테스트에서는 끈다)


class Job:
    _ids = itertools.count(1)

    def __init__(self, kind, params):
        self.id = f"j{next(self._ids)}"
        self.kind = kind
        self.params = params
        self.events = []
        self.cond = threading.Condition()
        self.cancelled = False
        self.done = False
        self.t0 = time.perf_counter()
        self.t_cancel = None
        # 진행 집계 (v4.3 F12): 계산 호출부가 progress=job.progress 로 넘기면 `progress` 이벤트가 흘러나간다.
        self.progress = cp.Progress(
            emit=lambda snap: self.emit("progress", **snap),
            log=(lambda line: print(line, flush=True)) if PROGRESS_LOG else None,
            label=f"{kind} {self.id}")

    def emit(self, type_, **data):
        with self.cond:
            self.events.append({"type": type_, "t": round(time.perf_counter() - self.t0, 3), **data})
            self.cond.notify_all()

    def finish(self, type_="done", **data):
        self.emit(type_, **data)
        with self.cond:
            self.done = True
            self.cond.notify_all()

    def cancel(self):
        if not self.done and not self.cancelled:
            self.cancelled = True
            self.t_cancel = time.perf_counter()

    def wait_events(self, start, timeout=10.0):
        with self.cond:
            if len(self.events) <= start and not self.done:
                self.cond.wait(timeout)
            return self.events[start:], self.done


class JobManager:
    def __init__(self, app):
        self.app = app
        self.jobs = {}
        self.current = None
        self.by_client = {}
        self.lock = threading.Lock()
        self.run_lock = threading.Lock()
        self.pending = 0          # 실행 대기 중인 인터랙티브 작업 수 (학습 작업이 보고 양보한다, v4.1 F10.4)

    def submit(self, kind, params):
        fn = JOB_KINDS.get(kind)
        if fn is None:
            raise ValueError(f"알 수 없는 작업 종류: {kind}")
        job = Job(kind, params)
        client = params.get("client") if isinstance(params, dict) else None
        with self.lock:
            # 기기(브라우저 탭)마다 자기 이전 작업만 취소한다 — 여러 기기가 한 서버를 같이 쓸 때 서로 끊지 않게.
            # client 가 없으면(구버전 뷰어·CLI) 예전처럼 진행 중인 작업을 취소한다. 실행은 run_lock 으로 차례대로.
            prev = self.by_client.get(client) if client else self.current
            if prev is not None:
                prev.cancel()
            if client:
                self.by_client[client] = job
                if len(self.by_client) > 200:
                    for k in list(self.by_client)[:-200]:
                        del self.by_client[k]
            self.current = job
            self.jobs[job.id] = job
            self.pending += 1
            # 오래된 작업 정리
            if len(self.jobs) > 50:
                for k in list(self.jobs)[:-50]:
                    del self.jobs[k]
        threading.Thread(target=self._run, args=(job, fn), daemon=True).start()
        return job

    def _run(self, job, fn):
        with self.run_lock:  # 이전 작업이 조각을 마치고 빠질 때까지 대기 (조각 ≤250판 → 1초 이내)
            with self.lock:
                self.pending -= 1
            if job.cancelled:
                job.finish("cancelled")
                return
            job.emit("started", kind=job.kind)
            try:
                result = fn(self.app, job)
                if job.cancelled:
                    job.finish("cancelled")
                else:
                    job.finish("done", result=result)
            except cp.Cancelled:
                job.finish("cancelled", after_s=round(time.perf_counter() - (job.t_cancel or job.t0), 3))
            except Exception as e:  # noqa: BLE001
                job.finish("error", message=str(e), trace=traceback.format_exc()[-2000:])

    def cancel(self, job_id):
        job = self.jobs.get(job_id)
        if job:
            job.cancel()
        return job


# ---------------------------------------------------------------------------
# 공통: 편집된 테이블·설정 준비
# ---------------------------------------------------------------------------
def prepare(app, edits, cfg_edits, cfg_set=None):
    edits = edits or []
    data, c1, e1 = ed.apply_edits(app.table_data, edits)
    cfg, c2, e2 = ed.apply_cfg_edits(ed.apply_cfg_set(app.base_cfg, cfg_set), cfg_edits or [])
    m_edits = [e for e in edits if e.get("target") in ("monster", "pattern", "gimmick")]
    c3 = e3 = []
    if m_edits:
        if app.monster_data is None:
            raise ValueError("몬스터 데이터가 없어 몬스터 편집을 적용할 수 없음")
        mdata, c3, e3 = ed.apply_monster_edits(app.monster_data, m_edits)
        if cfg["monsters"].get("model") == "table":
            cfg["monsters"]["table_file"] = app.materialize_monsters(mdata)
    if c1 or c2 or c3 or e1 or e2 or e3:
        raise ValueError("편집 적용 실패: " + "; ".join(
            f"{x.get('fid') or x.get('mid') or x.get('pid') or x.get('path')} {x.get('reason')}" for x in c1 + c2 + c3 + e1 + e2 + e3))
    path, h = st.materialize_table(data, app.tables_dir)
    cfg["fantasy"]["effects_file"] = path
    cfg["fantasy"]["effect_mode"] = "table"
    return cfg, h


def dh_of(cfg, h):
    return st.data_hash(h, st.monster_hash(cfg))


def _x_order(xs, x_sel):
    if x_sel is None:
        return list(xs)
    return sorted(xs, key=lambda x: (abs(x - x_sel), x))


class SeriesSet:
    """여러 계열(after/before)의 점 레코드를 모아 점 단위 결과를 만든다."""

    def __init__(self, app, job, x_key, seed):
        self.app, self.job, self.x_key, self.seed = app, job, x_key, seed
        self.cfg = {}
        self.hash = {}
        self.recs = {}

    def add_series(self, name, cfg, thash):
        self.cfg[name], self.hash[name] = cfg, thash

    def req(self, series, fid, x):
        c = copy.deepcopy(self.cfg[series])
        ms.set_path(c, self.x_key, x)
        fids = [] if fid == BASE else fid.split("+")   # "a+b" = 여러 환상 강제 포함
        return cp.make_req(c, fids, self.seed, self.hash[series], tag=(series, fid, x))

    def point(self, series, fid, x, n):
        rec = self.recs[(series, fid, x)]
        p = S.point_stats(rec, x, n)
        p["table_hash"] = self.hash[series]
        p["layer"] = "reference" if series == "before" else "current"     # §6.8
        if series == "after" and fid == BASE:
            bb = self.recs.get(("before", BASE, x))
            if bb and bb["n"] >= n:     # 기준선의 수정 전후 차이 (몬스터·설정·획득 시스템을 바꿨을 때)
                e = S.paired_delta(rec, bb, n)
                p["edit_effect"], p["edit_effect_se"], p["edit_effect_ci"] = e["delta"], e["delta_se"], e["delta_ci"]
        b = self.recs.get((series, BASE, x))
        if fid != BASE and b and b["n"] >= n:
            p.update(S.paired_delta(rec, b, n))
        if series == "after" and fid != BASE:
            bf = self.recs.get(("before", fid, x))
            if bf and bf["n"] >= n:
                e = S.paired_delta(rec, bf, n)
                p["edit_effect"] = e["delta"]
                p["edit_effect_se"] = e["delta_se"]
                p["edit_effect_ci"] = e["delta_ci"]
        return p

    def run(self, items, stages):
        """items: [(series, fid, x)] 우선순위 순서. 단계마다 모두 채우고 점마다 이벤트를 보낸다."""
        job = self.job
        total = len(items) * stages[-1]
        eng = self.app.engine
        try:   # 전체 계획: 새로 돌릴 판 수 = Σ max(0, 최종 n − 저장된 n)  (캐시에 있는 판은 제외)
            have = [min(eng.record(self.req(*it))["n"], stages[-1]) for it in items]
            job.progress.plan(sum(stages[-1] - h for h in have), cached=sum(have))
        except Exception:  # noqa: BLE001 — 계획 실패는 진행 표시만 덜 정확하게 할 뿐
            pass
        for si, n in enumerate(stages):
            reqs = [self.req(*it) for it in items]

            def on_pt(req, rec, n=n, si=si):
                tag = req["tag"]
                self.recs[tag] = rec
                series, fid, x = tag
                targets = [tag]
                if fid == BASE:  # 기준선이 채워지면 같은 X 의 환상 Δ 를 다시 보냄
                    targets += [k for k in self.recs if k[0] == series and k[2] == x and k[1] != BASE
                                and self.recs[k]["n"] >= n]
                if series == "before":
                    targets += [k for k in self.recs if k[0] == "after" and k[1] == fid and k[2] == x
                                and self.recs[k]["n"] >= n]
                for t in targets:
                    job.emit("point", series=t[0], fid=t[1], x=t[2], stage=si + 1, point=self.point(*t, n))

            self.app.engine.ensure(reqs, n, on_point=on_pt, cancel=lambda: job.cancelled, progress=job.progress)
            job.emit("stage", stage=si + 1, n=n, done_runs=len(items) * n, total_runs=total)


# ---------------------------------------------------------------------------
# 작업 종류
# ---------------------------------------------------------------------------
def job_recompute(app, job):
    """편집 후 재계산: 수정한 환상 + 기준선 (+ 선택한 환상). 수정 전(고스트)도 같이 계산.

    수정 전 = 비교 기준 스냅샷(app.ref, §6.8). 숫자 UI 편집(edits)과 JSON 편집(작업 사본)이 같은 경로를 쓴다.
    수정한 환상 = 숫자 편집한 환상 ∪ 작업 사본이 기준과 다른 환상."""
    p = job.params
    edits, cfg_edits, cfg_set = p.get("edits") or [], p.get("cfg_edits") or [], p.get("cfg_set") or {}
    cfg_after, h_after = prepare(app, edits, cfg_edits, cfg_set)
    xs = p.get("x_values") or app.x_values
    stages = sorted(set(int(s) for s in (p.get("stages") or app.progressive_stages)))
    ref = getattr(app, "ref", None)
    changed = app.changed() if ref else {"fantasies": [], "monsters": [], "patterns": [], "cfg_keys": []}
    known = set(app.table_ids)
    edited = list(dict.fromkeys([e["fid"] for e in edits if e.get("target", "fantasy") == "fantasy"]
                                + [f for f in changed["fantasies"] if f in known]))
    fids = list(dict.fromkeys(edited + list(p.get("fids") or [])))
    ss = SeriesSet(app, job, app.x_key, app.seed)
    ss.add_series("after", cfg_after, h_after)
    ref_differs = bool(ref) and ref["data_hash"] != app.data_hash
    ghost = bool(edits or cfg_edits or cfg_set or ref_differs)
    if ghost:
        if ref:
            ss.add_series("before", app.cfg_for(ref["table_data"], ref["monster_data"]), ref["table_hash"])
        else:
            ss.add_series("before", app.base_cfg, app.table_hash)
    items = []
    for x in _x_order(xs, p.get("x_sel")):
        items.append(("after", BASE, x))
        items += [("after", f, x) for f in edited]
        if ghost:
            items += [("before", f, x) for f in edited] + [("before", BASE, x)]
        items += [("after", f, x) for f in fids if f not in edited]
        if ghost:   # §6.8: 고스트 = 변경된 환상 + 기준선 + 사용자가 선택한 항목
            items += [("before", f, x) for f in fids if f not in edited]
    job.emit("plan", table_hash=h_after, data_hash=dh_of(cfg_after, h_after), base_data_hash=app.data_hash,
             ref_hash=ref["data_hash"] if ref else None, changed=changed, ghost=ghost,
             fids=fids, edited=edited, x_values=xs, stages=stages, points=len(items))
    ss.run(items, stages)
    return {"table_hash": h_after, "data_hash": dh_of(cfg_after, h_after)}


def job_scan(app, job):
    """전체 재계산 / 패싯 스캔: fantasy_scan.run_scan 으로 모든(또는 지정) 환상을 계산."""
    import fantasy_scan as fs
    p = job.params
    cfg, h = prepare(app, p.get("edits"), p.get("cfg_edits"), p.get("cfg_set"))
    fids = p.get("fids") or list(app.table_ids)
    stages = sorted(set(int(s) for s in (p.get("stages") or app.adaptive_stages)))
    facet_key = p.get("facet_key")
    facet_values = p.get("facet_values") or [None]
    job.emit("plan", table_hash=h, data_hash=dh_of(cfg, h), fids=fids, x_values=app.x_values, stages=stages,
             facet_key=facet_key, facet_values=facet_values)

    def on_point(fv, fid, x, pt):
        pt["table_hash"] = h
        job.emit("point", series="after", fid=fid, x=x, facet=fs.facet_label(fv), point=pt)

    res = fs.run_scan(app.engine, cfg, h, app.seed, app.x_key, app.x_values, fids, stages=stages,
                      adaptive=bool(p.get("adaptive", True)), epsilon=float(p.get("epsilon", app.epsilon)),
                      facet_key=facet_key, facet_values=facet_values, cancel=lambda: job.cancelled,
                      on_point=on_point, log=lambda *a, **k: None, progress=job.progress)
    if p.get("save"):
        ctx = ms.SimContext(cfg)
        data = fs.assemble(res, cfg, fids, ctx, h, seed=app.seed, x_key=app.x_key, fixed=app.fixed,
                           target=app.target, stages=stages, adaptive=bool(p.get("adaptive", True)),
                           epsilon=float(p.get("epsilon", app.epsilon)), facet_key=facet_key,
                           facet_values=facet_values, forced_at=None, n_max=stages[-1])
        app.save_scan(data, p.get("save_name"))
    if getattr(app, "surrogate_auto", "manual") == "after_scan" and hasattr(app, "trainer"):
        app.trainer.submit("surrogate_fit", {"auto": True})    # v4.1 Q30: 스캔 직후 후보 전체 (최하위 우선순위)
    return {"table_hash": h}


def _delta_at(app, job, table_data, cfg_edits, fid, x, stages, epsilon):
    """테이블·설정에서 fid 강제 포함 vs 기준선의 Δ (적응형)."""
    path, h = st.materialize_table(table_data, app.tables_dir)
    cfg, *_ = ed.apply_cfg_edits(app.base_cfg, cfg_edits or [])
    cfg["fantasy"]["effects_file"] = path
    cfg["fantasy"]["effect_mode"] = "table"
    ms.set_path(cfg, app.x_key, x)
    rb = cp.make_req(cfg, [], app.seed, h)
    rf = cp.make_req(cfg, [fid], app.seed, h)
    d = None
    for n in stages:
        recs = app.engine.ensure([rb, rf], n, cancel=lambda: job.cancelled, progress=job.progress)
        d = S.paired_delta(recs[rf["key"]], recs[rb["key"]], n)
        if S.half_width(d["delta_se"]) <= epsilon:
            break
    return d


def _with_value(app, edits, fid, effect, key, v):
    data, c, e = ed.apply_edits(app.table_data, edits or [])
    if c or e:
        raise ValueError(f"기존 편집 적용 실패: {c + e}")
    ent = {x["id"]: x for x in data["fantasies"]}[fid]
    ef = ent["effects"][effect]
    err = ed.validate(ed.key_schema(ef, key), v)
    if err:
        raise ValueError(f"{fid}.{key}={v}: {err}")
    ef[key] = v
    return data


def job_value_sweep(app, job):
    p = job.params
    fid, effect, key = p["fid"], int(p["effect"]), p["key"]
    x = p.get("x", app.x_values[len(app.x_values) // 2])
    stages = sorted(set(int(s) for s in (p.get("stages") or app.adaptive_stages)))
    eps = float(p.get("epsilon", app.epsilon))
    values = p["values"]
    ent = {e["id"]: e for e in app.table_data["fantasies"]}[fid]
    orig = ent["effects"][effect][key]
    job.emit("plan", fid=fid, key=key, x=x, values=values, original=orig)
    out = []
    for v in values:
        data = _with_value(app, p.get("edits"), fid, effect, key, v)
        d = _delta_at(app, job, data, p.get("cfg_edits"), fid, x, stages, eps)
        out.append({"value": v, **d})
        job.emit("sweep_point", value=v, **d)
    return {"points": out, "original": orig}


def job_solve_value(app, job):
    """목표 Δ 역산: 단조 가정 이분 탐색. 구간 자동 확장 최대 6회."""
    p = job.params
    fid, effect, key = p["fid"], int(p["effect"]), p["key"]
    x = p.get("x", app.x_values[len(app.x_values) // 2])
    target = float(p["target_delta"])
    stages = sorted(set(int(s) for s in (p.get("stages") or app.adaptive_stages)))
    eps = float(p.get("epsilon", app.epsilon))
    ent = {e["id"]: e for e in app.table_data["fantasies"]}[fid]
    ef = ent["effects"][effect]
    sch = ed.key_schema(ef, key)
    cur = float(ef[key])
    integer = bool(sch and sch["int"])
    lo = float(p.get("lo", cur * 0.5 if cur else sch["min"]))
    hi = float(p.get("hi", cur * 1.5 if cur else (sch["max"] if sch["max"] < 1e3 else 100)))
    lo, hi = min(lo, hi), max(lo, hi)
    clamp = lambda v: max(sch["min"] + (1e-6 if sch.get("min_exclusive") else 0), min(sch["max"], v))  # noqa: E731
    rnd = (lambda v: int(round(v))) if integer else (lambda v: round(v, 6))
    cache = {}

    def f(v):
        v = rnd(clamp(v))
        if v not in cache:
            data = _with_value(app, p.get("edits"), fid, effect, key, v)
            d = _delta_at(app, job, data, p.get("cfg_edits"), fid, x, stages, eps)
            cache[v] = d
            job.emit("solve_eval", value=v, **d)
        return v, cache[v]["delta"]

    lo, flo = f(lo)
    hi, fhi = f(hi)
    expansions = 0
    while (flo - target) * (fhi - target) > 0 and expansions < 6:
        expansions += 1
        width = hi - lo or 1
        # 목표에서 먼 쪽이 아니라 목표가 있을 법한 쪽으로 넓힌다 (단조 가정)
        increasing = fhi >= flo
        if (target > max(flo, fhi)) == increasing:
            hi, fhi = f(hi + width)
        else:
            lo, flo = f(lo - width)
        if hi == lo:
            break
    if (flo - target) * (fhi - target) > 0:
        return {"found": False, "reason": "탐색 범위 안에 해 없음 / 비단조 가능성", "lo": [lo, flo], "hi": [hi, fhi],
                "evals": [{"value": k, **v} for k, v in sorted(cache.items())]}
    for _ in range(10):
        if integer and hi - lo <= 1:
            break
        if not integer and abs(hi - lo) <= max(1e-3, abs(cur) * 0.01):
            break
        mid, fm = f((lo + hi) / 2)
        if mid in (lo, hi):
            break
        if (fm - target) * (flo - target) <= 0:
            hi, fhi = mid, fm
        else:
            lo, flo = mid, fm
    best = min(cache.items(), key=lambda kv: abs(kv[1]["delta"] - target))
    return {"found": True, "value": best[0], "delta": best[1], "target": target,
            "evals": [{"value": k, **v} for k, v in sorted(cache.items())]}


def combo_setup(app, p):
    from . import combo as cb
    cfg, h = prepare(app, p.get("edits"), p.get("cfg_edits"), p.get("cfg_set"))
    ids = list(dict.fromkeys(p.get("ids") or []))
    for i in ids:
        if i not in app.table_ids:
            raise ValueError(f"알 수 없는 환상: {i}")
    xs = p.get("x_values") or app.x_values
    stages = sorted(set(int(s) for s in (p.get("stages") or app.progressive_stages)))
    typ = p.get("baseline_type", "natural")
    return cb, cfg, h, ids, xs, stages, typ, p.get("arms", "all")


def estimate(app, p):
    """조합 작업 예상 시간 (실측 처리 속도 기준). 60초를 넘으면 뷰어가 확인을 받는다."""
    cb, cfg, h, ids, xs, stages, typ, arms = combo_setup(app, p)
    reqs, need = cb.plan(cfg, app.x_key, xs, ids, list(app.table_ids), typ, app.seed, h, app.engine, stages[-1], arms)
    rate = app.engine.rate or 700.0 * app.engine.workers
    return {"arms": len(reqs) // max(1, len(xs)), "points": len(reqs), "runs_needed": need,
            "rate": round(rate), "seconds": round(need / rate, 1), "measured": app.engine.rate is not None}


def job_combo(app, job):
    """조합 모드 (F4a): 체크한 환상(≤4)의 모든 부분집합 팔 x X 격자."""
    p = job.params
    cb, cfg, h, ids, xs, stages, typ, arms = combo_setup(app, p)
    order = list(app.table_ids)
    label = p.get("label", "pre")
    job.emit("plan", ids=ids, baseline_type=typ, x_values=xs, stages=stages, table_hash=h, data_hash=dh_of(cfg, h), label=label)
    holder = {}

    def on_stage(n, by_x):
        holder["by_x"] = by_x
        tmp = {"ids": sorted(ids, key=order.index), "baseline_type": typ, "arms": arms, "x_values": xs}
        job.emit("combo", stage_n=n, combo=cb.to_json(tmp, label, by_x))

    res = cb.run_combo(app.engine, cfg, h, app.seed, app.x_key, xs, ids, order, typ, stages,
                       float(p.get("epsilon", app.epsilon)), cancel=lambda: job.cancelled, on_stage=on_stage, arms=arms, progress=job.progress)
    out = cb.to_json(res, label)
    # 등가 체력 이득 (선택 X): 빈 집합 팔 곡선을 단조 회귀로 고른 뒤 역산
    x0 = p.get("x_sel", xs[len(xs) // 2])
    if x0 not in xs:
        x0 = xs[len(xs) // 2]
    base_w = [res["by_x"][x]["arms"][frozenset()]["win_rate"] for x in xs]
    recs0 = {r["tag"][0]: app.store.load(r["key"]) for r in res["reqs"] if not r["tag"][1]}
    gains = {}
    for k, a in res["by_x"][x0]["arms"].items():
        if not k:
            continue
        name = "+".join(sorted(k, key=res["ids"].index))
        if p.get("gain_ci") and len(xs) >= 2:
            arm_rec = app.store.load(next(r["key"] for r in res["reqs"] if r["tag"] == (x0, k)))
            gains[name] = S.equiv_gain_ci(xs, [recs0[x] for x in xs], arm_rec, x0, res["n"])
        else:
            g, why = S.equiv_gain(xs, base_w, a["win_rate"], x0) if len(xs) >= 2 else (None, "기준선 점 부족")
            gains[name] = {"gain": None if g is None else round(g, 4), "reason": why}
    out["equiv_gain"] = {"x": x0, "arms": gains}
    out["table_hash"] = h
    out["data_hash"] = dh_of(cfg, h)
    return out


def job_monster_probe(app, job):
    """몬스터 단독 전투 지표: 편집 전·후를 같은 시드로 비교 (몬스터를 고치는 즉시 갱신하는 용도)."""
    from . import monsters as mo
    p = job.params
    if app.monster_data is None:
        raise ValueError("몬스터 데이터 없음")
    cfg, h = prepare(app, [e for e in (p.get("edits") or []) if e.get("target", "fantasy") == "fantasy"],
                     p.get("cfg_edits"), p.get("cfg_set"))
    m_edits = [e for e in (p.get("edits") or []) if e.get("target") in ("monster", "pattern", "gimmick")]
    after, c, e = ed.apply_monster_edits(app.monster_data, m_edits)
    if c or e:
        raise ValueError(f"몬스터 편집 적용 실패: {c + e}")
    n = int(p.get("n", 2000))
    out = {}
    before = (getattr(app, "ref", None) or {}).get("monster_data") or app.monster_data   # 수정 전 = 비교 기준
    for label, tab in (("before", before), ("after", after)):
        mon = next((m for m in tab["monsters"] if m["id"] == p["mid"]), None)
        if mon is None:
            raise ValueError(f"몬스터 없음: {p.get('mid')}")
        out[label] = mo.probe(cfg, mon, n, p.get("seed", "probe"), p.get("fids") or [])
        job.emit("probe", which=label, **out[label])
    if p.get("compare_models"):     # v4 F8.6: 같은 상태로 gauss 와 digits 를 나란히 (규모 차이 확인)
        mon = next(m for m in after["monsters"] if m["id"] == p["mid"])
        out["models"] = {}
        for dm in ("gauss", "digits"):
            c2 = copy.deepcopy(cfg)
            c2["monsters"]["damage_model"] = dm
            if dm == "gauss":
                c2["monsters"]["gimmicks"] = "off"
            elif p.get("gimmicks") in ("on", "off"):
                c2["monsters"]["gimmicks"] = p["gimmicks"]
            out["models"][dm] = mo.probe(c2, mon, n, p.get("seed", "probe"), p.get("fids") or [])
            job.emit("probe", which="model:" + dm, **out["models"][dm])
    return out


def job_ember_sweep(app, job):
    """불씨 파라미터 스윕 (§7.5): slot_size x blue_chance 격자를 선택 X 에서 기준선만 돌린다. 정수 격자 전체 계산."""
    p = job.params
    slots = [int(v) for v in (p.get("slot_sizes") or [2, 3, 4, 5])]
    chances = [float(v) for v in (p.get("blue_chances") or [0.0, 0.1, 0.2, 0.3])]
    x = p.get("x", app.x_values[len(app.x_values) // 2])
    n = int(p.get("n", app.adaptive_stages[-1]))
    cfg_set = dict(p.get("cfg_set") or {})
    cfg_set["rewards.normal_battle.mode"] = "ember"
    job.emit("plan", slot_sizes=slots, blue_chances=chances, x=x, n=n, integer_param="slot_size")
    cells = []
    reqs = {}
    for sl in slots:
        for ch in chances:
            cfg, h = prepare(app, p.get("edits"), p.get("cfg_edits"), cfg_set)
            cfg["rewards"]["ember"]["slot_size"] = sl
            cfg["rewards"]["ember"]["blue_chance"] = ch
            ms.set_path(cfg, app.x_key, x)
            reqs[(sl, ch)] = cp.make_req(cfg, [], app.seed, h, tag=(sl, ch))

    def on_pt(req, rec):
        sl, ch = req["tag"]
        pt = S.point_stats(rec, x, n)
        wr = pt["win_rate"]
        se = (wr * (1 - wr) / pt["n"]) ** 0.5
        cell = {"slot_size": sl, "blue_chance": ch, "n": pt["n"], "win_rate": wr,
                "win_ci": [round(wr - 1.96 * se, 6), round(wr + 1.96 * se, 6)],
                "mean_fantasies": pt["mean_fantasies"], "mean_reached_floor": pt["mean_reached_floor"],
                "blue_fantasies": pt.get("ember_mean", {}).get("blue_picked"), "src_mean": pt.get("src_mean")}
        cells.append(cell)
        job.emit("cell", **cell)

    app.engine.ensure(list(reqs.values()), n, on_point=on_pt, cancel=lambda: job.cancelled, progress=job.progress)
    return {"x": x, "n": n, "cells": cells, "slot_sizes": slots, "blue_chances": chances}


JOB_KINDS = {
    "monster_probe": job_monster_probe,
    "combo": job_combo,
    "ember_sweep": job_ember_sweep,
    "recompute": job_recompute,
    "scan": job_scan,
    "skill_facet": job_scan,
    "value_sweep": job_value_sweep,
    "solve_value": job_solve_value,
    "tune": None,     # 아래에서 채움
}


TUNE_KEYS = ("monsters.hp_scale", "player.start_hp")


def job_tune(app, job):
    """목표 승률 맞추기 (v4.2 F11.6): 기준선 승률이 목표가 되는 몬스터 체력 배율 또는 시작 체력을 이분 탐색.
    CLI --tune 과 같은 탐색 함수·같은 시드 규칙(f"{seed}-{i}")이라 같은 시드·판 수면 결과가 같다 (AC-H8).
    몬스터 JSON·설정·시나리오 파일을 쓰지 않는다 — 환산 체력 표는 보여 주기만 한다."""
    p = job.params
    key = p.get("key", "monsters.hp_scale")
    if key not in TUNE_KEYS:
        raise ValueError(f"승률 맞추기 대상은 {', '.join(TUNE_KEYS)} 중 하나: {key}")
    lo, hi = float(p["lo"]), float(p["hi"])
    if not lo < hi:
        raise ValueError("탐색 범위: lo < hi")
    target = float(p.get("target", app.target))
    tol = float(p.get("tol", 0.01))
    runs = int(p.get("runs", 1000))
    max_evals = int(p.get("max_evals", 12))
    seed = str(p.get("seed") or "tune")
    cfg, h = prepare(app, p.get("edits"), p.get("cfg_edits"), p.get("cfg_set"))
    if key == "monsters.hp_scale" and cfg["monsters"].get("model") != "table":
        raise ValueError("monsters.hp_scale 은 몬스터 테이블 모델(table)에서만 의미가 있음")
    integer = not isinstance(ms.get_path(cfg, key), float)
    job.emit("plan", key=key, lo=lo, hi=hi, target=target, runs=runs, max_evals=max_evals, seed=seed)

    def evaluate(x):
        c = copy.deepcopy(cfg)
        ms.set_path(c, key, x)
        req = cp.make_req(c, [], seed, h)
        rec = app.engine.ensure([req], runs, cancel=lambda: job.cancelled, progress=job.progress)[req["key"]]
        w = round(rec["wins"][:runs].count("1") / runs, 4)      # CLI summarize() 와 같은 반올림
        job.emit("tune_point", x=x, win_rate=w, n=runs)
        return w

    try:
        evals, best, in_range, stop = ms.tune_search(evaluate, lo, hi, target, tol, max_evals, integer,
                                                     cancel=lambda: job.cancelled)
    except ms.TuneCancelled:
        raise cp.Cancelled()
    w = evals[best]
    ci = ms.wilson_ci(w, runs)
    res = {"key": key, "target": target, "found": best, "win_rate": w, "ci": [round(ci[0], 4), round(ci[1], 4)],
           "in_range": in_range, "stop": stop, "runs": runs, "seed": seed, "within_tol": abs(w - target) <= tol,
           "evals": [{"x": x, "win_rate": v} for x, v in sorted(evals.items())],
           "current": ms.get_path(app.base_cfg, key)}
    if key == "monsters.hp_scale":
        res["table"] = ms.scaled_hp_table(cfg, best)
    return res


JOB_KINDS["tune"] = job_tune
