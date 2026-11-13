# -*- coding: utf-8 -*-
"""작업 사본 (v3 §4.1, §6.7): 원본 파일 위에 얹은 "파일별 작업 텍스트"를 메모리에 둔다.

- 숫자 UI 편집과 JSON 직접 편집이 모두 이 사본을 바꾸고, 시뮬레이션은 항상 사본을 인메모리로
  임포트한 결과로 돈다. 디스크의 원본은 "반영"에서만 바뀐다.
- 편집기는 텍스트를 LF 로 다루고, 파일에 쓸 때 원본의 BOM·줄바꿈(CRLF/LF)·마지막 줄바꿈으로 되돌린다.
  아무것도 바꾸지 않으면 원본 바이트 그대로다.
- 검증 3단계: (1) 엄격한 JSON 문법(중복 키, NaN/Infinity 거부) (2) 구조(필수 필드, id 불변, 열거값)
  (3) dry-run 임포트(바뀌는 시뮬 효과·경고).
"""
from __future__ import annotations

import hashlib
import json
import os

import import_fantasies
import import_monsters

BOM = b"\xef\xbb\xbf"
KINDS = ("fantasy", "monster", "pattern", "overrides")
MAX_TEXT = 1024 * 1024
RARITIES = ("white", "blue", "red")
KNOWN = {
    "fantasy": {"schemaVersion", "id", "designerName", "designerNote", "enabled", "sourceId", "localization",
                "presentation", "rarity", "tags", "effects"},
    "monster": {"schemaVersion", "id", "sourceId", "designerName", "designerNote", "enabled", "localization",
                "presentation", "encounter", "stats", "ai", "passives"},
    "pattern": {"schemaVersion", "id", "sourceId", "designerName", "designerNote", "enabled", "localization",
                "presentation", "availability", "attack", "effects", "metadata"},
}
REQUIRED = {"fantasy": ("schemaVersion", "id", "rarity", "effects"), "monster": ("id", "encounter", "stats", "ai"),
            "pattern": ("id",)}


class OverlayError(Exception):
    pass


class DupKey(ValueError):
    pass


def strict_loads(text):
    """엄격한 JSON: 중복 키와 NaN/Infinity 를 오류로 처리."""
    def pairs(items):
        seen = {}
        for k, v in items:
            if k in seen:
                raise DupKey(k)
            seen[k] = v
        return seen

    def const(name):
        raise ValueError(f"{name} 은 허용되지 않음")

    return json.loads(text, object_pairs_hook=pairs, parse_constant=const)


def syntax_check(text):
    try:
        return strict_loads(text), []
    except json.JSONDecodeError as e:
        return None, [{"level": "error", "stage": "syntax", "line": e.lineno, "col": e.colno, "msg": f"JSON 문법 오류: {e.msg}"}]
    except DupKey as e:
        key = str(e)
        needle = json.dumps(key, ensure_ascii=False)
        first = text.find(needle)
        second = text.find(needle, first + 1) if first >= 0 else -1
        pos = second if second >= 0 else max(first, 0)
        line = text.count("\n", 0, pos) + 1
        col = pos - (text.rfind("\n", 0, pos) + 1) + 1
        return None, [{"level": "error", "stage": "syntax", "line": line, "col": col, "msg": f"중복 키: {key}"}]
    except ValueError as e:
        return None, [{"level": "error", "stage": "syntax", "line": 1, "col": 1, "msg": str(e)}]


def structure_check(kind, obj, orig_id):
    out = []
    err = lambda m: out.append({"level": "error", "stage": "structure", "msg": m})   # noqa: E731
    warn = lambda m: out.append({"level": "warning", "stage": "structure", "msg": m})  # noqa: E731
    if kind == "overrides":
        if not isinstance(obj, dict):
            err("overrides 는 객체여야 함")
            return out
        for k, v in obj.items():
            if k.startswith("_"):
                continue
            if not isinstance(v, dict):
                err(f"{k}: 객체여야 함")
            elif "effects" in v:
                if v.get("fidelity") not in ("exact", "approx", "none"):
                    err(f"{k}: fidelity 는 exact/approx/none")
                if not isinstance(v["effects"], list):
                    err(f"{k}: effects 는 배열")
            elif "notes_extra" not in v:
                warn(f"{k}: effects 도 notes_extra 도 없음 (무시됨)")
        return out
    if not isinstance(obj, dict):
        err("최상위는 객체여야 함")
        return out
    for f in REQUIRED[kind]:
        if f not in obj:
            err(f"필수 필드 누락: {f}")
    if obj.get("id") != orig_id:
        err(f"id 는 바꿀 수 없음 ({orig_id!r} → {obj.get('id')!r})")
    for k in obj:
        if k not in KNOWN[kind]:
            warn(f"알 수 없는 필드: {k}")
    if kind == "fantasy":
        if "rarity" in obj and obj["rarity"] not in RARITIES:
            err(f"rarity 는 {'/'.join(RARITIES)}: {obj['rarity']!r}")
        if "effects" in obj:
            if not isinstance(obj["effects"], list):
                err("effects 는 배열")
            else:
                for i, e in enumerate(obj["effects"]):
                    if not isinstance(e, dict) or "target" not in e or "operation" not in e:
                        err(f"effects[{i}]: target, operation 필수")
    elif kind == "monster":
        enc, stats, ai = obj.get("encounter"), obj.get("stats"), obj.get("ai")
        if isinstance(enc, dict):
            if enc.get("act") not in (1, 2, 3):
                err("encounter.act 는 1~3")
            if enc.get("grade") not in ("normal", "elite", "boss"):
                err("encounter.grade 는 normal/elite/boss")
        elif enc is not None:
            err("encounter 는 객체")
        if isinstance(stats, dict):
            if not isinstance(stats.get("health"), (int, float)) or isinstance(stats.get("health"), bool) or stats["health"] <= 0:
                err("stats.health 는 양수")
        elif stats is not None:
            err("stats 는 객체")
        if isinstance(ai, dict):
            if ai.get("mode") not in ("static", "random"):
                err("ai.mode 는 static/random")
            if not isinstance(ai.get("patterns"), list) or not all(isinstance(x, str) for x in ai.get("patterns") or []):
                err("ai.patterns 는 문자열 배열")
        elif ai is not None:
            err("ai 는 객체")
    return out


