# -*- coding: utf-8 -*-
"""원본 JSON 반영 (명세 v2 §6.6).

최소 diff 규칙
- JSON 을 파싱했다가 다시 직렬화하지 않는다. 오프셋을 기록하는 경량 파서로 해당 숫자 토큰
  (또는 표현식 문자열 안의 상수)의 바이트 구간만 교체한다.
- BOM, 줄바꿈, 들여쓰기, 키 순서, 나머지 바이트는 그대로. 숫자 표기(30.0 / 70)를 유지한다.
- 패치 후 다시 파싱해 의도한 경로의 값만 바뀌었는지 검증하고, 아니면 쓰지 않는다.

안전장치: 외부 변경 감지(sha1·mtime), 원자적 쓰기 + PermissionError 재시도, 반영 전 백업,
되돌리기(반영 이후 바뀌지 않았을 때만). 커밋은 하지 않는다.
"""
from __future__ import annotations

import copy
import difflib
import hashlib
import json
import os
import re
import shutil
import time
from datetime import datetime

from . import edits as ed

BOM = b"\xef\xbb\xbf"
UNITY_NOTE = "Unity에서 GoldfishWalking > Data > Import All Gameplay JSON 을 실행해야 게임에 반영됩니다."


class WriteBackError(Exception):
    pass


# ---------------------------------------------------------------------------
# 경량 JSON 파서 (값의 오프셋 기록)
# ---------------------------------------------------------------------------
_NUM = re.compile(r"-?(?:0|[1-9]\d*)(?:\.\d+)?(?:[eE][+-]?\d+)?")
_WS = " \t\r\n"


class _P:
    def __init__(self, text):
        self.t = text
        self.spans = {}

    def ws(self, i):
        t = self.t
        while i < len(t) and t[i] in _WS:
            i += 1
        return i

    def value(self, i, path):
        i = self.ws(i)
        c = self.t[i]
        start = i
        if c == "{":
            i = self.ws(i + 1)
            if self.t[i] == "}":
                end = i + 1
            else:
                while True:
                    i = self.ws(i)
                    k_start = i
                    i = self.string(i)
                    key = json.loads(self.t[k_start:i])
                    i = self.ws(i)
                    if self.t[i] != ":":
                        raise ValueError(f"':' 필요 @{i}")
                    i = self.value(i + 1, path + (key,))
                    i = self.ws(i)
                    if self.t[i] == ",":
                        i += 1
                        continue
                    if self.t[i] == "}":
                        end = i + 1
                        break
                    raise ValueError(f"',' 또는 '}}' 필요 @{i}")
        elif c == "[":
            i = self.ws(i + 1)
            k = 0
            if self.t[i] == "]":
                end = i + 1
            else:
                while True:
                    i = self.value(i, path + (k,))
                    k += 1
                    i = self.ws(i)
                    if self.t[i] == ",":
                        i += 1
                        continue
                    if self.t[i] == "]":
                        end = i + 1
                        break
                    raise ValueError(f"',' 또는 ']' 필요 @{i}")
        elif c == '"':
            end = self.string(i)
        elif c in "-0123456789":
            m = _NUM.match(self.t, i)
            if not m:
                raise ValueError(f"숫자 형식 오류 @{i}")
            end = m.end()
        else:
            for lit in ("true", "false", "null"):
                if self.t.startswith(lit, i):
                    end = i + len(lit)
                    break
            else:
                raise ValueError(f"알 수 없는 토큰 @{i}")
        self.spans[path] = (start, end)
        return end

    def string(self, i):
        if self.t[i] != '"':
            raise ValueError(f"문자열 필요 @{i}")
        i += 1
        t = self.t
        while True:
            c = t[i]
            if c == "\\":
                i += 2
            elif c == '"':
                return i + 1
            else:
                i += 1


def spans_of(text):
    p = _P(text)
    end = p.value(0, ())
    if p.ws(end) != len(text):
        raise ValueError("JSON 뒤에 남은 문자")
    return p.spans


