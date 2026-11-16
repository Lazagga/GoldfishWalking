#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Match Up 뷰어 로컬 서버 (명세 v2 §4)
====================================

  python viewer_server.py [--port 8765] [--open]
  python viewer_server.py --host 0.0.0.0          # 원격 모드: 다른 기기에서 접속 (README '원격 서버')

- 기본은 127.0.0.1 에만 바인드. 시작할 때 무작위 토큰을 만들어 HTML 에 넣고, 모든 /api/* 는 X-MatchUp-Token 헤더가 맞아야 한다.
- Host / Origin 이 localhost:<포트> 가 아니면 거부 (다른 웹페이지·DNS 리바인딩 방어). 쓰기 API 는 application/json 만.
- 원격 모드(--host 가 루프백이 아님): 페이지(/)도 토큰이 있어야 연다 (/?k=<토큰>). 토큰은 .matchupsim_remote_token 에
  저장해 재시작해도 주소가 그대로다. Host 는 검사하지 않고(토큰으로 막는다) Origin 은 같은 출처만 허용한다.
- 원본 JSON 이 서버 밖(에디터·Unity·git pull)에서 바뀌면 다음 요청 때 다시 읽는다 (비교 기준은 그대로 → 수정 전/후 비교).
- 파일 쓰기는 허용 목록(원본 fantasies 폴더, overrides, scenarios/, sim_results/, 백업 폴더) 안으로만,
  환상 ID → 파일 매핑은 서버가 직접 해석한다 (클라이언트가 보낸 경로를 쓰지 않음).
- 서버 없이 HTML 을 열면 뷰어는 읽기 전용으로 동작한다.
"""
from __future__ import annotations

import argparse
import copy
import gzip
import hashlib
import json
import os
import re
import secrets
import socket
import sys
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, unquote, urlparse

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import build_viewer  # noqa: E402
import fantasy_scan as fs  # noqa: E402
import import_fantasies  # noqa: E402
import import_monsters  # noqa: E402
from sim_service import overlay as ovl  # noqa: E402
from sim_service import reference as rf  # noqa: E402
from sim_service import results as rs  # noqa: E402
from sim_service import surrogate as sg  # noqa: E402
from sim_service import surrogate_train as sgt  # noqa: E402
import matchup_sim as ms  # noqa: E402
from sim_service import battlelog as bl_  # noqa: E402
from sim_service import compute as cp  # noqa: E402
from sim_service import edits as ed  # noqa: E402
from sim_service import export as exp  # noqa: E402
from sim_service import jobs as jb  # noqa: E402
from sim_service import stats as S  # noqa: E402
from sim_service import store as st  # noqa: E402
from sim_service import trace as trc  # noqa: E402
from sim_service import workspace as wsp  # noqa: E402
from sim_service import writeback as wb  # noqa: E402

class ReplayBusy(Exception):
    pass


class ReplayTimeout(Exception):
    pass


REPLAY_MAX = 2                 # 동시에 처리하는 재생 수
REPLAY_CTX_MAX = 4             # SimContext 재사용 한도 (설정·몬스터 테이블 해시별)
REPLAY_TIMEOUT_S = 5.0
SEED_RE = re.compile(r"^[0-9A-Za-z_-]{1,64}$")
_replay_sem = threading.BoundedSemaphore(REPLAY_MAX)

REPO = os.path.dirname(os.path.dirname(HERE))
DEFAULT_SRC = os.path.join(REPO, "Assets", "Data", "Json", "fantasies")
DEFAULT_MON = os.path.join(REPO, "Assets", "Data", "Json", "monsters")
DEFAULT_PAT = os.path.join(REPO, "Assets", "Data", "Json", "patterns")
MAX_BODY = 5 * 1024 * 1024
MAX_FILE_BODY = 1024 * 1024 + 4096   # JSON 편집기 본문 (파일당 1MB)
LOOPBACK = ("127.0.0.1", "localhost", "::1")
TOKEN_FILE = os.path.join(HERE, ".matchupsim_remote_token")


BUILD_FILES = ("viewer_server.py", "viewer_template.html", "build_viewer.py", "matchup_sim.py", "fantasy_scan.py",
               "import_fantasies.py", "import_monsters.py")


def code_build():
    """서버가 읽은 코드 파일들의 (이름, 크기, 수정 시각) → 짧은 해시 (v4.3 F13.6). 코드가 바뀐 뒤 재시작하면 달라진다."""
    import hashlib
    files = [os.path.join(HERE, f) for f in BUILD_FILES]
    sd = os.path.join(HERE, "sim_service")
    files += sorted(os.path.join(sd, f) for f in os.listdir(sd) if f.endswith(".py"))
    h = hashlib.sha1()
    for f in files:
        try:
            st_ = os.stat(f)
            h.update(f"{os.path.basename(f)}|{st_.st_size}|{st_.st_mtime_ns};".encode())
        except OSError:
            pass
    return h.hexdigest()[:10]


def remote_token(path=TOKEN_FILE):
    """원격 모드 토큰: 파일에 저장해 재시작해도 같은 주소로 접속할 수 있게 한다 (파일은 .gitignore)."""
    try:
        with open(path, encoding="utf-8") as fp:
            t = fp.read().strip()
        if len(t) >= 16:
            return t
    except OSError:
        pass
    t = secrets.token_urlsafe(24)
    with open(path, "w", encoding="utf-8") as fp:
        fp.write(t)
    return t


class App:
    def __init__(self, args):
        self.args = args
        self.results = os.path.realpath(args.results)
        os.makedirs(self.results, exist_ok=True)
        self.src_dir = os.path.realpath(args.src)
        self.overrides = os.path.realpath(args.overrides)
        self.effects_path = os.path.realpath(args.effects)
        self.scen_dir = os.path.realpath(args.scenarios)
        self.backup_dir = os.path.realpath(args.backup)
        self.targets_path = os.path.realpath(args.targets)
        self.tables_dir = os.path.join(self.results, "tables")
        self.scan_path = os.path.realpath(args.scan or os.path.join(self.results, "fantasy_curves.json"))
        self.host = getattr(args, "host", "127.0.0.1") or "127.0.0.1"
        self.remote = self.host not in LOOPBACK
        self.token = args.token or (remote_token(getattr(args, "token_file", None) or TOKEN_FILE) if self.remote
                                    else secrets.token_urlsafe(24))
        self.port = args.port
        self.store = st.PointStore(os.path.join(self.results, "point_cache"))
        self.engine = cp.Engine(self.store, args.workers)
        self.progressive_stages = [int(s) for s in args.stages.split(",")]
        self.adaptive_stages = [int(s) for s in args.adaptive_stages.split(",")]
        self.epsilon = args.epsilon
        self.lock = threading.RLock()
        self.mon_dir = os.path.realpath(args.monsters) if args.monsters and os.path.isdir(args.monsters) else None
        self.pat_dir = os.path.realpath(args.patterns) if args.patterns and os.path.isdir(args.patterns) else None
        self.monster_table_path = os.path.realpath(args.monster_table)
        self.overlay = ovl.Overlay({"fantasy": self.src_dir, "monster": self.mon_dir, "pattern": self.pat_dir}, self.overrides)
        self.wb = wb.WriteBack(self.src_dir, self.overrides, self.effects_path, self.backup_dir,
                               extra_allowed=[self.scen_dir, self.results, os.path.dirname(self.monster_table_path)],
                               dirs={"monster": self.mon_dir, "pattern": self.pat_dir}, overlay=self.overlay)
        self.monster_data = None
        self.workspace_dir = os.path.realpath(getattr(args, "workspace", None) or os.path.join(self.results, "workspace"))
        self.workspace = wsp.Workspace(self.workspace_dir)
        self.build = code_build()                                   # v4.3 F13.6: 서버·뷰어 버전 확인
        self.started_at = time.strftime("%Y-%m-%dT%H:%M:%S")
        self.load_scan()
        self._disk_sig = self.disk_signature()
        self.restore_file_edits()                 # v4.4 F14.3: JSON 편집 작업 사본(overlay)을 서버 재시작 뒤에도 되살림
        self.load_table()
        self.choose_scan()                        # v4.4 F14.5b: 원본 해시와 맞는 스캔을 우선 올림
        self.wb.snapshot()
        self.set_reference("disk", persist=False)
        self.restore_reference()                  # F14.3: 기준 핀
        self.restore_last_apply()                 # F14.3: 마지막 원본 반영 기록
        self.jobs = jb.JobManager(self)
        # v4.1 F10: 한계효과 학습 (백그라운드, 최하위 우선순위). 근사값은 어디에도 저장하지 않는다.
        self.surrogate_auto = getattr(args, "surrogate_auto", "after_scan")
        self.trainer = sgt.Trainer(self)

    # --- 데이터
    def load_scan(self, path=None):
        self.scan = None
        p = path or self.scan_path
        if os.path.exists(p):
            with open(p, encoding="utf-8") as fp:
                self.scan = json.load(fp)
        self._derive_scan_settings()

    def _derive_scan_settings(self):
        m = (self.scan or {}).get("meta", {})
        if self.scan is None:      # 스캔 파일이 없으면 v4.2 기본 (몬스터 JSON 체력, X = 시작 체력)
            self.x_key = "player.start_hp"
            self.x_values = list(range(100, 301, 20))
            self.fixed = {}
        else:
            self.x_key = m.get("x_param", "monsters.hp_base")
            self.x_values = m.get("x_values") or list(range(200, 1201, 100))
            self.fixed = m.get("fixed_overrides") or {}
        self.seed = m.get("master_seed", "scan1")
        self.target = m.get("target_win_rate", 0.10)
        # 스캔이 기록한 몬스터·피해 모델 (v4.1 이전 파일은 필드가 없거나 구 기본값 → 구버전 설정으로 재현, v4.2 AC-H3)
        self.scan_base = {}
        if self.scan is not None:
            legacy = ms.LEGACY_MONSTERS
            self.scan_base = {
                "monsters.model": m.get("monster_model") or legacy["model"],
                "monsters.damage_model": m.get("damage_model") or legacy["damage_model"],
                "monsters.gimmicks": m.get("monsters_gimmicks") or legacy["gimmicks"],
                # 저장된 스캔은 그 스캔이 쓴 획득 방식으로 이어서 계산한다 (필드가 없는 옛 스캔 = 환상 확정). 스캔이 없으면 새 기본(불씨)
                "rewards.normal_battle.mode": m.get("reward_system") or m.get("reward_mode") or "fantasy",
            }
            if self.scan_base["monsters.model"] == "tier_avg" and not self.fixed:
                self.fixed = {"monsters.act_hp_growth": 2.0}    # v4.1 까지의 동작 그대로 (고정값이 비면 이 값)

    # --- v4.4 F14.5b: 스캔 색인·선택
    def active_scan_id(self):
        return ((self.scan or {}).get("meta") or {}).get("scan_id")

    def _hash_under(self, meta):
        """그 스캔의 설정(X축·고정값·피해 모델)으로 지금 원본의 data_hash 를 계산한다 (파일을 올리지 않고 meta 만 쓴다)."""
        keep = (self.scan, self.x_key, self.x_values, self.fixed, self.seed, self.target, self.scan_base)
        try:
            self.scan = {"meta": meta}
            self._derive_scan_settings()
            cfg = self.cfg_for(self.table_data, self.monster_data)
            return st.data_hash(self.table_hash, st.monster_hash(cfg))
        finally:
            self.scan, self.x_key, self.x_values, self.fixed, self.seed, self.target, self.scan_base = keep

    def scans_listing(self):
        act = self.active_scan_id()
        out = []
        for ent in rs.scan_index(self.results):
            meta = {**ent, "fixed_overrides": ent.get("fixed_overrides") or {}}
            try:
                match = bool(ent.get("data_hash")) and ent["data_hash"] == self._hash_under(meta)
            except Exception:  # noqa: BLE001
                match = False
            out.append({"scan_id": ent["scan_id"], "generated_at": ent.get("generated_at"), "data_hash": ent.get("data_hash"),
                        "x_param": ent.get("x_param"), "match": match, "active": ent["scan_id"] == act})
        return out

    def activate_scan(self, scan_id):
        path = rs.scan_path(self.results, scan_id)
        with self.lock:
            self.load_scan(path)
            self.load_table()
            ref = getattr(self, "ref", None)
            if ref is not None and ref.get("source") == "disk":
                self.set_reference("disk", persist=False)
        return {"scan_id": self.active_scan_id(), "data_hash": self.data_hash}

    def choose_scan(self):
        """현재 data_hash 와 맞는 가장 최근 스캔을 올린다 (기본 파일이 이미 맞으면 그대로). 맞는 것이 없으면 아무것도 안 함."""
        try:
            cur = (self.scan or {}).get("meta")
            if cur and cur.get("data_hash") and cur["data_hash"] == self._hash_under(cur):
                return None
            for ent in rs.scan_index(self.results)[:8]:
                if ent.get("data_hash") and ent["data_hash"] == self._hash_under({**ent, "fixed_overrides": ent.get("fixed_overrides") or {}}):
                    self.activate_scan(ent["scan_id"])
                    return ent["scan_id"]
        except Exception as e:  # noqa: BLE001
            print(f"[scans] 스캔 선택 실패(기본 파일 유지): {e}", flush=True)
        return None

    def save_job_scan(self, job, as_current=True, name=None):
        """완료된 전체 재계산 작업의 결과를 스캔으로 저장 (v4.4 F14.5c). 원본 해시와 같을 때만 현재 스캔으로 올린다."""
        if job is None or job.kind != "scan" or not job.done or getattr(job, "assemble", None) is None:
            raise ValueError("저장할 수 있는 완료된 전체 재계산 작업이 아님")
        data = job.assemble()
        if name:
            data["meta"]["save_name"] = str(name)[:80]
        current = bool(as_current) and getattr(job, "data_hash", None) == self.data_hash
        if current:
            self.save_scan(data, None)
        else:
            d = rs.scans_dir(self.results)
            os.makedirs(d, exist_ok=True)
            rs._atomic_write(os.path.join(d, f"{data['meta']['scan_id']}.json"), json.dumps(data, ensure_ascii=False, separators=(",", ":")))
        return {"scan_id": data["meta"]["scan_id"], "current": current, "data_hash": getattr(job, "data_hash", None),
                "reason": None if current else ("원본 해시와 달라 현재 스캔으로 올리지 않음" if as_current else None)}

    def materialize_monsters(self, mdata):
        h = st.monster_hash_of(mdata)
        os.makedirs(self.tables_dir, exist_ok=True)
        path = os.path.join(self.tables_dir, f"mon_{h}.json")
        if not os.path.exists(path):
            with open(path + ".tmp", "w", encoding="utf-8") as fp:
                json.dump(mdata, fp, ensure_ascii=False)
            os.replace(path + ".tmp", path)
        return path

    def cfg_for(self, table_data, monster_data):
        """시뮬 테이블(환상·몬스터) → 기본 설정 (효과·몬스터 파일은 내용 주소로 저장)."""
        path, _ = st.materialize_table(table_data, self.tables_dir)
        cfg = copy.deepcopy(ms.DEFAULT_CONFIG)
        for k, v in getattr(self, "scan_base", {}).items():
            ms.set_path(cfg, k, v)
        for k, v in self.fixed.items():
            if k != "monsters.table_file":
                ms.set_path(cfg, k, v)
        ms.apply_fantasy_args(cfg, path)
        ms.normalize_models(cfg)
        if monster_data is not None:   # tier_avg 에서도 넣어 둔다 (digits 전환용, 키·해시에는 영향 없음)
            cfg["monsters"]["table_file"] = self.materialize_monsters(monster_data)
        return cfg

    def build_info(self):
        return {"build": self.build, "started_at": self.started_at, "sim_version": ms.SIM_VERSION}

    def disk_signature(self):
        """원본 폴더(환상·몬스터·패턴)와 overrides 의 (파일, 수정 시각, 크기). 바뀌면 서버 밖에서 고친 것."""
        sig = []
        for kind, d in sorted(self.overlay.dirs.items()):
            try:
                names = sorted(os.listdir(d))
            except OSError:
                continue
            for fn in names:
                if fn.endswith(".json"):
                    try:
                        stt = os.stat(os.path.join(d, fn))
                        sig.append((kind, fn, stt.st_mtime_ns, stt.st_size))
                    except OSError:
                        pass
        try:
            stt = os.stat(self.overrides)
            sig.append(("overrides", "", stt.st_mtime_ns, stt.st_size))
        except OSError:
            pass
        return tuple(sig)

    def refresh_from_disk(self):
        """서버 밖에서 원본 JSON 이 바뀌었으면 다시 읽는다. 비교 기준(스냅샷)은 그대로 둔다 → 수정 전/후 고스트."""
        sig = self.disk_signature()
        if sig == self._disk_sig:
            return False
        with self.lock:
            if sig == self._disk_sig:
                return False
            self.overlay.reindex()
            self.load_table()
            self._disk_sig = sig
        return True

    def load_table(self):
        """작업 사본(overlay)을 인메모리로 임포트해 현재 테이블을 만든다. 디스크 원본은 건드리지 않는다."""
        with self.lock:
            self.table_data = self.overlay.build_fantasy_table()
            self.table_hash = st.table_hash(self.table_data)
            self.table_ids = [e["id"] for e in self.table_data["fantasies"]]
            self.monster_data = self.overlay.build_monster_table()
            cfg = self.cfg_for(self.table_data, self.monster_data)
            self.base_cfg = cfg
            self.data_hash = st.data_hash(self.table_hash, st.monster_hash(cfg))
        return self.table_data

    # --- 비교 기준 스냅샷 (§6.8)
    def disk_files(self):
        out = {}
        ov = self.overlay
        for kind, idx in ov.index.items():
            for fid in idx:
                try:
                    out[f"{kind}/{fid}"] = ov.disk(kind, fid)["sha1"]
                except (OSError, ovl.OverlayError):
                    pass
        try:
            out["overrides/overrides"] = ov.disk("overrides", "overrides")["sha1"]
        except (OSError, ovl.OverlayError):
            pass
        return out

    def set_reference(self, source="disk", persist=True):
        """source = "disk": 디스크 원본(작업 사본 무시)을 임포트한 결과, "pinned": 현재 작업 사본.
        persist: 핀을 workspace/reference_<해시>.json.gz 로 남긴다 (F14.3) — 서버를 다시 켜도 고스트 기준이 유지된다."""
        with self.lock:
            if source == "disk":
                ot = {}
                for (k, i) in list(self.overlay.work):
                    ot[(k, i)] = self.overlay.disk(k, i)["text"]
                tdata = self.overlay.build_fantasy_table(ot) if ot else self.table_data
                mdata = self.overlay.build_monster_table(ot) if ot else self.monster_data
            else:
                tdata, mdata = self.table_data, self.monster_data
            cfg = self.cfg_for(tdata, mdata)
            th = st.table_hash(tdata)
            self.ref = rf.make(source, tdata, mdata, cfg, st.data_hash(th, st.monster_hash(cfg)), th, self.disk_files())
            if persist:
                self._persist_reference()
        return self.ref

    # --- v4.4 F14.3 영속화
    def _persist_reference(self):
        try:
            if self.ref["source"] != "pinned":
                self.workspace.set_reference("disk", None)
                self._prune_pins(None)
                return
            name = f"reference_{self.ref['data_hash']}.json.gz"
            path = os.path.join(self.workspace_dir, name)
            os.makedirs(self.workspace_dir, exist_ok=True)
            tmp = path + f".{os.getpid()}.tmp"
            with gzip.open(tmp, "wt", encoding="utf-8", compresslevel=6) as fp:
                json.dump(self.ref, fp, ensure_ascii=False, separators=(",", ":"))
            os.replace(tmp, path)
            self.workspace.set_reference("pinned", name)
            self._prune_pins(name)
        except (OSError, wsp.WorkspaceError) as e:
            print(f"[workspace] 기준 핀 저장 실패: {e}", flush=True)

    def _prune_pins(self, keep):
        try:
            for fn in os.listdir(self.workspace_dir):
                if fn.startswith("reference_") and fn.endswith(".json.gz") and fn != keep:
                    os.remove(os.path.join(self.workspace_dir, fn))
        except OSError:
            pass

    def restore_reference(self):
        info = self.workspace.reference()
        if info.get("source") != "pinned" or not info.get("pinned_file"):
            return False
        name = os.path.basename(info["pinned_file"])
        try:
            with gzip.open(os.path.join(self.workspace_dir, name), "rt", encoding="utf-8") as fp:
                ref = json.load(fp)
            if not all(k in ref for k in ("table_data", "cfg", "data_hash", "table_hash", "disk_files")):
                raise ValueError("형식 오류")
        except (OSError, ValueError, EOFError) as e:
            print(f"[workspace] 기준 핀을 복원하지 못해 디스크 원본 기준으로 시작: {e}", flush=True)
            return False
        ref["source"] = "pinned"
        self.ref = ref
        return True

    def disk_sig_str(self):
        return hashlib.sha1(repr(self.disk_signature()).encode("utf-8")).hexdigest()[:16]

    def file_edits_payload(self):
        out = []
        for kind, fid in self.overlay.dirty():
            d = self.overlay.disk(kind, fid)
            out.append({"kind": kind, "id": fid, "base_sha1": self.overlay.base.get((kind, fid)) or d["sha1"],
                        "new_text": self.overlay.work[(kind, fid)]})
        return out

    def sync_workspace_files(self):
        """JSON 편집 작업 사본이 바뀔 때마다 작업 공간 파일의 file_edits 를 같이 갱신한다 (서버가 소유)."""
        try:
            self.workspace.set_file_edits(self.file_edits_payload())
        except (OSError, wsp.WorkspaceError) as e:
            print(f"[workspace] 작업 사본 저장 실패: {e}", flush=True)

    def apply_file_edits(self, items):
        """저장된 작업 사본을 overlay 에 되돌린다. 복원하지 못한 항목은 held 로 돌려준다."""
        held = []
        for fe in items or []:
            try:
                kind, fid, text = fe["kind"], fe["id"], fe["new_text"]
                d = self.overlay.disk(kind, fid)
                if d["sha1"] != fe.get("base_sha1"):
                    held.append({"type": "file", "item": fe, "reason": "원본 파일이 편집 시작 때와 다름(base_sha1 불일치)"})
                    continue
                text, obj, msgs = self.overlay.validate(kind, fid, text)
                if obj is None or any(m["level"] == "error" for m in msgs):
                    held.append({"type": "file", "item": fe, "reason": "저장된 원문이 지금 검증을 통과하지 못함"})
                    continue
                self.overlay.set_text(kind, fid, text)
            except (KeyError, OSError, ovl.OverlayError) as e:
                held.append({"type": "file", "item": fe, "reason": f"{type(e).__name__}: {e}"})
        return held

    def restore_file_edits(self):
        items = self.workspace.file_edits()
        if not items:
            return
        held = self.apply_file_edits(items)
        if held:
            self.workspace.add_held(held)
        self.sync_workspace_files()

    def restore_last_apply(self):
        """가장 최근 백업의 manifest 가 가리키는 파일들이 아직 반영된 그대로일 때만 '반영 되돌리기'를 되살린다."""
        try:
            names = sorted(n for n in os.listdir(self.backup_dir) if os.path.isfile(os.path.join(self.backup_dir, n, "manifest.json")))
        except OSError:
            return
        if not names:
            return
        bdir = os.path.join(self.backup_dir, names[-1])
        try:
            with open(os.path.join(bdir, "manifest.json"), encoding="utf-8") as fp:
                files = (json.load(fp).get("files") or {})
            ok = bool(files)
            for v in files.values():
                with open(v["path"], "rb") as fp:
                    if not v.get("new_sha1") or hashlib.sha1(fp.read()).hexdigest() != v["new_sha1"]:
                        ok = False
                        break
        except (OSError, ValueError, KeyError):
            return
        if ok:
            self.wb.last = bdir

    def workspace_get(self):
        w = self.workspace.get()
        st = w.get("state")
        out = {**w, "disk_signature": self.disk_sig_str(), "data_hash": self.data_hash, "restore": None}
        if st:
            held_before = st.get("held") or []
            chk = wsp.check_state(st, self.table_data, self.base_cfg, self.monster_data)
            out["restore"] = {"edits": chk["edits"], "cfg_edits": chk["cfg_edits"], "cfg_set": chk["cfg_set"],
                              "held": held_before + chk["held"],
                              "signature_changed": (st.get("base") or {}).get("disk_signature") not in (None, self.disk_sig_str())}
        return out

    def changed(self):
        return rf.changed_set(self.ref, self.table_data, self.monster_data, self.base_cfg)

    def progress_info(self, client=None):
        """진행 중인 작업의 계산 진행 (v4.3 F12, v4.5 F18). 다른 기기·새로고침한 탭이 서버의 계산 상황을 볼 때 쓴다.
        jobs = 끝나지 않은 작업 전부(실행 중 → 대기), 각각 state·finished·서버 콘솔과 같은 마지막 진행 줄(line)과 그 줄의 나이(line_age_s).
        job = 하위 호환용: 끝나지 않은 첫 작업(없으면 가장 최근 작업). done 은 이제 종료 여부(불리언)이고 처리한 판 수는 runs_done 이다."""
        self.jobs.touch(client)

        def one(job):
            if job is None:
                return None
            snap = job.progress.snapshot()
            queued = job.state == "queued"
            line = f"대기 중(앞 작업 {getattr(job, '_ahead', 0)}개)" if queued else job.progress.line()
            return {"id": job.id, "kind": job.kind, "state": job.state, "finished": bool(job.done), "done": bool(job.done),
                    "cancelled": job.cancelled, "age_s": round(time.perf_counter() - job.t0, 1),
                    "line": line, "line_age_s": None if queued else job.progress.line_age_s(), "client": job.client,
                    **{("runs_done" if k == "done" else k): v for k, v in snap.items()}}
        live = [one(j) for j in self.jobs.unfinished()]
        cur = self.jobs.current
        tr = getattr(self.trainer, "current", None)
        return {"jobs": live, "job": live[0] if live else one(cur), "training": one(tr),
                "engine": {"workers": self.engine.workers, "rate": self.engine.rate,
                           "runs_computed": self.engine.runs_computed}}

    def reference_info(self):
        return rf.info(self.ref, self.data_hash, self.changed(), self.disk_files())

    def protected_hashes(self):
        return {self.data_hash, self.ref["data_hash"]}

    def reimport(self):
        """반영 후: 임포터를 프로세스 안에서 다시 돌려 산출물을 갱신하고 작업 사본을 비운다."""
        import_fantasies.main(["--src", self.src_dir, "--out", self.effects_path, "--overrides", self.overrides, "--quiet"])
        if self.mon_dir and self.pat_dir:
            import_monsters.main(["--monsters", self.mon_dir, "--patterns", self.pat_dir, "--out", self.monster_table_path, "--quiet"])
        self.overlay.clear()
        self.overlay.reindex()
        self.load_table()
        self._disk_sig = self.disk_signature()
        self.sync_workspace_files()
        self.set_reference("disk")     # 반영 후 기준 = 반영된 디스크 원본 (§6.8)
        return self.table_data

    def monsters_payload(self):
        m = self.monster_data or {"monsters": [], "pattern_users": {}}
        return {"data_hash": self.data_hash, "model": self.base_cfg["monsters"].get("model"),
                "damage_model": self.base_cfg["monsters"].get("damage_model"), "monsters": m["monsters"],
                "gimmicks": self.base_cfg["monsters"].get("gimmicks", "off"),
                "pattern_users": m.get("pattern_users", {}), "schema": ed.MONSTER_SCHEMA, "sim_reflected": ed.SIM_REFLECTED,
                "sim_reflected_by_model": {"gauss": ed.SIM_REFLECTED, "digits": ed.SIM_REFLECTED_DIGITS},
                "gimmick_schema": ed.GIMMICK_SCHEMA,
                "ambiguous_rules": m.get("ambiguous_rules", [])}

    def monster_log(self, body):
        """v4.5 F16.3: 몬스터 지표 때의 한 판을 같은 시드로 다시 돌려 그 몬스터의 ord 번째 전투 로그를 만든다. run_lock 을 쓰지 않는다."""
        mid, seed, run = body.get("mid"), str(body.get("seed") or "mon1"), body.get("run")
        ord_, expect = body.get("ord"), body.get("expect")
        if not isinstance(mid, str) or not mid:
            raise ValueError("mid 필요")
        if not SEED_RE.match(seed):
            raise ValueError("seed 는 영숫자·-_ 64자 이하")
        if isinstance(run, bool) or not isinstance(run, int) or not 0 <= run < 10_000_000:
            raise ValueError("run 은 0 이상 10,000,000 미만 정수")
        if ord_ is not None and (isinstance(ord_, bool) or not isinstance(ord_, int) or not 0 <= ord_ < 10_000):
            raise ValueError("ord 는 0 이상 정수")
        if expect is not None and (not isinstance(expect, dict) or not set(expect) <= {"turns", "taken", "max_hit", "outcome", "floor"}):
            raise ValueError("expect 는 turns·taken·max_hit·outcome·floor 만")
        with self.lock:
            self.refresh_from_disk()
            cfg, h, mdata, seed, ckey, dh = jb.monster_metrics_setup(self, {"edits": body.get("edits"), "cfg_edits": body.get("cfg_edits"),
                                                                           "cfg_set": body.get("cfg_set"), "x": body.get("x"), "seed": seed})
            if mid not in {m["id"] for m in mdata["monsters"]}:
                raise ValueError(f"몬스터 테이블에 없는 mid: {mid}")
            fants = {e["id"]: e for e in self.table_data["fantasies"]}
            cache = self.__dict__.setdefault("replay_ctx", {})
            ctx = cache.get(ckey)
            if ctx is None:
                ctx = cache[ckey] = ms.SimContext(cfg)
                while len(cache) > REPLAY_CTX_MAX:
                    cache.pop(next(iter(cache)))
        if not _replay_sem.acquire(blocking=False):
            raise ReplayBusy("재생은 동시에 %d개까지 — 잠시 뒤 다시 시도하세요" % REPLAY_MAX)
        box = {}

        def work():
            try:
                box["res"] = bl_.replay(cfg, fants, mid, seed, run, ord_, expect, ctx)
            except BaseException as e:  # noqa: BLE001
                box["err"] = e
            finally:
                _replay_sem.release()
        th = threading.Thread(target=work, daemon=True)
        th.start()
        th.join(REPLAY_TIMEOUT_S)
        if th.is_alive():
            raise ReplayTimeout(f"재생이 {REPLAY_TIMEOUT_S:.0f}초를 넘음")
        if "err" in box:
            raise box["err"]
        box["res"]["data_hash"] = dh
        return box["res"]

    def file_api(self, method, kind, fid, sub, body):
        """JSON 편집기: 종류 + ID 로만 파일을 고른다 (경로는 서버가 해석). 새 파일 생성·삭제 없음."""
        ov = self.overlay
        if kind not in ovl.KINDS:
            raise ovl.OverlayError(f"알 수 없는 파일 종류: {kind}")
        fid = "overrides" if kind == "overrides" else fid
        if method == "GET":
            return ov.info(kind, fid)
        if sub == "revert":
            with self.lock:
                ov.revert(kind, fid)
                self.load_table()
                self.sync_workspace_files()
            return {**ov.info(kind, fid), "data_hash": self.data_hash, "reference": self.reference_info()}
        if sub == "view":   # 숫자 UI 편집을 텍스트에 반영해 보여 주기 (양방향 동기화)
            pv = self.wb.preview(self.table_data, body.get("edits", []), self.monster_data)
            info = ov.info(kind, fid)
            key = self.wb.key_of(kind, info["file"])
            f = pv["files"].get(key)
            if f:
                text = f["new_bytes"].decode("utf-8-sig").replace("\r\n", "\n")
                return {**info, "text": text, "patched": [r["token_new"] for r in f["rows"]], "rows": f["rows"]}
            return {**info, "patched": [], "rows": []}
        text = body.get("text")
        if not isinstance(text, str):
            raise ValueError("text 필요")
        text, obj, msgs = ov.validate(kind, fid, text)
        errors = [m for m in msgs if m["level"] == "error"]
        dry = None
        if not errors:
            try:
                dry = ov.dry_run(kind, fid, text, self.table_data, self.monster_data)
                if dry["fantasy_table"] is not None:   # 시뮬레이터가 읽을 수 있는 테이블인지 확인
                    for e in dry["fantasy_table"]["fantasies"]:
                        for ef in e.get("effects", []):
                            if ef.get("type") not in ms.EFFECT_TYPES:
                                raise ValueError(f"{e['id']}: 알 수 없는 효과 타입 {ef.get('type')}")
            except Exception as ex:  # noqa: BLE001
                errors.append({"level": "error", "stage": "dryrun", "msg": f"dry-run 임포트 실패: {ex}"})
                msgs.append(errors[-1])
        ok = not errors
        out = {"ok": ok, "messages": msgs, "saved": False}
        if dry:
            fh = st.table_hash(dry["fantasy_table"]) if dry["fantasy_table"] is not None else self.table_hash
            out["dryrun"] = {"changes": dry["changes"], "warnings": dry["warnings"], "affected": dry["affected"],
                             "table_hash": fh,
                             "monster_hash": st.monster_hash_of(dry["monster_table"]) if dry["monster_table"] is not None else None}
        if method == "PUT" and ok:
            with self.lock:
                prev = self.data_hash
                ov.set_text(kind, fid, text)
                self.load_table()
                self.sync_workspace_files()
            out["saved"] = True
            out["data_hash"] = self.data_hash
            # 공백·키 순서·이름처럼 시뮬 값이 같은 변경 → 재계산 불필요 (AC-R2)
            out["sim_changed"] = prev != self.data_hash
            out["reference"] = self.reference_info()
            out["info"] = {k: v for k, v in ov.info(kind, fid).items() if k != "text"}
        return out

    def save_scan(self, data, name=None):
        fs.write_outputs(data, self.results, self.scan_path if not name else os.path.join(self.results, f"{name}.json"))
        if not name:
            self.load_scan()

    def balance_targets(self):
        try:
            with open(self.targets_path, encoding="utf-8") as fp:
                return json.load(fp)
        except (OSError, ValueError):
            return None

    def html(self):
        data = self.scan or {"meta": {"effect_mode": "table", "x_values": self.x_values, "x_param": self.x_key,
                                      "master_seed": self.seed, "schema": 2, "table_hash": self.table_hash,
                                      "fixed_overrides": self.fixed, "target_win_rate": self.target},
                             "fantasies": fs.fantasy_meta({e["id"]: e for e in self.table_data["fantasies"]},
                                                          {e["id"]: e["grade"] for e in self.table_data["fantasies"]},
                                                          self.table_ids),
                             "baseline": {"points": []}, "curves": {}}
        data = build_viewer.attach_extras(data, self.results)
        return build_viewer.build(data, server={"token": self.token, "port": self.port, "remote": self.remote},
                                  targets=self.balance_targets())

    def fantasies_payload(self):
        out = []
        for e in self.table_data["fantasies"]:
            info = ed.fantasy_edit_info(e)
            out.append({k: e.get(k) for k in ("id", "name", "grade", "fidelity", "notes", "mapping", "available",
                                               "description", "fidelity_digits", "notes_digits")}
                       | {"effects": e.get("effects", [])} | info)
        return {"table_hash": self.table_hash, "data_hash": self.data_hash, "fantasies": out,
                "dirty_files": [{"kind": k, "id": i} for k, i in self.overlay.dirty()]}


# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------
class Handler(BaseHTTPRequestHandler):
    server_version = "MatchUpSim/2"
    app: App = None

    def log_message(self, fmt, *args):  # 조용히
        if os.environ.get("MATCHUPSIM_HTTP_LOG"):
            super().log_message(fmt, *args)

    # --- 보안
    def _host_ok(self):
        p = self.app.port
        host = self.headers.get("Host", "")
        if self.app.remote:     # 원격 모드: 페이지·API 모두 토큰으로 막는다. Origin 은 같은 출처만.
            origin = self.headers.get("Origin")
            return origin is None or origin == f"http://{host}"

        if host not in (f"127.0.0.1:{p}", f"localhost:{p}"):
            return False
        origin = self.headers.get("Origin")
        if origin is not None and origin not in (f"http://127.0.0.1:{p}", f"http://localhost:{p}"):
            return False
        return True

    def _deny(self, code, msg):
        if code >= 400 and self.command in ("POST", "PUT") and not getattr(self, "_body_read", False):
            self._drain()      # 본문을 안 읽고 응답하면 Windows 에서 클라이언트 연결이 끊긴다 (WinError 10053)
        self._json({"error": msg}, code)

    def _guard_api(self, write=False):
        if not self._host_ok():
            self._deny(403, "Host/Origin 거부")
            return False
        if not secrets.compare_digest(self.headers.get("X-MatchUp-Token", ""), self.app.token):
            self._deny(403, "토큰 없음 또는 불일치")
            return False
        if write:
            ctype = (self.headers.get("Content-Type") or "").split(";")[0].strip().lower()
            if ctype != "application/json":
                self._deny(415, "Content-Type 은 application/json 만 허용")
                return False
        return True

    def _drain(self, limit=16 * 1024 * 1024):
        """거부할 요청의 본문을 읽어 버린다 (안 읽고 응답하면 클라이언트 쪽에서 연결이 끊길 수 있다)."""
        n = min(int(self.headers.get("Content-Length") or 0), limit)
        self._body_read = True
        while n > 0:
            chunk = self.rfile.read(min(n, 65536))
            if not chunk:
                break
            n -= len(chunk)

    def _body(self):
        n = int(self.headers.get("Content-Length") or 0)
        if n > MAX_BODY:
            raise ValueError("요청이 너무 큼")
        raw = self.rfile.read(n) if n else b"{}"
        self._body_read = True
        return json.loads(raw.decode("utf-8") or "{}")

    def _json(self, obj, code=200):
        b = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(b)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(b)

    # --- 라우팅
    def do_GET(self):
        path = urlparse(self.path).path
        if path in ("/", "/index.html"):
            if not self._host_ok():
                return self._deny(403, "Host/Origin 거부")
            if self.app.remote:
                k = (parse_qs(urlparse(self.path).query).get("k") or [""])[0]
                if not secrets.compare_digest(k, self.app.token):
                    return self._deny(403, "토큰 필요: 서버 창에 표시된 주소(/?k=…)로 여세요")
            self.app.refresh_from_disk()
            b = self.app.html().encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(b)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(b)
            return
        if not path.startswith("/api/"):
            return self._deny(404, "없음")
        if path.startswith("/api/export/dl/"):        # 큰 파일: 1회용 티켓이 인증을 대신한다 (브라우저가 직접 받으므로 헤더를 못 붙임)
            return self._export_dl(path.split("/")[4])
        if not self._guard_api():
            return
        try:
            if path == "/api/export":
                return self._json(exp.catalog())
            if path in ("/api/ping", "/api/state", "/api/fantasies", "/api/monsters"):
                self.app.refresh_from_disk()
            if path == "/api/ping":
                return self._json({"ok": True, "sim_version": ms.SIM_VERSION, "table_hash": self.app.table_hash,
                                   "data_hash": self.app.data_hash, **self.app.build_info()})
            if path == "/api/state":
                a = self.app
                return self._json({"table_hash": a.table_hash, "data_hash": a.data_hash, **a.build_info(),
                                   "dirty_files": [{"kind": k, "id": i} for k, i in a.overlay.dirty()],
                                   "has_monsters": a.monster_data is not None,
                                   "monster_model": a.base_cfg["monsters"].get("model"),
                                   "scan_meta": (a.scan or {}).get("meta"), "scan_id": a.active_scan_id(),
                                   "x_key": a.x_key, "x_values": a.x_values, "seed": a.seed,
                                   "stages": a.progressive_stages, "adaptive_stages": a.adaptive_stages,
                                   "epsilon": a.epsilon, "last_apply": a.wb.last,
                                   "current_job": a.jobs.current.id if a.jobs.current else None,
                                   "base_cfg": {k: ed.get_path(a.base_cfg, k) for k in ed.CFG_EDITABLE}})
            if path == "/api/progress":
                cl = (parse_qs(urlparse(self.path).query).get("client") or [None])[0]
                return self._json({**self.app.progress_info(cl), **self.app.build_info(), "data_hash": self.app.data_hash,
                                   "disk_sig": self.app.disk_sig_str()})
            if path == "/api/fantasies":
                return self._json(self.app.fantasies_payload())
            if path == "/api/reference":
                return self._json(self.app.reference_info())
            if path == "/api/workspace":
                self.app.refresh_from_disk()
                return self._json(self.app.workspace_get())
            if path == "/api/apply/history":
                return self._json({"history": self.app.wb.history()})
            if path == "/api/workspace/history":
                return self._json({"history": self.app.workspace.history()})
            if path == "/api/scans":
                return self._json({"scans": self.app.scans_listing(), "active": self.app.active_scan_id()})
            if path == "/api/results":
                kind = (parse_qs(urlparse(self.path).query).get("kind") or [""])[0]
                return self._json({"kind": kind, "results": rs.list_(self.app.results, kind)})
            if path.startswith("/api/results/"):
                parts = [unquote(x) for x in path.split("/")[3:]]
                if len(parts) != 2:
                    return self._deny(400, "형식: /api/results/<kind>/<key>")
                return self._json(rs.get(self.app.results, parts[0], parts[1]))
            if path.startswith("/api/surrogate/"):
                return self._json(self._surrogate_get(path, parse_qs(urlparse(self.path).query)))
            if path == "/api/monsters":
                return self._json(self.app.monsters_payload())
            if path.startswith("/api/files/"):
                parts = [unquote(x) for x in path.split("/")[3:]]
                if len(parts) != 2:
                    return self._deny(400, "형식: /api/files/<kind>/<id>")
                return self._json(self.app.file_api("GET", parts[0], parts[1], None, {}))
            if path == "/api/schema":
                return self._json(ed.schema_json())
            if path == "/api/targets":
                return self._json(self.app.balance_targets() or {})
            if path == "/api/scenarios":
                return self._json({"scenarios": ed.list_scenarios(self.app.scen_dir)})
            if path.startswith("/api/scenarios/"):
                name = unquote(path[len("/api/scenarios/"):])
                scen = ed.load_scenario(self.app.scen_dir, name)
                chk = ed.check_scenario(scen, self.app.table_data, self.app.base_cfg, self.app.monster_data,
                                        lambda k, i: self.app.overlay.disk(k, "overrides" if k == "overrides" else i)["sha1"])
                return self._json({"scenario": scen, **chk, "table_hash": self.app.table_hash,
                                   "data_hash": self.app.data_hash})
            if path.startswith("/api/jobs/") and path.endswith("/events"):
                return self._sse(path.split("/")[3])
            if path.startswith("/api/jobs/"):
                job = self.app.jobs.jobs.get(path.split("/")[3])
                if not job:
                    return self._deny(404, "작업 없음")
                return self._json({"id": job.id, "kind": job.kind, "done": job.done, "events": len(job.events)})
            return self._deny(404, "없음")
        except (ValueError, KeyError, FileNotFoundError, ovl.OverlayError) as e:
            return self._deny(400, str(e))

    def do_PUT(self):
        path = urlparse(self.path).path
        if path == "/api/workspace":
            return self._workspace_put()
        if not path.startswith("/api/files/"):
            return self._deny(405, "PUT 은 /api/files/<kind>/<id> 와 /api/workspace 만 허용")
        if not self._guard_api(write=True):
            return
        try:
            if int(self.headers.get("Content-Length") or 0) > MAX_FILE_BODY:
                self._drain()
                return self._deny(413, "본문이 1MB 를 넘음")
            parts = [unquote(x) for x in path.split("/")[3:]]
            if len(parts) != 2:
                return self._deny(400, "형식: /api/files/<kind>/<id>")
            return self._json(self.app.file_api("PUT", parts[0], parts[1], None, self._body()))
        except (ovl.OverlayError, wb.WriteBackError) as e:
            return self._deny(400, str(e))
        except (ValueError, KeyError, TypeError) as e:
            return self._deny(400, f"{type(e).__name__}: {e}")

    # --- v4.4 F15 내려받기
    def _export_dl(self, t):
        if not self._host_ok():
            return self._deny(403, "Host/Origin 거부")
        v = exp.use_ticket(unquote(t))
        if v is None:
            return self._deny(403, "티켓이 없거나 만료됨·이미 사용됨")
        try:
            return self._export_send(v["dataset"], v["body"])
        except (ValueError, KeyError, TypeError, FileNotFoundError) as e:
            return self._deny(400, f"{type(e).__name__}: {e}")

    def _export_send(self, dataset, body):
        a = self.app
        try:
            exp.acquire()
        except exp.ExportBusy as e:
            return self._deny(429, str(e))
        try:
            a.refresh_from_disk()
            try:
                with a.lock:                                  # 서버 잠금은 설정·계획을 준비하는 동안만
                    ex = exp.build(a, dataset, body)
            except exp.ExportError as e:
                return self._deny(e.code, str(e))
            meta = {k: v for k, v in ex.meta.items() if k != "missing"}
            mh = json.dumps(meta, ensure_ascii=True, separators=(",", ":"))
            if len(mh) > 6000:
                mh = json.dumps({k: meta.get(k) for k in ("dataset", "generated_at", "build", "sim_version", "master_seed",
                                                           "x_param", "base_data_hash", "view_data_hash", "rows", "missing_count")},
                                ensure_ascii=True, separators=(",", ":"))
            self.send_response(200)
            self.send_header("Content-Type", ex.ctype)
            self.send_header("Content-Disposition", f"attachment; filename=\"{ex.filename}\"; filename*=UTF-8''{ex.filename}")
            self.send_header("X-MatchUp-Meta", mh)
            self.send_header("X-MatchUp-Missing", str(ex.missing))
            self.send_header("Cache-Control", "no-store")
            self.send_header("Connection", "close")
            self.end_headers()
            try:
                for ch in ex.chunks:
                    self.wfile.write(ch)
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                return
        finally:
            exp.release()

    def _workspace_put(self):
        if not self._guard_api(write=True):
            return
        try:
            body = self._body()
            a = self.app
            try:
                res = a.workspace.put(int(body.get("rev") or 0), str(body.get("client") or ""), body.get("state"),
                                      force=bool(body.get("force")))
            except wsp.WorkspaceConflict as c:
                return self._json({"error": str(c), **c.cur}, 409)
            except wsp.WorkspaceTooLarge as e:
                return self._deny(413, str(e))
            except wsp.WorkspaceError as e:
                return self._deny(400, str(e))
            return self._json({**res, "disk_signature": a.disk_sig_str()})
        except (ValueError, KeyError, TypeError) as e:
            return self._deny(400, f"{type(e).__name__}: {e}")

    def do_DELETE(self):
        path = urlparse(self.path).path
        if not self._guard_api():
            return
        if path == "/api/workspace":
            a = self.app
            with a.lock:
                res = a.workspace.clear(self.headers.get("X-MatchUp-Client"))
                a.overlay.clear()                       # 초기화는 JSON 편집 작업 사본도 비운다
                a.load_table()
            return self._json({**res, "data_hash": a.data_hash})
        if path.startswith("/api/files/"):
            return self._deny(405, "파일 삭제는 지원하지 않음")
        if path.startswith("/api/jobs/"):
            job = self.app.jobs.cancel(path.split("/")[3])
            return self._json({"cancelled": bool(job)})
        return self._deny(404, "없음")

    def do_POST(self):
        path = urlparse(self.path).path
        if not path.startswith("/api/"):
            return self._deny(404, "없음")
        if not self._guard_api(write=True):
            return
        try:
            body = self._body()
            a = self.app
            if path.startswith("/api/files/"):
                if int(self.headers.get("Content-Length") or 0) > MAX_FILE_BODY:
                    self._drain()
                    return self._deny(413, "본문이 1MB 를 넘음")
                parts = [unquote(x) for x in path.split("/")[3:]]
                if len(parts) != 3 or parts[2] not in ("dryrun", "view", "revert"):
                    return self._deny(400, "형식: /api/files/<kind>/<id>/(dryrun|view|revert) — 새 파일 생성은 지원하지 않음")
                return self._json(a.file_api("POST", parts[0], parts[1], parts[2], body))
            if path in ("/api/jobs", "/api/estimate"):
                a.refresh_from_disk()
            if path == "/api/jobs":
                job = a.jobs.submit(body.get("kind"), body)
                return self._json({"id": job.id})
            if path.startswith("/api/surrogate/"):
                return self._json(self._surrogate_post(path, body))
            if path == "/api/monster_log":
                try:
                    return self._json(a.monster_log(body))
                except ReplayBusy as e:
                    return self._deny(429, str(e))
                except ReplayTimeout as e:
                    return self._deny(504, str(e))
                except LookupError as e:
                    return self._deny(400, f"{e}")
            if path == "/api/export/estimate":
                a.refresh_from_disk()
                return self._json(exp.estimate(a, body.get("id"), body))
            if path == "/api/export/ticket":
                return self._json(exp.make_ticket(body.get("id"), body))
            if path.startswith("/api/export/"):
                return self._export_send(unquote(path.split("/")[3]), body)
            if path.startswith("/api/scans/") and path.endswith("/activate"):
                with a.lock:
                    return self._json(a.activate_scan(unquote(path.split("/")[3])))
            if path.startswith("/api/jobs/") and path.endswith("/save"):
                return self._json(a.save_job_scan(a.jobs.jobs.get(path.split("/")[3]), body.get("as_current", True), body.get("name")))
            if path == "/api/results/lookup":
                kind = body.get("kind")
                cfg, h = jb.prepare(a, body.get("edits"), body.get("cfg_edits"), body.get("cfg_set"))
                hit = rs.lookup(a.results, kind, body.get("params") or {}, jb.dh_of(cfg, h),
                                rs.cfg_tag_of(body.get("cfg_edits"), body.get("cfg_set")))
                return self._json({"found": hit is not None, "result": hit})
            if path.startswith("/api/workspace/history/") and path.endswith("/restore"):
                hid = unquote(path.split("/")[4])
                with a.lock:
                    res = a.workspace.restore(hid, body.get("client"))
                    a.overlay.clear()
                    held = a.apply_file_edits(res["file_edits"])
                    if held:
                        a.workspace.add_held(held)
                    a.load_table()
                    a.sync_workspace_files()
                return self._json({"rev": res["rev"], "data_hash": a.data_hash})
            if path == "/api/reference/pin":
                a.set_reference("disk" if body.get("source") == "disk" else "pinned")
                return self._json(a.reference_info())
            if path == "/api/cache/prune":
                mb = float(body.get("max_mb", 500))
                if not (0 <= mb <= 1e6):
                    raise ValueError("max_mb 범위")
                res = a.store.prune(int(mb * 1024 * 1024), a.protected_hashes())
                return self._json({**res, "protected": sorted(a.protected_hashes())})
            if path == "/api/estimate":
                return self._json(jb.estimate(a, body))
            if path == "/api/scenarios":
                fe = [{"kind": k, "id": i, "base_sha1": a.overlay.base.get((k, i)), "new_text": a.overlay.text(k, i)}
                      for k, i in a.overlay.dirty()]
                p, data = ed.save_scenario(a.scen_dir, body.get("name", ""), body.get("edits", []),
                                           body.get("cfg_edits", []), a.data_hash, body.get("note", ""),
                                           body.get("results"), body.get("applied"), fe, body.get("cfg_set"), body.get("view"))
                return self._json({"saved": os.path.basename(p), "scenario": data})
            if path == "/api/apply/preview":
                pv = a.wb.preview(a.table_data, body.get("edits", []), a.monster_data)
                files = {fn: {k: v for k, v in f.items() if k != "new_bytes"} for fn, f in pv["files"].items()}
                changed = a.wb.changed_since_snapshot(list(set(list(pv["files"]) + (["@overrides"] if pv["overrides"] else []))))
                return self._json({**pv, "files": files, "externally_changed": changed, "note": wb.UNITY_NOTE})
            if path == "/api/apply":
                with a.lock:
                    # JSON 편집기로 고친 파일: dry-run 테이블(작업 사본) = 재임포트 결과인지 확인 (AC-J4)
                    had_raw = bool(a.overlay.dirty())
                    exp_f = st.table_hash(ed.apply_edits(a.table_data, body.get("edits", []))[0])
                    res = a.wb.apply(a.table_data, body.get("edits", []), a.reimport,
                                     selected_files=body.get("files"), include_overrides=body.get("include_overrides", True),
                                     monster_table=a.monster_data)
                    res["dryrun_matches_reimport"] = (not had_raw) or body.get("files") is not None or a.table_hash == exp_f
                    if res.get("monster_rows") and a.monster_data is not None:   # 몬스터 라운드트립
                        after = ed.apply_monster_edits(a.monster_data, [])[0]
                        by = {m["id"]: m for m in after["monsters"]}
                        for r in res["monster_rows"]:
                            m = by.get(r.get("mid"))
                            got = None
                            if m and r["target"] == "gimmick":
                                got = (m.get("sim") or [{}] * (r["gi"] + 1))[r["gi"]].get(r["key"])
                            elif m and r["target"] == "monster":
                                got = m.get(r["key"])
                            elif m and r["target"] == "pattern":
                                got = m["patterns"][r["step"]].get(ed.PATTERN_FIELD[r["key"]])
                            elif r["target"] == "pattern" and r.get("pid"):
                                got = next((p.get(ed.PATTERN_FIELD[r["key"]]) for mm in by.values() for p in mm["patterns"]
                                            if p["key"] == r["pid"]), None)
                            if got is None or not ed.num_eq(got, r["new"]):
                                res["roundtrip_mismatch"].append({**r, "got": got})
                if body.get("scenario"):
                    try:
                        scen = ed.load_scenario(a.scen_dir, body["scenario"])
                        base = scen.get("base") or {}
                        ed.save_scenario(a.scen_dir, scen["name"], scen.get("edits", []), scen.get("cfg_edits", []),
                                         base.get("data_hash") or base.get("table_hash") or a.data_hash, scen.get("note", ""),
                                         scen.get("results"), {"at": res["at"], "files": res["files"], "backup_dir": res["backup_dir"]},
                                         scen.get("file_edits"), scen.get("cfg_set"), scen.get("view"))
                    except (OSError, ValueError, KeyError, TypeError) as ex:     # 조용히 삼키지 않는다 (v4.4 F14.7)
                        res["scenario_update_error"] = f"{type(ex).__name__}: {ex}"
                return self._json({**res, "table_hash": a.table_hash, "data_hash": a.data_hash})
            if path == "/api/apply/revert":
                with a.lock:
                    target = a.wb.last
                    if body.get("backup"):
                        target = os.path.join(a.backup_dir, os.path.basename(body["backup"]))
                    if not target:
                        return self._deny(400, "되돌릴 반영 기록 없음")
                    res = a.wb.revert(target, a.reimport)
                return self._json({"restored": res["restored"], "table_hash": a.table_hash, "data_hash": a.data_hash})
            if path == "/api/trace":
                return self._json(self._trace(body))
            return self._deny(404, "없음")
        except wb.WriteBackError as e:
            return self._deny(409, str(e))
        except ovl.OverlayError as e:
            return self._deny(400, str(e))
        except (ValueError, KeyError, TypeError, FileNotFoundError) as e:
            return self._deny(400, f"{type(e).__name__}: {e}")

    # --- v4.1 한계효과 미리보기
    def _surrogate_get(self, path, q):
        a = self.app
        one = lambda k: (q.get(k) or [None])[0]  # noqa: E731
        if path == "/api/surrogate/audit":
            return {"records": sgt.read_audit(a)}
        if path == "/api/surrogate/model":
            m = sgt.load_model(a, one("kind") or "fantasy", one("id"), one("field"), probe=one("probe") == "1")
            if m is None:
                raise ValueError("학습된 모델 없음")
            if "strong_hash" in m:
                m["validity"], m["validity_reason"] = sgt.status_for(a, m)
            return m
        if path == "/api/surrogate/predict":
            m = sgt.load_model(a, one("kind") or "fantasy", one("id"), one("field"))
            if m is None:
                raise ValueError("학습된 모델 없음")
            th, x = float(one("theta")), float(one("x"))
            anc = one("anchor")
            out = sg.predict(m, sg_x(m, x), th, float(anc) if anc is not None else None,
                             float(one("theta_anchor")) if one("theta_anchor") is not None else None)
            mg = sg.marginal(m, sg_x(m, x), th)
            return {**out, "marginal": mg}
        raise ValueError("없음")

    def _surrogate_post(self, path, body):
        a = self.app
        if path == "/api/surrogate/fit":
            targets = body.get("targets") or sgt.fantasy_targets(a)
            for t in targets:
                if t.get("kind") not in ("fantasy", "monster") or (t.get("kind") == "monster" and t.get("field") not in ("hp", "strength")):
                    raise ValueError(f"근사 대상이 아님: {t}")
            job = a.trainer.submit("surrogate_fit", {**body, "targets": targets})
            return {"id": job.id, "estimate": sgt.estimate(a, targets, int(body.get("k", 6)), body.get("n"),
                                                           body.get("x_points"), body.get("x_sel"))}
        if path == "/api/surrogate/estimate":
            targets = body.get("targets") or sgt.fantasy_targets(a)
            return sgt.estimate(a, targets, int(body.get("k", 6)), body.get("n"), body.get("x_points"), body.get("x_sel"))
        if path == "/api/surrogate/probe_fit":
            job = a.trainer.submit("surrogate_probe", body)
            return {"id": job.id}
        if path == "/api/surrogate/models":
            out = []
            for m in sgt.list_models(a):
                if "strong_hash" in m:
                    m["validity"], m["validity_reason"] = sgt.status_for(a, m, body.get("edits") or [],
                                                                         body.get("cfg_edits") or [], body.get("cfg_set"))
                out.append(m)
            return {"models": out, "candidates": sgt.fantasy_targets(a), "auto": a.surrogate_auto,
                    "training": a.trainer.current.id if a.trainer.current else None}
        if path == "/api/surrogate/audit":
            return sgt.append_audit(a, body)
        raise ValueError("없음")

    def _trace(self, body):
        a = self.app
        cfg, h = jb.prepare(a, body.get("edits"), body.get("cfg_edits"), body.get("cfg_set"))
        x = body.get("x", a.x_values[len(a.x_values) // 2])
        ms.set_path(cfg, a.x_key, x)
        fid = body["fid"]
        if body.get("seed"):
            res = trc.compare(cfg, str(body["seed"]), fid)
            return res
        # 시드 제안
        rb, rf = cp.make_req(cfg, [], a.seed, h), cp.make_req(cfg, [fid], a.seed, h)
        recs = a.engine.ensure([rb, rf], int(body.get("n", 300)))
        return {"suggest": trc.suggest_seeds(recs[rb["key"]], recs[rf["key"]], a.seed)}

    def _sse(self, job_id):
        job = self.app.jobs.jobs.get(job_id)
        if not job:
            return self._deny(404, "작업 없음")
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "close")
        self.end_headers()
        i = 0
        try:
            while True:
                evs, done = job.wait_events(i, timeout=10)
                if not evs and not done:
                    self.wfile.write(b": ping\n\n")
                    self.wfile.flush()
                    continue
                for e in evs:
                    self.wfile.write(f"event: {e['type']}\ndata: {json.dumps(e, ensure_ascii=False)}\n\n".encode("utf-8"))
                i += len(evs)
                self.wfile.flush()
                if done and i >= len(job.events):
                    return
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            return


def sg_x(model, x):
    """모델의 X 키(문자열)와 같은 값으로 맞춘다 (600 ↔ 600.0)."""
    for k in model.get("x", {}):
        if abs(float(k) - x) < 1e-9:
            return float(k) if "." in k else int(float(k))
    return x


def local_ips():
    """이 PC 의 IPv4 주소 (원격 접속 안내용)."""
    ips = set()
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ips.add(info[4][0])
    except OSError:
        pass
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sk:   # 패킷을 보내지 않음 (라우팅 표만 조회)
            sk.connect(("10.255.255.255", 1))
            ips.add(sk.getsockname()[0])
    except OSError:
        pass
    return sorted(i for i in ips if not i.startswith("127.")) or ["<이 PC 의 IP>"]


def make_server(args):
    app = App(args)
    Handler.app = app
    host = getattr(args, "host", "127.0.0.1") or "127.0.0.1"
    cls = ThreadingHTTPServer
    if ":" in host:      # IPv6
        cls = type("V6Server", (ThreadingHTTPServer,), {"address_family": socket.AF_INET6})
    srv = cls((host, args.port), Handler)
    srv.daemon_threads = True
    if args.port == 0:
        app.port = srv.server_address[1]
    return srv, app


def parse_args(argv=None):
    ap = argparse.ArgumentParser(description="Match Up 뷰어 로컬 서버")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--host", default="127.0.0.1",
                    help="바인드 주소. 0.0.0.0 = 원격 모드 (같은 네트워크의 다른 기기에서 접속, 토큰 필요)")
    ap.add_argument("--token-file", default=TOKEN_FILE, help="원격 모드 토큰 저장 파일")
    ap.add_argument("--open", action="store_true", help="브라우저 자동 열기")
    ap.add_argument("--results", default=os.path.join(HERE, "sim_results"))
    ap.add_argument("--scan", help="뷰어에 올릴 스캔 JSON (기본 <results>/fantasy_curves.json)")
    ap.add_argument("--effects", default=os.path.join(HERE, "fantasy_effects.json"))
    ap.add_argument("--src", default=DEFAULT_SRC, help="원본 fantasies 폴더 (반영 대상)")
    ap.add_argument("--monsters", default=DEFAULT_MON, help="원본 monsters 폴더")
    ap.add_argument("--patterns", default=DEFAULT_PAT, help="원본 patterns 폴더")
    ap.add_argument("--monster-table", default=os.path.join(HERE, "monster_table.json"))
    ap.add_argument("--overrides", default=os.path.join(HERE, "fantasy_effects.overrides.json"))
    ap.add_argument("--scenarios", default=os.path.join(HERE, "scenarios"))
    ap.add_argument("--workspace", help="작업 공간(자동 저장) 폴더 (기본 <results>/workspace) — v4.4 F14")
    ap.add_argument("--backup", default=os.path.join(HERE, ".matchupsim_backup"))
    ap.add_argument("--targets", default=os.path.join(HERE, "balance_targets.json"))
    ap.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2) - 1))
    ap.add_argument("--stages", default="300,1000,3000", help="편집 재계산 점진 단계 (시드 수)")
    ap.add_argument("--adaptive-stages", default="500,1500,3000")
    ap.add_argument("--epsilon", type=float, default=0.015)
    ap.add_argument("--surrogate-auto", choices=["after_scan", "manual"], default="after_scan",
                    help="한계효과 근사 학습 시점 (v4.1 Q30): 스캔 직후 백그라운드 / 수동 버튼만")
    ap.add_argument("--token", help=argparse.SUPPRESS)
    return ap.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    srv, app = make_server(args)
    url = f"http://127.0.0.1:{app.port}/" + (f"?k={app.token}" if app.remote else "")
    print(f"Match Up 뷰어 서버: {url}  (Ctrl+C 로 종료)")
    if app.remote:
        print("  원격 모드 — 다른 기기에서 아래 주소 중 하나로 여세요 (토큰 포함, 외부에 공유하지 말 것):")
        for ip in local_ips():
            print(f"    http://{ip}:{app.port}/?k={app.token}")
        print("  접속이 안 되면 이 PC 방화벽에서 TCP", app.port, "인바운드를 허용하세요 (README '원격 서버').")
    print(f"  원본: {app.src_dir}\n  효과 테이블: {app.effects_path} (해시 {app.table_hash})\n  워커 {app.engine.workers}개")
    if args.open:
        threading.Timer(0.5, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        srv.server_close()
        app.engine.close()


if __name__ == "__main__":
    main()
