"""Seed una tantum: ricostruisce il registro chiamate d1w sugli ultimi N giorni,
ricalcolando il segnale (non modifica i motori, li USA). Da lanciare una volta.

Uso: python scripts/seed_calls.py --oanda --days 20 --out reports/prerottura/calls_log.csv
"""

from __future__ import annotations

import argparse
import csv
import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import backtest_compression_tf as TF
import backtest_h1_d1_w_align as HD
from fx_bias_radar import calls as CALLS
from fx_bias_radar import compression as COMP
from fx_bias_radar import pairs as P

H1_WINDOW = 12
D1_K = 10
W_K = 8


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--oanda", action="store_true")
    ap.add_argument("--days", type=int, default=20)
    ap.add_argument("--out", default="reports/prerottura/calls_log.csv")
    args = ap.parse_args()
    if not args.oanda:
        ap.error("serve --oanda")
        return 2
    from fx_bias_radar.oanda_fetch import env_credentials
    token, env = env_credentials()
    h1_all = TF.fetch_all(token, env, "H1", 700)   # ~29 giorni di H1
    d1_all = TF.fetch_all(token, env, "D", 300)
    w_all = TF.fetch_all(token, env, "W", 200)
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=args.days)
    rows = []
    for pair in P.PAIRS:
        h1 = h1_all.get(pair)
        d1 = d1_all.get(pair)
        w = w_all.get(pair)
        if not h1 or not d1 or not w:
            continue
        if len(d1) < COMP.DEFAULT_WINDOW + COMP.RANK_WINDOW + 1:
            continue
        if len(w) < COMP.DEFAULT_WINDOW + COMP.RANK_WINDOW + 1:
            continue
        d1_dates = [HD._date_key(c) for c in d1]
        w_dates = [HD._date_key(c) for c in w]
        d1_active = HD.active_map(d1, D1_K)
        w_active = HD.active_map(w, W_K)
        for t in range(H1_WINDOW + 1, len(h1)):
            tt = CALLS._parse(str(h1[t].time))
            if tt is None or tt < cutoff:
                continue
            d = COMP.is_new_breakout(h1, t, H1_WINDOW)
            if d is None:
                continue
            date = HD._date_key(h1[t])
            if HD.prior_active(d1_dates, d1_active, date) == d and \
               HD.prior_active(w_dates, w_active, date) == d:
                rows.append((str(h1[t].time), pair, d))
    rows.sort()
    parent = os.path.dirname(args.out)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(args.out, "w", newline="", encoding="utf-8") as f:
        wr = csv.DictWriter(f, fieldnames=CALLS.FIELDS)
        wr.writeheader()
        for ts, pair, d in rows:
            wr.writerow({"ts_utc": ts, "h1_bar_utc": ts, "pair": pair, "dir": d})
    print(f"seed: {len(rows)} chiamate negli ultimi {args.days} giorni -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
