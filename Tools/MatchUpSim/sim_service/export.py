# -*- coding: utf-8 -*-
"""시뮬레이션 데이터 내려받기 (v4.4 F15).

- 점 캐시는 읽기만 한다: 캐시에 없는 점은 새로 계산하지 않고 missing 으로 보고한다 (Engine.ensure 를 부르지 않는다).
- 스트리밍: 행 제너레이터로 쓰고 전체를 메모리에 올리지 않는다 (PointStore.read 는 메모리 캐시에 올리지 않는다).
- CSV: UTF-8 BOM(기본), 쉼표, \\r\\n, 영문 snake_case 헤더, 숫자는 repr 정밀도, 없는 값은 빈칸, 불리언 0/1.
  문자열 열이 = + - @ 탭으로 시작하면 앞에 ' 를 붙인다 (CSV 주입 방지).
- 클라이언트가 보낸 경로는 받지 않는다: 데이터 집합 id 는 레지스트리에서만, 스캔은 scan_id 형식으로만 고른다.
"""
from __future__ import annotations

import hashlib
import io
import json
import os
import secrets
import threading
import time
import zipfile
from datetime import datetime

import matchup_sim as ms

from . import edits as ed
from . import jobs as jb
from . import results as rs
from . import stats as S
from . import workspace as wsp

BOM = b"\xef\xbb\xbf"
BASE = jb.BASE
MAX_ROWS = 5_000_000
MAX_CONCURRENT = 2
TICKET_TTL = 60.0
BIG_BYTES = 100 * 1024 * 1024
BATCH = 500
_sem = threading.BoundedSemaphore(MAX_CONCURRENT)
_tickets = {}
_tlock = threading.Lock()


class ExportError(ValueError):
    code = 400


class ExportTooBig(ExportError):
    code = 413


class ExportBusy(Exception):
    code = 429


# ---------------------------------------------------------------------------
# 열 정의 (영문 헤더 고정 + 한글 설명)
# ---------------------------------------------------------------------------
CURVE_COLS = [
    ("series", "시리즈: after(수정 후)·before(수정 전 고스트)·scan(저장된 스캔)"), ("fantasy_id", "환상 ID (기준선은 __baseline__)"),
    ("fantasy_name", "환상 이름"), ("grade", "등급"), ("fidelity", "충실도 exact/approx/none"), ("facet", "패싯 값(없으면 빈칸)"),
    ("x_param", "X축 설정 키"), ("x", "X 값"), ("n", "판 수"), ("wins", "클리어한 판 수"), ("win_rate", "승률"),
    ("delta", "기준선 대비 Δ승률(같은 시드 쌍 비교)"), ("delta_se", "Δ 표준오차"), ("delta_ci_lo", "Δ 95% 신뢰구간 하한"),
    ("delta_ci_hi", "Δ 95% 신뢰구간 상한"), ("delta_n", "Δ 계산에 쓴 판 수"), ("mde", "최소 검출 효과"),
    ("flips_up", "기준선은 졌는데 이 환상은 이긴 판"), ("flips_down", "기준선은 이겼는데 이 환상은 진 판"),
    ("mean_reached_floor", "평균 도달 층"), ("mean_fantasies", "평균 보유 환상 수"), ("mean_reach_delta", "평균 도달 층 차이"),
    ("mean_reach_delta_se", "평균 도달 층 차이 표준오차"), ("death_act1_rate", "1막 사망률"), ("death_act2_rate", "2막 사망률"),
    ("death_act3_rate", "3막 사망률"), ("stage", "계산 단계(빈칸)"), ("table_hash", "환상 테이블 해시"), ("data_hash", "데이터 해시"),
    ("cfg_tag", "설정 편집 태그"), ("stale", "1 = 현재 데이터와 다른 기준(옛 데이터)")]
REACH_COLS = [("series", "시리즈"), ("fantasy_id", "환상 ID"), ("facet", "패싯"), ("x", "X 값"), ("floor", "층 번호(1부터)"),
              ("reach_rate", "그 층에 도달한 판의 비율")]
RUNS_COLS = [("arm", "팔: baseline 또는 강제 포함 환상(+로 연결)"), ("fantasy_id", "환상 ID"), ("facet", "패싯"),
             ("x_param", "X축 설정 키"), ("x", "X 값"), ("data_hash", "데이터 해시"),
             ("seed", "시드 문자열 f\"{master_seed}-{run_index}\" — 런 재생(/api/trace)에 그대로 넣을 수 있음"),
             ("run_index", "판 번호(0부터)"), ("win", "클리어 1/0"), ("reached_floor", "도달 층"),
             ("death_act", "사망한 막(클리어면 0)"), ("n_fantasies", "보유 환상 수")]
EDITS_COLS = [("target", "대상 종류: fantasy·monster·pattern·gimmick·cfg·cfg_set"), ("id", "환상/몬스터/패턴 ID"), ("name", "이름"),
              ("effect", "효과 번호(환상)"), ("key", "수치 키"), ("path", "설정 경로(설정 편집)"), ("old", "원래 값"), ("new", "바꾼 값"),
              ("source", "원본연결·시뮬전용·시나리오전용·설정")]
