# -*- coding: utf-8 -*-
"""수치 보정 (명세 v2 F3): 플레이 기록의 생존 곡선(층별 도달률)에 시뮬레이션을 맞춘다.

목적함수 = Σ_f w_f (obs_f − sim_f)², w_f = 1 / (관측 이항 분산). 시뮬레이션은 공통 시드 n판(점 캐시 사용).
탐색 = 의존성 없는 Nelder–Mead (경계는 잘라냄). 한 번에 2~3개 파라미터까지.
"""
from __future__ import annotations

import copy
import csv
import math

import matchup_sim as ms

from . import compute as cp
from . import stats as S

DEFAULT_PARAMS = {
    "player.skill": (0.2, 1.0),
    "player.attack_gain_per_move": (0.1, 2.0),
    "player.defense_cut_per_move": (0.05, 0.9),
}
REQUIRED = ("run_id", "result", "end_act", "end_floor")
MIN_RUNS = 30


def read_playtest(path):
    rows = []
    with open(path, encoding="utf-8-sig", newline="") as fp:
        rd = csv.DictReader(fp)
        miss = [c for c in REQUIRED if c not in (rd.fieldnames or [])]
        if miss:
            raise ValueError(f"필수 열 없음: {miss} (필수: {', '.join(REQUIRED)})")
        for r in rd:
            if not r.get("run_id"):
                continue
            res = r["result"].strip().lower()
            if res not in ("win", "lose"):
                raise ValueError(f"result 는 win/lose: {r['result']}")
            act, fl = int(r["end_act"]), int(r["end_floor"])
            reached = ms.TOTAL_FLOORS if res == "win" else (act - 1) * ms.FLOORS_PER_ACT + fl
            rows.append({"run_id": r["run_id"], "result": res, "reached": reached})
    return rows


def observed_reach(rows):
    n = len(rows)
    return [sum(1 for r in rows if r["reached"] >= f) / n for f in range(1, ms.TOTAL_FLOORS + 1)], n


def weights(obs, n):
    w = []
    for p in obs:
        q = min(max(p, 1 / (2 * n)), 1 - 1 / (2 * n))
        w.append(n / (q * (1 - q)))
    return w


class Objective:
    def __init__(self, engine, cfg, thash, seed, n_sim, obs, n_obs, params, cancel=None, on_eval=None):
        self.engine, self.cfg, self.thash, self.seed, self.n_sim = engine, cfg, thash, seed, n_sim
        self.obs, self.n_obs, self.w = obs, n_obs, weights(obs, n_obs)
        self.params = params
        self.cancel, self.on_eval = cancel, on_eval
        self.cache = {}

    def sim_reach(self, values):
        c = copy.deepcopy(self.cfg)
        for k, v in zip(self.params, values):
            ms.set_path(c, k, v)
        r = cp.make_req(c, [], self.seed, self.thash)
        rec = self.engine.ensure([r], self.n_sim, cancel=self.cancel)[r["key"]]
        return S.point_stats(rec, None, self.n_sim)["reach_rate"]

    def __call__(self, values):
        key = tuple(round(v, 6) for v in values)
        if key not in self.cache:
            sim = self.sim_reach(key)
            sse = sum(w * (o - s) ** 2 for w, o, s in zip(self.w, self.obs, sim))
            self.cache[key] = (sse, sim)
            if self.on_eval:
                self.on_eval(dict(zip(self.params, key)), sse)
        return self.cache[key][0]


