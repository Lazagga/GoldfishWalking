#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""fantasy_curves.json 을 viewer_template.html 에 내장해 단일 HTML(fantasy_viewer.html)을 만든다.

file:// 로 더블클릭해서 열 수 있어야 하므로(브라우저는 file:// 에서 fetch 를 막음) 데이터를
<script type="application/json"> 안에 넣는다. 외부 라이브러리·네트워크 요청 없음.

  python build_viewer.py                                   # sim_results/fantasy_curves.json → sim_results/fantasy_viewer.html
  python build_viewer.py --data X.json --out viewer.html
"""
from __future__ import annotations

import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PLACEHOLDER = "/*__DATA__*/"


SERVER_PLACEHOLDER = "/*__SERVER__*/null"
DEFAULT_TARGETS = os.path.join(HERE, "balance_targets.json")


def _script_safe(obj):
    blob = json.dumps(obj, ensure_ascii=False, separators=(",", ":"))
    # <script> 안에서 안전하도록: </script>, <!-- 를 끊는다 (JSON 의미는 같음)
    return blob.replace("</", "<\\/").replace("<!--", "<\\!--")


def load_targets(path=DEFAULT_TARGETS):
    try:
        with open(path, encoding="utf-8") as fp:
            return json.load(fp)
    except (OSError, ValueError):
        return None


def build(data, template_path=os.path.join(HERE, "viewer_template.html"), server=None, targets="default"):
    """server = {"token", "port"} 이면 편집 UI 가 켜진 서버 모드 HTML. None 이면 읽기 전용 정적 HTML."""
    with open(template_path, encoding="utf-8") as fp:
        tpl = fp.read()
    if tpl.count(PLACEHOLDER) != 1 or tpl.count(SERVER_PLACEHOLDER) != 1:
        raise ValueError("템플릿에 데이터/서버 자리표시자가 각각 정확히 1개 있어야 함")
    data = dict(data)
    data["balance_targets"] = load_targets() if targets == "default" else targets
    out = tpl.replace(PLACEHOLDER, _script_safe(data))
    return out.replace(SERVER_PLACEHOLDER, _script_safe(server) if server else "null")


# 시너지 히트맵(synergy.json)은 뷰어에서 뺐다 — 조합은 승률·생존 곡선에서 체크한 환상으로 계산한다 (synergy_scan.py CLI 는 그대로).
EXTRAS = {"monster_metrics": "monster_metrics.json", "calibration": "calibration.json"}


def attach_extras(data, results_dir):
    """결과 폴더에 몬스터 지표(F2)·보정(F3) 결과가 있으면 뷰어 데이터에 붙인다 (새 탭)."""
    data = dict(data)
    for key, fn in EXTRAS.items():
        p = os.path.join(results_dir, fn)
        if key not in data and os.path.exists(p):
            try:
                with open(p, encoding="utf-8") as fp:
                    data[key] = json.load(fp)
            except (OSError, ValueError):
                pass
    return data


def main(argv=None):
    ap = argparse.ArgumentParser(description="단일 HTML 뷰어 생성")
    ap.add_argument("--data", default=os.path.join("sim_results", "fantasy_curves.json"))
    ap.add_argument("--out", default=None, help="기본: 데이터 파일과 같은 폴더의 fantasy_viewer.html")
    ap.add_argument("--template", default=os.path.join(HERE, "viewer_template.html"))
    ap.add_argument("--no-extras", action="store_true", help="시너지·몬스터·보정 결과를 붙이지 않음")
    args = ap.parse_args(argv)
    with open(args.data, encoding="utf-8") as fp:
        data = json.load(fp)
    if not args.no_extras:
        data = attach_extras(data, os.path.dirname(os.path.abspath(args.data)))
    out = args.out or os.path.join(os.path.dirname(os.path.abspath(args.data)), "fantasy_viewer.html")
    html = build(data, args.template)
    with open(out, "w", encoding="utf-8") as fp:
        fp.write(html)
    m = data.get("meta", {})
    print(f"{out} ({len(html) / 1024:.0f} KB, scan {m.get('scan_id')}, effect_mode {m.get('effect_mode')})")
    if m.get("effect_mode") != "table":
        print("  ※ effect_mode 가 table 이 아니므로 뷰어는 차단 메시지만 표시함", file=sys.stderr)
    return out


if __name__ == "__main__":
    main()
