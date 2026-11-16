# -*- coding: utf-8 -*-
"""작업 공간 (v4.4 F14): 뷰어에서 바꾼 것을 서버에 자동 저장한다.

파일 `<workspace>/current.json`:
  {"rev": n, "updated_at": ..., "updated_by": client,
   "state": {...},                 # 뷰어가 소유 (편집·실행 취소·보기 상태·보류 ...)
   "file_edits": [...],            # 서버가 소유: JSON 편집 작업 사본(overlay) — 뷰어가 보내도 무시
   "reference": {...}}             # 서버가 소유: 비교 기준 핀 정보
- 쓰기는 임시 파일 → os.replace (원자적, OneDrive 동기화 때문에 PermissionError 는 짧게 재시도).
- `rev` 낙관적 동시성: PUT 의 rev 가 서버 값과 다르면 충돌 (force 면 덮어씀).
- 갱신할 때 이전 파일을 history/ 에 보관한다 (최대 HISTORY_MAX 개; 자동 저장이 잦아 보관은 HISTORY_GAP_S 초에 한 번).
- 크기 상한 MAX_BYTES: 넘으면 undo/redo 를 줄이고, 그래도 넘으면 WorkspaceTooLarge.
"""
from __future__ import annotations

import json
import os
import re
import threading
import time
from datetime import datetime

MAX_BYTES = 5 * 1024 * 1024
HISTORY_MAX = 20
HISTORY_GAP_S = 30.0
UNDO_KEEP = 50
SERVER_KEYS = ("file_edits", "reference")          # state 안에서 서버가 소유하는 키
HIST_ID = re.compile(r"^\d{8}-\d{6}-\d{6}$")


class WorkspaceError(ValueError):
    pass


class WorkspaceTooLarge(WorkspaceError):
    pass


class WorkspaceConflict(WorkspaceError):
    def __init__(self, cur):
        super().__init__("다른 기기에서 먼저 저장했습니다")
        self.cur = cur


def empty_state():
    return {"schema": 1, "base": {}, "edits": [], "cfg_edits": [], "cfg_set": {}, "undo": [], "redo": [],
            "view": {}, "reference": {"source": "disk", "pinned_file": None}, "last_scenario": None,
            "json_draft": None, "held": []}


def _atomic_write(path, data: bytes, retries=5):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + f".{os.getpid()}.{threading.get_ident()}.tmp"
    with open(tmp, "wb") as fp:
        fp.write(data)
    last = None
    for k in range(retries):
        try:
            os.replace(tmp, path)
            return
        except PermissionError as e:       # OneDrive 동기화·백신이 잡고 있을 때
            last = e
            time.sleep(0.1 * (k + 1))
    try:
        os.remove(tmp)
    except OSError:
        pass
    raise WorkspaceError(f"작업 공간 쓰기 실패(파일 잠김?): {path}: {last}")


