"""Confluenza H1 + D1 + W: rottura H1 allineata a daily e weekly.

Research-only. Non tocca motore, soglie operative, dashboard o scanner live.

Obiettivo:
- H1 = evento veloce: rottura nuova del range a 12 barre.
- D1 = contesto: ultimo breakout da compressione daily ancora attivo.
- W = filtro piu' lento: ultimo breakout da compressione weekly ancora attivo.

No lookahead: per ogni barra H1 si usa solo la barra D1/W strettamente precedente
alla data della barra H1. Il confronto principale e':
aligned_d1w vs aligned_d1 vs all.
"""

from __future__ import annotations

import argparse
import bisect
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import backtest_compression_tf as TF
from fx_bias_radar import compression as COMP
from fx_bias_radar import pairs as P

H1_WINDOW = 12
D1_K = 10
W_K = 8
HORIZONS = [4, 12, 24, 48]
SPLIT_FRAC = 0.6
COHORTS = (
    "all",
    "aligned_d1",
    "aligned_w",
    "aligned_d1w",
    "d1_aligned_w_missing",
    "d1_aligned_w_counter",
    "context_none",
)


def active_map(candles, k):
    """Direzione attiva dopo un breakout da compressione entro k barre."""
    active = [None] * len(candles)
    last_dir = None
    last_bar = -10 ** 9
    for i in range(len(candles)):
        d = COMP.compression_breakout(candles, i)
        if d is not None:
            last_dir, last_bar = d, i
        if last_dir is not None and (i - last_bar) <= k:
            active[i] = last_dir
    return active


def _date_key(candle):
    return str(candle.time)[:10]


def prior_active(date_keys, active, h1_date):
    """Stato attivo della barra superiore strettamente precedente a h1_date."""
    idx = bisect.bisect_left(date_keys, h1_date) - 1
    return active[idx] if 0 <= idx < len(active) else None


def _fwd(closes, t, h, direction):
    if t + h >= len(closes):
        return None
    p0, p1 = closes[t], closes[t + h]
    if p0 is None or p1 is None or p0 == 0:
        return None
    r = (p1 - p0) / p0
    return r if direction == "LONG" else -r


def _empty():
    return {
        cohort: {"train": {h: [] for h in HORIZONS}, "test": {h: [] for h in HORIZONS}}
        for cohort in COHORTS
    }


def _add_event(buckets, cohort, sample, closes, t, direction):
    for h in HORIZONS:
        fr = _fwd(closes, t, h, direction)
        if fr is not None:
            buckets[cohort][sample][h].append(fr)


def process_pair(h1, d1, w1, buckets, d1_k=D1_K, w_k=W_K):
    if len(h1) < H1_WINDOW + 5:
        return
    if len(d1) < COMP.DEFAULT_WINDOW + COMP.RANK_WINDOW + 2:
        return
    if len(w1) < COMP.DEFAULT_WINDOW + COMP.RANK_WINDOW + 2:
        return

    closes = [c.c for c in h1]
    d1_dates = [_date_key(c) for c in d1]
    w_dates = [_date_key(c) for c in w1]
    d1_active = active_map(d1, d1_k)
    w_active = active_map(w1, w_k)
    split = int(len(h1) * SPLIT_FRAC)

    for t in range(H1_WINDOW + 1, len(h1)):
        direction = COMP.is_new_breakout(h1, t, H1_WINDOW)
        if direction is None:
            continue

        sample = "train" if t < split else "test"
        h1_date = _date_key(h1[t])
        d1_dir = prior_active(d1_dates, d1_active, h1_date)
        w_dir = prior_active(w_dates, w_active, h1_date)

        _add_event(buckets, "all", sample, closes, t, direction)

        if d1_dir == direction:
            _add_event(buckets, "aligned_d1", sample, closes, t, direction)
            if w_dir == direction:
                _add_event(buckets, "aligned_d1w", sample, closes, t, direction)
            elif w_dir is None:
                _add_event(buckets, "d1_aligned_w_missing", sample, closes, t, direction)
            else:
                _add_event(buckets, "d1_aligned_w_counter", sample, closes, t, direction)

        if w_dir == direction:
            _add_event(buckets, "aligned_w", sample, closes, t, direction)

        if d1_dir is None and w_dir is None:
            _add_event(buckets, "context_none", sample, closes, t, direction)


