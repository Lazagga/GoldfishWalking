#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""몬스터 전투 로그 재생 (v4.5 F16.6) — 서버 없이 같은 재생을 하고 표로 출력한다.

  python monster_log.py --monster Mob_30302_CosmicTree --seed mon1 --run 1234 [--ord 0] [--set key=value] [--json]

monster_metrics.py 와 같은 설정(몬스터 테이블 모델, digits 등)으로 그 런을 그대로 다시 돌려, 그 몬스터의 ord 번째 전투의
보유 환상과 턴별 로그를 보여 준다. 같은 코드 버전·같은 설정이어야 지표 때의 전투와 같다.
"""
import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import fantasy_scan as fs  # noqa: E402
import matchup_sim as ms  # noqa: E402
from sim_service import battlelog as bl  # noqa: E402


def main(argv=None):
    ap = argparse.ArgumentParser(description="몬스터 전투 로그 재생")
    ap.add_argument("--monster", required=True, help="몬스터 ID (예: Mob_30302_CosmicTree)")
    ap.add_argument("--seed", default="mon1")
    ap.add_argument("--run", type=int, required=True, help="런 번호 (시드 = <seed>-<run>)")
    ap.add_argument("--ord", type=int, default=0, help="그 런에서 이 몬스터의 전투 순번 (기본 0)")
    ap.add_argument("--table", default=os.path.join(HERE, "monster_table.json"))
    ap.add_argument("--effects", default=os.path.join(HERE, "fantasy_effects.json"))
    ap.add_argument("--set", action="append", default=[], help="설정 값 key=value (여러 번 가능)")
    ap.add_argument("--json", action="store_true", help="표 대신 JSON 으로 출력")
    args = ap.parse_args(argv)
    if not (0 <= args.run < 10_000_000):
        ap.error("--run 은 0 이상 10,000,000 미만")
    cfg, _ = fs.build_cfg(None, args.set, args.effects)
    cfg["monsters"]["model"] = "table"
    cfg["monsters"]["table_file"] = os.path.abspath(args.table)
    with open(args.effects, encoding="utf-8") as fp:
        fants = {e["id"]: e for e in json.load(fp).get("fantasies", [])}
    try:
        res = bl.replay(cfg, fants, args.monster, args.seed, args.run, args.ord, ctx=ms.SimContext(cfg))
    except LookupError as e:
        print(f"오류: {e}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(res, ensure_ascii=False, indent=1))
        return res
    b = res["battle"]
    print(f"{res['mid']}  시드 {res['seed']}  결과 {res['run'].get('result')}  도달 {res['run'].get('reached_floor')}층")
    print(f"{b['act']}막 {b['floor']}층  {b['ord'] + 1}번째 전투 | 체력 {b['hp0']} → {b['hp1']} | {b['turns']}턴 | 받은 피해 {b['taken']} "
          f"(체력 한도 {b['taken_cap']}) | 최대 1타 {b['max_hit']} | {b['outcome']} | 보유 환상 {b['nfant']}개")
    print(f"\n보유 환상 ({len(res['owned'])}):")
    for o in res["owned"]:
        fl = f"{o['floor'][0]}막 {o['floor'][1]}층" if o["floor"] else "시작"
        print(f"  {o['n']:>2}. {o['name']} [{o['grade']}] {fl} {o['source']}{' *' if o['fx'] else ''}")
    print("\n턴  행동        패턴                굴린→편집→유효          준 피해  받은 피해(초과)  내 체력  몬스터 체력  힘  비고")
    for t in res["turns"]:
        dm = f"{t['mon_dmg']}" + (f"→{t['mon_dmg_edit']}" if t.get("mon_dmg_edit") != t["mon_dmg"] else "") + \
            (f"→{t['mon_dmg_eff']}" if t.get("mon_dmg_eff") != t.get("mon_dmg_edit") else "")
        over = f" (+{t['over']})" if t["over"] else ""
        notes = "; ".join(json.dumps(n, ensure_ascii=False) for n in t["notes"])
        print(f"{t['t']:>2}  {str(t['intent']):<10} {str(t.get('pattern') or ''):<18} {dm:<22} {t['dealt']:>7}  {t['taken']:>9}{over:<10} {t['hp']:>7}  {t['mhp']:>10}  {t['mstr']:>2}  {notes}")
    return res


if __name__ == "__main__":
    r = main()
    sys.exit(r if isinstance(r, int) else 0)