MON_COLS = [("id", "몬스터 ID"), ("name", "이름"), ("act", "막"), ("tier", "등급"), ("hp", "체력"), ("fidelity", "충실도"),
            ("battles", "전투 수"), ("avg_turns", "평균 턴 수"), ("turns_ci_lo", "평균 턴 95% 하한"), ("turns_ci_hi", "평균 턴 95% 상한"),
            ("turn_target", "목표 턴 밴드"), ("turn_verdict", "턴 수 판정"), ("avg_taken", "전투당 받은 피해"),
            ("death_rate_in_battle", "전투 중 사망률"), ("death_share", "전체 사망 중 이 몬스터 비중"), ("timeouts", "시간 초과 수"),
            ("max_hit_avg", "최대 1타 평균"), ("max_hit_max", "최대 1타 최댓값"), ("escapes", "도주 수"),
            ("battle_wins", "이긴 전투 수"), ("battle_win_rate", "조우 시 전투 승률"), ("battle_win_ci_lo", "전투 승률 95% 하한"),
            ("battle_win_ci_hi", "전투 승률 95% 상한"), ("runs_met", "이 몬스터를 만난 런 수"),
            ("run_win_rate_met", "조우한 런 승률"), ("run_win_ci_met_lo", "조우한 런 승률 95% 하한"),
            ("run_win_ci_met_hi", "조우한 런 승률 95% 상한"), ("gimmicks", "기믹"), ("warning", "경고"),
            # v4.5 F16.5: 이상치 대응 열 (기존 열 뒤에 추가 — 기존 CSV 소비자가 깨지지 않는다)
            ("avg_taken_cap", "전투당 체력 한도 받은 피해 평균"), ("taken_p50", "받은 피해 중앙값(로그 눈금 근사 ±5%)"), ("taken_p90", "받은 피해 90% 분위"),
            ("max_hit_p50", "전투 중 최대 1타 중앙값"), ("max_hit_p90", "전투 중 최대 1타 90% 분위"),
            ("overkill_share", "사망 전투 중 받은 피해가 시작 체력의 2배를 넘은 비율"), ("outlier", "이상치 배지 (1 = ⚠)")]
BATTLE_COLS = [("mid", "몬스터 ID"), ("name", "몬스터 이름"), ("category", "표본 분류: death·max_hit·taken·long·short·win·escape·random"),
               ("run", "런 번호(시드 = master_seed-run)"), ("ord", "그 런에서 이 몬스터의 전투 순번(0부터)"), ("act", "막"), ("floor", "층"),
               ("hp0", "전투 시작 체력"), ("hp1", "전투 종료 체력"), ("turns", "턴 수"), ("taken", "받은 피해(원본)"),
               ("taken_cap", "체력 한도 받은 피해"), ("max_hit", "최대 1타"), ("outcome", "결과 win/death/escape/timeout"), ("nfant", "보유 환상 수")]
TURN_COLS = [("t", "턴"), ("intent", "몬스터 행동"), ("pattern", "패턴 키"), ("mon_dmg", "몬스터 피해 굴린 값"), ("mon_dmg_edit", "내가 편집한 값"),
             ("mon_dmg_eff", "피해 계산에 쓰인 유효 값"), ("hits", "몬스터 타수 굴린 값"), ("hits_edit", "편집한 타수"), ("base", "내 기본 피해 굴린 값"),
             ("base_edit", "편집한 기본 피해"), ("p_hits", "내 타수"), ("moves", "이동 한도"), ("K", "쓸모 있게 쓴 이동 수"), ("used", "실제 사용 이동"),
             ("items", "아이템 사용"), ("dealt", "내가 준 피해"), ("mhp", "몬스터 체력(턴 끝)"), ("taken", "내가 받은 피해"),
             ("taken_cap", "체력 한도 받은 피해"), ("over", "체력 한도를 넘은 초과 피해"), ("hp_change", "내 체력 변화"), ("hp", "내 체력(턴 끝)"),
             ("mstr", "몬스터 힘"), ("countdown", "카운트다운"), ("phase", "페이즈"), ("aim", "조준 숫자"), ("special", "접미 숫자"),
             ("notes", "기믹 주석(JSON)"), ("end", "종료 사유"),
             ("calc_json", "턴 피해 분해(JSON, v4.5 F21 — battle_calc 데이터셋에 행으로 펼친 것과 같음)")]
CALC_COLS = [("t", "턴"), ("side", "구분: dealt(내가 준 피해)·taken(내가 받은 피해)"), ("part", "분류: step·hits·extra·over·reduced·ablate·over_ablate"),
             ("n", "분류 안 순번"), ("kind", "단계 종류(move·mult·flat·def·…)·extra 종류"), ("source", "출처: 환상 ID·move·mon:<기믹>·base_roll"),
             ("source_name", "출처 이름"), ("effect_type", "효과 타입"), ("before", "전"), ("after", "후"), ("delta", "증감(제거 시 차이는 delta)"),
             ("over", "초과 기여")]
OWNED_COLS = [("n", "획득 순번"), ("fid", "환상 ID"), ("name", "이름"), ("grade", "등급"), ("floor_act", "획득 막"), ("floor", "획득 층"),
              ("source", "경로"), ("fx", "이 전투에서 효과가 관여한 환상 1/0")]
TEXT_COLS = {"fantasy_name", "name", "gimmicks", "warning", "key", "path", "id", "fantasy_id", "arm", "turn_verdict", "facet", "notes",
             "pattern", "intent", "fid", "mid", "category", "source", "grade", "calc_json", "source_name", "kind", "side", "part", "effect_type"}

DATASETS = {
    "curves": {"title": "곡선 점", "formats": ["csv", "json"], "columns": CURVE_COLS},
    "reach": {"title": "층 도달률", "formats": ["csv"], "columns": REACH_COLS},
    "edits": {"title": "변경 목록", "formats": ["csv", "json"], "columns": EDITS_COLS},
    "monsters": {"title": "몬스터별 지표", "formats": ["csv", "json"], "columns": MON_COLS},
    "battles": {"title": "몬스터 전투 표본 목록", "formats": ["csv", "json"], "columns": BATTLE_COLS},
    "battle_log": {"title": "선택한 전투의 턴 로그", "formats": ["csv", "json", "zip"], "columns": TURN_COLS},
    "battle_calc": {"title": "선택한 전투의 턴 피해 분해(단계·출처)", "formats": ["csv", "json"], "columns": CALC_COLS},
    "runs": {"title": "판별 원자료", "formats": ["csv", "ndjson"], "columns": RUNS_COLS},
    "scans": {"title": "저장된 스캔(원본 그대로)", "formats": ["json", "csv"], "columns": []},
    "workspace": {"title": "작업 공간", "formats": ["json"], "columns": []},
    "results": {"title": "저장된 작업 결과", "formats": ["json"], "columns": []},
    "bundle": {"title": "묶음(zip)", "formats": ["zip"], "columns": []},
}
CLIENT_ONLY = ("ranking", "monster_hp")        # 뷰어가 화면 표에서 직접 만든다 (서버에 목록으로만 알림)


