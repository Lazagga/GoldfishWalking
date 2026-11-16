# -*- coding: utf-8 -*-
"""작업 결과 저장 (v4.4 F14.6) 과 스캔 색인 (F14.5b).

결과 파일: `<results>/job_results/<kind>/<key>.json`
  key = sha1(kind + 정규화한 params + data_hash + cfg_tag)[:16]
  {kind, params, data_hash, cfg_tag, created_at, sim_version, result}
- params 에서 client·edits·cfg_edits·cfg_set 은 뺀다 (편집은 data_hash·cfg_tag 에 이미 들어 있다).
- 보관 한도: 종류별 PER_KIND_MAX 개, 전체 TOTAL_MAX_BYTES. 넘으면 오래된 것부터 지우되 현재 data_hash 의 결과는 보호한다.

몬스터별 지표는 `<results>/monster_metrics/<data_hash>-<seed>-<설정 8자>.json` 에 따로 둔다 (서버 재시작 뒤에도 같은 상태면 바로 표시).
스캔 색인: `<results>/fantasy_scans/index.json` — 파일 수정 시각·크기가 바뀐 스캔만 다시 읽는다.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import threading
import time
from datetime import datetime

import matchup_sim as ms

PER_KIND_MAX = 30
TOTAL_MAX_BYTES = 200 * 1024 * 1024
KINDS = ("combo", "ember_sweep", "tune", "value_sweep", "solve_value")
DROP = ("client", "edits", "cfg_edits", "cfg_set", "kind", "stages_hint")
KEY_RE = re.compile(r"^[0-9a-f]{16}$")
SCAN_ID_RE = re.compile(r"^\d{8}-\d{6}-[0-9a-f]{6}$")
_lock = threading.RLock()


def _atomic_write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + f".{os.getpid()}.{threading.get_ident()}.tmp"
    with open(tmp, "w", encoding="utf-8") as fp:
        fp.write(text)
    for k in range(5):
        try:
            os.replace(tmp, path)
            return
        except PermissionError:       # OneDrive 동기화
            time.sleep(0.1 * (k + 1))
    try:
        os.remove(tmp)
    except OSError:
        pass
    raise OSError(f"쓰기 실패(파일 잠김?): {path}")


def norm_params(params):
    return {k: v for k, v in (params or {}).items() if k not in DROP}


def cfg_tag_of(cfg_edits, cfg_set):
    return json.dumps([[c.get("path"), c.get("new")] for c in (cfg_edits or [])], sort_keys=True) + \
        json.dumps(sorted((cfg_set or {}).items()), ensure_ascii=False)


def key_of(kind, params, data_hash, cfg_tag):
    raw = json.dumps([kind, norm_params(params), data_hash, cfg_tag, ms.SIM_VERSION], sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def _dir(root, kind):
    if kind not in KINDS:
        raise ValueError(f"결과를 저장하지 않는 작업 종류: {kind}")
    return os.path.join(root, "job_results", kind)


def save(root, kind, params, data_hash, cfg_tag, result):
    key = key_of(kind, params, data_hash, cfg_tag)
    body = {"kind": kind, "key": key, "params": norm_params(params), "data_hash": data_hash, "cfg_tag": cfg_tag,
            "created_at": datetime.now().isoformat(timespec="seconds"), "sim_version": ms.SIM_VERSION, "result": result}
    with _lock:
        _atomic_write(os.path.join(_dir(root, kind), key + ".json"), json.dumps(body, ensure_ascii=False, separators=(",", ":")))
        prune(root, protect={data_hash})
    return key


def get(root, kind, key):
    if not KEY_RE.match(key or ""):
        raise ValueError("결과 키 형식 오류")
    try:
        with open(os.path.join(_dir(root, kind), key + ".json"), encoding="utf-8") as fp:
            return json.load(fp)
    except OSError:
        raise FileNotFoundError("저장된 결과 없음")


def lookup(root, kind, params, data_hash, cfg_tag):
    try:
        d = get(root, kind, key_of(kind, params, data_hash, cfg_tag))
    except (FileNotFoundError, ValueError):
        return None
    return d if d.get("sim_version") == ms.SIM_VERSION else None


def list_(root, kind):
    out = []
    d = _dir(root, kind)
    if not os.path.isdir(d):
        return out
    for fn in os.listdir(d):
        if not fn.endswith(".json") or not KEY_RE.match(fn[:-5]):
            continue
        p = os.path.join(d, fn)
        try:
            with open(p, encoding="utf-8") as fp:
                b = json.load(fp)
            out.append({"key": b["key"], "kind": kind, "created_at": b.get("created_at"), "data_hash": b.get("data_hash"),
                        "cfg_tag": b.get("cfg_tag"), "params": b.get("params"), "bytes": os.path.getsize(p)})
        except (OSError, ValueError, KeyError):
            continue
    out.sort(key=lambda r: r["created_at"] or "", reverse=True)
    return out


def prune(root, protect=(), per_kind=PER_KIND_MAX, total=TOTAL_MAX_BYTES):
    """종류별 per_kind 개, 전체 total 바이트 이하로 오래된 것부터 지운다. protect = 지우지 않을 data_hash 집합."""
    base = os.path.join(root, "job_results")
    keep_hashes = set(protect)

    def protected(p):
        try:
            with open(p, encoding="utf-8") as fp:
                return json.load(fp).get("data_hash") in keep_hashes
        except (OSError, ValueError):
            return False

    def rm(p):
        try:
            os.remove(p)
            return True
        except OSError:
            return False

    removed, kept = 0, []
    for kind in KINDS:
        d = os.path.join(base, kind)
        if not os.path.isdir(d):
            continue
        items = []
        for fn in os.listdir(d):
            if fn.endswith(".json"):
                p = os.path.join(d, fn)
                try:
                    items.append((os.path.getmtime(p), os.path.getsize(p), p))
                except OSError:
                    pass
        items.sort(reverse=True)                                    # 최신 먼저
        for i, (m, sz, p) in enumerate(items):
            if i >= per_kind and not protected(p):                  # 종류별 한도 초과분
                removed += rm(p)
            else:
                kept.append((m, sz, p))
    used = sum(sz for _, sz, _ in kept)
    for m, sz, p in sorted(kept):                                   # 전체 용량 한도: 오래된 것부터
        if used <= total:
            break
        if not protected(p) and rm(p):
            used -= sz
            removed += 1
    return removed


# ---------------------------------------------------------------------------
# 몬스터별 지표 (F14.6): data_hash 별 파일
# ---------------------------------------------------------------------------
def mon_path(root, data_hash, seed, cfg_digest):
    safe = re.sub(r"[^0-9A-Za-z_\-]", "_", f"{data_hash}-{seed}-{cfg_digest[:8]}")
    return os.path.join(root, "monster_metrics", safe + ".json")


def mon_load(root, data_hash, seed, cfg_digest):
    try:
        with open(mon_path(root, data_hash, seed, cfg_digest), encoding="utf-8") as fp:
            d = json.load(fp)
    except (OSError, ValueError):
        return None
    return d if d.get("sim_version") == ms.SIM_VERSION and isinstance(d.get("data"), dict) else None


def mon_save(root, data_hash, seed, cfg_digest, data, keep=PER_KIND_MAX):
    cur = mon_load(root, data_hash, seed, cfg_digest)
    if cur and cur["data"].get("runs", 0) > data.get("runs", 0):      # 더 많은 판으로 계산한 결과를 덮지 않는다
        return
    body = {"data_hash": data_hash, "seed": seed, "cfg": cfg_digest[:8], "sim_version": ms.SIM_VERSION,
            "saved_at": datetime.now().isoformat(timespec="seconds"), "data": data}
    with _lock:
        _atomic_write(mon_path(root, data_hash, seed, cfg_digest), json.dumps(body, ensure_ascii=False, separators=(",", ":")))
        d = os.path.join(root, "monster_metrics")
        files = sorted(((os.path.getmtime(os.path.join(d, f)), os.path.join(d, f)) for f in os.listdir(d) if f.endswith(".json")),
                       reverse=True)
        for _, p in files[keep:]:
            try:
                os.remove(p)
            except OSError:
                pass


# ---------------------------------------------------------------------------
# 스캔 색인 (F14.5b)
# ---------------------------------------------------------------------------
META_KEYS = ("scan_id", "data_hash", "table_hash", "x_param", "x_values", "damage_model", "monster_model", "monsters_gimmicks",
             "generated_at", "master_seed", "runs_per_point", "fixed_overrides", "target_win_rate", "effect_mode")


def scans_dir(root):
    return os.path.join(root, "fantasy_scans")


def scan_index(root):
    """fantasy_scans/*.json 의 meta 색인. 수정 시각·크기가 바뀐 파일만 다시 읽는다."""
    d = scans_dir(root)
    ip = os.path.join(d, "index.json")
    if not os.path.isdir(d):
        return []
    try:
        with open(ip, encoding="utf-8") as fp:
            idx = json.load(fp)
    except (OSError, ValueError):
        idx = {}
    changed, out, seen = False, [], set()
    for fn in sorted(os.listdir(d)):
        if not fn.endswith(".json") or fn == "index.json" or not SCAN_ID_RE.match(fn[:-5]):
            continue
        p = os.path.join(d, fn)
        try:
            stt = os.stat(p)
        except OSError:
            continue
        sig = [stt.st_mtime_ns, stt.st_size]
        ent = idx.get(fn)
        if not ent or ent.get("sig") != sig:
            try:
                with open(p, encoding="utf-8") as fp:
                    meta = json.load(fp).get("meta") or {}
            except (OSError, ValueError):
                continue
            ent = {"sig": sig, "meta": {k: meta.get(k) for k in META_KEYS}}
            idx[fn] = ent
            changed = True
        seen.add(fn)
        out.append({"scan_id": fn[:-5], "file": fn, **ent["meta"]})
    for fn in [k for k in idx if k not in seen]:
        del idx[fn]
        changed = True
    if changed:
        try:
            _atomic_write(ip, json.dumps(idx, ensure_ascii=False, separators=(",", ":")))
        except OSError:
            pass
    out.sort(key=lambda r: r["scan_id"], reverse=True)
    return out


def scan_path(root, scan_id):
    if not SCAN_ID_RE.match(scan_id or ""):
        raise ValueError("scan_id 형식 오류")
    p = os.path.join(scans_dir(root), scan_id + ".json")
    if not os.path.isfile(p):
        raise FileNotFoundError("스캔 없음")
    return p
