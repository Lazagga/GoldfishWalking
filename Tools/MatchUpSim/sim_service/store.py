# -*- coding: utf-8 -*-
"""점 캐시 (명세 v2 S1).

- 정규 테이블 해시: 시뮬레이션에 영향을 주는 필드만 (id, grade, available, effects[src 제외]) 를 정규화해 sha1.
  임포터를 데이터 변경 없이 다시 돌려도 (generated_at, notes 등이 바뀌어도) 해시가 같다.
- 점 키: 설정(효과 파일 경로·강제 포함 제외) + 강제 포함 환상 + 시드 + 테이블 해시 + SIM_VERSION.
  판 수는 키에 넣지 않는다. 레코드는 "시드 0..n-1 의 결과" 이고 더 필요하면 [n, N) 만 돌려 이어 붙인다.
- 저장: <root>/<key[:2]>/<key>.json.gz (원자적 쓰기).
"""
from __future__ import annotations

import copy
import gzip
import hashlib
import json
import os
import threading

import matchup_sim as ms

HASH_FIELDS = ("id", "grade", "available")
EFFECT_SKIP_KEYS = ("src", "surrogate_candidate")   # 시뮬에 쓰이지 않는 표시 → 해시 제외


def canonical_entries(fantasies):
    out = []
    for e in fantasies:
        out.append({
            "id": e["id"],
            "grade": e.get("grade"),
            "available": e.get("available", True),
            "effects": [{k: v for k, v in ef.items() if k not in EFFECT_SKIP_KEYS} for ef in e.get("effects", [])],
        })
    return out


