"""M4 Test #3 - EDGE sul prezzo dell'INCROCIO delle linee di forza (spread=0).

Domanda: quando z_base incrocia z_quote (la debole supera la forte = cambio di
leadership), il PREZZO prosegue nella nuova direzione? Misura hit rate e ritorno a
+4/+12/+24 barre H1, complessivo e per FASCIA di decisione dell'incrocio (slope).
Display/ricerca: non tocca il motore.

Uso:
  python scripts/backtest_crossover.py --oanda --count 4000 --out reports/crossover
  python scripts/backtest_crossover.py --fixtures-h1 tests/fixtures/golden_2026H1
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fx_bias_radar import candles as C
from fx_bias_radar import currency_index as CI
from fx_bias_radar import pairs as P
from fx_bias_radar import rotation as ROT

HORIZONS = [4, 12, 24]
SLOPE_EDGES = [0.0, 0.15, 0.3, 0.6, 1.0]   # decisione dell'incrocio (|var| al cross)


def spreads_and_prices(candles_by_pair):
    times, closes, _ = C.align(candles_by_pair, include_incomplete=False)
    cd = CI.build(times, closes)
    out = {}
    for pair in P.PAIRS:
        base, quote = P.base_quote(pair)
        zb, zq = cd.z[base], cd.z[quote]
        sp = [(zb[i] - zq[i]) if (zb[i] is not None and zq[i] is not None) else None
              for i in range(len(zb))]
        out[pair] = sp
    return out, closes, len(times)


def _fwd(prices, t, h, d):
    if t + h >= len(prices):
        return None
    p0, p1 = prices[t], prices[t + h]
    if p0 is None or p1 is None or p0 == 0:
        return None
    r = (p1 - p0) / p0
    return r if d == "LONG" else -r


def _slope_bucket(s):
    e = SLOPE_EDGES
    for i in range(len(e) - 1):
        if e[i] <= s < e[i + 1]:
            return f"{e[i]}-{e[i+1]}"
    return f"{e[-1]}+"


def measure(sp_by_pair, closes, key):
    buckets = {}
    for pair, sp in sp_by_pair.items():
        prices = closes.get(pair) if isinstance(closes, dict) else None
        if not prices:
            continue
        for cx in ROT.detect_crossovers(sp):
            b = key(cx)
            if b is None:
                continue
            buckets.setdefault(b, {h: [] for h in HORIZONS})
            for h in HORIZONS:
                fr = _fwd(prices, cx["bar"], h, cx["dir"])
                if fr is not None:
                    buckets[b][h].append(fr)
    out = {}
    for b, hd in buckets.items():
        out[b] = {}
        for h, vals in hd.items():
            out[b][h] = {"n": len(vals),
                         "hit": round(sum(1 for v in vals if v > 0) / len(vals), 3) if vals else None,
                         "mean_pct": round(100 * sum(vals) / len(vals), 4) if vals else None}
    return out


def _tbl(title, res, order):
    L = [f"### {title}", "",
         "| categoria | n(+12) | hit +4 | hit +12 | hit +24 | medio% +12 |",
         "|---|---|---|---|---|---|"]
    for k in order:
        if k not in res:
            continue
        hd = res[k]
        n12 = hd.get(12, {}).get("n")
        L.append(f"| {k} | {n12} | {hd.get(4,{}).get('hit')} | {hd.get(12,{}).get('hit')} | "
                 f"{hd.get(24,{}).get('hit')} | {hd.get(12,{}).get('mean_pct')} |")
    L.append("")
    return L


def write_report(sp_by_pair, closes, n_bars, out_dir, source):
    os.makedirs(out_dir, exist_ok=True)
    by_all = measure(sp_by_pair, closes, key=lambda c: "TUTTI")
    by_slope = measure(sp_by_pair, closes, key=lambda c: _slope_bucket(c["slope"]))
    n_events = sum(len(ROT.detect_crossovers(sp)) for sp in sp_by_pair.values())
    with open(os.path.join(out_dir, "crossover_edge.json"), "w", encoding="utf-8") as f:
        json.dump({"source": source, "n_bars": n_bars, "n_events": n_events,
                   "horizons_h1": HORIZONS, "all": by_all, "by_slope": by_slope}, f, indent=2)
    L = ["# Edge prezzo INCROCIO linee di forza (spread=0)", ""]
    L.append(f"Fonte: {source} | barre H1: {n_bars} | incroci: {n_events}")
    L.append("hit 0.50 = lancio di moneta. by_slope = decisione dell'incrocio (|var| al cross).")
    L.append("")
    L += _tbl("Tutti gli incroci", by_all, ["TUTTI"])
    order = [f"{SLOPE_EDGES[i]}-{SLOPE_EDGES[i+1]}" for i in range(len(SLOPE_EDGES)-1)] + [f"{SLOPE_EDGES[-1]}+"]
    L += _tbl("Per decisione dell'incrocio (slope)", by_slope, order)
    path = os.path.join(out_dir, "crossover_edge.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(L) + "\n")
    return path


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--oanda", action="store_true")
    ap.add_argument("--fixtures-h1")
    ap.add_argument("--count", type=int, default=4000)
    ap.add_argument("--out", default="reports/crossover")
    args = ap.parse_args()
    try:
        if args.oanda:
            from fx_bias_radar.strength_h1 import fetch_all_h1
            from fx_bias_radar.oanda_fetch import env_credentials
            token, env = env_credentials()
            candles = fetch_all_h1(token, env=env, count=args.count)
            src = "OANDA H1"
        elif args.fixtures_h1:
            candles = C.load_fixture_dir(args.fixtures_h1)
            src = f"fixtures {args.fixtures_h1}"
        else:
            ap.error("specificare --oanda oppure --fixtures-h1 DIR")
            return 2
        sp_by_pair, closes, n = spreads_and_prices(candles)
    except Exception as exc:  # noqa: BLE001
        print(f"ERRORE: {exc}")
        return 2
    path = write_report(sp_by_pair, closes, n, args.out, src)
    print(f"Crossover edge -> {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
