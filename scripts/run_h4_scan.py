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
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fx_bias_radar import candles as C
from fx_bias_radar import currency_index as CI
from fx_bias_radar import engine as E
from fx_bias_radar import pairs as P
from fx_bias_radar import report as R
from fx_bias_radar.focus import build_focus


def main() -> int:
    ap = argparse.ArgumentParser()
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--fixtures", help="directory with <PAIR>.json candle files")
    src.add_argument("--oanda", action="store_true", help="fetch live from OANDA")
    ap.add_argument("--count", type=int, default=500, help="H4 bars to fetch (>=400 raccomandato)")
    ap.add_argument("--out", default="reports", help="output directory")
    args = ap.parse_args()

    if args.fixtures:
        candles_by_pair = C.load_fixture_dir(args.fixtures)
    else:
        from fx_bias_radar.oanda_fetch import env_credentials, fetch_all_pairs
        token, env = env_credentials()
        candles_by_pair = fetch_all_pairs(token, env=env, count=args.count)

    missing = [p for p in P.PAIRS if p not in candles_by_pair]
    if missing:
        print(f"ERRORE: coppie mancanti: {missing}")
        return 2

    times, closes, align_info = C.align(candles_by_pair)
    cd = CI.build(times, closes)

    last_by_pair = {}
    for pair in P.PAIRS:
        frames = CI.pair_frames(cd, pair)
        results = E.run_pair(pair, frames)
        last_by_pair[pair] = results[-1]

    focus_rows = build_focus(last_by_pair)
    run_time = datetime.now(timezone.utc).isoformat(timespec="seconds")
    rep = R.build_report(run_time, align_info, last_by_pair, focus_rows)

    os.makedirs(args.out, exist_ok=True)
    stamp = run_time.replace(":", "").replace("+0000", "Z").replace("+00:00", "Z")
    md_path = os.path.join(args.out, f"scan_{stamp}.md")
    json_path = os.path.join(args.out, f"scan_{stamp}.json")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(R.render_markdown(rep))
    with open(json_path, "w", encoding="utf-8") as f:
        f.write(R.to_json(rep))

    print(f"Report: {md_path}")
    if align_info.misaligned_pairs:
        print(f"ATTENZIONE coppie non allineate: {align_info.misaligned_pairs}")
    for f_ in rep["focus"]:
        print(f"  {f_['rank']}. {f_['pair']} {f_['bias']} {f_['stato']} "
              f"score {f_['score']} spread {f_['spread']:.2f} {f_['note']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