# ---------------------------------------------------------------------------
# 숫자 표기
# ---------------------------------------------------------------------------
def _clean(v):
    v = round(float(v), 10)
    return int(round(v)) if abs(v - round(v)) < 1e-9 else v


def format_like(orig_token, value):
    """원본 토큰 표기(정수/소수)를 유지해 value 를 쓴다. 소수는 가장 짧은 표현."""
    v = _clean(value)
    float_style = any(ch in orig_token for ch in ".eE")
    if isinstance(v, int):
        return f"{v}.0" if float_style else str(v)
    return repr(float(v))


def inverse(transform, sim_value, orig_value):
    if transform in ("identity", "expr_mul", "expr_div", "token_digits"):
        return sim_value
    if transform == "percent_div_100":
        return sim_value * 100
    if transform == "pct_scale_gt1":
        return sim_value * 100 if float(orig_value) > 1 else sim_value
    raise WriteBackError(f"알 수 없는 transform: {transform}")


def forward(transform, orig_value):
    if transform in ("identity", "expr_mul", "expr_div"):
        return orig_value
    if transform == "percent_div_100":
        return orig_value / 100.0
    if transform == "pct_scale_gt1":
        return orig_value / 100.0 if orig_value > 1 else orig_value
    raise WriteBackError(f"알 수 없는 transform: {transform}")


_EXPR = {"expr_mul": re.compile(r"\*\s*(\d+(?:\.\d+)?)"), "expr_div": re.compile(r"/\s*(\d+(?:\.\d+)?)")}


def src_path(src):
    if "path" in src:                      # 몬스터·패턴: 명시적 경로
        return tuple(src["path"])
    path = ("effects", int(src["effect"]))
    for part in src["field"].split("."):
        path += (part,)
    return path


# 패턴 토큰 문자열 안의 숫자 ("2_Single" 의 2, "2_Multi_1" 의 1, "Str_3" 의 3)
_TOKEN = {"digits": re.compile(r'^"(\d+)_'), "hits": re.compile(r'_Multi_(\d+)"$'), "n": re.compile(r'^"Str_(-?\d+)"$')}


def plan_patch(text, src, sim_new):
    """원본 텍스트에서 src 가 가리키는 토큰 구간과 새 토큰을 계산한다. 반환 (start, end, old_tok, new_tok, path)."""
    spans = spans_of(text)
    path = src_path(src)
    if path not in spans:
        raise WriteBackError(f"원본에 경로 없음: {'.'.join(map(str, path))}")
    s, e = spans[path]
    tok = text[s:e]
    tr = src["transform"]
    if tr == "token_digits":
        m = _TOKEN[src["part"]].search(tok)
        if not m:
            raise WriteBackError(f"패턴 토큰 {tok} 에서 {src['part']} 숫자를 찾을 수 없음")
        return s + m.start(1), s + m.end(1), m.group(1), str(int(round(float(sim_new)))), path
    if src.get("field") == "amount.expression":
        if not tok.startswith('"'):
            raise WriteBackError("표현식 문자열이 아님")
        rx = _EXPR.get(tr)
        if rx is None:
            raise WriteBackError(f"표현식에 쓸 수 없는 transform: {tr}")
        ms_ = list(rx.finditer(tok))
        if len(ms_) != 1:
            raise WriteBackError(f"표현식 {tok} 에서 상수를 하나로 특정할 수 없음 ({len(ms_)}개)")
        m = ms_[0]
        const = m.group(1)
        new_const = format_like(const, inverse(tr, sim_new, float(const)))
        return s + m.start(1), s + m.end(1), const, new_const, path
    if not _NUM.fullmatch(tok):
        raise WriteBackError(f"숫자 토큰이 아님: {tok}")
    orig = float(tok)
    return s, e, tok, format_like(tok, inverse(tr, sim_new, orig)), path


def read_source(path):
    with open(path, "rb") as fp:
        raw = fp.read()
    bom = raw.startswith(BOM)
    return raw, bom, raw[len(BOM):].decode("utf-8") if bom else raw.decode("utf-8")


