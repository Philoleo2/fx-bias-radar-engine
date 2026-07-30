"""Logger forward-only del segnale d1w con k_d=5 e k_w=6.

Il live resta (10,8). Questo runner scarica candele chiuse, calcola soltanto la
coorte ombra (5,6) e la accoda a un CSV separato, idempotente per barra H1.
Non modifica snapshot, payload, classifica, pagina o email.
"""

from __future__ import annotations

import argparse
import csv
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fx_bias_radar import calls as CALLS
from fx_bias_radar import compression as COMP
from fx_bias_radar import pairs as P
from fx_bias_radar import strength_h1 as SH
from fx_bias_radar.oanda_fetch import env_credentials

SHADOW_K_D = 5
SHADOW_K_W = 6
H1_WINDOW = 12
SHADOW_LOG = os.path.join(
    "reports", "prerottura", "calls_log_shadow_56.csv"
)


def _aligned_h1(candles_by_pair):
    missing = [pair for pair in P.PAIRS if not candles_by_pair.get(pair)]
    if missing:
        raise RuntimeError(f"H1 mancanti per: {', '.join(missing)}")
    maps = {
        pair: {str(candle.time): candle for candle in candles_by_pair[pair]}
        for pair in P.PAIRS
    }
    common = set(maps[P.PAIRS[0]])
    for pair in P.PAIRS[1:]:
        common &= set(maps[pair])
    if not common:
        raise RuntimeError("nessun timestamp H1 comune alle 28 coppie")
    ordered = sorted(common)
    return {
        pair: [maps[pair][timestamp] for timestamp in ordered]
        for pair in P.PAIRS
    }, ordered[-1]


def shadow_signals(h1_by_pair, d1_by_pair, w_by_pair):
    aligned_h1, h1_bar = _aligned_h1(h1_by_pair)
    rows = COMP.daily_weekly_aligned_breakouts(
        aligned_h1,
        d1_by_pair,
        w_by_pair,
        k_d=SHADOW_K_D,
        k_w=SHADOW_K_W,
        h1_window=H1_WINDOW,
    )
    return h1_bar, rows


def _ensure_log(path):
    if os.path.isfile(path):
        return
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as handle:
        csv.DictWriter(handle, fieldnames=CALLS.FIELDS).writeheader()


def run_shadow(h1_by_pair, d1_by_pair, w_by_pair, log_path=SHADOW_LOG,
               ts_utc=None):
    h1_bar, signals = shadow_signals(h1_by_pair, d1_by_pair, w_by_pair)
    _ensure_log(log_path)
    stamp = ts_utc or datetime.now(timezone.utc).isoformat(timespec="seconds")
    written = CALLS.append_calls(log_path, h1_bar, signals, stamp)
    return {
        "h1_bar_utc": h1_bar,
        "signals": signals,
        "written": written,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--oanda", action="store_true")
    parser.add_argument("--out", default=SHADOW_LOG)
    parser.add_argument("--h1-count", type=int, default=SH.DEFAULT_H1_COUNT)
    parser.add_argument("--d1-count", type=int, default=300)
    parser.add_argument("--w-count", type=int, default=200)
    args = parser.parse_args()
    if not args.oanda:
        parser.error("serve --oanda")
        return 2
    try:
        token, env = env_credentials()
        h1 = SH.fetch_all_h1(token, env=env, count=args.h1_count)
        d1 = SH.fetch_all_daily(token, env=env, count=args.d1_count)
        w1 = SH.fetch_all_weekly(token, env=env, count=args.w_count)
        result = run_shadow(h1, d1, w1, log_path=args.out)
    except Exception as exc:  # noqa: BLE001
        print(f"ERRORE shadow (5,6): {exc}")
        return 2
    print(
        f"shadow (5,6): barra={result['h1_bar_utc']} "
        f"segnali={len(result['signals'])} scritti={result['written']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
