"""Backtest compressione multi-timeframe.

Research-only. Non tocca motore live, API, dashboard o scanner.

Test richiesti:
1. Uscita da compressione H4 allineata a D e W.
2. Uscita da compressione H1 allineata a H4 e D.

Baseline di confronto: rottura H1 semplice allineata a D e W, cioe' la coorte
H1+D1+W gia' promossa nel sito. Tutto e' valutato in ore (+4/+12/+24/+48) e
senza lookahead: per ogni evento si usa solo contesto superiore gia' chiuso.
"""

from __future__ import annotations

import argparse
import bisect
import json
import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import backtest_compression_tf as TF
from fx_bias_radar import compression as COMP
from fx_bias_radar import pairs as P

H1_WINDOW = 12
H4_WINDOW = 12
D1_K = 10
W_K = 8
H4_K = 12
SPLIT_FRAC = 0.6
HORIZONS_HOURS = [4, 12, 24, 48]

COHORTS = (
    "h1_breakout_d1w",
    "h4_compression_d1w",
    "h1_compression_h4d",
    "h1_breakout_all",
    "h4_compression_all",
    "h1_compression_all",
)

COHORT_LABELS = {
    "h1_breakout_d1w": "Baseline H1 breakout + D + W",
    "h4_compression_d1w": "H4 compressione + D + W",
    "h1_compression_h4d": "H1 compressione + H4 + D",
    "h1_breakout_all": "H1 breakout tutti",
    "h4_compression_all": "H4 compressioni tutte",
    "h1_compression_all": "H1 compressioni tutte",
}


def parse_time(value: str) -> datetime:
    text = str(value)
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    dt = datetime.fromisoformat(text)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def candle_open(candle) -> datetime:
    return parse_time(candle.time)


def close_time(candle, granularity: str) -> datetime:
    if granularity == "H1":
        return candle_open(candle) + timedelta(hours=1)
    if granularity == "H4":
        return candle_open(candle) + timedelta(hours=4)
    if granularity == "D":
        return candle_open(candle) + timedelta(days=1)
    if granularity == "W":
        return candle_open(candle) + timedelta(days=7)
    raise ValueError(f"granularity non supportata: {granularity}")


def active_map(candles, k, window=COMP.DEFAULT_WINDOW, percentile=COMP.DEFAULT_PERCENTILE):
    """Direzione attiva dopo un breakout da compressione entro k barre."""
    active = [None] * len(candles)
    last_dir = None
    last_bar = -10 ** 9
    for i in range(len(candles)):
        direction = COMP.compression_breakout(candles, i, window, percentile)
        if direction is not None:
            last_dir, last_bar = direction, i
        if last_dir is not None and (i - last_bar) <= k:
            active[i] = last_dir
    return active


def prior_active(close_times, active, event_close):
    """Stato della barra superiore gia' chiusa al momento dell'evento."""
    idx = bisect.bisect_right(close_times, event_close) - 1
    return active[idx] if 0 <= idx < len(active) else None


def _empty():
    return {
        cohort: {"train": {h: [] for h in HORIZONS_HOURS},
                 "test": {h: [] for h in HORIZONS_HOURS}}
        for cohort in COHORTS
    }


def _fwd(closes, t, bars, direction):
    if t + bars >= len(closes):
        return None
    p0 = closes[t]
    p1 = closes[t + bars]
    if p0 is None or p1 is None or p0 == 0:
        return None
    ret = (p1 - p0) / p0
    return ret if direction == "LONG" else -ret


def _add_event(buckets, cohort, sample, closes, t, direction, bars_per_hour):
    for hours in HORIZONS_HOURS:
        bars = int(hours * bars_per_hour)
        if bars <= 0:
            continue
        value = _fwd(closes, t, bars, direction)
        if value is not None:
            buckets[cohort][sample][hours].append(value)


