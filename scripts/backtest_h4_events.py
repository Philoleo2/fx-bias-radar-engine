"""M4 Test #2 - EDGE sul prezzo degli eventi del motore H4 (RESUME / ROT).

Domanda: quando il motore validato accende un RESUME o un ROT su una coppia, il
PREZZO prosegue nella direzione segnalata? Misura hit rate e ritorno per tipo
(RESUME/ROT) e per stato (NUOVO/ATTIVO/ESTESO). Il motore non viene toccato: solo
LETTO bar-per-bar (causale). Nessun parametro da tarare -> niente overfitting,
misura sull'intero campione.

Uso:
  python scripts/backtest_h4_events.py --oanda --count 4000 --out reports/h4events
  python scripts/backtest_h4_events.py --fixtures tests/fixtures/golden_2026H1
"""

from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fx_bias_radar import candles as C
from fx_bias_radar import currency_index as CI
from fx_bias_radar import engine as E
from fx_bias_radar import pairs as P

HORIZONS = [1, 3, 6, 12, 30]   # barre H4: 4h, 12h, 1g, 2g, ~1 settimana


def events_and_prices(candles_by_pair):
    """Gira il motore su tutta la storia H4 e raccoglie gli eventi + i prezzi."""
    times, closes, _ = C.align(candles_by_pair, include_incomplete=False)
    cd = CI.build(times, closes)
    events = []
    for pair in P.PAIRS:
        frames = CI.pair_frames(cd, pair)
        results = E.run_pair(pair, frames)
        prev_state = "NESSUNO"
        for i, r in enumerate(results):
            st = r.panel_stato
            # EVENTO FRESCO: transizione verso lo stato NUOVO (una volta per evento)
            if r.panel_bias in ("LONG", "SHORT") and st == "NUOVO" and prev_state != "NUOVO":
                events.append({
                    "pair": pair, "bar": i, "dir": r.panel_bias,
                    "type": r.panel_tipo, "state": st,
                    "score": r.panel_score, "spread": r.panel_spread,
                })
            prev_state = st
    return events, closes, len(times)


def _fwd(prices, t, h, direction):
    if t + h >= len(prices):
        return None
    p0, p1 = prices[t], prices[t + h]
    if p0 is None or p1 is None or p0 == 0:
        return None
    r = (p1 - p0) / p0
    return r if direction == "LONG" else -r


def measure(events, closes, key):
    """key(event) -> nome bucket (o None per scartare)."""
    buckets = {}
    for e in events:
        prices = closes.get(e["pair"]) if isinstance(closes, dict) else None
        if not prices:
            continue
        b = key(e)
        if b is None:
            continue
        buckets.setdefault(b, {h: [] for h in HORIZONS})
        for h in HORIZONS:
            fr = _fwd(prices, e["bar"], h, e["dir"])
            if fr is not None:
                buckets[b][h].append(fr)
    out = {}
    for b, hd in buckets.items():
        out[b] = {}
        for h, vals in hd.items():
            out[b][h] = {
                "n": len(vals),
                "hit": round(sum(1 for v in vals if v > 0) / len(vals), 3) if vals else None,
                "mean_pct": round(100 * sum(vals) / len(vals), 4) if vals else None,
            }
    return out


def _tbl(title, res, order=None):
    L = [f"### {title}", ""]
    L.append("| categoria | n(+6) | hit +1 | hit +3 | hit +6 | hit +12 | hit +30 | medio% +6 |")
    L.append("|---|---|---|---|---|---|---|---|")
    keys = order or sorted(res.keys())
    for k in keys:
        if k not in res:
            continue
        hd = res[k]
        def g(h, f):
            return hd.get(h, {}).get(f)
        n6 = g(6, "n")
        row = f"| {k} | {n6} |"
        for h in HORIZONS:
            row += f" {g(h, 'hit')} |"
        row += f" {g(6, 'mean_pct')} |"
        L.append(row)
    L.append("")
    return L


def write_report(events, closes, n_bars, out_dir, source):
    os.makedirs(out_dir, exist_ok=True)
    by_all = measure(events, closes, key=lambda e: "TUTTI")
    by_type = measure(events, closes, key=lambda e: e["type"] if e["type"] in ("RESUME", "ROT") else None)
    by_type_state = measure(events, closes,
                            key=lambda e: (e["type"] + "/" + e["state"])
                            if e["type"] in ("RESUME", "ROT") else None)

    payload = {"source": source, "n_bars": n_bars, "n_events": len(events),
               "horizons_h4": HORIZONS, "all": by_all, "by_type": by_type,
               "by_type_state": by_type_state}
    with open(os.path.join(out_dir, "h4_events_edge.json"), "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)

    L = ["# Edge prezzo eventi motore H4 (RESUME / ROT)", ""]
    L.append(f"Fonte: {source} | barre H4: {n_bars} | eventi: {len(events)}")
    L.append("Orizzonti in barre H4: +1=4h, +3=12h, +6=1g, +12=2g, +30=~1 sett. "
             "hit 0.50 = lancio di moneta. Segnale fisso (motore) -> misura su tutto il campione.")
    L.append("")
    L += _tbl("Tutti gli eventi freschi (onset NUOVO)", by_all, order=["TUTTI"])
    L += _tbl("Per tipo (eventi freschi)", by_type, order=["RESUME", "ROT"])
    path = os.path.join(out_dir, "h4_events_edge.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(L) + "\n")
    return path


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--oanda", action="store_true")
    ap.add_argument("--fixtures")
    ap.add_argument("--count", type=int, default=4000)
    ap.add_argument("--out", default="reports/h4events")
    args = ap.parse_args()
    try:
        if args.oanda:
            from fx_bias_radar.oanda_fetch import env_credentials, fetch_all_pairs
            token, env = env_credentials()
            candles = fetch_all_pairs(token, env=env, count=args.count)
            src = "OANDA H4"
        elif args.fixtures:
            candles = C.load_fixture_dir(args.fixtures)
            src = f"fixtures {args.fixtures}"
        else:
            ap.error("specificare --oanda oppure --fixtures DIR")
            return 2
        events, closes, n = events_and_prices(candles)
    except Exception as exc:  # noqa: BLE001
        print(f"ERRORE: {exc}")
        return 2
    path = write_report(events, closes, n, args.out, src)
    print(f"H4 events edge -> {path} | eventi: {len(events)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
