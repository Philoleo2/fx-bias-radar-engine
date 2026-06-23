"""Compressione + espansione H1: il prezzo prosegue?

Esperimento research-only. Cerca una compressione oggettiva (range recente
storicamente stretto) seguita da una chiusura fuori dal range. Confronta contro
il breakout da solo, senza filtro compressione.

Uso:
  python scripts/backtest_compression_expansion.py --oanda --count 4000 --out reports/compexp
  python scripts/backtest_compression_expansion.py --fixtures-h1 tests/fixtures/golden_2026H1
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import asdict, dataclass

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fx_bias_radar import candles as C
from fx_bias_radar import pairs as P

HORIZONS = [4, 12, 24]
RANK_WINDOW = 120
TRAIN_FRAC = 0.6
MIN_TRAIN_N = 50


@dataclass(frozen=True)
class Profile:
    window: int
    percentile: float

    @property
    def name(self) -> str:
        pct = int(self.percentile * 100)
        return f"w{self.window}_p{pct}"


@dataclass(frozen=True)
class Row:
    o: float
    h: float
    l: float
    c: float


PROFILES = [
    Profile(12, 0.20),
    Profile(12, 0.30),
    Profile(18, 0.20),
    Profile(18, 0.30),
    Profile(24, 0.20),
    Profile(24, 0.30),
]


def aligned_ohlc(candles_by_pair):
    times, closes, _ = C.align(candles_by_pair, include_incomplete=False)
    out = {}
    for pair in P.PAIRS:
        by_t = {c.time: c for c in candles_by_pair[pair] if c.complete}
        out[pair] = [Row(by_t[t].o, by_t[t].h, by_t[t].l, by_t[t].c) for t in times]
    return times, closes, out


def _quantile(values, q):
    if not values:
        return None
    xs = sorted(values)
    pos = (len(xs) - 1) * q
    lo = int(pos)
    hi = min(lo + 1, len(xs) - 1)
    frac = pos - lo
    return xs[lo] * (1.0 - frac) + xs[hi] * frac


def window_bounds(rows, end, window):
    """Return (range, high, low) for rows[end-window:end]."""
    if end < window:
        return None
    chunk = rows[end - window:end]
    hi = max(r.h for r in chunk)
    lo = min(r.l for r in chunk)
    return hi - lo, hi, lo


def is_compressed(rows, t, profile, rank_window=RANK_WINDOW):
    """Compressione nota prima della candela t: range precedente <= percentile."""
    cur = window_bounds(rows, t, profile.window)
    if cur is None or t < profile.window + rank_window:
        return False
    history = []
    for end in range(t - rank_window, t):
        b = window_bounds(rows, end, profile.window)
        if b is not None:
            history.append(b[0])
    threshold = _quantile(history, profile.percentile)
    return threshold is not None and cur[0] <= threshold


def breakout_dir(rows, t, window):
    """Nuova chiusura fuori dal range precedente."""
    b = window_bounds(rows, t, window)
    if b is None:
        return None
    _, hi, lo = b
    c = rows[t].c
    if c > hi:
        return "LONG"
    if c < lo:
        return "SHORT"
    return None


def is_new_breakout(rows, t, window):
    direction = breakout_dir(rows, t, window)
    if direction is None:
        return None
    prev_direction = breakout_dir(rows, t - 1, window) if t > 0 else None
    return direction if direction != prev_direction else None


def compression_expansion_dir(rows, t, profile):
    direction = is_new_breakout(rows, t, profile.window)
    if direction is None:
        return None
    return direction if is_compressed(rows, t, profile) else None


def _fwd(prices, t, h, direction):
    if t + h >= len(prices):
        return None
    p0, p1 = prices[t], prices[t + h]
    if p0 is None or p1 is None or p0 == 0:
        return None
    r = (p1 - p0) / p0
    return r if direction == "LONG" else -r


def _agg(vals_by_h):
    out = {}
    for h, vals in vals_by_h.items():
        out[h] = {
            "n": len(vals),
            "hit": round(sum(1 for v in vals if v > 0) / len(vals), 3) if vals else None,
            "mean_pct": round(100 * sum(vals) / len(vals), 4) if vals else None,
        }
    return out


def _empty_h():
    return {h: [] for h in HORIZONS}


def measure(ohlc_by_pair, closes, profile, split_bar):
    buckets = {
        "train": {"compression_expansion": _empty_h(), "breakout_only": _empty_h()},
        "test": {"compression_expansion": _empty_h(), "breakout_only": _empty_h()},
        "all": {"compression_expansion": _empty_h(), "breakout_only": _empty_h()},
    }
    counts = {
        "compression_expansion": {"LONG": 0, "SHORT": 0},
        "breakout_only": {"LONG": 0, "SHORT": 0},
    }
    for pair, rows in ohlc_by_pair.items():
        prices = closes.get(pair) if isinstance(closes, dict) else None
        if not prices:
            continue
        start = profile.window + RANK_WINDOW
        for t in range(start, len(rows)):
            sample = "train" if t < split_bar else "test"
            for set_name, direction in (
                ("breakout_only", is_new_breakout(rows, t, profile.window)),
                ("compression_expansion", compression_expansion_dir(rows, t, profile)),
            ):
                if direction is None:
                    continue
                counts[set_name][direction] += 1
                for h in HORIZONS:
                    fr = _fwd(prices, t, h, direction)
                    if fr is None:
                        continue
                    buckets[sample][set_name][h].append(fr)
                    buckets["all"][set_name][h].append(fr)
    return {
        "samples": {
            sample: {name: _agg(vals) for name, vals in sets.items()}
            for sample, sets in buckets.items()
        },
        "direction_counts": counts,
    }


def _edge_at_12(result, sample):
    ce = result["samples"][sample]["compression_expansion"].get(12, {})
    bo = result["samples"][sample]["breakout_only"].get(12, {})
    if ce.get("hit") is None or bo.get("hit") is None:
        return None
    return round(ce["hit"] - bo["hit"], 3)


def choose_best_train(results):
    eligible = []
    for name, result in results.items():
        ce12 = result["samples"]["train"]["compression_expansion"].get(12, {})
        if ce12.get("n", 0) < MIN_TRAIN_N:
            continue
        edge = _edge_at_12(result, "train")
        if edge is not None:
            eligible.append((edge, ce12.get("n", 0), name))
    if not eligible:
        return None
    eligible.sort(reverse=True)
    return eligible[0][2]


def run(ohlc_by_pair, closes, n_bars):
    split_bar = int(n_bars * TRAIN_FRAC)
    results = {}
    for profile in PROFILES:
        results[profile.name] = {
            "profile": asdict(profile),
            **measure(ohlc_by_pair, closes, profile, split_bar),
        }
    return results, choose_best_train(results), split_bar


def _metric(res, sample, set_name, h, field):
    return res["samples"][sample][set_name].get(h, {}).get(field)


def _profile_row(name, res, sample, set_name):
    n12 = _metric(res, sample, set_name, 12, "n")
    hit4 = _metric(res, sample, set_name, 4, "hit")
    hit12 = _metric(res, sample, set_name, 12, "hit")
    hit24 = _metric(res, sample, set_name, 24, "hit")
    mean12 = _metric(res, sample, set_name, 12, "mean_pct")
    edge12 = _edge_at_12(res, sample)
    return f"| {name} | {set_name} | {n12} | {hit4} | {hit12} | {hit24} | {mean12} | {edge12} |"


def write_report(results, best_name, n_bars, split_bar, out_dir, source):
    os.makedirs(out_dir, exist_ok=True)
    payload = {
        "source": source,
        "n_bars": n_bars,
        "timeframe": "H1",
        "rank_window": RANK_WINDOW,
        "horizons_h1": HORIZONS,
        "train_frac": TRAIN_FRAC,
        "split_bar": split_bar,
        "best_train_profile": best_name,
        "results": results,
    }
    with open(os.path.join(out_dir, "compression_expansion_edge.json"), "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)

    L = ["# Compressione + espansione H1 - edge prezzo", ""]
    L.append(f"Fonte: {source} | barre H1: {n_bars} | split train/test: {split_bar}/{n_bars - split_bar}")
    L.append("Compressione = range delle ultime N barre <= percentile storico su 120 finestre precedenti.")
    L.append("Espansione = nuova chiusura fuori dal range delle ultime N barre. hit 0.50 = caso.")
    L.append("")
    if best_name:
        L.append(f"Profilo migliore su TRAIN per edge hit +12: **{best_name}**.")
    else:
        L.append("Nessun profilo con campione TRAIN sufficiente.")
    L.append("")
    L.append("## Profilo scelto train/test")
    L.append("")
    L.append("| profilo | set | n(+12) | hit +4 | hit +12 | hit +24 | medio% +12 | edge hit +12 vs baseline |")
    L.append("|---|---|---|---|---|---|---|---|")
    if best_name:
        best = results[best_name]
        for sample in ("train", "test", "all"):
            L.append(_profile_row(f"{best_name} {sample}", best, sample, "compression_expansion"))
            L.append(_profile_row(f"{best_name} {sample}", best, sample, "breakout_only"))
    L.append("")
    L.append("## Tutti i profili - TEST out-of-sample")
    L.append("")
    L.append("| profilo | set | n(+12) | hit +4 | hit +12 | hit +24 | medio% +12 | edge hit +12 vs baseline |")
    L.append("|---|---|---|---|---|---|---|---|")
    for name in sorted(results):
        res = results[name]
        L.append(_profile_row(name, res, "test", "compression_expansion"))
        L.append(_profile_row(name, res, "test", "breakout_only"))
    L.append("")
    path = os.path.join(out_dir, "compression_expansion_edge.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(L) + "\n")
    return path


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--oanda", action="store_true")
    ap.add_argument("--fixtures-h1")
    ap.add_argument("--count", type=int, default=4000)
    ap.add_argument("--out", default="reports/compexp")
    args = ap.parse_args()
    try:
        if args.oanda:
            from fx_bias_radar.strength_h1 import fetch_all_h1
            from fx_bias_radar.oanda_fetch import env_credentials
            token, env = env_credentials()
            candles = fetch_all_h1(token, env=env, count=args.count)
            source = "OANDA H1"
        elif args.fixtures_h1:
            candles = C.load_fixture_dir(args.fixtures_h1)
            source = f"fixtures {args.fixtures_h1}"
        else:
            ap.error("specificare --oanda oppure --fixtures-h1 DIR")
            return 2
        _, closes, ohlc = aligned_ohlc(candles)
        n_bars = len(next(iter(ohlc.values())))
    except Exception as exc:  # noqa: BLE001
        print(f"ERRORE: {exc}")
        return 2
    results, best_name, split_bar = run(ohlc, closes, n_bars)
    path = write_report(results, best_name, n_bars, split_bar, args.out, source)
    print(f"Compressione+espansione -> {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
