# -*- coding: utf-8 -*-
"""한계효과 미리보기 (v4.1 F10) — 표준 라이브러리만.

근사값 격리 원칙 (F10.1): 이 모듈의 출력은 **화면 미리보기 전용**이다. 점 캐시·스캔 JSON·시나리오·순위·판정·조합·
스윕·solve_value 어디에도 들어가지 않는다. 학습 격자의 점은 일반 시뮬레이션 점(편집 오버레이)이라 캐시에 저장되지만
그것은 근사가 아니라 실제 시뮬레이션 결과다.

모델 (X 마다 따로)
  y(θ) = 짝지은 Δ (환상: 강제 포함 팔 − 같은 θ 의 기준선 / 몬스터: θ 의 기준선 − 원래 값의 기준선)
  척도: prob (y = Δ) 또는 logit (y = logit(w_ref + Δ) − logit(w_ref)), 차수 1 또는 2, 표준화 z = (θ − mu) / sd
  가중 최소제곱 (가중치 1/se²), 척도·차수는 leave-one-out 교차 검증 RMSE(%p, prob 척도)가 작은 쪽
예측(앵커): p̂(X; θ') = clip(p_실제(X) + Δ̂(θ') − Δ̂(θ_실제), 0, 1). 실제 곡선이 없으면 clip(w_기준선 + Δ̂(θ'), 0, 1) + "앵커 없음".
이산(몬스터 기본 힘): 학습한 정수 값의 Δ 표, 그 값에만 예측.
JS(viewer_template.html 의 SG.predict)와 같은 순서의 산술로 계산한다 (AC-Y7, 1e-9).
"""
from __future__ import annotations

import math

VERSION = 1
TRUST, CAUTION = 0.015, 0.03          # Q31 기본값: 신뢰 1.5%p, 주의 3%p (판정 = max(고정, 2 × 평균 se))
SAT_LO, SAT_HI = 0.03, 0.97           # 포화 구간 (F10.5)
EPS = 1e-6


# ---------------------------------------------------------------------------
# 작은 선형대수 (정규방정식)
# ---------------------------------------------------------------------------
def _solve(A, b):
    n = len(A)
    M = [list(A[i]) + [b[i]] for i in range(n)]
    for c in range(n):
        p = max(range(c, n), key=lambda r: abs(M[r][c]))
        if abs(M[p][c]) < 1e-15:
            return None
        M[c], M[p] = M[p], M[c]
        for r in range(n):
            if r != c:
                f = M[r][c] / M[c][c]
                for k in range(c, n + 1):
                    M[r][k] -= f * M[c][k]
    return [M[i][n] / M[i][i] for i in range(n)]


def _inv(A):
    n = len(A)
    cols = []
    for j in range(n):
        e = [1.0 if i == j else 0.0 for i in range(n)]
        x = _solve(A, e)
        if x is None:
            return None
        cols.append(x)
    return [[cols[j][i] for j in range(n)] for i in range(n)]


def wls(zs, ys, ws, deg):
    """가중 최소제곱 y = Σ c_k z^k. 반환 (coef, cov) 또는 None."""
    m = deg + 1
    A = [[0.0] * m for _ in range(m)]
    b = [0.0] * m
    for z, y, w in zip(zs, ys, ws):
        row = [z ** k for k in range(m)]
        for i in range(m):
            b[i] += w * row[i] * y
            for j in range(m):
                A[i][j] += w * row[i] * row[j]
    c = _solve(A, b)
    if c is None:
        return None
    cov = _inv(A)
    # 잔차로 분산 척도 보정 (자유도가 있을 때, 과소분산은 그대로 1)
    dof = len(zs) - m
    if dof > 0:
        chi = sum(w * (y - sum(c[k] * z ** k for k in range(m))) ** 2 for z, y, w in zip(zs, ys, ws)) / dof
        s = max(1.0, chi)
        cov = [[v * s for v in r] for r in cov] if cov else None
    return c, cov


# ---------------------------------------------------------------------------
# 척도
# ---------------------------------------------------------------------------
def _clamp01(p):
    return min(1.0 - EPS, max(EPS, p))


def logit(p):
    p = _clamp01(p)
    return math.log(p / (1.0 - p))


def sigmoid(x):
    if x >= 0:
        return 1.0 / (1.0 + math.exp(-x))
    e = math.exp(x)
    return e / (1.0 + e)


def poly(c, z):
    """c0 + c1 z + c2 z² — JS 와 같은 순서."""
    v = 0.0
    zk = 1.0
    for k in range(len(c)):
        v = v + c[k] * zk
        zk = zk * z
    return v