class Overlay:
    def __init__(self, dirs, overrides_path):
        """dirs = {"fantasy": 폴더, "monster": 폴더 또는 None, "pattern": 폴더 또는 None}"""
        self.dirs = {k: os.path.realpath(v) for k, v in dirs.items() if v}
        self.overrides_path = os.path.realpath(overrides_path)
        self.work = {}        # (kind, id) → 작업 텍스트 (LF)
        self.base = {}        # (kind, id) → 편집 시작 시점 원본 sha1
        self.reindex()

    # --- 파일 해석 (클라이언트 경로를 쓰지 않는다: 종류 + ID → 파일)
    def reindex(self):
        self.index = {}
        for kind, d in self.dirs.items():
            idx = {}
            if os.path.isdir(d):
                for fn in sorted(os.listdir(d)):
                    if not fn.endswith(".json"):
                        continue
                    try:
                        with open(os.path.join(d, fn), encoding="utf-8-sig") as fp:
                            idx[json.load(fp).get("id", fn[:-5])] = fn
                    except (OSError, ValueError):
                        idx[fn[:-5]] = fn
            self.index[kind] = idx

    def path(self, kind, fid):
        if kind == "overrides":
            return self.overrides_path
        if kind not in self.dirs:
            raise OverlayError(f"알 수 없는 파일 종류: {kind}")
        fn = self.index[kind].get(fid)
        if fn is None:
            raise OverlayError(f"파일 없음 (새 파일 생성은 지원하지 않음): {kind}/{fid}")
        return os.path.join(self.dirs[kind], fn)

    def disk(self, kind, fid):
        p = self.path(kind, fid)
        with open(p, "rb") as fp:
            raw = fp.read()
        bom = raw.startswith(BOM)
        text = (raw[len(BOM):] if bom else raw).decode("utf-8")
        return {"path": p, "raw": raw, "bom": bom, "crlf": "\r\n" in text, "text": text.replace("\r\n", "\n"),
                "sha1": hashlib.sha1(raw).hexdigest(), "file": os.path.basename(p)}

    def text(self, kind, fid):
        return self.work.get((kind, fid)) if (kind, fid) in self.work else self.disk(kind, fid)["text"]

    def info(self, kind, fid):
        d = self.disk(kind, fid)
        t = self.text(kind, fid)
        return {"kind": kind, "id": fid, "file": d["file"], "text": t, "base_sha1": d["sha1"], "bom": d["bom"],
                "crlf": d["crlf"], "dirty": t != d["text"], "disk_text": d["text"] if t != d["text"] else None,
                "diff_lines": sum(1 for a, b in zip(t.split("\n"), d["text"].split("\n")) if a != b)
                + abs(t.count("\n") - d["text"].count("\n"))}

    def encode(self, kind, fid, text=None):
        """작업 텍스트 → 파일 바이트 (원본의 BOM·줄바꿈·마지막 줄바꿈 유지). 내용이 같으면 원본 바이트 그대로."""
        d = self.disk(kind, fid)
        t = self.text(kind, fid) if text is None else text
        if t == d["text"]:
            return d["raw"]
        body = t.rstrip("\n")
        tail = d["text"][len(d["text"].rstrip("\n")):]
        out = body + tail
        if d["crlf"]:
            out = out.replace("\n", "\r\n")
        return (BOM if d["bom"] else b"") + out.encode("utf-8")

    def dirty(self):
        return [(k, i) for (k, i) in self.work if self.work[(k, i)] != self.disk(k, i)["text"]]

    def externally_changed(self):
        return [(k, i) for (k, i) in self.dirty() if self.base.get((k, i)) != self.disk(k, i)["sha1"]]

    # --- 검증·저장
    def validate(self, kind, fid, text):
        if kind not in KINDS:
            raise OverlayError(f"알 수 없는 파일 종류: {kind}")
        self.path(kind, fid)   # 존재 확인 (새 파일 거부)
        if len(text.encode("utf-8")) > MAX_TEXT:
            raise OverlayError("본문이 1MB 를 넘음")
        text = text.replace("\r\n", "\n")
        obj, msgs = syntax_check(text)
        if obj is not None:
            msgs += structure_check(kind, obj, None if kind == "overrides" else self._orig_id(kind, fid))
        return text, obj, msgs

    def _orig_id(self, kind, fid):
        return json.loads(self.disk(kind, fid)["text"]).get("id")

    def set_text(self, kind, fid, text):
        d = self.disk(kind, fid)
        if text == d["text"]:
            self.work.pop((kind, fid), None)
            self.base.pop((kind, fid), None)
        else:
            self.work[(kind, fid)] = text
            self.base.setdefault((kind, fid), d["sha1"])

    def revert(self, kind, fid):
        self.work.pop((kind, fid), None)
        self.base.pop((kind, fid), None)

    def clear(self):
        self.work.clear()
        self.base.clear()

    # --- 인메모리 임포트
    def entries(self, kind, override_text=None):
        """작업 사본 기준의 원본 dict 목록. override_text = {(kind, id): text} 는 저장 없이 dry-run 용."""
        out = []
        for fid, fn in self.index.get(kind, {}).items():
            t = (override_text or {}).get((kind, fid))
            if t is None:
                t = self.text(kind, fid)
            d = json.loads(t)
            d["_file"] = fn
            out.append(d)
        return out

    def overrides(self, override_text=None):
        t = (override_text or {}).get(("overrides", "overrides"))
        if t is None:
            t = self.text("overrides", "overrides")
        return json.loads(t)

    def build_fantasy_table(self, override_text=None):
        return import_fantasies.build_table(self.entries("fantasy", override_text), self.overrides(override_text),
                                            "작업 사본(overlay)")

    def build_monster_table(self, override_text=None):
        if "monster" not in self.dirs:
            return None
        return import_monsters.build_table(self.entries("monster", override_text), self.entries("pattern", override_text))

    def dry_run(self, kind, fid, text, current_fantasy, current_monster=None):
        """text 를 저장하지 않고 임포트해 시뮬 테이블 변화와 경고를 돌려준다."""
        ot = {(kind, "overrides" if kind == "overrides" else fid): text}
        changes, warnings, new_f, new_m = [], [], None, None
        if kind in ("fantasy", "overrides"):
            new_f = self.build_fantasy_table(ot)
            before = {e["id"]: e for e in current_fantasy["fantasies"]}
            for e in new_f["fantasies"]:
                b = before.get(e["id"])
                keys = ("grade", "available", "fidelity", "effects")
                strip = lambda x: json.dumps({k: _nosrc(x.get(k)) for k in keys}, sort_keys=True, ensure_ascii=False)  # noqa: E731
                if b is None or strip(b) != strip(e):
                    changes.append({"id": e["id"], "name": e.get("name"),
                                    "before": {k: _nosrc(b.get(k)) for k in keys} if b else None,
                                    "after": {k: _nosrc(e.get(k)) for k in keys}})
                    if e["fidelity"] == "none":
                        warnings.append(f"{e['id']}: 매핑할 수 없는 효과 → none (곡선에 반영되지 않음)")
                    unl = [ef["type"] for ef in e["effects"] if not ef.get("src")]
                    if unl and e.get("mapping") != "override":
                        warnings.append(f"{e['id']}: 원본 연결(src)이 없는 효과 {unl} — 이후 숫자 UI 편집이 원본에 반영되지 않을 수 있음")
            gone = set(before) - {e["id"] for e in new_f["fantasies"]}
            for g in sorted(gone):
                changes.append({"id": g, "name": before[g].get("name"), "before": "있음", "after": None})
                warnings.append(f"{g}: 비활성(enabled=false) 등으로 테이블에서 빠짐")
        else:
            new_m = self.build_monster_table(ot)
            before = {m["id"]: m for m in (current_monster or {}).get("monsters", [])}
            keys = ("act", "tier", "hp", "strength", "ai", "patterns", "fidelity")
            strip = lambda x: json.dumps({k: _nosrc(x.get(k)) for k in keys}, sort_keys=True, ensure_ascii=False)  # noqa: E731
            for m in new_m["monsters"]:
                b = before.get(m["id"])
                if b is None or strip(b) != strip(m):
                    changes.append({"id": m["id"], "name": m.get("name"),
                                    "before": {k: _nosrc(b.get(k)) for k in keys} if b else None,
                                    "after": {k: _nosrc(m.get(k)) for k in keys}})
                for w in m.get("warnings", []):
                    warnings.append(f"{m['id']}: {w}")
        return {"changes": changes, "warnings": warnings, "affected": [c["id"] for c in changes],
                "fantasy_table": new_f, "monster_table": new_m}


def _nosrc(x):
    if isinstance(x, list):
        return [_nosrc(v) for v in x]
    if isinstance(x, dict):
        return {k: _nosrc(v) for k, v in x.items() if k not in ("src", "_file")}
    return x