class Workspace:
    def __init__(self, root):
        self.root = os.path.realpath(root)
        self.path = os.path.join(self.root, "current.json")
        self.hist = os.path.join(self.root, "history")
        self.lock = threading.RLock()
        self._last_hist = 0.0

    # --- 읽기
    def _read(self, path=None):
        try:
            with open(path or self.path, encoding="utf-8") as fp:
                d = json.load(fp)
            return d if isinstance(d, dict) else None
        except (OSError, ValueError):
            return None

    def raw(self):
        with self.lock:
            return self._read()

    def get(self):
        """{exists, rev, updated_at, updated_by, state}. 서버 소유 키를 state 에 합쳐 돌려준다."""
        with self.lock:
            d = self._read()
            if d is None:
                return {"exists": False, "rev": 0, "updated_at": None, "updated_by": None, "state": None}
            st = dict(d.get("state") or empty_state())
            st["file_edits"] = d.get("file_edits") or []
            st["reference"] = d.get("reference") or st.get("reference") or {"source": "disk", "pinned_file": None}
            return {"exists": True, "rev": d.get("rev", 0), "updated_at": d.get("updated_at"),
                    "updated_by": d.get("updated_by"), "state": st}

    # --- 쓰기
    def _dump(self, d):
        return json.dumps(d, ensure_ascii=False, separators=(",", ":")).encode("utf-8")

    def _archive(self, d, force=False):
        """이전 파일을 history/ 에 보관 (최대 HISTORY_MAX 개)."""
        if d is None:
            return
        now = time.time()
        if not force and now - self._last_hist < HISTORY_GAP_S:
            return
        self._last_hist = now
        name = datetime.now().strftime("%Y%m%d-%H%M%S-%f") + ".json"
        _atomic_write(os.path.join(self.hist, name), self._dump(d))
        files = sorted(f for f in os.listdir(self.hist) if f.endswith(".json"))
        for f in files[:-HISTORY_MAX]:
            try:
                os.remove(os.path.join(self.hist, f))
            except OSError:
                pass

    def _fit(self, d):
        data = self._dump(d)
        if len(data) > MAX_BYTES:
            st = d.get("state") or {}
            for k in ("undo", "redo"):
                if st.get(k):
                    st[k] = []
            data = self._dump(d)
        if len(data) > MAX_BYTES:
            raise WorkspaceTooLarge(f"작업 공간이 {MAX_BYTES // (1024 * 1024)} MB 를 넘음")
        return data

    def put(self, rev, client, state, force=False):
        """저장하고 새 rev 를 돌려준다. rev 가 다르면 WorkspaceConflict."""
        if not isinstance(state, dict):
            raise WorkspaceError("state 는 객체여야 함")
        with self.lock:
            cur = self._read()
            cur_rev = cur.get("rev", 0) if cur else 0
            if cur is not None and not force and rev != cur_rev:
                raise WorkspaceConflict(self.get())
            st = {k: v for k, v in state.items() if k not in SERVER_KEYS}
            st["undo"] = (st.get("undo") or [])[-UNDO_KEEP:]
            st["redo"] = (st.get("redo") or [])[-UNDO_KEEP:]
            d = {"rev": cur_rev + 1, "updated_at": datetime.now().isoformat(timespec="seconds"), "updated_by": client,
                 "state": st, "file_edits": (cur or {}).get("file_edits") or [],
                 "reference": (cur or {}).get("reference") or {"source": "disk", "pinned_file": None}}
            data = self._fit(d)
            self._archive(cur)
            _atomic_write(self.path, data)
            return {"rev": d["rev"], "updated_at": d["updated_at"]}

    def clear(self, client=None):
        """초기화: 현재 파일을 history 로 옮기고 빈 작업 공간으로 시작 (rev 는 이어서 올라간다)."""
        with self.lock:
            cur = self._read()
            self._archive(cur, force=True)
            d = {"rev": (cur.get("rev", 0) if cur else 0) + 1, "updated_at": datetime.now().isoformat(timespec="seconds"),
                 "updated_by": client, "state": empty_state(), "file_edits": [],
                 "reference": {"source": "disk", "pinned_file": None}}
            _atomic_write(self.path, self._dump(d))
            return {"rev": d["rev"]}

    # --- 서버 소유 부분
    def _mutate(self, fn):
        with self.lock:
            cur = self._read() or {"rev": 0, "state": empty_state(), "file_edits": [],
                                   "reference": {"source": "disk", "pinned_file": None}}
            fn(cur)
            _atomic_write(self.path, self._dump(cur))

    def set_file_edits(self, items):
        """JSON 편집 작업 사본 [{kind, id, base_sha1, new_text}]. rev 는 올리지 않는다(뷰어 저장과 충돌 방지)."""
        def f(d):
            d["file_edits"] = items
        self._mutate(f)

    def file_edits(self):
        d = self.raw()
        return (d or {}).get("file_edits") or []

    def set_reference(self, source, pinned_file=None):
        def f(d):
            d["reference"] = {"source": source, "pinned_file": pinned_file}
        self._mutate(f)

    def reference(self):
        d = self.raw()
        return (d or {}).get("reference") or {"source": "disk", "pinned_file": None}

    def add_held(self, items):
        """서버 시작 때 복원하지 못한 항목을 state.held 에 보탠다."""
        if not items:
            return

        def f(d):
            st = d.setdefault("state", empty_state())
            st["held"] = (st.get("held") or []) + items
        self._mutate(f)

    # --- 이력
    def history(self):
        out = []
        if not os.path.isdir(self.hist):
            return out
        for fn in sorted(os.listdir(self.hist), reverse=True):
            if not fn.endswith(".json") or not HIST_ID.match(fn[:-5]):
                continue
            d = self._read(os.path.join(self.hist, fn))
            if d is None:
                continue
            st = d.get("state") or {}
            out.append({"id": fn[:-5], "saved_at": d.get("updated_at"), "rev": d.get("rev"),
                        "edits": len(st.get("edits") or []), "cfg_edits": len(st.get("cfg_edits") or []),
                        "cfg_set": len(st.get("cfg_set") or {}), "file_edits": len(d.get("file_edits") or [])})
        return out

    def restore(self, hid, client=None):
        if not HIST_ID.match(hid or ""):
            raise WorkspaceError("이력 ID 형식 오류")
        with self.lock:
            d = self._read(os.path.join(self.hist, hid + ".json"))
            if d is None:
                raise WorkspaceError("이력 없음")
            cur = self._read()
            self._archive(cur, force=True)
            d["rev"] = (cur.get("rev", 0) if cur else 0) + 1
            d["updated_at"] = datetime.now().isoformat(timespec="seconds")
            d["updated_by"] = client
            _atomic_write(self.path, self._dump(d))
            return {"rev": d["rev"], "file_edits": d.get("file_edits") or []}


