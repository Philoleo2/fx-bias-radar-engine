"""M4 Test #4 - ROTAZIONE + BREAKOUT 9 candele -> il prezzo prosegue?

Combina il segnale di rotazione H1 (scanner) con una conferma di PREZZO: dopo la
rotazione, la prima candela che CHIUDE oltre il max/min dei 9 close precedenti
(long -> sopra il max; short -> sotto il min) = entrata. Misura il follow-through a
+4/+12/+24 barre H1. Confronta col breakout DA SOLO (baseline) per vedere se la
rotazione aggiunge qualcosa. Display/ricerca: motore non toccato.

Uso:
  python scripts/backtest_rotation_breakout.py --oanda --count 4000 --out reports/rotbreak
  python scripts/backtest_rotation_breakout.py --fixtures-h1 tests/fixtures/golden_2026H1
"""

from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fx_bias_radar import candles as C
from fx_bias_radar import currency_index as CI
from fx_bias_radar import pairs as P
from fx_bias_radar import rotation as ROT
from fx_bias_radar.rotation import RotParams

HORIZONS = [4, 12, 24]
LOOKBACK = 9      # candele precedenti per il breakout
WINDOW = 12       # entro quante barre dalla rotazione cerco il breakout
ROT_PARAMS = ROT.DEFAULT_ROT_PARAMS


def series_and_prices(candles_by_pair):
    times, closes, _ = C.align(candles_by_pair, include_incomplete=False)
    cd = CI.build(times, closes)
    out = {}
    for pair in P.PAIRS:
        base, quote = P.base_quote(pair)
        zb, zq = cd.z[base], cd.z[quote]
        sp = [(zb[i] - zq[i]) if (zb[i] is not None and zq[i] is not None) else None
              for i in range(len(zb))]
        out[pair] = (sp, list(zb), list(zq))
    return out, closes, len(times)


def is_breakout(prices, t, direction, lookback=LOOKBACK):
    if t < lookback:
        return False
    win = prices[t - lookback:t]
    if any(v is None for v in win) or prices[t] is None:
        return False
    return prices[t] > max(win) if direction == "LONG" else prices[t] < min(win)


def _fwd(prices, t, h, d):
    if t + h >= len(prices):
        return None
    p0, p1 = prices[t], prices[t + h]
    if p0 is None or p1 is None or p0 == 0:
        return None
    r = (p1 - p0) / p0
    return r if d == "LONG" else -r


def _agg(vals_by_h):
    out = {}
    for h, vals in vals_by_h.items():
        out[h] = {"n": len(vals),
                  "hit": round(sum(1 for v in vals if v > 0) / len(vals), 3) if vals else None,
                  "mean_pct": round(100 * sum(vals) / len(vals), 4) if vals else None}
    return out


def run(sp_by_pair, closes):
    rb = {h: [] for h in HORIZONS}        # rotazione + breakout
    bo = {h: [] for h in HORIZONS}        # breakout da solo (baseline)
    n_rot = 0
    n_confirmed = 0
    for pair, (sp, zb, zq) in sp_by_pair.items():
        prices = closes.get(pair) if isinstance(closes, dict) else None
        if not prices:
            continue
        # baseline: tutti i breakout (in entrambe le direzioni)
        for t in range(LOOKBACK, len(prices)):
            for d in ("LONG", "SHORT"):
                if is_breakout(prices, t, d):
                    for h in HORIZONS:
                        fr = _fwd(prices, t, h, d)
                        if fr is not None:
                            bo[h].append(fr)
        # rotazione + primo breakout entro WINDOW
        for r in ROT.detect_rotations(sp, zb, zq, ROT_PARAMS):
            n_rot += 1
            t0, d = r["bar"], r["dir"]
            t_entry = None
            for t in range(t0, min(t0 + WINDOW + 1, len(prices))):
                if is_breakout(prices, t, d):
                    t_entry = t
                    break
            if t_entry is None:
                continue
            n_confirmed += 1
            for h in HORIZONS:
                fr = _fwd(prices, t_entry, h, d)
                if fr is not None:
                    rb[h].append(fr)
    return _agg(rb), _agg(bo), n_rot, n_confirmed


def write_report(rb, bo, n_rot, n_conf, n_bars, out_dir, source):
    os.makedirs(out_dir, exist_ok=True)
    conf_rate = round(n_conf / n_rot, 3) if n_rot else None
    with open(os.path.join(out_dir, "rotbreak_edge.json"), "w", encoding="utf-8") as f:
        json.dump({"source": source, "n_bars": n_bars, "lookback": LOOKBACK,
                   "window": WINDOW, "n_rotations": n_rot, "n_confirmed": n_conf,
                   "confirm_rate": conf_rate, "rotation_breakout": rb,
                   "breakout_only": bo}, f, indent=2)
    L = ["# Rotazione + breakout 9 candele - edge prezzo", ""]
    L.append(f"Fonte: {source} | barre: {n_bars} | breakout = close oltre max/min dei {LOOKBACK} "
             f"close precedenti | finestra conferma {WINDOW} barre")
    L.append(f"Rotazioni: {n_rot} | confermate da breakout: {n_conf} ({conf_rate}) | hit 0.50 = caso.")
    L.append("")
    L.append("| set | n(+12) | hit +4 | hit +12 | hit +24 | medio% +12 |")
    L.append("|---|---|---|---|---|---|")
    for name, d in (("rotazione+breakout", rb), ("breakout da solo (baseline)", bo)):
        L.append(f"| {name} | {d.get(12,{}).get('n')} | {d.get(4,{}).get('hit')} | "
                 f"{d.get(12,{}).get('hit')} | {d.get(24,{}).get('hit')} | {d.get(12,{}).get('mean_pct')} |")
    L.append("")
    path = os.path.join(out_dir, "rotbreak_edge.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(L) + "\n")
    return path


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--oanda", action="store_true")
    ap.add_argument("--fixtures-h1")
    ap.add_argument("--count", type=int, default=4000)
    ap.add_argument("--out", default="reports/rotbreak")
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
        sp_by_pair, closes, n = series_and_prices(candles)
    except Exception as exc:  # noqa: BLE001
        print(f"ERRORE: {exc}")
        return 2
    rb, bo, n_rot, n_conf = run(sp_by_pair, closes)
    path = write_report(rb, bo, n_rot, n_conf, n, args.out, src)
    print(f"Rotazione+breakout -> {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