def _deep_set(obj, path, value):
    cur = obj
    for k in path[:-1]:
        cur = cur[k]
    cur[path[-1]] = value


def _deep_get(obj, path):
    cur = obj
    for k in path:
        cur = cur[k]
    return cur


def patch_text(text, patches):
    """patches: [(start, end, new_tok)] 원본 기준 오프셋. 뒤에서부터 교체."""
    out = text
    for s, e, new in sorted(patches, key=lambda x: x[0], reverse=True):
        out = out[:s] + new + out[e:]
    return out


def verify_patch(old_text, new_text, expected):
    """expected: [(path, 기대값)] — 그 경로만 바뀌고 나머지는 같아야 한다."""
    a, b = json.loads(old_text), json.loads(new_text)
    want = copy.deepcopy(a)
    for path, val in expected:
        _deep_set(want, path, val)
    if want != b:
        raise WriteBackError("패치 검증 실패: 의도하지 않은 값이 바뀜")
    for path, val in expected:
        got = _deep_get(b, path)
        if got != val or type(got) is not type(val):
            raise WriteBackError(f"패치 검증 실패: {path} = {got!r} (기대 {val!r})")


# ---------------------------------------------------------------------------
# 파일 안전
# ---------------------------------------------------------------------------
def sha1_bytes(b):
    return hashlib.sha1(b).hexdigest()


def file_sig(path):
    with open(path, "rb") as fp:
        b = fp.read()
    return {"sha1": sha1_bytes(b), "mtime": os.path.getmtime(path)}


def safe_child(base, name):
    """base 폴더 안의 파일 이름만 허용 (절대 경로, .., 하위 폴더, 심볼릭 링크 거부)."""
    if not name or os.path.isabs(name) or name != os.path.basename(name) or name in (".", "..") \
            or "/" in name or "\\" in name or ":" in name:
        raise WriteBackError(f"허용되지 않는 파일 이름: {name!r}")
    base_r = os.path.realpath(base)
    p = os.path.join(base_r, name)
    if os.path.islink(p):
        raise WriteBackError(f"심볼릭 링크는 쓰지 않음: {name}")
    if os.path.dirname(os.path.realpath(p)) != base_r:
        raise WriteBackError(f"경로 이탈: {name}")
    return p


def check_allowed(path, allowed_roots):
    r = os.path.realpath(path)
    forbid = os.environ.get("MATCHUPSIM_FORBID_PATH")
    if forbid and (r + os.sep).lower().startswith(os.path.realpath(forbid).lower() + os.sep):
        raise WriteBackError(f"테스트 격리: 금지된 경로에 쓰기 시도 {r}")
    for root in allowed_roots:
        rr = os.path.realpath(root)
        if r == rr or r.startswith(rr + os.sep):
            return r
    raise WriteBackError(f"허용 목록 밖 경로: {r}")


def atomic_write(path, data, allowed_roots, retries=5):
    check_allowed(path, allowed_roots)
    tmp = path + f".matchupsim.{os.getpid()}.tmp"
    with open(tmp, "wb") as fp:
        fp.write(data)
    last = None
    for k in range(retries):
        try:
            os.replace(tmp, path)
            return
        except PermissionError as e:  # OneDrive 동기화·에디터가 잡고 있을 때
            last = e
            time.sleep(0.2 * (k + 1))
    try:
        os.remove(tmp)
    except OSError:
        pass
    raise WriteBackError(f"쓰기 실패(파일 잠김?): {path}: {last}")


def unified(name, a, b):
    return "".join(difflib.unified_diff(a.splitlines(True), b.splitlines(True), f"a/{name}", f"b/{name}", n=2))


