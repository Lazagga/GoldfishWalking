# -*- coding: utf-8 -*-
"""계산 엔진: 점(설정 + 강제 포함 환상 + 시드 접두)을 ≤250판 조각으로 나눠 워커에 배분하고,
조각을 시드 순서대로 이어 붙여 PointStore 에 저장한다 (명세 v2 S1 작업 단위, §6.3 취소·점진 정밀화).

조각은 서로 독립(판 시드 = f"{seed}-{i}")이므로 워커 수·조각 크기·이어 붙이기 여부와 관계없이
결과가 비트 단위로 같다.
"""
from __future__ import annotations

import copy
import multiprocessing as mp
import os
import queue
import threading
import time

import matchup_sim as ms

from . import store as st

CHUNK = 100     # 조각 크기는 결과에 영향 없음. 작을수록 취소가 빠름 (AC-E2 < 1초)


def make_req(cfg, fids, seed, thash, tag=None, banned=None):
    """cfg: X·패싯·설정 편집·효과 파일 경로가 반영된 설정. fids: 강제 포함 환상 목록(빈 목록 = 기준선)."""
    c = copy.deepcopy(cfg)
    forced = c["fantasy"].get("forced") or {}
    c["fantasy"]["forced"] = {"ids": list(fids), "at": forced.get("at", "start")}
    if banned is not None:
        c["fantasy"]["banned"] = {"ids": sorted(banned)}
    bn = sorted((c["fantasy"].get("banned") or {}).get("ids") or [])
    return {"key": st.point_key(c, fids, seed, thash), "cfg": c, "fids": list(fids), "banned": bn, "seed": seed,
            "thash": thash, "dhash": st.data_hash(thash, st.monster_hash(c)), "tag": tag}


_CTX = {}


def run_chunk(task):
    """워커: (cfg, seed, start, end) → 조각 결과."""
    cfg, seed, start, end = task
    import json
    k = json.dumps(cfg, sort_keys=True)
    ctx = _CTX.get(k)
    if ctx is None:
        if len(_CTX) > 64:
            _CTX.clear()
        ctx = _CTX[k] = ms.SimContext(cfg)
    wins, reached, death_act, nfant = [], [], [], []
    agg = {k: 0 for k in st.AGG_KEYS}
    fbf_sum, fbf_n = [0] * ms.TOTAL_FLOORS, [0] * ms.TOTAL_FLOORS
    for i in range(start, end):
        fbf = []
        r = ms.simulate_run(cfg, f"{seed}-{i}", ctx=ctx, fbf=fbf)
        win = r["result"] == "win"
        wins.append("1" if win else "0")
        reached.append(r["reached_floor"])
        death_act.append(0 if win else r["end_act"])
        nfant.append(r["fant_white"] + r["fant_blue"] + r["fant_red"])
        for k in st.AGG_KEYS:
            agg[k] += r[k]
        for f, v in enumerate(fbf):   # 층 f+1 을 마친(또는 거기서 죽은) 판의 보유 환상 수 — 생존 편향 있음
            fbf_sum[f] += v
            fbf_n[f] += 1
    return {"start": start, "wins": "".join(wins), "reached": reached, "death_act": death_act, "nfant": nfant,
            "agg": agg, "fbf_sum": fbf_sum, "fbf_n": fbf_n}