def catalog():
    out = [{"id": k, "title": v["title"], "formats": v["formats"], "client_only": False,
            "columns": [{"name": c, "desc": d} for c, d in v["columns"]],
            "params_schema": {"scope": {"fids": "환상 ID 목록 또는 'all'", "x": "숫자·'all'(생략=가운데 X)",
                                        "series": "after·before·scan 목록", "n": "판 수 상한(선택)"}} if k in ("curves", "reach", "runs") else {}}
           for k, v in DATASETS.items()]
    out += [{"id": "ranking", "title": "랭킹 표(현재 정렬·필터)", "formats": ["csv"], "client_only": True, "columns": [], "params_schema": {}},
            {"id": "monster_hp", "title": "몬스터 체력 리포트", "formats": ["csv"], "client_only": True, "columns": [], "params_schema": {}}]
    return {"datasets": out, "limits": {"max_rows": MAX_ROWS, "max_concurrent": MAX_CONCURRENT, "ticket_ttl_s": TICKET_TTL}}


# ---------------------------------------------------------------------------
# CSV / JSON 인코딩
# ---------------------------------------------------------------------------
def cell(v, text=False):
    if v is None:
        return ""
    if isinstance(v, bool):
        return "1" if v else "0"
    if isinstance(v, int):
        return str(v)
    if isinstance(v, float):
        return repr(v)
    s = v if isinstance(v, str) else json.dumps(v, ensure_ascii=False)
    if text and s[:1] in ("=", "+", "-", "@", "\t", "\r"):
        s = "'" + s
    if any(ch in s for ch in ',"\r\n'):
        s = '"' + s.replace('"', '""') + '"'
    return s


def csv_stream(columns, rows, bom=True):
    names = [c for c, _ in columns]
    if bom:
        yield BOM
    yield (",".join(names) + "\r\n").encode("utf-8")
    buf = []
    for r in rows:
        buf.append(",".join(cell(r.get(c), c in TEXT_COLS) for c in names) + "\r\n")
        if len(buf) >= BATCH:
            yield "".join(buf).encode("utf-8")
            buf = []
    if buf:
        yield "".join(buf).encode("utf-8")


def json_stream(meta, rows):
    yield b'{"meta":' + json.dumps(meta, ensure_ascii=False).encode("utf-8") + b',"rows":['
    first = True
    for r in rows:
        yield ((b"" if first else b",") + json.dumps(r, ensure_ascii=False).encode("utf-8"))
        first = False
    yield b"]}"


def ndjson_stream(rows):
    for r in rows:
        yield (json.dumps(r, ensure_ascii=False) + "\n").encode("utf-8")


# ---------------------------------------------------------------------------
# 요청 컨텍스트 (편집 상태 → 설정·해시, 범위)
# ---------------------------------------------------------------------------
class _NullJob:
    cancelled = False

    def emit(self, *a, **k):
        return None