def table_hash(data_or_list):
    """fantasy_effects.json 의 dict 또는 fantasies 목록 → 정규 해시 (16자리)."""
    fants = data_or_list.get("fantasies", []) if isinstance(data_or_list, dict) else data_or_list
    blob = json.dumps(canonical_entries(fants), sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha1(blob.encode("utf-8")).hexdigest()[:16]


_MON_HASH = {}


PATTERN_HASH_KEYS = ("key", "kind", "multi", "dmg_digits", "hit_digits", "str_units", "max_uses")
# v4 (digits·기믹): 있을 때만 해시에 넣는다 → 이 필드가 없는 기존 테이블의 해시는 그대로
PATTERN_HASH_KEYS_V4 = ("sim", "dynamic", "heal", "timing", "condition", "self_destruct", "effects", "hit_count",
                        "deal", "value_expr")
MONSTER_HASH_KEYS_V4 = ("sim", "gimmicks", "phase_two", "special_box")


def pattern_canon(p):
    c = {k: p.get(k) for k in PATTERN_HASH_KEYS}
    for k in PATTERN_HASH_KEYS_V4:
        if k in p:
            c[k] = p[k]
    return c


def monster_canon(m):
    c = {"id": m["id"], "enabled": m.get("enabled", True), "act": m.get("act"), "tier": m.get("tier"),
         "hp": m.get("hp"), "strength": m.get("strength", 0), "ai": m.get("ai"),
         "patterns": [pattern_canon(p) for p in m.get("patterns", [])]}
    for k in MONSTER_HASH_KEYS_V4:
        if k in m:
            c[k] = m[k]
    return c


def _strip_src(x):
    if isinstance(x, list):
        return [_strip_src(v) for v in x]
    if isinstance(x, dict):
        return {k: _strip_src(v) for k, v in x.items() if k != "src"}
    return x


def monster_hash_of(table):
    """monster_table.json dict → 정규 해시. 시뮬레이션에 쓰이는 필드만 (이름·설명·메모·src 제외)."""
    canon = [_strip_src(monster_canon(m)) for m in table.get("monsters", [])]
    blob = json.dumps(canon, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha1(blob.encode("utf-8")).hexdigest()[:16]


def monster_hash(cfg):
    """monsters.model = table 일 때만 몬스터 테이블 해시, 아니면 빈 문자열."""
    M = cfg.get("monsters", {})
    if M.get("model", "tier_avg") != "table" or not M.get("table_file"):
        return ""
    path = os.path.abspath(ms.resolve_table_file(M["table_file"]))
    key = (path, os.path.getmtime(path))
    if key not in _MON_HASH:
        with open(path, encoding="utf-8-sig") as fp:
            _MON_HASH[key] = monster_hash_of(json.load(fp))
    return _MON_HASH[key]


def data_hash(thash, mhash=""):
    """data_hash = sha1(table_hash | monster_hash). 몬스터 테이블을 안 쓰면 table_hash 와 1:1."""
    return hashlib.sha1(f"{thash}|{mhash}".encode("utf-8")).hexdigest()[:16]


def load_table(path):
    with open(path, encoding="utf-8-sig") as fp:
        data = json.load(fp)
    return data, table_hash(data)


def materialize_table(data, tables_dir):
    """편집한 테이블을 내용 주소(해시) 이름의 파일로 저장하고 경로를 돌려준다 (워커가 경로로 읽음)."""
    h = table_hash(data)
    os.makedirs(tables_dir, exist_ok=True)
    path = os.path.join(tables_dir, f"{h}.json")
    if not os.path.exists(path):
        tmp = path + f".{os.getpid()}.{threading.get_ident()}.tmp"
        with open(tmp, "w", encoding="utf-8") as fp:
            json.dump(data, fp, ensure_ascii=False)
        os.replace(tmp, path)
    return path, h


V4_DEFAULTS = (("monsters", "gimmicks"), ("player", "policy"), ("monsters", "encounter"), ("monsters", "encounter_rules"))
# 키에서 지우는 값은 "그 키가 생기기 전 동작" 으로 고정한다 (기본값이 바뀌어도 구 키가 그대로 — v4.2 AC-H3, AC-H11).
KEY_STRIP_VALUES = {("monsters", "gimmicks"): "off"}


def strip_v4_defaults(c):
    """v4 이후 추가한 설정 키가 '추가 전 동작' 값이면 지운다 → 이전 점 캐시 키가 그대로 (AC-D0)."""
    for sec, k in V4_DEFAULTS:
        d = c.get(sec)
        ref = KEY_STRIP_VALUES.get((sec, k), ms.DEFAULT_CONFIG[sec][k])
        if isinstance(d, dict) and k in d and d[k] == ref:
            del d[k]
    return c


def point_key(cfg, fids, seed, thash):
    """cfg 에는 X 값·패싯·설정 편집이 이미 반영돼 있어야 한다. fids = 강제 포함 환상 (정렬하지 않음: 획득 순서)."""
    c = copy.deepcopy(cfg)
    c["fantasy"]["effects_file"] = ""
    forced = c["fantasy"].get("forced") or {}
    c["fantasy"]["forced"] = {"ids": [], "at": forced.get("at", "start")}
    banned = sorted((c["fantasy"].get("banned") or {}).get("ids") or [])
    c["fantasy"]["banned"] = {"ids": []}
    dh = data_hash(thash, monster_hash(cfg))
    strip_v4_defaults(c)
    if c.get("monsters", {}).get("table_file"):
        c["monsters"]["table_file"] = ""     # 파일 위치가 아니라 내용(monster_hash)으로 구분
    blob = json.dumps(c, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    # 팔(arm) = 강제 포함(획득 순서) + 제외(정렬) + 강제 시점(설정에 포함)
    raw = f"{blob}|forced={','.join(fids)}|banned={','.join(banned)}|{seed}|{dh}|{ms.SIM_VERSION}"
    Mc = cfg.get("monsters") or {}
    if Mc.get("model") == "table" and Mc.get("encounter", "game") == "game":
        raw += "|enc1"      # 게임 규칙 몬스터 배정 (table 모델만 동작이 바뀜 → tier_avg 키는 그대로)
    if (cfg.get("monsters") or {}).get("damage_model") == "digits":   # digits 엔진 버전 (gauss 키는 그대로)
        from . import box_moves as bm, fight_digits as fd
        raw += f"|dg{fd.VERSION}.{bm.VERSION}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:24]


AGG_KEYS = ("fantasies_reward", "fantasies_shop", "fantasies_forced", "embers_white", "embers_blue", "slots_done",
            "blue_offers", "blue_picked", "blue_wasted", "normal_wins")


def empty_record(key, fids, seed, thash, dhash=None, banned=()):
    return {"key": key, "fids": list(fids), "banned": list(banned), "seed": seed, "table_hash": thash,
            "data_hash": dhash or thash, "sim_version": ms.SIM_VERSION,
            "n": 0, "wins": "", "reached": [], "death_act": [], "nfant": [],
            "agg": {k: 0 for k in AGG_KEYS}, "fbf_sum": [0] * ms.TOTAL_FLOORS, "fbf_n": [0] * ms.TOTAL_FLOORS}


def append_chunk(rec, chunk):
    """chunk = {start, wins, reached, death_act, nfant}. start 가 rec['n'] 과 같아야 한다."""
    if chunk["start"] != rec["n"]:
        raise ValueError(f"이어 붙이기 위치 불일치: {chunk['start']} != {rec['n']}")
    rec["wins"] += chunk["wins"]
    rec["reached"].extend(chunk["reached"])
    rec["death_act"].extend(chunk["death_act"])
    rec["nfant"].extend(chunk["nfant"])
    rec["n"] = len(rec["wins"])
    # 집계 통계 (판 전체 합계 — 접두 n 으로 자를 수 없으므로 통계는 레코드 전체 n 기준)
    for k, v in chunk.get("agg", {}).items():
        rec["agg"][k] = rec["agg"].get(k, 0) + v
    for f, (a, b) in enumerate(zip(chunk.get("fbf_sum", ()), chunk.get("fbf_n", ()))):
        rec["fbf_sum"][f] += a
        rec["fbf_n"][f] += b
    return rec


class PointStore:
    def __init__(self, root):
        self.root = root
        self._lock = threading.Lock()
        self._mem = {}

    def path(self, key):
        return os.path.join(self.root, key[:2], f"{key}.json.gz")

    def load(self, key):
        with self._lock:
            if key in self._mem:
                return self._mem[key]
        p = self.path(key)
        try:
            with gzip.open(p, "rt", encoding="utf-8") as fp:
                rec = json.load(fp)
        except (OSError, ValueError, EOFError):
            return None
        if rec.get("sim_version") != ms.SIM_VERSION or len(rec.get("wins", "")) != rec.get("n") or "agg" not in rec:
            return None
        with self._lock:
            self._mem[key] = rec
        return rec

    def save(self, rec):
        p = self.path(rec["key"])
        os.makedirs(os.path.dirname(p), exist_ok=True)
        tmp = p + f".{os.getpid()}.{threading.get_ident()}.tmp"
        with gzip.open(tmp, "wt", encoding="utf-8", compresslevel=6) as fp:
            json.dump(rec, fp, separators=(",", ":"))
        for _ in range(5):
            try:
                os.replace(tmp, p)
                break
            except PermissionError:  # OneDrive 동기화 등
                import time
                time.sleep(0.1)
        with self._lock:
            self._mem[rec["key"]] = rec

    def disk_usage(self):
        total = 0
        for dp, _, files in os.walk(self.root):
            for f in files:
                total += os.path.getsize(os.path.join(dp, f))
        return total

    def prune(self, max_bytes, protect=()):
        """오래된(수정 시각) 점부터 지워 max_bytes 이하로 만든다. protect = 지우지 않을 data_hash 집합
        (현재 작업 사본·비교 기준, §6.8 캐시 보호). 돌려주는 값: {removed, kept_protected, bytes}."""
        protect = set(protect)
        files = []
        for dp, _, fs_ in os.walk(self.root):
            for f in fs_:
                if f.endswith(".json.gz"):
                    p = os.path.join(dp, f)
                    try:
                        files.append((os.path.getmtime(p), os.path.getsize(p), p))
                    except OSError:
                        pass
        total = sum(s for _, s, _ in files)
        removed, kept = 0, 0
        for _, size, p in sorted(files):
            if total <= max_bytes:
                break
            try:
                with gzip.open(p, "rt", encoding="utf-8") as fp:
                    dh = json.load(fp).get("data_hash")
            except (OSError, ValueError, EOFError):
                dh = None
            if dh in protect:
                kept += 1
                continue
            try:
                os.remove(p)
            except OSError:
                continue
            key = os.path.basename(p)[:-len(".json.gz")]
            with self._lock:
                self._mem.pop(key, None)
            total -= size
            removed += 1
        return {"removed": removed, "kept_protected": kept, "bytes": total}