class Progress:
    """계산 진행 집계 (v4.3): 여러 ensure 호출(단계)에 걸쳐 완료·전체·캐시 판 수와 속도·남은 시간을 모은다.

    - begin(todo, cached): ensure 가 시작될 때. todo = 새로 돌릴 판, cached = 이미 저장돼 있던 판.
    - chunk(runs): 조각이 끝날 때마다. emit(snapshot) 을 최대 min_interval 초에 한 번 부른다.
    - end(remaining): ensure 가 끝났을 때(취소·양보로 남은 판이 있으면 전체에서 뺀다).
    - plan(total): 작업 전체에서 새로 돌릴 판 수를 미리 알면 준다(남은 시간이 단계를 넘어 정확해진다).
    결과(시뮬레이션 값)에는 영향이 없다."""

    def __init__(self, emit=None, min_interval=0.3, log=None, log_interval=10.0, label=""):
        self.emit_fn, self.log_fn, self.label = emit, log, label
        self.min_interval, self.log_interval = min_interval, log_interval
        self.planned = None
        self.planned_cached = None
        self.total = 0          # 지금까지 알려진 "새로 돌릴" 판 수
        self.done = 0           # 돌린 판 수
        self.cached = 0         # 캐시에서 가져온(돌리지 않은) 판 수
        self.carry = 0          # 끊긴 ensure 가 저장해 둔 판(다음 begin 의 cached 에서 뺌)
        self.t0 = None
        self.call_done = 0
        self._last = 0.0
        self._last_log = 0.0
        self._lock = threading.Lock()

    def plan(self, total, cached=None):
        """작업 전체에서 새로 돌릴 판 수(와 이미 저장돼 있던 판 수)를 미리 알려 준다. 단계가 여럿인 작업용."""
        self.planned = max(0, int(total))
        if cached is not None:
            self.planned_cached = max(0, int(cached))

    def begin(self, todo, cached):
        with self._lock:
            cached = max(0, cached - self.carry)
            self.carry = 0
            self.total += todo
            if self.planned_cached is None:
                self.cached += cached
            else:
                self.cached = self.planned_cached
            self.call_done = 0
            if todo > 0 and self.t0 is None:
                self.t0 = time.perf_counter()
        self._emit(force=True)

    def chunk(self, runs):
        with self._lock:
            self.done += runs
            self.call_done += runs
        self._emit()

    def end(self, remaining=0):
        with self._lock:
            if remaining > 0:
                self.total -= remaining
                self.carry += self.call_done
        self._emit(force=True)

    def snapshot(self):
        with self._lock:
            total = self.planned if self.planned is not None else self.total
            total = max(total, self.done)
            rate = None
            if self.t0 is not None and self.done > 0:
                dt = time.perf_counter() - self.t0
                if dt > 0.2:
                    rate = self.done / dt
            left = max(0, total - self.done)
            eta = (left / rate) if rate else None
            return {"done": self.done, "total": total, "cached": self.cached,
                    "rate": round(rate, 2) if rate else None, "eta_s": round(eta, 1) if eta is not None else None,
                    "elapsed_s": round(time.perf_counter() - self.t0, 1) if self.t0 is not None else 0.0,
                    "total_final": self.planned is not None}

    def _emit(self, force=False):
        now = time.perf_counter()
        # 오래 걸리는 작업일수록 간격을 늘려 이벤트 수가 불어나지 않게 한다(10시간 작업도 수천 개 이내)
        gap = max(self.min_interval, ((now - self.t0) / 200.0) if self.t0 is not None else 0.0)
        if not force and now - self._last < gap:
            return
        self._last = now
        snap = self.snapshot()
        if self.emit_fn:
            self.emit_fn(snap)
        if self.log_fn and (force and snap["done"] == 0 or now - self._last_log >= self.log_interval):
            self._last_log = now
            self.log_fn(format_progress(snap, self.label))


def _fmt_time(sec):
    if sec is None:
        return "?"
    sec = int(sec)
    if sec < 90:
        return f"{sec}초"
    if sec < 5400:
        return f"{sec // 60}분"
    h = sec / 3600
    return f"{h:.1f}시간" if h < 48 else f"{h / 24:.1f}일"


def format_progress(s, label=""):
    """한 줄 요약: `[라벨] 12,300 / 385,000판 (3.2%) · 캐시 40,000 · 17.0판/초 · 남은 약 6.1시간`."""
    pct = 100.0 * s["done"] / s["total"] if s["total"] else 100.0
    head = f"[{label}] " if label else ""
    tot = f"{s['total']:,}" + ("" if s.get("total_final") else "+")
    rate = f"{s['rate']:.1f}판/초" if s["rate"] else "속도 측정 중"
    cache = f" · 캐시 {s['cached']:,}" if s["cached"] else ""
    return f"{head}{s['done']:,} / {tot}판 ({pct:.1f}%){cache} · {rate} · 남은 약 {_fmt_time(s['eta_s'])}"


class Cancelled(Exception):
    pass