def process_pair(pair, h1, h4, d1, w1, buckets,
                 d1_k=D1_K, w_k=W_K, h4_k=H4_K):
    if len(h1) < H1_WINDOW + 5:
        return
    if len(h4) < H4_WINDOW + 5:
        return
    if len(d1) < COMP.DEFAULT_WINDOW + COMP.RANK_WINDOW + 2:
        return
    if len(w1) < COMP.DEFAULT_WINDOW + COMP.RANK_WINDOW + 2:
        return

    h1_closes = [c.c for c in h1]
    h4_closes = [c.c for c in h4]

    h4_close_times = [close_time(c, "H4") for c in h4]
    d1_close_times = [close_time(c, "D") for c in d1]
    w_close_times = [close_time(c, "W") for c in w1]

    h4_active = active_map(h4, h4_k, H4_WINDOW)
    d1_active = active_map(d1, d1_k)
    w_active = active_map(w1, w_k)

    h1_split = int(len(h1) * SPLIT_FRAC)
    h4_split = int(len(h4) * SPLIT_FRAC)

    for t in range(H1_WINDOW + 1, len(h1)):
        event_close = close_time(h1[t], "H1")
        sample = "train" if t < h1_split else "test"

        breakout = COMP.is_new_breakout(h1, t, H1_WINDOW)
        if breakout is not None:
            _add_event(buckets, "h1_breakout_all", sample, h1_closes, t, breakout, 1)
            d1_dir = prior_active(d1_close_times, d1_active, event_close)
            w_dir = prior_active(w_close_times, w_active, event_close)
            if d1_dir == breakout and w_dir == breakout:
                _add_event(buckets, "h1_breakout_d1w", sample, h1_closes, t, breakout, 1)

        compressed = COMP.compression_breakout(h1, t, H1_WINDOW)
        if compressed is not None:
            _add_event(buckets, "h1_compression_all", sample, h1_closes, t, compressed, 1)
            h4_dir = prior_active(h4_close_times, h4_active, event_close)
            d1_dir = prior_active(d1_close_times, d1_active, event_close)
            if h4_dir == compressed and d1_dir == compressed:
                _add_event(buckets, "h1_compression_h4d", sample, h1_closes, t, compressed, 1)

    for t in range(H4_WINDOW + 1, len(h4)):
        event_close = close_time(h4[t], "H4")
        sample = "train" if t < h4_split else "test"
        compressed = COMP.compression_breakout(h4, t, H4_WINDOW)
        if compressed is None:
            continue
        _add_event(buckets, "h4_compression_all", sample, h4_closes, t, compressed, 0.25)
        d1_dir = prior_active(d1_close_times, d1_active, event_close)
        w_dir = prior_active(w_close_times, w_active, event_close)
        if d1_dir == compressed and w_dir == compressed:
            _add_event(buckets, "h4_compression_d1w", sample, h4_closes, t, compressed, 0.25)


def _agg(values):
    if not values:
        return {"n": 0, "hit": None, "mean_pct": None}
    return {
        "n": len(values),
        "hit": round(sum(1 for v in values if v > 0) / len(values), 3),
        "mean_pct": round(100 * sum(values) / len(values), 4),
    }


def _edge(a, b, digits=3):
    return round(a - b, digits) if a is not None and b is not None else None


def aggregate(buckets):
    return {
        cohort: {
            sample: {h: _agg(buckets[cohort][sample][h]) for h in HORIZONS_HOURS}
            for sample in ("train", "test")
        }
        for cohort in COHORTS
    }


def verdict(agg):
    test = {c: agg[c]["test"] for c in COHORTS}
    baseline = test["h1_breakout_d1w"][12]
    h4 = test["h4_compression_d1w"][12]
    h1 = test["h1_compression_h4d"][12]

    def improves(row):
        if not baseline["hit"] or not row["hit"]:
            return False
        return row["hit"] > baseline["hit"] and (
            row["mean_pct"] is not None and baseline["mean_pct"] is not None
            and row["mean_pct"] > baseline["mean_pct"]
        )

    h4_improves = improves(h4)
    h1_improves = improves(h1)
    if not h4_improves and not h1_improves:
        text = ("Nessuna delle due nuove coorti migliora la baseline H1+D+W su hit "
                "e ritorno medio +12h. Per la decisione sul sito: non c'e' evidenza "
                "per tenere un motore H4 come filtro direzionale operativo.")
    elif h4_improves and not h1_improves:
        text = "Solo H4 compressione + D + W migliora la baseline H1+D+W."
    elif h1_improves and not h4_improves:
        text = "Solo H1 compressione + H4 + D migliora la baseline H1+D+W."
    else:
        text = "Entrambe le nuove coorti migliorano la baseline H1+D+W."
    return {
        "baseline_hit_12": baseline["hit"],
        "baseline_mean_12": baseline["mean_pct"],
        "h4_d1w_hit_12": h4["hit"],
        "h4_d1w_mean_12": h4["mean_pct"],
        "h1_h4d_hit_12": h1["hit"],
        "h1_h4d_mean_12": h1["mean_pct"],
        "h4_improves_baseline": h4_improves,
        "h1_improves_baseline": h1_improves,
        "text": text,
    }