# ---------------------------------------------------------------------------
# 복원 충돌 검사 (F14.4)
# ---------------------------------------------------------------------------
def check_state(state, table_data, base_cfg, monster_data):
    """저장된 편집을 현재 원본 위에 항목별로 적용해 본다. 충돌·오류 항목은 held 로 분리한다.
    반환: {edits, cfg_edits, cfg_set (적용 가능), held (보류: {type, item, reason})}."""
    from . import edits as ed
    held = []
    ok_edits, ok_cfg, ok_set = [], [], {}
    for e in state.get("edits") or []:
        try:
            if e.get("target") in ("monster", "pattern", "gimmick"):
                if monster_data is None:
                    c, er = [{"reason": "몬스터 테이블 없음"}], []
                else:
                    _, c, er = ed.apply_monster_edits(monster_data, [e])
            else:
                _, c, er = ed.apply_edits(table_data, [e])
        except Exception as ex:  # noqa: BLE001
            c, er = [{"reason": f"{type(ex).__name__}: {ex}"}], []
        if c or er:
            held.append({"type": "edit", "item": e, "reason": (c + er)[0].get("reason", "충돌")})
        else:
            ok_edits.append(e)
    for e in state.get("cfg_edits") or []:
        _, c, er = ed.apply_cfg_edits(base_cfg, [e])
        if c or er:
            held.append({"type": "cfg_edit", "item": e, "reason": (c + er)[0].get("reason", "충돌")})
        else:
            ok_cfg.append(e)
    for k, v in (state.get("cfg_set") or {}).items():
        try:
            ed.apply_cfg_set(base_cfg, {k: v})
            ok_set[k] = v
        except Exception as ex:  # noqa: BLE001
            held.append({"type": "cfg_set", "item": {"path": k, "value": v}, "reason": str(ex)})
    return {"edits": ok_edits, "cfg_edits": ok_cfg, "cfg_set": ok_set, "held": held}