def _agg(values):
    return {
        "n": len(values),
        "hit": round(sum(1 for v in values if v > 0) / len(values), 3) if values else None,
        "mean_pct": round(100 * sum(values) / len(values), 4) if values else None,
    }


def _edge(a, b):
    return round(a - b, 3) if a is not None and b is not None else None


def write_report(buckets, out_dir, source, n_h1, n_d1, n_w):
    os.makedirs(out_dir, exist_ok=True)
    agg = {
        cohort: {
            sample: {h: _agg(buckets[cohort][sample][h]) for h in HORIZONS}
            for sample in ("train", "test")
        }
        for cohort in COHORTS
    }
    payload = {
        "source": source,
        "n_h1": n_h1,
        "n_d1": n_d1,
        "n_w": n_w,
        "h1_window": H1_WINDOW,
        "d1_k": D1_K,
        "w_k": W_K,
        "horizons_h1": HORIZONS,
        "agg": agg,
    }
    json_path = os.path.join(out_dir, "h1_d1_w_align.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)

    test = {cohort: agg[cohort]["test"] for cohort in COHORTS}
    all12 = test["all"][12]["hit"]
    d112 = test["aligned_d1"][12]["hit"]
    d1w12 = test["aligned_d1w"][12]["hit"]
    allm = test["all"][12]["mean_pct"]
    d1m = test["aligned_d1"][12]["mean_pct"]
    d1wm = test["aligned_d1w"][12]["mean_pct"]

    lines = [
        "# Confluenza H1 + D1 + W",
        "",
        f"Fonte: {source} | H1 ~{n_h1} | D1 ~{n_d1} | W ~{n_w}",
        f"H1 window={H1_WINDOW}; D1 attivo={D1_K} giorni; W attivo={W_K} settimane.",
        "No lookahead: H1 usa solo D1/W strettamente precedenti alla sua data.",
        "",
        "## TEST out-of-sample",
        "| coorte | n(+12) | hit +4 | hit +12 | hit +24 | hit +48 | medio% +12 |",
        "|---|---|---|---|---|---|---|",
    ]
    for cohort in COHORTS:
        row = test[cohort]
        lines.append(
            f"| {cohort} | {row[12]['n']} | {row[4]['hit']} | {row[12]['hit']} | "
            f"{row[24]['hit']} | {row[48]['hit']} | {row[12]['mean_pct']} |"
        )

    mean_edge_all = round(d1wm - allm, 4) if d1wm is not None and allm is not None else None
    mean_edge_d1 = round(d1wm - d1m, 4) if d1wm is not None and d1m is not None else None
    lines.extend(
        [
            "",
            "## Confronto chiave +12 H1",
            f"- Edge hit aligned_d1w vs all: {_edge(d1w12, all12)}",
            f"- Edge hit aligned_d1w vs aligned_d1: {_edge(d1w12, d112)}",
            f"- Edge medio% aligned_d1w vs all: {mean_edge_all}",
            f"- Edge medio% aligned_d1w vs aligned_d1: {mean_edge_d1}",
            "",
            f"aligned_d1w medio% +12: {d1wm}% | aligned_d1: {d1m}% | all: {allm}%",
            "",
        ]
    )

    md_path = os.path.join(out_dir, "h1_d1_w_align.md")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    return md_path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--oanda", action="store_true")
    ap.add_argument("--h1-count", type=int, default=20000)
    ap.add_argument("--d1-count", type=int, default=1500)
    ap.add_argument("--w-count", type=int, default=800)
    ap.add_argument("--out", default="reports/h1d1w")
    args = ap.parse_args()
    if not args.oanda:
        ap.error("serve --oanda")
        return 2

    try:
        from fx_bias_radar.oanda_fetch import env_credentials

        token, env = env_credentials()
        h1_all = TF.fetch_all(token, env, "H1", args.h1_count)
        d1_all = TF.fetch_all(token, env, "D", args.d1_count)
        w_all = TF.fetch_all(token, env, "W", args.w_count)
        buckets = _empty()
        for pair in P.PAIRS:
            process_pair(h1_all.get(pair, []), d1_all.get(pair, []), w_all.get(pair, []), buckets)
    except Exception as exc:  # noqa: BLE001
        print(f"ERRORE: {exc}")
        return 2

    path = write_report(
        buckets,
        args.out,
        "OANDA H1+D1+W",
        args.h1_count,
        args.d1_count,
        args.w_count,
    )
    print(f"Confluenza H1+D1+W -> {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
