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

    def ensure(self, reqs, n_target, on_point=None, cancel=None, n_targets=None, chunk=None):
        """reqs 를 각각 n_target(또는 n_targets[key]) 판까지 채운다. 반환 {key: rec}.
        on_point(req, rec): 요청이 목표에 도달할 때(이미 도달했으면 즉시). cancel(): True 면 Cancelled.
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