def write_report(buckets, out_dir, source, counts):
    os.makedirs(out_dir, exist_ok=True)
    agg = aggregate(buckets)
    decision = verdict(agg)
    payload = {
        "source": source,
        "counts_requested": counts,
        "split_frac": SPLIT_FRAC,
        "horizons_hours": HORIZONS_HOURS,
        "params": {
            "h1_window": H1_WINDOW,
            "h4_window": H4_WINDOW,
            "d1_active_bars": D1_K,
            "w_active_bars": W_K,
            "h4_active_bars": H4_K,
        },
        "cohort_labels": COHORT_LABELS,
        "agg": agg,
        "verdict": decision,
    }
    json_path = os.path.join(out_dir, "compression_align.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)

    test = {cohort: agg[cohort]["test"] for cohort in COHORTS}
    train = {cohort: agg[cohort]["train"] for cohort in COHORTS}
    base12 = test["h1_breakout_d1w"][12]

    lines = [
        "# Backtest compressione allineata multi-timeframe",
        "",
        f"Fonte: {source}",
        f"Richieste: H1={counts['h1']} H4={counts['h4']} D1={counts['d1']} W={counts['w']}",
        f"Split walk-forward semplice: train {int(SPLIT_FRAC * 100)}%, test {int((1 - SPLIT_FRAC) * 100)}%.",
        "No lookahead: ogni evento usa solo timeframe superiori gia' chiusi al momento dell'ingresso.",
        "",
        "## Cosa viene confrontato",
        "- Baseline: rottura H1 semplice allineata a Daily + Weekly, cioe' il motore `allineate` attuale.",
        "- Test 1: rottura da compressione H4 allineata a Daily + Weekly.",
        "- Test 2: rottura da compressione H1 allineata a H4 + Daily.",
        "",
        "## TEST out-of-sample",
        "| coorte | n(+12h) | hit +4h | hit +12h | hit +24h | hit +48h | medio% +12h | edge hit vs baseline | edge medio vs baseline |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for cohort in COHORTS:
        row = test[cohort]
        row12 = row[12]
        edge_hit = _edge(row12["hit"], base12["hit"])
        edge_mean = _edge(row12["mean_pct"], base12["mean_pct"], 4)
        lines.append(
            f"| {COHORT_LABELS[cohort]} | {row12['n']} | {row[4]['hit']} | {row12['hit']} | "
            f"{row[24]['hit']} | {row[48]['hit']} | {row12['mean_pct']} | {edge_hit} | {edge_mean} |"
        )

    lines.extend([
        "",
        "## TRAIN sample",
        "| coorte | n(+12h) | hit +12h | medio% +12h |",
        "|---|---:|---:|---:|",
    ])
    for cohort in COHORTS:
        row12 = train[cohort][12]
        lines.append(f"| {COHORT_LABELS[cohort]} | {row12['n']} | {row12['hit']} | {row12['mean_pct']} |")

    lines.extend([
        "",
        "## Decisione provvisoria",
        decision["text"],
        "",
        "## Numeri chiave +12h",
        f"- Baseline H1+D+W: hit {decision['baseline_hit_12']} | medio% {decision['baseline_mean_12']}",
        f"- H4 compressione+D+W: hit {decision['h4_d1w_hit_12']} | medio% {decision['h4_d1w_mean_12']}",
        f"- H1 compressione+H4+D: hit {decision['h1_h4d_hit_12']} | medio% {decision['h1_h4d_mean_12']}",
        "",
        "## Nota per Sonnet",
        "Se entrambe le coorti restano sotto la baseline H1+D+W, il dato supporta l'ipotesi di rimuovere dal sito il motore H4 come guida direzionale e lasciare solo il filtro daily+weekly piu' selettivo.",
        "",
    ])

    md_path = os.path.join(out_dir, "compression_align.md")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    return md_path


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--oanda", action="store_true")
    ap.add_argument("--h1-count", type=int, default=20000)
    ap.add_argument("--h4-count", type=int, default=5000)
    ap.add_argument("--d1-count", type=int, default=1500)
    ap.add_argument("--w-count", type=int, default=800)
    ap.add_argument("--out", default="reports/compression_align")
    args = ap.parse_args()
    if not args.oanda:
        ap.error("serve --oanda")
        return 2

    try:
        from fx_bias_radar.oanda_fetch import env_credentials

        token, env = env_credentials()
        h1_all = TF.fetch_all(token, env, "H1", args.h1_count)
        h4_all = TF.fetch_all(token, env, "H4", args.h4_count)
        d1_all = TF.fetch_all(token, env, "D", args.d1_count)
        w_all = TF.fetch_all(token, env, "W", args.w_count)

        buckets = _empty()
        for pair in P.PAIRS:
            process_pair(
                pair,
                h1_all.get(pair, []),
                h4_all.get(pair, []),
                d1_all.get(pair, []),
                w_all.get(pair, []),
                buckets,
            )
    except Exception as exc:  # noqa: BLE001
        print(f"ERRORE: {exc}")
        return 2

    path = write_report(
        buckets,
        args.out,
        "OANDA H1/H4/D/W",
        {"h1": args.h1_count, "h4": args.h4_count, "d1": args.d1_count, "w": args.w_count},
    )
    print(f"Backtest compressione allineata -> {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
