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


def build(data, template_path=os.path.join(HERE, "viewer_template.html")):
    with open(template_path, encoding="utf-8") as fp:
        tpl = fp.read()
    if tpl.count(PLACEHOLDER) != 1:
        raise ValueError("템플릿에 데이터 자리표시자가 정확히 1개 있어야 함")
    blob = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    # <script> 안에서 안전하도록: </script>, <!-- 를 끊는다 (JSON 의미는 같음)
    blob = blob.replace("</", "<\\/").replace("<!--", "<\\!--")
    return tpl.replace(PLACEHOLDER, blob)


def main(argv=None):
    ap = argparse.ArgumentParser(description="단일 HTML 뷰어 생성")
    ap.add_argument("--data", default=os.path.join("sim_results", "fantasy_curves.json"))
    ap.add_argument("--out", default=None, help="기본: 데이터 파일과 같은 폴더의 fantasy_viewer.html")
    ap.add_argument("--template", default=os.path.join(HERE, "viewer_template.html"))
    args = ap.parse_args(argv)
    with open(args.data, encoding="utf-8") as fp:
        data = json.load(fp)
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