def delta_from(sx, theta):
    """X 하나의 적합 sx 로 Δ̂(θ) (prob 척도)."""
    z = (theta - sx["mu"]) / sx["sd"]
    eta = poly(sx["coef"], z)
    if sx["scale"] == "logit":
        lw = logit(sx["w_ref"])
        return sigmoid(lw + eta) - sx["w_ref"]
    return eta


def _deta_dtheta(sx, theta):
    z = (theta - sx["mu"]) / sx["sd"]
    d = 0.0
    zk = 1.0
    for k in range(1, len(sx["coef"])):
        d = d + k * sx["coef"][k] * zk
        zk = zk * z
    return d / sx["sd"]


def _pred_var_eta(sx, theta):
    if not sx.get("cov"):
        return 0.0
    z = (theta - sx["mu"]) / sx["sd"]
    g = [z ** k for k in range(len(sx["coef"]))]
    v = 0.0
    for i in range(len(g)):
        for j in range(len(g)):
            v = v + g[i] * sx["cov"][i][j] * g[j]
    return max(0.0, v)


def _dprob_deta(sx, theta):
    if sx["scale"] != "logit":
        return 1.0
    p = delta_from(sx, theta) + sx["w_ref"]
    return p * (1.0 - p)


# ---------------------------------------------------------------------------
# 학습
# ---------------------------------------------------------------------------
def spearman(a, b):
    def ranks(v):
        o = sorted(range(len(v)), key=lambda i: v[i])
        r = [0.0] * len(v)
        i = 0
        while i < len(o):
            j = i
            while j + 1 < len(o) and v[o[j + 1]] == v[o[i]]:
                j += 1
            for k in range(i, j + 1):
                r[o[k]] = (i + j) / 2.0
            i = j + 1
        return r
    ra, rb = ranks(a), ranks(b)
    n = len(a)
    ma, mb = sum(ra) / n, sum(rb) / n
    num = sum((x - ma) * (y - mb) for x, y in zip(ra, rb))
    den = math.sqrt(sum((x - ma) ** 2 for x in ra) * sum((y - mb) ** 2 for y in rb))
    return num / den if den > 0 else 0.0


def _y_of(scale, w_ref, d):
    if scale == "logit":
        return logit(w_ref + d) - logit(w_ref)
    return d


def _w_of(scale, w_ref, d, se):
    if scale == "logit":
        p = _clamp01(w_ref + d)
        s = se / max(p * (1 - p), 1e-4)
    else:
        s = se
    return 1.0 / max(s, 1e-4) ** 2


def fit_x(thetas, deltas, ses, w_ref, n, mu, sd, scales=("prob", "logit"), degs=(1, 2)):
    """X 하나: 척도·차수를 LOO 교차 검증으로 고른 적합 + 판정 재료."""
    zs = [(t - mu) / sd for t in thetas]
    se_f = [max(s, 1.0 / max(1, n)) for s in ses]
    best = None
    for scale in scales:
        for deg in degs:
            if len(thetas) < deg + 2:
                continue
            ys = [_y_of(scale, w_ref, d) for d in deltas]
            ws = [_w_of(scale, w_ref, d, s) for d, s in zip(deltas, se_f)]
            full = wls(zs, ys, ws, deg)
            if full is None:
                continue
            errs = []
            for i in range(len(zs)):
                sub = wls(zs[:i] + zs[i + 1:], ys[:i] + ys[i + 1:], ws[:i] + ws[i + 1:], deg)
                if sub is None:
                    errs = None
                    break
                sx = {"scale": scale, "coef": sub[0], "mu": mu, "sd": sd, "w_ref": w_ref}
                errs.append(delta_from(sx, thetas[i]) - deltas[i])
            if errs is None:
                continue
            cv = math.sqrt(sum(e * e for e in errs) / len(errs))
            key = (round(cv, 12), deg, 0 if scale == "prob" else 1)   # 동점이면 단순한 쪽
            if best is None or key < best[0]:
                best = (key, {"scale": scale, "deg": deg, "coef": full[0], "cov": full[1], "cv": cv})
    if best is None:
        return None
    sx = dict(best[1], mu=mu, sd=sd, w_ref=w_ref)
    mean_se = sum(ses) / len(ses)
    z = [abs(d) / s if s > 0 else (0.0 if d == 0 else float("inf")) for d, s in zip(deltas, se_f)]
    sx["mean_se"] = mean_se
    sx["max_z"] = max(z)
    sx["rho"] = spearman(thetas, deltas)
    sx["trust_thr"] = max(TRUST, 2 * mean_se)
    sx["caution_thr"] = max(CAUTION, 2 * mean_se)
    sx["status"], sx["reason"] = judge_x(sx)
    return sx


