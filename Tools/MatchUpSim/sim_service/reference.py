# -*- coding: utf-8 -*-
"""비교 기준(reference) 스냅샷 (v4 §6.8).

- 기준 = {시뮬 테이블(환상·몬스터), 해시, 파일별 sha1, 설정}. 기본은 세션 시작 시점의 디스크 원본.
  원본 반영(apply)·반영 되돌리기 뒤에는 디스크 원본으로 자동 갱신, `기준 다시 잡기`로 현재 작업 사본을 고정.
- 수정 전(고스트) 곡선 = 기준의 data_hash 로 계산한 곡선. 숫자 UI 편집과 JSON 편집이 같은 경로를 쓴다.
- 변경 집합 = 현재 작업 사본의 시뮬 테이블 vs 기준의 시뮬 테이블 (시뮬에 쓰이는 필드만 비교 → 공백·키 순서·이름은 무시).
"""
from __future__ import annotations

import copy
import json
import time

from . import store as st


def _canon_fantasies(table):
    return {e["id"]: json.dumps(c, sort_keys=True, ensure_ascii=False)
            for e, c in zip(table.get("fantasies", []), st.canonical_entries(table.get("fantasies", [])))}


def _canon_monster(m):
    return json.dumps(st.monster_canon(m), sort_keys=True, ensure_ascii=False)


def _patterns(mtable):
    out = {}
    for m in (mtable or {}).get("monsters", []):
        for p in m.get("patterns", []):
            k = p.get("key")
            if k is not None:
                out.setdefault(k, json.dumps(st.pattern_canon(p), sort_keys=True, ensure_ascii=False))
    return out


def _flat(d, prefix=""):
    out = {}
    for k, v in (d or {}).items():
        p = f"{prefix}{k}"
        if isinstance(v, dict):
            out.update(_flat(v, p + "."))
        else:
            out[p] = v
    return out


PATH_KEYS = ("fantasy.effects_file", "monsters.table_file")


def changed_set(ref, table_data, monster_data, cfg):
    a, b = _canon_fantasies(ref["table_data"]), _canon_fantasies(table_data)
    fants = sorted(k for k in set(a) | set(b) if a.get(k) != b.get(k))
    ma = {m["id"]: _canon_monster(m) for m in (ref.get("monster_data") or {}).get("monsters", [])}
    mb = {m["id"]: _canon_monster(m) for m in (monster_data or {}).get("monsters", [])}
    mons = sorted(k for k in set(ma) | set(mb) if ma.get(k) != mb.get(k))
    pa, pb = _patterns(ref.get("monster_data")), _patterns(monster_data)
    pats = sorted(k for k in set(pa) | set(pb) if pa.get(k) != pb.get(k))
    fa, fb = _flat(ref["cfg"]), _flat(cfg)
    keys = sorted(k for k in set(fa) | set(fb) if k not in PATH_KEYS and fa.get(k) != fb.get(k))
    return {"fantasies": fants, "monsters": mons, "patterns": pats, "cfg_keys": keys}


def make(source, table_data, monster_data, cfg, data_hash, table_hash, disk_files):
    return {"source": source, "table_data": copy.deepcopy(table_data), "monster_data": copy.deepcopy(monster_data),
            "cfg": copy.deepcopy(cfg), "data_hash": data_hash, "table_hash": table_hash,
            "disk_files": dict(disk_files), "pinned_at": time.strftime("%Y-%m-%dT%H:%M:%S")}


def info(ref, cur_hash, changed, disk_now):
    stale = sorted(k for k in set(ref["disk_files"]) | set(disk_now) if ref["disk_files"].get(k) != disk_now.get(k))
    return {"ref_hash": ref["data_hash"], "cur_hash": cur_hash, "same": ref["data_hash"] == cur_hash,
            "changed": changed, "pinned_at": ref["pinned_at"], "source": ref["source"],
            "source_label": "디스크 원본" if ref["source"] == "disk" else "고정한 작업 사본",
            "stale": bool(stale), "stale_files": stale}