class Engine:
    def __init__(self, store, workers=None, chunk=CHUNK):
        self.store = store
        self.workers = max(1, workers if workers is not None else (os.cpu_count() or 2) - 1)
        self.chunk = chunk
        self._pool = None
        self.runs_computed = 0
        self.rate = None      # 최근 측정한 처리 속도 (판/초, 워커 전체)

    @property
    def pool(self):
        if self._pool is None and self.workers > 1:
            self._pool = mp.get_context("spawn").Pool(self.workers)
        return self._pool

    def close(self):
        if self._pool is not None:
            self._pool.terminate()
            self._pool.join()
            self._pool = None

    def record(self, req):
        return self.store.load(req["key"]) or st.empty_record(req["key"], req["fids"], req["seed"], req["thash"],
                                                              req.get("dhash"), req.get("banned", ()))

    def ensure(self, reqs, n_target, on_point=None, cancel=None, n_targets=None, chunk=None, progress=None):
        """reqs 를 각각 n_target(또는 n_targets[key]) 판까지 채운다. 반환 {key: rec}.
        on_point(req, rec): 요청이 목표에 도달할 때(이미 도달했으면 즉시). cancel(): True 면 Cancelled.
        progress: Progress (v4.3) — 조각마다 완료 판 수를 알린다. 결과에는 영향 없음.
        취소되면 그때까지 시드 순서대로 이어진 부분은 저장한다."""
        uniq = {}
        for r in reqs:
            uniq.setdefault(r["key"], r)
        recs, pending, target = {}, [], {}
        for key, req in uniq.items():
            rec = self.record(req)
            recs[key] = rec
            tgt = (n_targets or {}).get(key, n_target)
            target[key] = tgt
            if rec["n"] >= tgt:
                if on_point:
                    on_point(req, rec)
                continue
            step = int(chunk or self.chunk)   # 조각 크기는 결과에 영향 없음 (시드 순서대로 이어 붙임)
            for s in range(rec["n"], tgt, step):
                pending.append((key, s, min(s + step, tgt)))
        if progress is not None:
            progress.begin(sum(e - s_ for _, s_, e in pending),
                           sum(min(recs[k]["n"], target[k]) for k in recs))
            try:
                return self._ensure_run(uniq, recs, pending, target, on_point, cancel, progress)
            finally:
                progress.end(max(0, sum(e - s_ for _, s_, e in pending) - progress.call_done))
        return self._ensure_run(uniq, recs, pending, target, on_point, cancel, None)

    def _ensure_run(self, uniq, recs, pending, target, on_point, cancel, progress):
        if not pending:
            return recs
        t_start, n_start = time.perf_counter(), self.runs_computed
        buffers = {k: {} for k in uniq}
        dirty = set()

        def absorb(key, res):
            buffers[key][res["start"]] = res
            rec = recs[key]
            while rec["n"] in buffers[key]:
                st.append_chunk(rec, buffers[key].pop(rec["n"]))
                dirty.add(key)
            if rec["n"] >= target[key] and key in dirty:
                self.store.save(rec)
                dirty.discard(key)
                if on_point:
                    on_point(uniq[key], rec)

        def flush_partial():
            for key in list(dirty):
                self.store.save(recs[key])
            dirty.clear()

        if self.workers <= 1:
            for key, s, e in pending:
                if cancel and cancel():
                    flush_partial()
                    raise Cancelled()
                res = run_chunk((uniq[key]["cfg"], uniq[key]["seed"], s, e))
                self.runs_computed += e - s
                if progress is not None:
                    progress.chunk(e - s)
                absorb(key, res)
            return recs

        q = queue.Queue()
        inflight = 0
        it = iter(pending)
        exhausted = False
        cancelled = False
        max_inflight = self.workers * 2
        errors = []
        while True:
            while not exhausted and not cancelled and inflight < max_inflight:
                try:
                    key, s, e = next(it)
                except StopIteration:
                    exhausted = True
                    break
                req = uniq[key]
                self.pool.apply_async(run_chunk, ((req["cfg"], req["seed"], s, e),),
                                      callback=lambda res, key=key: q.put((key, res)),
                                      error_callback=lambda exc: q.put((None, exc)))
                inflight += 1
            if inflight == 0:
                break
            try:
                key, res = q.get(timeout=0.05)
            except queue.Empty:
                if cancel and cancel():
                    cancelled = True
                continue
            inflight -= 1
            if key is None:
                errors.append(res)
                cancelled = True
                continue
            self.runs_computed += len(res["wins"])
            if progress is not None:
                progress.chunk(len(res["wins"]))
            absorb(key, res)
            if cancel and cancel():
                cancelled = True
        dt = time.perf_counter() - t_start
        if dt > 0.3 and self.runs_computed > n_start:
            r = (self.runs_computed - n_start) / dt
            self.rate = r if self.rate is None else 0.5 * self.rate + 0.5 * r
        if errors:
            flush_partial()
            raise errors[0]
        if cancelled:
            flush_partial()
            raise Cancelled()
        return recs


def stage_plan(stages, n_max=None):
    s = sorted(set(int(x) for x in stages))
    if n_max:
        s = [x for x in s if x < n_max] + [n_max]
    return s


class Timer:
    def __init__(self):
        self.t0 = time.perf_counter()

    def __call__(self):
        return time.perf_counter() - self.t0


_lock = threading.Lock()


def peak_rss_mb():
    """현재 프로세스의 최대 메모리 사용량(MB). Windows 는 PeakWorkingSetSize, 그 밖은 ru_maxrss."""
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes

        class PMC(ctypes.Structure):
            _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD),
                        ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t),
                        ("QuotaPeakPagedPoolUsage", ctypes.c_size_t), ("QuotaPagedPoolUsage", ctypes.c_size_t),
                        ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t), ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                        ("PagefileUsage", ctypes.c_size_t), ("PeakPagefileUsage", ctypes.c_size_t)]
        pmc = PMC()
        pmc.cb = ctypes.sizeof(PMC)
        k32, psapi = ctypes.WinDLL("kernel32"), ctypes.WinDLL("psapi")
        k32.GetCurrentProcess.restype = wintypes.HANDLE
        psapi.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(PMC), wintypes.DWORD]
        psapi.GetProcessMemoryInfo.restype = wintypes.BOOL
        if not psapi.GetProcessMemoryInfo(k32.GetCurrentProcess(), ctypes.byref(pmc), pmc.cb):
            raise OSError("GetProcessMemoryInfo 실패")
        return pmc.PeakWorkingSetSize / 1e6
    import resource
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1e3


def worker_report(_=None):
    """워커 상태 보고 (메모리·맵 캐시 크기). 테스트·벤치용."""
    return {"pid": os.getpid(), "peak_rss_mb": peak_rss_mb(), "map_cache": len(ms._MAP_CACHE)}
