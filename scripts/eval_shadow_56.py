"""Valuta live (10,8) e shadow (5,6) sullo stesso intervallo forward.

Da eseguire manualmente dopo 4-6 settimane. Sono inclusi solo eventi per cui
sono gia' disponibili almeno 48 barre H1 successive. Lo script non prende
decisioni e non modifica il prodotto.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import backtest_compression_tf as TF
from fx_bias_radar import pairs as P
from fx_bias_radar.oanda_fetch import env_credentials

HORIZONS = (4, 12, 24, 48)
LIVE_LOG = os.path.join("reports", "prerottura", "calls_log.csv")
SHADOW_LOG = os.path.join(
    "reports", "prerottura", "calls_log_shadow_56.csv"
)


def _parse_time(value):
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def load_rows(path):
    if not os.path.isfile(path):
        return []
    with open(path, newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _forward(closes, index, horizon, direction):
    p0, p1 = closes[index], closes[index + horizon]
    raw = (p1 - p0) / p0
    return raw if direction == "LONG" else -raw


def _agg(values):
    return {
        "n": len(values),
        "hit": round(sum(value > 0 for value in values) / len(values), 4)
        if values
        else None,
        "mean_pct": round(100 * sum(values) / len(values), 4)
        if values
        else None,
    }


def evaluate_rows(rows, candles_by_pair, start, end):
    returns = {horizon: [] for horizon in HORIZONS}
    directions = {"LONG": [], "SHORT": []}
    rejected_without_48 = 0
    maps = {}
    closes = {}
    for pair, candles in candles_by_pair.items():
        maps[pair] = {
            _parse_time(candle.time): index
            for index, candle in enumerate(candles)
        }
        closes[pair] = [candle.c for candle in candles]

    for row in rows:
        try:
            bar = _parse_time(row.get("h1_bar_utc"))
        except (TypeError, ValueError):
            continue
        if not (start <= bar < end):
            continue
        pair = row.get("pair")
        direction = row.get("dir")
        if pair not in maps or direction not in ("LONG", "SHORT"):
            continue
        index = maps[pair].get(bar)
        if index is None or index + max(HORIZONS) >= len(closes[pair]):
            rejected_without_48 += 1
            continue
        for horizon in HORIZONS:
            value = _forward(closes[pair], index, horizon, direction)
            returns[horizon].append(value)
            if horizon == 12:
                directions[direction].append(value)

    window_weeks = (end - start).total_seconds() / (7 * 86400)
    horizon_metrics = {
        str(horizon): _agg(returns[horizon]) for horizon in HORIZONS
    }
    n = horizon_metrics["12"]["n"]
    return {
        "horizons": horizon_metrics,
        "direction_12": {
            "LONG": _agg(directions["LONG"]),
            "SHORT": _agg(directions["SHORT"]),
        },
        "signals_per_week": round(n / window_weeks, 2)
        if window_weeks > 0
        else None,
        "excluded_without_48_h1": rejected_without_48,
    }


def _fmt(value):
    return "-" if value is None else str(value)


def render(result):
    lines = [
        "# Confronto forward live (10,8) vs shadow (5,6)",
        "",
        f"Finestra: {result['start_utc']} <= evento < {result['end_utc']}.",
        "Inclusi solo eventi con almeno +48 H1 disponibili. Nessuna decisione "
        "automatica; campioni sotto ~150 eventi non sono conclusivi.",
        "",
        "| coorte | n | hit +12 | medio% +12 | LONG | SHORT | segnali/settimana |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for cohort in ("live_10_8", "shadow_5_6"):
        metrics = result["cohorts"][cohort]
        h12 = metrics["horizons"]["12"]
        lines.append(
            f"| {cohort} | {h12['n']} | {_fmt(h12['hit'])} | "
            f"{_fmt(h12['mean_pct'])} | "
            f"{metrics['direction_12']['LONG']['n']} | "
            f"{metrics['direction_12']['SHORT']['n']} | "
            f"{_fmt(metrics['signals_per_week'])} |"
        )
    lines.extend(
        [
            "",
            "## Orizzonti completi",
            "",
            "| coorte | orizzonte H1 | n | hit | medio% |",
            "|---|---:|---:|---:|---:|",
        ]
    )
    for cohort in ("live_10_8", "shadow_5_6"):
        for horizon in HORIZONS:
            row = result["cohorts"][cohort]["horizons"][str(horizon)]
            lines.append(
                f"| {cohort} | +{horizon} | {row['n']} | "
                f"{_fmt(row['hit'])} | {_fmt(row['mean_pct'])} |"
            )
    lines.append("")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", required=True, help="ISO UTC inclusivo")
    parser.add_argument("--end", required=True, help="ISO UTC esclusivo")
    parser.add_argument("--live-log", default=LIVE_LOG)
    parser.add_argument("--shadow-log", default=SHADOW_LOG)
    parser.add_argument("--out", help="prefisso output opzionale, senza estensione")
    parser.add_argument("--max-workers", type=int, default=8)
    args = parser.parse_args()
    try:
        start, end = _parse_time(args.start), _parse_time(args.end)
        if end <= start:
            raise ValueError("--end deve essere successivo a --start")
        live_rows = load_rows(args.live_log)
        shadow_rows = load_rows(args.shadow_log)
        earliest = min(
            [start]
            + [
                _parse_time(row["h1_bar_utc"])
                for row in live_rows + shadow_rows
                if row.get("h1_bar_utc")
            ]
        )
        hours = (datetime.now(timezone.utc) - earliest).total_seconds() / 3600
        count = max(500, math.ceil(hours) + 200)
        token, env = env_credentials()
        h1 = TF.fetch_all(
            token, env, "H1", count, max_workers=args.max_workers
        )
        result = {
            "start_utc": start.isoformat(),
            "end_utc": end.isoformat(),
            "cohorts": {
                "live_10_8": evaluate_rows(live_rows, h1, start, end),
                "shadow_5_6": evaluate_rows(shadow_rows, h1, start, end),
            },
        }
        report = render(result)
        print(report)
        if args.out:
            parent = os.path.dirname(args.out)
            if parent:
                os.makedirs(parent, exist_ok=True)
            with open(f"{args.out}.md", "w", encoding="utf-8") as handle:
                handle.write(report)
            with open(f"{args.out}.json", "w", encoding="utf-8") as handle:
                json.dump(result, handle, indent=2)
    except Exception as exc:  # noqa: BLE001
        print(f"ERRORE eval shadow: {exc}")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