def nelder_mead(f, x0, bounds, step=0.1, max_evals=60, tol=1e-3):
    n = len(x0)
    clip = lambda x: [min(max(v, lo), hi) for v, (lo, hi) in zip(x, bounds)]  # noqa: E731
    pts = [clip(list(x0))]
    for i in range(n):
        x = list(x0)
        span = bounds[i][1] - bounds[i][0]
        x[i] = x[i] + step * span if x[i] + step * span <= bounds[i][1] else x[i] - step * span
        pts.append(clip(x))
    vals = [f(p) for p in pts]
    evals = len(pts)
    while evals < max_evals:
        order = sorted(range(n + 1), key=lambda k: vals[k])
        pts, vals = [pts[k] for k in order], [vals[k] for k in order]
        if abs(vals[-1] - vals[0]) <= tol * (1 + abs(vals[0])) and max(
                max(abs(pts[k][i] - pts[0][i]) / (bounds[i][1] - bounds[i][0]) for i in range(n)) for k in range(1, n + 1)) < 0.01:
            break
        cen = [sum(p[i] for p in pts[:-1]) / n for i in range(n)]
        xr = clip([cen[i] + (cen[i] - pts[-1][i]) for i in range(n)])
        fr = f(xr)
        evals += 1
        if fr < vals[0]:
            xe = clip([cen[i] + 2 * (cen[i] - pts[-1][i]) for i in range(n)])
            fe = f(xe)
            evals += 1
            pts[-1], vals[-1] = (xe, fe) if fe < fr else (xr, fr)
        elif fr < vals[-2]:
            pts[-1], vals[-1] = xr, fr
        else:
            xc = clip([cen[i] + 0.5 * (pts[-1][i] - cen[i]) for i in range(n)])
            fc = f(xc)
            evals += 1
            if fc < vals[-1]:
                pts[-1], vals[-1] = xc, fc
            else:
                for k in range(1, n + 1):
                    pts[k] = clip([pts[0][i] + 0.5 * (pts[k][i] - pts[0][i]) for i in range(n)])
                    vals[k] = f(pts[k])
                    evals += 1
    k = min(range(n + 1), key=lambda k: vals[k])
    return pts[k], vals[k], evals


def calibrate(engine, cfg, thash, seed, rows, params=None, n_sim=3000, start=None, max_evals=60, cancel=None,
              on_eval=None, profile_points=5):
    params = params or list(DEFAULT_PARAMS)
    if len(params) > 3:
        raise ValueError("한 번에 3개까지만 맞춘다 (식별 불가 문제)")
    bounds = [DEFAULT_PARAMS.get(p, (0.0, 1.0)) for p in params]
    obs, n_obs = observed_reach(rows)
    warnings = []
    if n_obs < MIN_RUNS:
        warnings.append(f"관측 {n_obs}판 < {MIN_RUNS}판: 과적합 위험이 큼")
    obj = Objective(engine, cfg, thash, seed, n_sim, obs, n_obs, params, cancel, on_eval)
    cur = []
    for p in params:
        v = cfg
        for k in p.split("."):
            v = v[k]
        cur.append(float(v))
    x0 = start or cur
    best, sse, evals = nelder_mead(obj, x0, bounds, max_evals=max_evals)
    sim = obj.cache[tuple(round(v, 6) for v in best)][1]
    profile = {}
    for i, p in enumerate(params):
        lo, hi = bounds[i]
        span = (hi - lo) * 0.15
        xs = sorted({round(min(hi, max(lo, best[i] + span * (k / (profile_points // 2) - 1) if profile_points > 1 else best[i])), 6)
                     for k in range(profile_points)} | {round(best[i], 6)})
        prof = []
        for v in xs:
            x = list(best)
            x[i] = v
            prof.append([v, round(obj(x), 4)])
        profile[p] = prof
    dof = max(1, ms.TOTAL_FLOORS - len(params))
    return {
        "params": dict(zip(params, [round(v, 6) for v in best])),
        "start": dict(zip(params, x0)),
        "bounds": dict(zip(params, bounds)),
        "fit": {"weighted_sse": round(sse, 4), "chi2_per_dof": round(sse / dof, 4), "n_obs": n_obs, "n_sim": n_sim,
                "evals": evals},
        "observed_reach": [round(v, 6) for v in obs],
        "sim_reach": sim,
        "residuals": [round(o - s, 6) for o, s in zip(obs, sim)],
        "profile": profile,
        "warnings": warnings,
        "cfg_edits": [{"path": p, "old": c, "new": round(v, 6)} for p, c, v in zip(params, cur, best)],
    }
