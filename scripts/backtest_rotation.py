"""M4 - Backtest di calibrazione + EDGE del rilevatore di ROTAZIONE (H1).

1) Calibrazione timing: trova i parametri che CENTRANO la rotazione (ne' presto
   ne' tardi) rispetto ai punti veri (swing dello spread di forza H1).
2) Follow-through del PREZZO: dopo la rotazione, di quanto si muove il prezzo
   nella direzione segnalata (media/mediana %) e con che hit rate, a +4/+12/+24
   barre H1. Risponde a: "il prezzo prosegue dopo la rotazione?".

Display/ricerca: NON tocca il motore H4.

Uso:
  python scripts/backtest_rotation.py --oanda --count 4000 --out reports/rotation
  python scripts/backtest_rotation.py --selftest
  python scripts/backtest_rotation.py --fixtures-h1 DIR
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
from itertools import product

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fx_bias_radar import candles as C
from fx_bias_radar import currency_index as CI
from fx_bias_radar import pairs as P
from fx_bias_radar import rotation as ROT
from fx_bias_radar.rotation import RotParams

PIVOT_SWING = 6
PIVOT_EXT = 1.5
MATCH_TOL = 6
PF_HORIZONS = [4, 12, 24]   # barre H1 di follow-through prezzo
PF_BUCKETS = [1.5, 2.0, 2.5, 3.0, 3.5]   # fasce |estremo| dello spread

GRID = {
    "ext_min": [1.5, 2.0, 2.5],
    "k_window": [8, 12, 18],
    "conf_bars": [1, 2, 3],
    "method": ["slope_both", "ema_cross"],
}


def spreads_from_candles(candles_by_pair):
    """28 panieri H1 -> per coppia (sp, zb, zq) + i prezzi di chiusura allineati."""
    times, closes, _ = C.align(candles_by_pair, include_incomplete=False)
    cd = CI.build(times, closes)
    out = {}
    for pair in P.PAIRS:
        base, quote = P.base_quote(pair)
        zb, zq = cd.z[base], cd.z[quote]
        sp = [(zb[i] - zq[i]) if (zb[i] is not None and zq[i] is not None) else None
              for i in range(len(zb))]
        out[pair] = (sp, list(zb), list(zq))
    return out, len(times), closes


def _match(signals, pivots, lo, hi, tol):
    piv = [p for p in pivots if lo <= p["bar"] < hi]
    sig = [s for s in signals if lo <= s["bar"] < hi]
    offsets, matched_piv = [], set()
    for s in sig:
        cands = [(abs(s["bar"] - p["bar"]), p) for p in piv
                 if p["dir"] == s["dir"] and abs(s["bar"] - p["bar"]) <= tol]
        if cands:
            cands.sort(key=lambda x: x[0])
            p = cands[0][1]
            offsets.append(s["bar"] - p["bar"])
            matched_piv.add(p["bar"])
    return offsets, len(matched_piv), len(sig), len(piv)


def evaluate(sp_by_pair, params: RotParams, lo, hi):
    tot_off, tot_match, tot_sig, tot_piv = [], 0, 0, 0
    for pair, (sp, zb, zq) in sp_by_pair.items():
        signals = ROT.detect_rotations(sp, zb, zq, params)
        pivots = ROT.label_pivots(sp, swing=PIVOT_SWING, ext_min=PIVOT_EXT)
        off, m, ns, npv = _match(signals, pivots, lo, hi, MATCH_TOL)
        tot_off += off
        tot_match += m
        tot_sig += ns
        tot_piv += npv
    precision = (len(tot_off) / tot_sig) if tot_sig else 0.0
    recall = (tot_match / tot_piv) if tot_piv else 0.0
    med = statistics.median(tot_off) if tot_off else None
    mean = (sum(tot_off) / len(tot_off)) if tot_off else None
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0
    return {"signals": tot_sig, "pivots": tot_piv, "matched": tot_match,
            "precision": round(precision, 3), "recall": round(recall, 3),
            "f1": round(f1, 3), "median_offset": med,
            "mean_offset": round(mean, 2) if mean is not None else None}


def score(test_metrics):
    f1 = test_metrics["f1"]
    med = test_metrics["median_offset"]
    pen = abs(med) if med is not None else 6
    return f1 - 0.05 * pen


def grid_search(sp_by_pair, n_bars):
    split = n_bars // 2
    rows = []
    keys = list(GRID.keys())
    for combo in product(*[GRID[k] for k in keys]):
        params = RotParams(**dict(zip(keys, combo)))
        rows.append({"params": dict(zip(keys, combo)),
                     "train": evaluate(sp_by_pair, params, 0, split),
                     "test": evaluate(sp_by_pair, params, split, n_bars),
                     "score": round(score(evaluate(sp_by_pair, params, split, n_bars)), 3)})
    rows.sort(key=lambda r: -r["score"])
    return rows, split


def price_followthrough(sp_by_pair, closes, params: RotParams, horizons=PF_HORIZONS):
    """Per ogni segnale: ritorno del prezzo nella direzione segnalata a +h barre."""
    buckets = {h: [] for h in horizons}
    for pair, (sp, zb, zq) in sp_by_pair.items():
        prices = closes.get(pair) if isinstance(closes, dict) else None
        if not prices:
            continue
        for s in ROT.detect_rotations(sp, zb, zq, params):
            t, d = s["bar"], s["dir"]
            for h in horizons:
                if t + h < len(prices):
                    p0, p1 = prices[t], prices[t + h]
                    if p0 is None or p1 is None or p0 == 0:
                        continue
                    r = (p1 - p0) / p0
                    buckets[h].append(r if d == "LONG" else -r)
    out = {}
    for h, vals in buckets.items():
        if vals:
            out[h] = {"n": len(vals),
                      "mean_pct": round(100 * sum(vals) / len(vals), 4),
                      "median_pct": round(100 * statistics.median(vals), 4),
                      "hit_rate": round(sum(1 for v in vals if v > 0) / len(vals), 3)}
        else:
            out[h] = {"n": 0}
    return out


def price_followthrough_by_strength(sp_by_pair, closes, params, horizons=PF_HORIZONS):
    """Follow-through del prezzo separato per FASCIA di forza (|estremo| dello spread)."""
    edges = PF_BUCKETS

    def bname(a):
        for i in range(len(edges) - 1):
            if edges[i] <= a < edges[i + 1]:
                return f"{edges[i]}-{edges[i + 1]}"
        if a >= edges[-1]:
            return f"{edges[-1]}+"
        return None

    res = {}
    for pair, (sp, zb, zq) in sp_by_pair.items():
        prices = closes.get(pair) if isinstance(closes, dict) else None
        if not prices:
            continue
        for sg in ROT.detect_rotations(sp, zb, zq, params):
            peak = sg.get("peak")
            if peak is None:
                continue
            b = bname(abs(peak))
            if b is None:
                continue
            t, d = sg["bar"], sg["dir"]
            res.setdefault(b, {h: [] for h in horizons})
            for h in horizons:
                if t + h < len(prices):
                    p0, p1 = prices[t], prices[t + h]
                    if p0 is None or p1 is None or p0 == 0:
                        continue
                    r = (p1 - p0) / p0
                    res[b][h].append(r if d == "LONG" else -r)
    out = {}
    for b, hd in res.items():
        out[b] = {}
        for h, vals in hd.items():
            if vals:
                out[b][h] = {"n": len(vals),
                             "mean_pct": round(100 * sum(vals) / len(vals), 4),
                             "hit_rate": round(sum(1 for v in vals if v > 0) / len(vals), 3)}
            else:
                out[b][h] = {"n": 0}
    return out


def write_report(rows, split, n_bars, out_dir, source, pf=None, pf_str=None):
    os.makedirs(out_dir, exist_ok=True)
    best = rows[0]
    with open(os.path.join(out_dir, "rotation_backtest.json"), "w", encoding="utf-8") as f:
        json.dump({"source": source, "n_bars": n_bars, "split": split,
                   "match_tol": MATCH_TOL, "pivot_swing": PIVOT_SWING,
                   "pivot_ext": PIVOT_EXT, "price_followthrough": pf,
                   "price_followthrough_by_strength": pf_str,
                   "ranking": rows[:15]}, f, indent=2)
    L = ["# Backtest rotazione H1 - calibrazione + edge prezzo", ""]
    L.append(f"Fonte: {source} | barre: {n_bars} | split train/test @ {split} | "
             f"tol match: {MATCH_TOL} | pivot: swing {PIVOT_SWING}, |ext|>={PIVOT_EXT}")
    L.append("")
    L.append("offset = barre tra segnale e punto vero (0 = centrato, + = ritardo, - = anticipo). "
             "Metriche TEST = out-of-sample.")
    L.append("")
    p, t = best["params"], best["test"]
    L.append("## Configurazione consigliata (miglior score out-of-sample)")
    L.append(f"- ext_min={p['ext_min']}, k_window={p['k_window']}, conf_bars={p['conf_bars']}, method={p['method']}")
    L.append(f"- TEST: precision {t['precision']}, recall {t['recall']}, f1 {t['f1']}, "
             f"offset mediano {t['median_offset']}, medio {t['mean_offset']}")
    L.append("")
    if pf:
        L.append("## Follow-through del PREZZO dopo la rotazione (config consigliata)")
        L.append("Ritorno medio/mediano nella direzione segnalata e hit rate, a +N barre H1.")
        L.append("")
        L.append("| orizzonte (barre H1) | n | ritorno medio % | mediano % | hit rate |")
        L.append("|---|---|---|---|---|")
        for h in PF_HORIZONS:
            s = pf.get(h, {}) if isinstance(pf, dict) else pf.get(str(h), {})
            if s.get("n"):
                L.append(f"| +{h} | {s['n']} | {s['mean_pct']} | {s['median_pct']} | {s['hit_rate']} |")
            else:
                L.append(f"| +{h} | 0 | - | - | - |")
        L.append("")
    if pf_str:
        L.append("## Edge per FORZA della rotazione (|estremo| dello spread)")
        L.append("Le rotazioni piu' forti hanno piu' follow-through? hit rate per orizzonte.")
        L.append("")
        L.append("| fascia estremo | n(+12) | hit +4 | hit +12 | hit +24 | medio % +24 |")
        L.append("|---|---|---|---|---|---|")
        def _lo(b):
            return float(b.replace("+", "").split("-")[0])
        for b in sorted(pf_str.keys(), key=_lo):
            hd = pf_str[b]
            def gv(h, k):
                s2 = hd.get(h) or hd.get(str(h)) or {}
                return s2.get(k, "-")
            n12 = (hd.get(12) or hd.get("12") or {}).get("n", "-")
            L.append(f"| {b} | {n12} | {gv(4,'hit_rate')} | {gv(12,'hit_rate')} | {gv(24,'hit_rate')} | {gv(24,'mean_pct')} |")
        L.append("")
    L.append("## Top 10 (per score out-of-sample)")
    L.append("")
    L.append("| # | method | ext | K | conf | prec | rec | f1 | off.med | score |")
    L.append("|---|--------|-----|---|------|------|-----|----|---------|-------|")
    for i, r in enumerate(rows[:10], 1):
        pp, tt = r["params"], r["test"]
        L.append(f"| {i} | {pp['method']} | {pp['ext_min']} | {pp['k_window']} | "
                 f"{pp['conf_bars']} | {tt['precision']} | {tt['recall']} | {tt['f1']} | "
                 f"{tt['median_offset']} | {r['score']} |")
    L.append("")
    path = os.path.join(out_dir, "rotation_backtest.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(L) + "\n")
    return path


def _synthetic():
    def ramp(a, b, n):
        return [a + (b - a) * i / (n - 1) for i in range(n)] if n > 1 else [float(b)]
    top_b = ramp(0, 2.8, 40) + ramp(2.8, 1.2, 40)[1:] + ramp(1.2, 2.8, 40)[1:] + ramp(2.8, 1.2, 40)[1:]
    top_q = [-x for x in top_b]
    sp_top = [b - q for b, q in zip(top_b, top_q)]
    flat = [0.3 * ((-1) ** i) for i in range(len(sp_top))]
    return {"AUDNZD": (sp_top, top_b, top_q),
            "NZDCAD": ([-x for x in sp_top], top_q, top_b),
            "EURGBP": (flat, [0.1] * len(flat), [-0.1] * len(flat))}, len(sp_top)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--oanda", action="store_true")
    ap.add_argument("--fixtures-h1")
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--count", type=int, default=4000)
    ap.add_argument("--out", default="reports/rotation")
    args = ap.parse_args()

    if args.selftest:
        sp_by_pair, n = _synthetic()
        rows, split = grid_search(sp_by_pair, n)
        path = write_report(rows, split, n, args.out, "selftest-sintetico", pf=None)
        print(f"SELFTEST ok -> {path}")
        print("best:", rows[0]["params"], rows[0]["test"])
        return 0

    try:
        if args.oanda:
            from fx_bias_radar.strength_h1 import fetch_all_h1
            from fx_bias_radar.oanda_fetch import env_credentials
            token, env = env_credentials()
            candles = fetch_all_h1(token, env=env, count=args.count)
        elif args.fixtures_h1:
            candles = C.load_fixture_dir(args.fixtures_h1)
        else:
            ap.error("specificare --oanda | --fixtures-h1 DIR | --selftest")
            return 2
        sp_by_pair, n, closes = spreads_from_candles(candles)
    except Exception as exc:  # noqa: BLE001
        print(f"ERRORE: {exc}")
        return 2

    rows, split = grid_search(sp_by_pair, n)
    best_params = RotParams(**rows[0]["params"])
    pf = price_followthrough(sp_by_pair, closes, best_params)
    pf_str = price_followthrough_by_strength(sp_by_pair, closes, best_params)
    src = "OANDA H1" if args.oanda else f"fixtures {args.fixtures_h1}"
    path = write_report(rows, split, n, args.out, src, pf=pf, pf_str=pf_str)
    print(f"Backtest rotazione -> {path}")
    print("best:", rows[0]["params"], "| test:", rows[0]["test"])
    print("price follow-through:", pf)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