def judge_x(sx):
    if sx["w_ref"] < SAT_LO or sx["w_ref"] > SAT_HI:
        return "포화", f"기준 승률 {sx['w_ref'] * 100:.1f}% (3% 미만·97% 초과)"
    if sx["max_z"] < 1:
        return "효과 미검출", "격자 전 구간에서 |z| < 1 — 노이즈와 구분되지 않음 (0 이라고 단정하지 않음)"
    if abs(sx["rho"]) < 0.9:
        return "근사 불가", f"비단조 (스피어만 {sx['rho']:.2f})"
    if sx["cv"] > sx["caution_thr"]:
        return "근사 불가", f"교차 검증 오차 {sx['cv'] * 100:.2f}%p > {sx['caution_thr'] * 100:.2f}%p"
    if sx["cv"] > sx["trust_thr"]:
        return "주의", f"교차 검증 오차 {sx['cv'] * 100:.2f}%p"
    return "신뢰", f"교차 검증 오차 {sx['cv'] * 100:.2f}%p"


DRAWABLE = ("신뢰", "주의")


def fit(grid, n, theta0, discrete=False):
    """grid = {x: [(θ, Δ, se, w_base), ...]} → 모델 dict (저장 형식).
    discrete=True 면 정수 θ 별 Δ 표 (몬스터 기본 힘)."""
    xs = sorted(grid)
    thetas = sorted({t for x in xs for t, *_ in grid[x]})
    mu = sum(thetas) / len(thetas)
    sd = (max(thetas) - min(thetas)) / 2.0 or 1.0
    per_x = {}
    for x in xs:
        rows = sorted(grid[x])
        ts = [r[0] for r in rows]
        ds = [r[1] for r in rows]
        ss = [r[2] for r in rows]
        w_ref = sum(r[3] for r in rows) / len(rows)
        if discrete:
            mean_se = sum(ss) / len(ss)
            zmax = max((abs(d) / s if s > 0 else (0 if d == 0 else 99)) for d, s in zip(ds, ss))
            sx = {"table": {str(int(t)): [d, s] for t, d, s in zip(ts, ds, ss)}, "w_ref": w_ref, "mean_se": mean_se,
                  "max_z": zmax}
            sx["status"], sx["reason"] = (("포화", "기준 승률 포화") if (w_ref < SAT_LO or w_ref > SAT_HI) else
                                          ("효과 미검출", "|z| < 1") if zmax < 1 else ("신뢰", "학습한 정수 값의 실제 Δ"))
        else:
            sx = fit_x(ts, ds, ss, w_ref, n, mu, sd)
            if sx is None:
                sx = {"status": "근사 불가", "reason": "적합 실패", "w_ref": w_ref}
        sx["points"] = [[t, d, s] for t, d, s in zip(ts, ds, ss)]
        per_x[str(x)] = sx
    usable = [s for s in per_x.values() if s["status"] != "포화"]
    if usable and all(s["status"] == "효과 미검출" for s in usable):
        overall = "효과 미검출"
    elif any(s["status"] in DRAWABLE for s in usable):
        overall = "주의" if any(s["status"] == "주의" for s in usable) or any(s["status"] == "근사 불가" for s in usable) else "신뢰"
    else:
        overall = "근사 불가"
    return {"version": VERSION, "discrete": discrete, "thetas": thetas, "theta0": theta0, "lo": min(thetas),
            "hi": max(thetas), "mu": mu, "sd": sd, "n": n, "x": {str(x): per_x[str(x)] for x in xs},
            "status": overall, "ok": overall in DRAWABLE}


# ---------------------------------------------------------------------------
# 예측 (파이썬 — JS 와 같은 식)
# ---------------------------------------------------------------------------
def delta_hat(model, x, theta):
    """Δ̂(X; θ) 또는 None(거절). 반환 (값, 사유)."""
    sx = model["x"].get(str(x))
    if sx is None:
        return None, "학습하지 않은 X"
    if model["discrete"]:
        if theta != int(theta) or str(int(theta)) not in sx["table"]:
            return None, "학습하지 않은 값 (정수 격자만)"
        return sx["table"][str(int(theta))][0], None
    if theta < model["lo"] - 1e-12 or theta > model["hi"] + 1e-12:
        return None, "학습 범위 밖 (외삽 금지)"
    if sx["status"] not in DRAWABLE:
        return None, sx["status"] + ": " + sx.get("reason", "")
    return delta_from(sx, theta), None


