"""Run a full 28-pair H4 scan and write the Markdown/JSON report.

Usage:
  python scripts/run_h4_scan.py --fixtures tests/fixtures/golden_2026H1
  python scripts/run_h4_scan.py --oanda --count 500   (needs OANDA_ACCESS_TOKEN)

Radar of attention only. No orders, no alerts (alerts are M2).
"""

from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fx_bias_radar import report as R
from fx_bias_radar import scan_service as S


def main() -> int:
    ap = argparse.ArgumentParser()
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--fixtures", help="directory with <PAIR>.json candle files")
    src.add_argument("--oanda", action="store_true", help="fetch live from OANDA")
    ap.add_argument("--count", type=int, default=500, help="H4 bars to fetch (>=400 raccomandato)")
    ap.add_argument("--out", default="reports", help="output directory")
    args = ap.parse_args()

    try:
        if args.fixtures:
            rep = S.run_scan_from_fixtures(args.fixtures)
        else:
            rep = S.run_scan_from_oanda(count=args.count)
    except ValueError as exc:
        print(f"ERRORE: {exc}")
        return 2

    os.makedirs(args.out, exist_ok=True)
    run_time = rep["run_time_utc"]
    stamp = run_time.replace(":", "").replace("+0000", "Z").replace("+00:00", "Z")
    md_path = os.path.join(args.out, f"scan_{stamp}.md")
    json_path = os.path.join(args.out, f"scan_{stamp}.json")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(R.render_markdown(rep))
    with open(json_path, "w", encoding="utf-8") as f:
        f.write(R.to_json(rep))

    print(f"Report: {md_path}")
    if rep["misaligned_pairs"]:
        print(f"ATTENZIONE coppie non allineate: {rep['misaligned_pairs']}")
    for f_ in rep["focus"]:
        print(f"  {f_['rank']}. {f_['pair']} {f_['bias']} {f_['stato']} "
              f"score {f_['score']} spread {f_['spread']:.2f} {f_['note']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