# ---------------------------------------------------------------------------
# 반영 관리자
# ---------------------------------------------------------------------------
class WriteBack:
    def __init__(self, src_dir, overrides_path, effects_path, backup_root, extra_allowed=(), dirs=None, overlay=None):
        """dirs = {"monster": 폴더, "pattern": 폴더} (선택). 파일 키: 환상 "x.json", 몬스터 "monsters/x.json",
        패턴 "patterns/x.json", overrides "@overrides". overlay 가 있으면 JSON 편집기로 고친 원문도 반영한다."""
        self.dirs = {"monster": None, "pattern": None}
        self.dirs.update({k: os.path.realpath(v) for k, v in (dirs or {}).items() if v})
        self.overlay = overlay
        self.src_dir = os.path.realpath(src_dir)
        self.overrides_path = os.path.realpath(overrides_path)
        self.effects_path = os.path.realpath(effects_path)
        self.backup_root = os.path.realpath(backup_root)
        self.allowed = [self.src_dir, os.path.dirname(self.overrides_path), os.path.dirname(self.effects_path),
                        self.backup_root] + [os.path.realpath(p) for p in extra_allowed] + [d for d in self.dirs.values() if d]
        self.snap = {}
        self.last = None

    # --- 파일 키 → 경로 (클라이언트 경로를 쓰지 않는다)
    PREFIX = {"monster": "monsters/", "pattern": "patterns/"}

    def key_of(self, kind, filename):
        return filename if kind == "fantasy" else ("@overrides" if kind == "overrides" else self.PREFIX[kind] + filename)

    def resolve(self, key):
        if key == "@overrides":
            return self.overrides_path
        for kind, pre in self.PREFIX.items():
            if key.startswith(pre):
                if not self.dirs.get(kind):
                    raise WriteBackError(f"{kind} 폴더가 설정되지 않음")
                return safe_child(self.dirs[kind], key[len(pre):])
        return safe_child(self.src_dir, key)

    # --- 외부 변경 감지
    def snapshot(self):
        self.snap = {}
        for fn in os.listdir(self.src_dir):
            if fn.endswith(".json"):
                self.snap[fn] = file_sig(os.path.join(self.src_dir, fn))
        for kind, pre in self.PREFIX.items():
            d = self.dirs.get(kind)
            if d and os.path.isdir(d):
                for fn in os.listdir(d):
                    if fn.endswith(".json"):
                        self.snap[pre + fn] = file_sig(os.path.join(d, fn))
        if os.path.exists(self.overrides_path):
            self.snap["@overrides"] = file_sig(self.overrides_path)
        return self.snap

    def changed_since_snapshot(self, files):
        bad = []
        for fn in files:
            path = self.resolve(fn)
            old = self.snap.get(fn)
            if old is None or not os.path.exists(path):
                bad.append(fn)
                continue
            now = file_sig(path)
            if now["sha1"] != old["sha1"]:
                bad.append(fn)
        return bad

    # --- 계획
    def classify(self, table_data, edits):
        by_id = {e["id"]: e for e in table_data["fantasies"]}
        src_edits, ov_edits, scen_only, problems = [], [], [], []
        for edit in edits:
            e = by_id.get(edit["fid"])
            if e is None:
                problems.append({**edit, "reason": "환상 없음"})
                continue
            effs = e.get("effects", [])
            i = edit["effect"]
            if not 0 <= i < len(effs) or edit["key"] not in effs[i]:
                problems.append({**edit, "reason": "효과/키 없음"})
                continue
            ef = effs[i]
            if not ed.num_eq(ef[edit["key"]], edit["old"]):
                problems.append({**edit, "reason": f"현재 값 {ef[edit['key']]} ≠ old {edit['old']}"})
                continue
            err = ed.validate(ed.key_schema(ef, edit["key"]), edit["new"])
            if err:
                problems.append({**edit, "reason": err})
                continue
            src = ed.src_for(ef, edit["key"])
            if src:
                src_edits.append({**edit, "src": src, "type": ef["type"]})
            elif e.get("mapping") == "override":
                ov_edits.append({**edit, "type": ef["type"]})
            else:
                scen_only.append({**edit, "reason": "원본 연결 없음 (임포터 상수 등) — 시나리오에만 저장"})
        return src_edits, ov_edits, scen_only, problems

    def monster_src_edits(self, monster_table, edits):
        """몬스터·패턴 숫자 편집 → src 가 붙은 항목과 문제 목록."""
        out, problems = [], []
        by_id = {m["id"]: m for m in (monster_table or {}).get("monsters", [])}
        for e in edits:
            src, cur = None, None
            if e.get("target") == "gimmick":
                m = by_id.get(e.get("mid"))
                sims = (m or {}).get("sim") or []
                gi = e.get("gi", -1)
                if m and 0 <= gi < len(sims):
                    src, cur = (sims[gi].get("src") or {}).get(e["key"]), sims[gi].get(e["key"])
                sch = ed.GIMMICK_SCHEMA.get(e.get("key"))
                if src is None:
                    problems.append({**e, "reason": "원본 연결 없음"})
                elif not ed.num_eq(cur, e.get("old")):
                    problems.append({**e, "reason": f"현재 값 {cur} ≠ old {e.get('old')}"})
                elif sch is None or ed.validate(sch, e.get("new")):
                    problems.append({**e, "reason": "범위를 벗어남"})
                else:
                    out.append({**e, "src": src, "fkey": self.key_of(src["kind"], src["file"])})
                continue
            if e.get("target") == "monster":
                m = by_id.get(e.get("mid"))
                if m:
                    src, cur = m.get("src", {}).get(e["key"]), m.get(e["key"])
            elif e.get("target") == "pattern" and "mid" in e:
                m = by_id.get(e["mid"])
                if m and 0 <= e.get("step", -1) < len(m["patterns"]):
                    p = m["patterns"][e["step"]]
                    src = (p.get("src") or {}).get(e["key"])
                    cur = p.get({"digits": "dmg_digits", "hits": "hit_digits", "n": "str_units"}[e["key"]])
            elif e.get("target") == "pattern" and "pid" in e:
                for m in by_id.values():
                    for p in m["patterns"]:
                        if p["key"] == e["pid"] and (p.get("src") or {}).get(e["key"]):
                            src = p["src"][e["key"]]
                            cur = p.get({"digits": "dmg_digits", "hits": "hit_digits"}[e["key"]])
            if src is None:
                problems.append({**e, "reason": "원본 연결 없음"})
            elif not ed.num_eq(cur, e.get("old")):
                problems.append({**e, "reason": f"현재 값 {cur} ≠ old {e.get('old')}"})
            elif not isinstance(e.get("new"), (int, float)) or float(e["new"]) != int(e["new"]) or e["new"] < (1 if e["key"] in ("hp", "digits", "hits") else -99):
                problems.append({**e, "reason": "정수 범위를 벗어남"})
            else:
                out.append({**e, "src": src, "fkey": self.key_of(src["kind"], src["file"])})
        return out, problems

    def preview(self, table_data, edits, monster_table=None):
        f_edits = [e for e in edits if e.get("target", "fantasy") == "fantasy"]
        m_edits, m_problems = self.monster_src_edits(monster_table, [e for e in edits if e.get("target") in ("monster", "pattern", "gimmick")])
        src_edits, ov_edits, scen_only, problems = self.classify(table_data, f_edits)
        problems = problems + m_problems
        files = {}
        by_file = {}
        for x in src_edits:
            by_file.setdefault(x["src"]["file"], []).append(x)
        for x in m_edits:
            by_file.setdefault(x["fkey"], []).append(x)
        # JSON 편집기로 고친 파일 (원문 그대로 반영). 숫자 편집이 같은 파일에 있으면 작업 텍스트 위에 패치한다.
        raw_files = {}
        if self.overlay is not None:
            for kind, fid in self.overlay.dirty():
                d = self.overlay.disk(kind, fid)
                raw_files[self.key_of(kind, d["file"])] = (kind, fid, d)
        for fn in sorted(set(by_file) | set(raw_files)):
            items = by_file.get(fn, [])
            if fn == "@overrides":
                continue
            path = self.resolve(fn)
            raw, bom, text = read_source(path)
            disk_text = text
            rawinfo = raw_files.get(fn)
            if rawinfo:
                text = self.overlay.text(rawinfo[0], rawinfo[1])   # LF 작업 텍스트
            patches, rows = [], []
            for x in items:
                try:
                    s, e, old_tok, new_tok, p = plan_patch(text, x["src"], x["new"])
                except WriteBackError as err:
                    problems.append({**{k: x.get(k) for k in ("fid", "effect", "key", "old", "new", "mid", "pid")}, "reason": str(err)})
                    continue
                if old_tok == new_tok:
                    continue
                patches.append((s, e, new_tok))
                rows.append({"fid": x.get("fid"), "effect": x.get("effect"), "key": x["key"], "old": x["old"], "new": x["new"],
                             "target": x.get("target", "fantasy"), "mid": x.get("mid"), "step": x.get("step"), "pid": x.get("pid"),
                             "gi": x.get("gi"),
                             "token_old": old_tok, "token_new": new_tok, "path": list(p), "field": x["src"].get("field", "token")})
            if not patches and not rawinfo:
                continue
            new_text = patch_text(text, patches)
            # 기대값: 새 텍스트에서 해당 경로 값 (검증은 '그 경로 외에는 안 바뀜' + 토큰 일치)
            newobj = json.loads(new_text)
            exp = [(tuple(r["path"]), _deep_get(newobj, tuple(r["path"]))) for r in rows]
            verify_patch(text, new_text, exp)
            if rawinfo:
                new_bytes = self.overlay.encode(rawinfo[0], rawinfo[1], new_text)
                files[fn] = {"rows": rows, "raw": True, "kind": rawinfo[0], "id": rawinfo[1],
                             "diff": unified(fn, disk_text.replace("\r\n", "\n"), new_text), "bom": bom, "new_bytes": new_bytes}
            else:
                files[fn] = {"rows": rows, "diff": unified(fn, text, new_text), "bom": bom,
                             "new_bytes": (BOM if bom else b"") + new_text.encode("utf-8")}
        if "@overrides" in raw_files:
            kind, fid, d = raw_files["@overrides"]
            files["@overrides"] = {"rows": [], "raw": True, "kind": kind, "id": fid, "bom": d["bom"],
                                   "diff": unified("fantasy_effects.overrides.json", d["text"], self.overlay.text(kind, fid)),
                                   "new_bytes": self.overlay.encode(kind, fid)}
        ov_rows = [{k: x[k] for k in ("fid", "effect", "key", "old", "new")} for x in ov_edits]
        return {"files": files, "overrides": ov_rows, "scenario_only": scen_only, "problems": problems}

    # --- 반영
    def apply(self, table_data, edits, reimport, selected_files=None, include_overrides=True, monster_table=None):
        """reimport(): 임포터를 다시 돌리고 새 환상 테이블 dict 를 돌려주는 함수 (프로세스 안 호출)."""
        pv = self.preview(table_data, edits, monster_table)
        files = {fn: v for fn, v in pv["files"].items() if selected_files is None or fn in selected_files}
        ov_raw = files.pop("@overrides", None)
        if ov_raw is not None and pv["overrides"]:
            raise WriteBackError("overrides 파일을 JSON 편집기로 고친 상태에서는 overrides 숫자 편집을 함께 반영할 수 없음")
        targets = list(files) + (["@overrides"] if (include_overrides and pv["overrides"]) or ov_raw else [])
        if not targets:
            raise WriteBackError("반영할 변경이 없음")
        bad = self.changed_since_snapshot(targets)
        if bad:
            raise WriteBackError("뷰어가 읽은 뒤 바뀐 파일이 있어 반영을 거부함: " + ", ".join(bad))
        ts = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        bdir = os.path.join(self.backup_root, ts)
        os.makedirs(bdir, exist_ok=True)
        check_allowed(bdir, self.allowed)
        manifest = {"at": datetime.now().isoformat(timespec="seconds"), "files": {}}
        # 백업
        for fn in targets:
            path = self.resolve(fn)
            bname = "overrides.json" if fn == "@overrides" else fn.replace("/", "__")
            shutil.copy2(path, os.path.join(bdir, bname))
            with open(path, "rb") as fp:
                manifest["files"][fn] = {"backup": bname, "orig_sha1": sha1_bytes(fp.read()), "path": path}
        # 쓰기
        for fn, v in files.items():
            path = self.resolve(fn)
            atomic_write(path, v["new_bytes"], self.allowed)
            manifest["files"][fn]["new_sha1"] = sha1_bytes(v["new_bytes"])
        if ov_raw is not None:
            atomic_write(self.overrides_path, ov_raw["new_bytes"], self.allowed)
            manifest["files"]["@overrides"]["new_sha1"] = sha1_bytes(ov_raw["new_bytes"])
        elif "@overrides" in targets:
            with open(self.overrides_path, encoding="utf-8") as fp:
                ov = json.load(fp)
            for x in pv["overrides"]:
                ov[x["fid"]]["effects"][x["effect"]][x["key"]] = x["new"]
            data = (json.dumps(ov, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
            atomic_write(self.overrides_path, data, self.allowed)
            manifest["files"]["@overrides"]["new_sha1"] = sha1_bytes(data)
        with open(os.path.join(bdir, "manifest.json"), "w", encoding="utf-8") as fp:
            json.dump(manifest, fp, ensure_ascii=False, indent=2)
        # 재임포트 + 라운드트립
        new_table = reimport()
        mismatch = self.roundtrip(new_table, [x for fn in files for x in files[fn]["rows"] if x.get("target", "fantasy") == "fantasy"],
                                  pv["overrides"], "@overrides" in targets and ov_raw is None)
        self.snapshot()
        self.last = bdir
        return {"backup_dir": bdir, "files": list(files) + (["@overrides"] if ov_raw is not None else []),
                "raw_files": [fn for fn, v in files.items() if v.get("raw")] + (["@overrides"] if ov_raw is not None else []),
                "monster_rows": [x for fn in files for x in files[fn]["rows"] if x.get("target", "fantasy") != "fantasy"],
                "overrides": pv["overrides"] if "@overrides" in targets and ov_raw is None else [],
                "scenario_only": pv["scenario_only"], "problems": pv["problems"], "roundtrip_mismatch": mismatch,
                "note": UNITY_NOTE, "at": manifest["at"]}

    def roundtrip(self, new_table, src_rows, ov_rows, ov_written):
        by_id = {e["id"]: e for e in new_table["fantasies"]}
        bad = []
        for r in src_rows:
            e = by_id.get(r["fid"])
            ef = e["effects"][r["effect"]] if e and r["effect"] < len(e.get("effects", [])) else None
            got = ef.get(r["key"]) if ef else None
            if got is None or not ed.num_eq(got, r["new"]):
                bad.append({**r, "got": got})
        if ov_written:
            for r in ov_rows:
                e = by_id.get(r["fid"])
                got = e["effects"][r["effect"]].get(r["key"]) if e else None
                if got is None or not ed.num_eq(got, r["new"]):
                    bad.append({**r, "got": got})
        return bad

    def revert(self, backup_dir, reimport):
        bdir = os.path.realpath(backup_dir)
        if os.path.dirname(bdir) != self.backup_root:
            raise WriteBackError("백업 폴더가 아님")
        with open(os.path.join(bdir, "manifest.json"), encoding="utf-8") as fp:
            manifest = json.load(fp)
        # 반영 이후 바뀐 파일이 있으면 거부
        changed = []
        for fn, info in manifest["files"].items():
            path = self.resolve(fn)
            with open(path, "rb") as fp:
                if sha1_bytes(fp.read()) != info.get("new_sha1"):
                    changed.append(fn)
        if changed:
            raise WriteBackError("반영 이후 바뀐 파일이 있어 복원을 거부함: " + ", ".join(changed))
        for fn, info in manifest["files"].items():
            path = self.resolve(fn)
            with open(os.path.join(bdir, info["backup"]), "rb") as fp:
                atomic_write(path, fp.read(), self.allowed)
        new_table = reimport()
        self.snapshot()
        return {"restored": list(manifest["files"]), "table": new_table}
