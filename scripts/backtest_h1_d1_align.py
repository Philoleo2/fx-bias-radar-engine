"""Confluenza H1 + D1: rottura H1 ALLINEATA al daily.

Idea: l'edge della compressione vive sul DAILY (trend persistenti). Quindi prendi
una rottura H1 SOLO se e' nella direzione di una rottura-da-compressione D1 ancora
"attiva" (finestra di K giorni). Il daily da' il contesto/edge, l'H1 da' l'entrata
veloce (stile intraday). Confronta col prendere TUTTE le rotture H1. No lookahead:
si usa solo il D1 strettamente precedente alla barra H1.

Research-only, motore non toccato.

Uso:
  python scripts/backtest_h1_d1_align.py --oanda --h1-count 20000 --d1-count 1500 --out reports/h1d1
"""

from __future__ import annotations

import argparse
import bisect
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import backtest_compression_expansion as CE
import backtest_compression_tf as TF
from fx_bias_radar import candles as C
from fx_bias_radar import compression as COMP
from fx_bias_radar import pairs as P

H1_WINDOW = 12
D1_K = 10               # giorni di finestra attiva dopo un breakout D1
HORIZONS = [4, 12, 24, 48]
SPLIT_FRAC = 0.6
CLASSES = ("aligned", "counter", "context_none", "all")


def d1_active_map(d1, k=D1_K):
    """Direzione 'attiva' per ogni barra D1 (da un breakout da compressione entro k barre)."""
    n = len(d1)
    active = [None] * n
    last_dir = None
    last_bar = -10 ** 9
    for i in range(n):
        d = COMP.compression_breakout(d1, i)
        if d is not None:
            last_dir, last_bar = d, i
        if last_dir is not None and (i - last_bar) <= k:
            active[i] = last_dir
    return active


def _fwd(closes, t, h, direction):
    if t + h >= len(closes):
        return None
    p0, p1 = closes[t], closes[t + h]
    if p0 is None or p1 is None or p0 == 0:
        return None
    r = (p1 - p0) / p0
    return r if direction == "LONG" else -r


def _empty():
    return {cls: {"train": {h: [] for h in HORIZONS},
                  "test": {h: [] for h in HORIZONS}} for cls in CLASSES}


def process_pair(h1, d1, buckets, k=D1_K):
    if len(h1) < H1_WINDOW + 5 or len(d1) < COMP.DEFAULT_WINDOW + COMP.RANK_WINDOW + 2:
        return
    closes = [c.c for c in h1]
    d1_dates = [str(c.time)[:10] for c in d1]
    active = d1_active_map(d1, k)
    split = int(len(h1) * SPLIT_FRAC)
    for t in range(H1_WINDOW + 1, len(h1)):
        d = CE.is_new_breakout(h1, t, H1_WINDOW)
        if d is None:
            continue
        date = str(h1[t].time)[:10]
        j = bisect.bisect_left(d1_dates, date) - 1     # ultimo D1 con data < oggi
        adir = active[j] if 0 <= j < len(active) else None
        if adir == d:
            cls = "aligned"
        elif adir is not None and adir != d:
            cls = "counter"
        else:
            cls = "context_none"
        sample = "train" if t < split else "test"
        for h in HORIZONS:
            fr = _fwd(closes, t, h, d)
            if fr is None:
                continue
            buckets[cls][sample][h].append(fr)
            buckets["all"][sample][h].append(fr)


def _agg(vals):
    return {"n": len(vals),
            "hit": round(sum(1 for v in vals if v > 0) / len(vals), 3) if vals else None,
            "mean_pct": round(100 * sum(vals) / len(vals), 4) if vals else None}


def write_report(buckets, out_dir, source, n_h1, n_d1):
    os.makedirs(out_dir, exist_ok=True)
    agg = {cls: {s: {h: _agg(buckets[cls][s][h]) for h in HORIZONS}
                 for s in ("train", "test")} for cls in CLASSES}
    with open(os.path.join(out_dir, "h1_d1_align.json"), "w", encoding="utf-8") as f:
        json.dump({"source": source, "n_h1": n_h1, "n_d1": n_d1, "h1_window": H1_WINDOW,
                   "d1_k": D1_K, "horizons_h1": HORIZONS, "agg": agg}, f, indent=2)
    L = ["# Confluenza H1 + D1: rottura H1 allineata al daily", ""]
    L.append(f"Fonte: {source} | H1 barre/coppia ~{n_h1} | D1 ~{n_d1} | finestra attiva D1 = {D1_K} giorni")
    L.append("Rottura H1 (window 12) classificata vs direzione attiva D1. Orizzonti in barre H1. "
             "Metriche su TEST (out-of-sample, ultima parte). edge = aligned - all.")
    L.append("")
    L.append("## TEST out-of-sample")
    L.append("| classe | n(+12) | hit +4 | hit +12 | hit +24 | hit +48 | medio% +12 |")
    L.append("|---|---|---|---|---|---|---|")
    for cls in ("aligned", "counter", "context_none", "all"):
        t = agg[cls]["test"]
        L.append(f"| {cls} | {t[12]['n']} | {t[4]['hit']} | {t[12]['hit']} | {t[24]['hit']} | "
                 f"{t[48]['hit']} | {t[12]['mean_pct']} |")
    a12 = agg["aligned"]["test"][12]["hit"]
    all12 = agg["all"]["test"][12]["hit"]
    edge = round(a12 - all12, 3) if (a12 is not None and all12 is not None) else None
    L.append("")
    L.append(f"**Edge hit +12 (aligned vs all): {edge}**  |  ritorno medio aligned +12: "
             f"{agg['aligned']['test'][12]['mean_pct']}% vs all {agg['all']['test'][12]['mean_pct']}%")
    L.append("")
    path = os.path.join(out_dir, "h1_d1_align.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(L) + "\n")
    return path


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--oanda", action="store_true")
    ap.add_argument("--h1-count", type=int, default=20000)
    ap.add_argument("--d1-count", type=int, default=1500)
    ap.add_argument("--out", default="reports/h1d1")
    args = ap.parse_args()
    if not args.oanda:
        ap.error("serve --oanda (richiede H1 e D1 reali)")
        return 2
    try:
        from fx_bias_radar.oanda_fetch import env_credentials
        token, env = env_credentials()
        h1_all = TF.fetch_all(token, env, "H1", args.h1_count)
        d1_all = TF.fetch_all(token, env, "D", args.d1_count)
        buckets = _empty()
        for pair in P.PAIRS:
            process_pair(h1_all.get(pair, []), d1_all.get(pair, []), buckets)
    except Exception as exc:  # noqa: BLE001
        print(f"ERRORE: {exc}")
        return 2
    path = write_report(buckets, args.out, "OANDA H1+D1", args.h1_count, args.d1_count)
    print(f"Confluenza H1+D1 -> {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