class Ctx:
    def __init__(self, app, body):
        self.app, self.body = app, body or {}
        ws = None

        def pick(k, empty):
            nonlocal ws
            if k in self.body and self.body[k] is not None:
                return self.body[k]
            if ws is None:
                ws = app.workspace.get().get("state") or {}      # 본문이 비어 있으면 작업 공간의 현재 값
            return ws.get(k) or empty
        self.edits, self.cfg_edits, self.cfg_set = pick("edits", []), pick("cfg_edits", []), pick("cfg_set", {})
        self.cfg_after, self.h_after = jb.prepare(app, self.edits, self.cfg_edits, self.cfg_set)
        self.after_hash = jb.dh_of(self.cfg_after, self.h_after)
        self.ss = jb.SeriesSet(app, _NullJob(), app.x_key, app.seed)
        self.ss.add_series("after", self.cfg_after, self.h_after)
        self.ref = getattr(app, "ref", None)
        self.ref_differs = bool(self.ref) and self.ref["data_hash"] != self.after_hash
        if self.ref:
            self.ss.add_series("before", app.cfg_for(self.ref["table_data"], self.ref["monster_data"]), self.ref["table_hash"])
        self.fmeta = {e["id"]: e for e in app.table_data["fantasies"]}
        self.cfg_tag = rs.cfg_tag_of(self.cfg_edits, self.cfg_set)
        self.scope = self._scope()

    def _scope(self):
        a, sc = self.app, (self.body.get("scope") or {})
        fids = sc.get("fids", [])
        if fids == "all":
            fids = list(a.table_ids)
        if not isinstance(fids, list) or any(f not in self.fmeta for f in fids):
            raise ExportError("scope.fids: 알 수 없는 환상 ID")
        x = sc.get("x")
        if x == "all":
            xs = list(a.x_values)
        else:
            if x is None:
                x = a.x_values[len(a.x_values) // 2]
            hit = [v for v in a.x_values if isinstance(x, (int, float)) and abs(v - x) < 1e-9]
            if not hit:
                raise ExportError("scope.x: X 격자에 없는 값")
            xs = hit
        series = sc.get("series") or ["after"]
        if not isinstance(series, list) or any(s not in ("after", "before", "scan") for s in series):
            raise ExportError("scope.series: after·before·scan 만 가능")
        n = sc.get("n")
        if n is not None and (not isinstance(n, int) or n <= 0):
            raise ExportError("scope.n: 양의 정수")
        return {"fids": fids, "x": xs, "series": series, "n": n, "include_baseline": sc.get("include_baseline", True) is not False,
                "facet": sc.get("facet")}

    # --- 점 계획: 캐시에 있는 점과 없는 점
    def plan(self):
        sc = self.scope
        present, missing = [], []
        for series in sc["series"]:
            if series == "scan" or (series == "before" and not self.ref):
                continue
            for x in sc["x"]:
                ids = ([BASE] if sc["include_baseline"] else []) + sc["fids"]
                for fid in ids:
                    it = (series, fid, x)
                    key = self.ss.req(*it)["key"]
                    (present if self.app.store.exists(key) else missing).append((it, key))
        return present, missing

    def name_of(self, fid):
        if fid == BASE:
            return "기준선", "", ""
        e = self.fmeta.get(fid, {})
        return e.get("name", fid), e.get("grade", ""), e.get("fidelity", "")

    def scan_points(self):
        """저장된 스캔(scan 시리즈)의 점: [(fid, point)] — 선택한 환상·X 만."""
        sc = self.scope
        data = self.app.scan
        if not data or "scan" not in sc["series"]:
            return []
        ids = ([BASE] if sc["include_baseline"] else []) + sc["fids"]
        out = []
        for fid in ids:
            pts = (data.get("baseline") or {}).get("points") if fid == BASE else ((data.get("curves") or {}).get(fid) or {}).get("points")
            for p in pts or []:
                if any(abs(p["x"] - x) < 1e-9 for x in sc["x"]):
                    out.append((fid, p))
        return out


def _meta(app, ctx, dataset, missing, rows=None):
    m = app.base_cfg["monsters"]
    return {"generated_at": datetime.now().isoformat(timespec="seconds"), "dataset": dataset, "build": app.build,
            "sim_version": ms.SIM_VERSION, "master_seed": app.seed, "x_param": app.x_key, "x_values": app.x_values,
            "effect_mode": (app.base_cfg.get("fantasy") or {}).get("effect_mode"), "damage_model": m.get("damage_model"),
            "monster_model": m.get("model"), "monster_gimmicks": m.get("gimmicks"), "base_data_hash": app.data_hash,
            "view_data_hash": ctx.after_hash if ctx else app.data_hash,
            "edits": {"edits": len(ctx.edits), "cfg_edits": len(ctx.cfg_edits), "cfg_set": len(ctx.cfg_set)} if ctx else None,
            "scope": ctx.scope if ctx else None, "rows": rows, "missing_count": len(missing),
            "missing": [{"series": it[0], "fantasy_id": it[1], "x": it[2]} for it, _ in missing[:200]]}


# ---------------------------------------------------------------------------
# 데이터 집합별 행 생성
# ---------------------------------------------------------------------------
def _point_row(ctx, series, fid, p):
    if series == "before":
        stale = ctx.ref_differs
    elif series == "scan":
        stale = ((ctx.app.scan or {}).get("meta") or {}).get("data_hash") != ctx.app.data_hash
    else:
        stale = False
    name, grade, fid_q = ctx.name_of(fid)
    ci = p.get("delta_ci") or [None, None]
    da = p.get("death_by_act") or [None, None, None]
    return {"series": series, "fantasy_id": fid, "fantasy_name": name, "grade": grade, "fidelity": fid_q, "facet": "",
            "x_param": ctx.app.x_key, "x": p.get("x"), "n": p.get("n"), "wins": p.get("wins"), "win_rate": p.get("win_rate"),
            "delta": p.get("delta"), "delta_se": p.get("delta_se"), "delta_ci_lo": ci[0], "delta_ci_hi": ci[1],
            "delta_n": p.get("delta_n"), "mde": p.get("mde"), "flips_up": p.get("flips_up"), "flips_down": p.get("flips_down"),
            "mean_reached_floor": p.get("mean_reached_floor"), "mean_fantasies": p.get("mean_fantasies"),
            "mean_reach_delta": p.get("mean_reach_delta"), "mean_reach_delta_se": p.get("mean_reach_delta_se"),
            "death_act1_rate": da[0], "death_act2_rate": da[1], "death_act3_rate": da[2], "stage": "",
            "table_hash": p.get("table_hash"), "data_hash": p.get("data_hash"),
            "cfg_tag": ctx.cfg_tag if series == "after" else "", "stale": 1 if stale else 0}


def _iter_points(ctx, present):
    """(series, fid, x, point 통계) 를 하나씩 — 기준선 레코드는 (series, x) 마다 한 번만 읽는다."""
    store = ctx.app.store
    cap = ctx.scope["n"]
    base_cache = {}

    def base_rec(series, x):
        k = (series, x)
        if k not in base_cache:
            key = ctx.ss.req(series, BASE, x)["key"]
            base_cache[k] = store.read(key)
        return base_cache[k]
    for (series, fid, x), key in present:
        rec = store.read(key)
        if rec is None or rec["n"] <= 0:
            continue
        n = min(rec["n"], cap) if cap else rec["n"]
        b = base_rec(series, x) if fid != BASE else None
        if b is not None:
            n = min(n, b["n"])
        p = S.point_stats(rec, x, n)
        if b is not None and n > 0:
            p.update(S.paired_delta(rec, b, n))
        yield series, fid, x, p, rec, n


def rows_curves(ctx, present):
    for series, fid, x, p, rec, n in _iter_points(ctx, present):
        yield _point_row(ctx, series, fid, p)
    for fid, p in ctx.scan_points():
        yield _point_row(ctx, "scan", fid, p)


def rows_reach(ctx, present):
    for series, fid, x, p, rec, n in _iter_points(ctx, present):
        for f, v in enumerate(p["reach_rate"], start=1):
            yield {"series": series, "fantasy_id": fid, "facet": "", "x": x, "floor": f, "reach_rate": v}
    for fid, p in ctx.scan_points():
        for f, v in enumerate(p.get("reach_rate") or [], start=1):
            yield {"series": "scan", "fantasy_id": fid, "facet": "", "x": p["x"], "floor": f, "reach_rate": v}


def rows_runs(ctx, present):
    app = ctx.app
    for (series, fid, x), key in present:
        rec = app.store.read(key)
        if rec is None:
            continue
        n = min(rec["n"], ctx.scope["n"]) if ctx.scope["n"] else rec["n"]
        arm = "+".join(rec.get("fids") or []) or "baseline"
        for i in range(n):
            yield {"arm": arm, "fantasy_id": fid, "facet": "", "x_param": app.x_key, "x": x,
                   "data_hash": rec.get("data_hash"), "seed": f"{app.seed}-{i}", "run_index": i,
                   "win": rec["wins"][i] == "1", "reached_floor": rec["reached"][i], "death_act": rec["death_act"][i],
                   "n_fantasies": rec["nfant"][i]}


def rows_edits(ctx):
    app = ctx.app
    mons = {m["id"]: m for m in (app.monster_data or {}).get("monsters", [])}
    f_edits = [e for e in ctx.edits if e.get("target", "fantasy") == "fantasy"]
    src, ov, scen, _ = app.wb.classify(app.table_data, f_edits)
    kind = {}
    for lst, lab in ((src, "원본연결"), (ov, "시뮬전용"), (scen, "시나리오전용")):
        for e in lst:
            kind[(e.get("fid"), e.get("effect"), e.get("key"))] = lab
    for e in ctx.edits:
        t = e.get("target", "fantasy")
        if t == "fantasy":
            yield {"target": t, "id": e["fid"], "name": ctx.name_of(e["fid"])[0], "effect": e.get("effect"), "key": e.get("key"),
                   "path": "", "old": e.get("old"), "new": e.get("new"), "source": kind.get((e["fid"], e.get("effect"), e.get("key")), "시뮬전용")}
        else:
            mid = e.get("mid") or e.get("pid")
            m = mons.get(e.get("mid"))
            try:
                ok, _prob = app.wb.monster_src_edits(app.monster_data, [e])
                lab = "원본연결" if ok else "시나리오전용"
            except Exception:  # noqa: BLE001
                lab = "시나리오전용"
            yield {"target": t, "id": mid, "name": (m or {}).get("name", mid), "effect": e.get("step", e.get("gi")), "key": e.get("key"),
                   "path": "", "old": e.get("old"), "new": e.get("new"), "source": lab}
    for c in ctx.cfg_edits:
        yield {"target": "cfg", "id": "", "name": "", "effect": "", "key": "", "path": c.get("path"), "old": c.get("old"),
               "new": c.get("new"), "source": "설정"}
    for k, v in ctx.cfg_set.items():
        yield {"target": "cfg_set", "id": "", "name": "", "effect": "", "key": "", "path": k, "old": "", "new": v, "source": "설정"}


def monster_data(app, ctx):
    """몬스터별 지표 원본 데이터(저장된 서버 결과 → 없으면 CLI monster_metrics.json) 와 출처."""
    data, src = None, None
    try:
        xs = ctx.scope["x"]
        cfg, h, mdata, seed, ckey, dh = jb.monster_metrics_setup(app, {"edits": ctx.edits, "cfg_edits": ctx.cfg_edits, "cfg_set": ctx.cfg_set,
                                                                      "x": xs[0] if len(xs) == 1 else None})
        saved = rs.mon_load(app.results, dh, seed, ckey)
        if saved:
            data, src = saved["data"], "server_saved"
    except ValueError:
        pass
    if data is None:
        p = os.path.join(app.results, "monster_metrics.json")
        try:
            with open(p, encoding="utf-8") as fp:
                data, src = json.load(fp), "monster_metrics.json(스캔 시점 값 — 현재 편집 미반영)"
        except (OSError, ValueError):
            data, src = {"monsters": []}, "없음"
    return data, src


def battle_rows(app, ctx):
    data, src = monster_data(app, ctx)
    rows = []
    for m in data.get("monsters", []):
        for cat, lst in (m.get("samples") or {}).items():
            for s_ in lst:
                rows.append({"mid": m["id"], "name": m.get("name"), "category": cat, **{k: s_.get(k) for k, _ in BATTLE_COLS[3:]}})
    return rows, src, data.get("meta")


def monster_rows(app, ctx):
    """몬스터별 지표: 지금 상태로 저장된 결과 → 없으면 CLI 가 만든 monster_metrics.json."""
    data, src = monster_data(app, ctx)
    rows = []
    for m in data.get("monsters", []):
        ci = m.get("turns_ci") or [None, None]
        bci = m.get("battle_win_ci") or [None, None]
        rci = m.get("run_win_ci_met") or [None, None]
        rows.append({**{k: m.get(k) for k, _ in MON_COLS}, "turns_ci_lo": ci[0], "turns_ci_hi": ci[1],
                     "turn_target": "-".join(str(v) for v in (m.get("turn_target") or [])), "battle_win_ci_lo": bci[0],
                     "battle_win_ci_hi": bci[1], "run_win_ci_met_lo": rci[0], "run_win_ci_met_hi": rci[1],
                     "gimmicks": ", ".join(m.get("gimmicks") or [])})
    return rows, src, data.get("meta")


# ---------------------------------------------------------------------------
# 한 데이터 집합 → Export (파일명·헤더 정보·바이트 청크)
# ---------------------------------------------------------------------------
class Export:
    def __init__(self, filename, ctype, meta, chunks, rows=None, missing=0):
        self.filename, self.ctype, self.meta, self.chunks, self.rows, self.missing = filename, ctype, meta, chunks, rows, missing


def _fname(dataset, h, ext):
    return f"matchup_{dataset}_{(h or 'nohash')[:8]}_{datetime.now():%Y%m%d-%H%M%S}.{ext}"


def _fmt(dataset, body):
    fm = body.get("format") or DATASETS[dataset]["formats"][0]
    if fm not in DATASETS[dataset]["formats"]:
        raise ExportError(f"{dataset}: 지원하지 않는 형식 {fm!r} (가능: {', '.join(DATASETS[dataset]['formats'])})")
    return fm


def _bom(body):
    return body.get("bom", True) is not False


def build(app, dataset, body):
    """데이터 집합을 만든다. 행 수 상한을 넘으면 ExportTooBig. 계산하지 않는다."""
    if dataset not in DATASETS:
        raise ExportError("알 수 없는 데이터 집합")
    body = body or {}
    if dataset == "bundle":                      # 묶음은 항상 zip — 뷰어가 보내는 format(csv/json)은 안의 파일 형식 선택일 뿐
        return _bundle(app, body)
    fm = _fmt(dataset, body)
    if dataset == "workspace":
        w = app.workspace_get()
        if body.get("scenario"):
            w["scenario"] = ed.load_scenario(app.scen_dir, body["scenario"])
        data = json.dumps(w, ensure_ascii=False, indent=1).encode("utf-8")
        return Export(_fname(dataset, app.data_hash, "json"), "application/json; charset=utf-8", _meta(app, None, dataset, []),
                      iter([data]), 1)
    if dataset == "results":
        sc = body.get("scope") or {}
        d = rs.get(app.results, str(sc.get("kind") or ""), str(sc.get("key") or ""))
        return Export(_fname(dataset, d.get("data_hash"), "json"), "application/json; charset=utf-8", _meta(app, None, dataset, []),
                      iter([json.dumps(d, ensure_ascii=False).encode("utf-8")]), 1)
    if dataset == "scans":
        sc = body.get("scope") or {}
        if fm == "csv":
            p = os.path.join(app.results, "fantasy_curves.csv")
            if not os.path.isfile(p):
                raise ExportError("fantasy_curves.csv 없음")
            return Export(_fname(dataset, app.data_hash, "csv"), "text/csv; charset=utf-8", _meta(app, None, dataset, []), _file_chunks(p), 1)
        p = rs.scan_path(app.results, str(sc.get("scan_id") or ""))
        return Export(os.path.basename(p), "application/json; charset=utf-8", _meta(app, None, dataset, []), _file_chunks(p), 1)
    ctx = Ctx(app, body)
    if dataset == "edits":
        rows = list(rows_edits(ctx))
        meta = _meta(app, ctx, dataset, [], len(rows))
        return _table(dataset, fm, ctx.after_hash, DATASETS[dataset]["columns"], iter(rows), meta, len(rows), 0, _bom(body))
    if dataset == "battles":
        rows, src, mm = battle_rows(app, ctx)
        meta = {**_meta(app, ctx, dataset, [], len(rows)), "source": src, "monster_meta": mm}
        return _table(dataset, fm, ctx.after_hash, BATTLE_COLS, iter(rows), meta, len(rows), 0, _bom(body))
    if dataset == "battle_log":
        return _battle_log(app, ctx, body, fm)
    if dataset == "battle_calc":
        return _battle_calc(app, ctx, body, fm)
    if dataset == "monsters":
        rows, src, mm = monster_rows(app, ctx)
        meta = {**_meta(app, ctx, dataset, [], len(rows)), "source": src, "monster_meta": mm}
        return _table(dataset, fm, ctx.after_hash, MON_COLS, iter(rows), meta, len(rows), 0, _bom(body))
    present, missing = ctx.plan()
    scan_pts = ctx.scan_points()
    if dataset == "curves":
        est = len(present) + len(scan_pts)
        gen = rows_curves(ctx, present)
    elif dataset == "reach":
        est = len(present) * ms.TOTAL_FLOORS + sum(len(p.get("reach_rate") or []) for _, p in scan_pts)
        gen = rows_reach(ctx, present)
    else:
        est = 0
        for _, key in present:
            rec = app.store.read(key)
            if rec:
                est += min(rec["n"], ctx.scope["n"]) if ctx.scope["n"] else rec["n"]
        gen = rows_runs(ctx, present)
    if est > MAX_ROWS:
        raise ExportTooBig(f"행이 {est:,}개로 한 요청 상한 {MAX_ROWS:,}개를 넘음 — 범위(scope)를 줄이세요")
    meta = _meta(app, ctx, dataset, missing, est)
    return _table(dataset, fm, ctx.after_hash, DATASETS[dataset]["columns"], gen, meta, est, len(missing), _bom(body))


def _table(dataset, fm, h, columns, rows, meta, nrows, nmissing, bom):
    if fm == "csv":
        return Export(_fname(dataset, h, "csv"), "text/csv; charset=utf-8", meta, csv_stream(columns, rows, bom), nrows, nmissing)
    if fm == "ndjson":
        return Export(_fname(dataset, h, "ndjson"), "application/x-ndjson; charset=utf-8", meta, ndjson_stream(rows), nrows, nmissing)
    return Export(_fname(dataset, h, "json"), "application/json; charset=utf-8", meta, json_stream(meta, rows), nrows, nmissing)


def _battle_log(app, ctx, body, fm):
    """선택한 전투의 턴 로그 + 보유 환상. csv = 턴 로그, zip = 턴 로그 + 보유 환상 + meta, json = 전체 재생 결과."""
    sc = body.get("scope") or {}
    res = app.monster_log({"mid": sc.get("mid"), "seed": sc.get("seed") or "mon1", "run": sc.get("run"), "ord": sc.get("ord"),
                           "x": sc.get("x_value"), "edits": ctx.edits, "cfg_edits": ctx.cfg_edits, "cfg_set": ctx.cfg_set})
    meta = {**_meta(app, ctx, "battle_log", [], len(res["turns"])), "mid": res["mid"], "seed": res["seed"], "replay_match": res["replay_match"]}
    turn_rows = [{**{k: v for k, v in t.items() if k != "calc"}, "notes": json.dumps(t.get("notes") or [], ensure_ascii=False),
                  "calc_json": json.dumps(t.get("calc"), ensure_ascii=False, separators=(",", ":")) if t.get("calc") else ""} for t in res["turns"]]
    owned_rows = [{**o, "floor_act": (o.get("floor") or [None, None])[0], "floor": (o.get("floor") or [None, None])[1]} for o in res["owned"]]
    h = ctx.after_hash
    if fm == "json":
        return Export(_fname("battle_log", h, "json"), "application/json; charset=utf-8", meta,
                      iter([json.dumps(res, ensure_ascii=False).encode("utf-8")]), len(turn_rows))
    if fm == "csv":
        return _table("battle_log", "csv", h, TURN_COLS, iter(turn_rows), meta, len(turn_rows), 0, _bom(body))
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("turns.csv", b"".join(csv_stream(TURN_COLS, iter(turn_rows), _bom(body))))
        zf.writestr("owned.csv", b"".join(csv_stream(OWNED_COLS, iter(owned_rows), _bom(body))))
        zf.writestr("calc.csv", b"".join(csv_stream(CALC_COLS, iter(calc_rows(app, res)), _bom(body))))
        zf.writestr("battle.json", json.dumps({k: res[k] for k in ("mid", "seed", "run", "battle", "items", "replay_match", "data_hash")}, ensure_ascii=False, indent=1))
        zf.writestr("meta.json", json.dumps(meta, ensure_ascii=False, indent=1))
    return Export(_fname("battle_log", h, "zip"), "application/zip", meta, iter([buf.getvalue()]), len(turn_rows))


def calc_rows(app, res):
    """턴 피해 분해를 행으로 펼친다 (F21 battle_calc): 단계·타수·extra·초과 기여·초과 감소·제거 시 차이."""
    names = {e["id"]: e.get("name", e["id"]) for e in (app.table_data or {}).get("fantasies", [])}

    def srcs(src):
        if src.get("kind") == "fx":
            return [(f[0], names.get(f[0], f[0])) for f in src.get("fids") or ()] or [("", "")]
        k = src.get("kind", "")
        return [("mon:" + src.get("sim", "") if k == "monster" else k, k)]
    for t in res["turns"]:
        c = t.get("calc")
        if not c or "error" in c:
            continue
        for side in ("dealt", "taken"):
            s = c[side]
            yield {"t": t["t"], "side": side, "part": "step", "n": 0, "kind": "base", "source": "base_roll", "source_name": "굴림", "after": s.get("base"), "delta": ""}
            for i, st in enumerate(s["steps"], 1):
                for sid, sn in srcs(st["src"]):
                    yield {"t": t["t"], "side": side, "part": "step", "n": i, "kind": st["k"], "source": sid, "source_name": sn, "effect_type": st["src"].get("type", ""),
                           "before": st["from"], "after": st["to"], "delta": st["to"] - st["from"]}
            for i, st in enumerate(s["hits"].get("steps", ()), 1):
                for sid, sn in srcs(st["src"]):
                    yield {"t": t["t"], "side": side, "part": "hits", "n": i, "kind": "hits", "source": sid, "source_name": sn, "effect_type": st["src"].get("type", ""),
                           "before": st["from"], "after": st["to"], "delta": st["to"] - st["from"]}
            for i, e in enumerate(s["extra"], 1):
                for sid, sn in (srcs(e["src"]) if e.get("src") else [("", "")]):
                    yield {"t": t["t"], "side": side, "part": "extra", "n": i, "kind": e["k"], "source": sid, "source_name": sn or e.get("label", ""), "delta": e["amount"]}
            for i, b in enumerate(s["over"]["by"], 1):
                yield {"t": t["t"], "side": side, "part": "over", "n": i, "kind": "over", "source": b["src"], "source_name": names.get(b["src"], b["src"]), "over": b["n"]}
            for i, b in enumerate(s["over"]["reduced"], 1):
                yield {"t": t["t"], "side": side, "part": "reduced", "n": i, "kind": "over_reduced", "source": b["src"], "source_name": names.get(b["src"], b["src"]), "over": -b["n"]}
            for i, a in enumerate(s["ablate"], 1):
                yield {"t": t["t"], "side": side, "part": "ablate", "n": i, "kind": "ablate", "source": a["src"], "source_name": names.get(a["src"], a["src"]), "before": a["without"], "after": s["total"], "delta": a["delta"]}
            for i, a in enumerate(s["over"]["ablate"], 1):
                yield {"t": t["t"], "side": side, "part": "over_ablate", "n": i, "kind": "ablate", "source": a["src"], "source_name": names.get(a["src"], a["src"]), "delta": a["delta"], "over": s["over"]["n"]}


def _battle_calc(app, ctx, body, fm):
    sc = body.get("scope") or {}
    res = app.monster_log({"mid": sc.get("mid"), "seed": sc.get("seed") or "mon1", "run": sc.get("run"), "ord": sc.get("ord"),
                           "x": sc.get("x_value"), "edits": ctx.edits, "cfg_edits": ctx.cfg_edits, "cfg_set": ctx.cfg_set})
    rows = list(calc_rows(app, res))
    meta = {**_meta(app, ctx, "battle_calc", [], len(rows)), "mid": res["mid"], "seed": res["seed"], "replay_match": res["replay_match"], "has_calc": res.get("has_calc")}
    return _table("battle_calc", fm, ctx.after_hash, CALC_COLS, iter(rows), meta, len(rows), 0, _bom(body))


def _file_chunks(path, size=1 << 20):
    with open(path, "rb") as fp:
        while True:
            b = fp.read(size)
            if not b:
                break
            yield b


class _Sink:
    """쓰기만 되는 출력 (zipfile 이 비탐색 스트림으로 쓴다). 청크를 모아 두었다가 꺼낸다."""

    def __init__(self):
        self.parts = []

    def write(self, b):
        self.parts.append(bytes(b))
        return len(b)

    def flush(self):
        return None

    def take(self):
        out, self.parts = b"".join(self.parts), []
        return out


def _bundle(app, body):
    ids = body.get("datasets") or ["curves", "edits", "monsters"]
    allowed = [d for d in DATASETS if d not in ("bundle", "workspace", "results", "scans")] + ["workspace"]
    if not isinstance(ids, list) or any(i not in allowed for i in ids):
        raise ExportError(f"bundle.datasets: {', '.join(allowed)} 중에서 고르세요")
    parts = []
    total = 0
    for i in ids:
        want = body.get("format") if body.get("format") in ("csv", "json") else "csv"
        sub = {**body, "format": "json" if i == "workspace" else ("ndjson" if (i == "runs" and want == "json") else ("csv" if i == "reach" else want))}
        sub.pop("datasets", None)
        ex = build(app, i, sub)
        total += ex.rows or 0
        parts.append((i, ex))
    if total > MAX_ROWS:
        raise ExportTooBig(f"묶음의 행이 {total:,}개로 상한 {MAX_ROWS:,}개를 넘음")
    ctx = None
    try:
        ctx = Ctx(app, body)
    except ValueError:
        pass
    missing_total = sum(ex.missing for _, ex in parts)
    meta = {**_meta(app, ctx, "bundle", []), "datasets": ids, "rows": total, "missing_count": missing_total}
    h = ctx.after_hash if ctx else app.data_hash

    def chunks():
        sink = _Sink()
        with zipfile.ZipFile(sink, "w", zipfile.ZIP_DEFLATED) as zf:
            for i, ex in parts:
                with zf.open(ex.filename, "w", force_zip64=True) as w:
                    for ch in ex.chunks:
                        w.write(ch)
                        out = sink.take()
                        if out:
                            yield out
                yield sink.take()
            zf.writestr("meta.json", json.dumps(meta, ensure_ascii=False, indent=1))
            zf.writestr("README.txt", _readme(parts, meta))
            yield sink.take()
        yield sink.take()
    return Export(_fname("bundle", h, "zip"), "application/zip", meta, chunks(), total, missing_total)


def _readme(parts, meta):
    lines = ["Match Up 시뮬레이션 데이터 묶음", "=" * 40, f"생성: {meta['generated_at']}  서버 build {meta['build']}  SIM_VERSION {meta['sim_version']}",
             f"시드 규칙: 판 i 의 시드는 f\"{{master_seed}}-{{i}}\" (master_seed = {meta['master_seed']}). 같은 설정·시드면 결과가 같다.",
             "재현: 뷰어의 '런 재생' 탭(/api/trace)에 runs.csv 의 seed 열 값을 넣으면 그 판의 이벤트를 다시 볼 수 있다.",
             f"기준 data_hash {meta['base_data_hash']} / 화면 data_hash {meta['view_data_hash']}", ""]
    for i, ex in parts:
        lines.append(f"[{ex.filename}] {DATASETS[i]['title']} — {ex.rows}행")
        for c, d in DATASETS[i]["columns"]:
            lines.append(f"  {c}: {d}")
        lines.append("")
    lines.append(f"캐시에 없어 빠진 점: {meta['missing_count']}개 (계산하지 않음)")
    return "\n".join(lines)


def estimate(app, dataset, body):
    """계산하지 않고 캐시 파일의 존재만 확인해 예상 행 수·용량을 낸다."""
    body = body or {}
    if dataset == "bundle":
        tot = {"rows": 0, "missing_count": 0, "bytes_est": 0}
        for i in (body.get("datasets") or ["curves", "edits", "monsters"]):
            e = estimate(app, i, body)
            for k in tot:
                tot[k] += e[k]
        return {**tot, "missing": []}
    if dataset not in DATASETS:
        raise ExportError("알 수 없는 데이터 집합")
    if dataset in ("workspace", "results", "scans"):
        return {"rows": 1, "bytes_est": 0, "missing_count": 0, "missing": []}
    ctx = Ctx(app, body)
    if dataset == "edits":
        n = len(ctx.edits) + len(ctx.cfg_edits) + len(ctx.cfg_set)
        return {"rows": n, "bytes_est": n * 90, "missing_count": 0, "missing": []}
    if dataset == "monsters":
        return {"rows": len((app.monster_data or {}).get("monsters", [])), "bytes_est": 60 * 220, "missing_count": 0, "missing": []}
    if dataset in ("battles", "battle_log", "battle_calc"):
        n = len((app.monster_data or {}).get("monsters", [])) * 64 if dataset == "battles" else (20 if dataset == "battle_log" else 400)
        return {"rows": n, "bytes_est": n * 120, "missing_count": 0, "missing": []}
    present, missing = ctx.plan()
    pts = len(present) + len(ctx.scan_points())
    if dataset == "curves":
        rows, per = pts, 260
    elif dataset == "reach":
        rows, per = pts * ms.TOTAL_FLOORS, 50
    else:
        rows = 0
        for _, key in present:
            rec = app.store.read(key)
            if rec:
                rows += min(rec["n"], ctx.scope["n"]) if ctx.scope["n"] else rec["n"]
        per = 60
    return {"rows": rows, "bytes_est": rows * per, "missing_count": len(missing),
            "missing": [{"series": it[0], "fantasy_id": it[1], "x": it[2]} for it, _ in missing[:50]], "too_big": rows > MAX_ROWS}


# ---------------------------------------------------------------------------
# 동시 내보내기 제한과 1회용 티켓
# ---------------------------------------------------------------------------
def acquire():
    if not _sem.acquire(blocking=False):
        raise ExportBusy("동시 내보내기는 최대 %d개 — 잠시 뒤 다시 시도하세요" % MAX_CONCURRENT)


def release():
    try:
        _sem.release()
    except ValueError:
        pass


def _body_hash(dataset, body):
    return hashlib.sha256(json.dumps([dataset, body], sort_keys=True, ensure_ascii=False, default=str).encode("utf-8")).hexdigest()


def make_ticket(dataset, body):
    if dataset not in DATASETS:
        raise ExportError("알 수 없는 데이터 집합")
    t = secrets.token_urlsafe(24)
    with _tlock:
        now = time.time()
        for k in [k for k, v in _tickets.items() if v["exp"] < now]:
            del _tickets[k]
        _tickets[t] = {"dataset": dataset, "body": body, "hash": _body_hash(dataset, body), "exp": now + TICKET_TTL}
    return {"t": t, "url": f"/api/export/dl/{t}", "expires_in": int(TICKET_TTL)}


def use_ticket(t):
    """1회용: 쓰면 지운다. 만료·재사용·불일치면 None."""
    with _tlock:
        v = _tickets.pop(t, None)
    if not v or v["exp"] < time.time() or v["hash"] != _body_hash(v["dataset"], v["body"]):
        return None
    return v