def predict(model, x, theta, anchor=None, theta_anchor=None):
    """앵커 예측. anchor = 화면의 실제 곡선 값 p_실제(X) (θ_anchor 로 계산된 것). 없으면 w_ref + Δ̂.
    반환 dict {p, band, no_anchor} 또는 {reject}."""
    d1, why = delta_hat(model, x, theta)
    if d1 is None:
        return {"reject": why}
    sx = model["x"][str(x)]
    if anchor is not None and theta_anchor is not None:
        d0, why0 = delta_hat(model, x, theta_anchor)
        if d0 is None:
            return {"reject": "앵커 값이 학습 범위 밖: " + why0}
        p = anchor + (d1 - d0)
        no_anchor = False
    else:
        p = sx["w_ref"] + d1
        no_anchor = True
    p = min(1.0, max(0.0, p))
    return {"p": p, "band": band(model, x, theta), "no_anchor": no_anchor, "status": sx["status"]}


def band(model, x, theta):
    """근사 범위 반폭 = √(계수 오차² + 교차 검증 오차²) (prob 척도). 실제 CI 와 다르다."""
    sx = model["x"][str(x)]
    if model["discrete"]:
        return 1.96 * sx["table"][str(int(theta))][1]
    v = _pred_var_eta(sx, theta)
    g = _dprob_deta(sx, theta)
    return math.sqrt(v * g * g + sx["cv"] * sx["cv"])


def marginal(model, x, theta):
    """한계효과 m = ∂Δ̂/∂θ (%p 가 아니라 prob/단위) 와 표준오차. 이산이면 None."""
    sx = model["x"].get(str(x))
    if model["discrete"] or sx is None or "coef" not in sx:
        return None
    g = _dprob_deta(sx, theta)
    m = _deta_dtheta(sx, theta) * g
    z = (theta - sx["mu"]) / sx["sd"]
    gr = [0.0] + [k * z ** (k - 1) / sx["sd"] for k in range(1, len(sx["coef"]))]
    v = 0.0
    for i in range(len(gr)):
        for j in range(len(gr)):
            v = v + gr[i] * (sx["cov"][i][j] if sx.get("cov") else 0.0) * gr[j]
    # 계수 오차 + 교차 검증 오차를 기울기로 환산한 것 (모형 선택 오차, 격자 폭의 절반당 cv)
    cvs = 2.0 * sx["cv"] / max(1e-12, model["hi"] - model["lo"])
    se = math.sqrt(max(0.0, v) * g * g + cvs * cvs)
    return {"m": m, "se": se}


def solve_target(model, x, target, steps=60):
    """근사 해: Δ̂(X; θ) = target 인 θ (학습 범위 안, 이분 탐색). 없으면 None. 저장하지 않는다 (F10.7)."""
    if model["discrete"]:
        best = None
        for t in model["thetas"]:
            d, _ = delta_hat(model, x, t)
            if d is not None and (best is None or abs(d - target) < abs(best[1] - target)):
                best = (t, d)
        return best[0] if best and abs(best[1] - target) <= 0.01 else None
    lo, hi = model["lo"], model["hi"]
    f_lo, w1 = delta_hat(model, x, lo)
    f_hi, w2 = delta_hat(model, x, hi)
    if f_lo is None or f_hi is None:
        return None
    if (f_lo - target) * (f_hi - target) > 0:
        return None
    for _ in range(steps):
        mid = (lo + hi) / 2.0
        fm, _ = delta_hat(model, x, mid)
        if (f_lo - target) * (fm - target) <= 0:
            hi, f_hi = mid, fm
        else:
            lo, f_lo = mid, fm
    return (lo + hi) / 2.0


def interp(xs, ys, x):
    """구간 선형 보간 (몬스터 단독 지표 모델). 범위 밖이면 None."""
    if x < xs[0] - 1e-12 or x > xs[-1] + 1e-12:
        return None
    for i in range(len(xs) - 1):
        if xs[i] <= x <= xs[i + 1]:
            t = (x - xs[i]) / (xs[i + 1] - xs[i]) if xs[i + 1] != xs[i] else 0.0
            return ys[i] + t * (ys[i + 1] - ys[i])
    return ys[-1]


# ---------------------------------------------------------------------------
# 격자
# ---------------------------------------------------------------------------
def theta_grid(orig, lo, hi, k=6, integer=False, mode="fantasy"):
    """Q32: 원본값의 0~2배와 스키마 범위의 교집합 (몬스터 체력: 0.5~2배, Q37). 정수형은 정수만."""
    if mode == "monster_hp":
        a, b = 0.5 * orig, 2.0 * orig
    else:
        a, b = sorted((0.0, 2.0 * orig)) if orig != 0 else (lo, hi)
    a, b = max(a, lo), min(b, hi)
    if b < a:
        a, b = lo, hi
    pts = [a + (b - a) * i / (k - 1) for i in range(k)] if k > 1 else [a]
    if integer:
        pts = sorted({int(round(p)) for p in pts})
    else:
        pts = sorted({round(p, 6) for p in pts})
    if orig not in pts and a <= orig <= b and len(pts) < k + 1:
        pts = sorted(set(pts) | {orig})
    return pts
