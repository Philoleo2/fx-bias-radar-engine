"""Migliorare la compressione+espansione: EXPECTANCY in R + filtro SESSIONE.

Riusa il segnale di Codex (compression_expansion_dir) ma cambia la METRICA: invece
dell'hit rate a orizzonte fisso, simula un trade gestito - stop sull'altro lato della
compressione, target a k*R - e misura l'EXPECTANCY (R medio per trade) e il win rate.
Idea: una rottura da squeeze tende a correre, quindi l'edge puo' stare nel rapporto
vincita/perdita, non nella frequenza. In piu' filtra per sessione (Londra/NY) e fa la
sanity prima/seconda meta' (out-of-sample). Confronta col breakout da solo.

Research-only, motore non toccato.

Uso:
  python scripts/backtest_compression_rr.py --oanda --count 4000 --out reports/comprr
  python scripts/backtest_compression_rr.py --fixtures-h1 tests/fixtures/golden_2026H1
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import backtest_compression_expansion as CE
from fx_bias_radar import candles as C

TARGETS = [1.0, 2.0, 3.0]      # target in multipli del rischio
MAX_BARS = 48                  # uscita a tempo se non tocca stop/target
SESSION_START, SESSION_END = 7, 16   # ora UTC "attiva" (Londra+NY)
PROFILES = [CE.Profile(12, 0.20), CE.Profile(12, 0.30)]


def trade_outcome(rows, t, direction, window, target_k, max_bars=MAX_BARS):
    """Outcome in R: stop sull'altro lato della compressione, target a k*R."""
    b = CE.window_bounds(rows, t, window)
    if b is None:
        return None
    _, hi, lo = b
    entry = rows[t].c
    if direction == "LONG":
        stop = lo
        risk = entry - stop
        if risk <= 0:
            return None
        target = entry + target_k * risk
    else:
        stop = hi
        risk = stop - entry
        if risk <= 0:
            return None
        target = entry - target_k * risk
    end = min(t + max_bars, len(rows))
    for t2 in range(t + 1, end):
        h, l = rows[t2].h, rows[t2].l
        if direction == "LONG":
            if l <= stop:
                return -1.0               # stop prima (conservativo)
            if h >= target:
                return float(target_k)
        else:
            if h >= stop:
                return -1.0
            if l <= target:
                return float(target_k)
    cexit = rows[end - 1].c
    return (cexit - entry) / risk if direction == "LONG" else (entry - cexit) / risk


def _hour(time_iso):
    try:
        return datetime.fromisoformat(str(time_iso).replace("Z", "+00:00")).hour
    except Exception:
        return None


def _agg_r(vals):
    if not vals:
        return {"n": 0, "expectancy_R": None, "win_rate": None}
    return {"n": len(vals),
            "expectancy_R": round(sum(vals) / len(vals), 4),
            "win_rate": round(sum(1 for v in vals if v > 0) / len(vals), 3)}


def run(ohlc_by_pair, times, n_bars):
    half = n_bars // 2
    # struttura: [set][session][sample][target] -> list di R
    def newbucket():
        return {tk: [] for tk in TARGETS}
    data = {}
    for prof in PROFILES:
        for set_name in ("compression_expansion", "breakout_only"):
            for sess in ("all", "session", "off"):
                for sample in ("all", "h1", "h2"):
                    data[(prof.name, set_name, sess, sample)] = newbucket()
    for pair, rows in ohlc_by_pair.items():
        for prof in PROFILES:
            start = prof.window + CE.RANK_WINDOW
            for t in range(start, len(rows)):
                for set_name in ("breakout_only", "compression_expansion"):
                    if set_name == "breakout_only":
                        d = CE.is_new_breakout(rows, t, prof.window)
                    else:
                        d = CE.compression_expansion_dir(rows, t, prof)
                    if d is None:
                        continue
                    hr = _hour(times[t]) if t < len(times) else None
                    in_sess = hr is not None and SESSION_START <= hr < SESSION_END
                    sample = "h1" if t < half else "h2"
                    for tk in TARGETS:
                        out = trade_outcome(rows, t, d, prof.window, tk)
                        if out is None:
                            continue
                        for sess in ("all", "session" if in_sess else "off"):
                            for smp in ("all", sample):
                                data[(prof.name, set_name, sess, smp)][tk].append(out)
    # aggrega
    res = {}
    for key, byk in data.items():
        res["|".join(key)] = {str(tk): _agg_r(v) for tk, v in byk.items()}
    return res, half


def write_report(res, n_bars, half, out_dir, source):
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "compression_rr.json"), "w", encoding="utf-8") as f:
        json.dump({"source": source, "n_bars": n_bars, "split": half,
                   "targets": TARGETS, "max_bars": MAX_BARS,
                   "session_utc": [SESSION_START, SESSION_END], "results": res}, f, indent=2)
    L = ["# Compressione + espansione: EXPECTANCY in R + sessione", ""]
    L.append(f"Fonte: {source} | barre H1: {n_bars} | split prima/seconda meta @ {half}")
    L.append(f"Stop = altro lato della compressione. Target = k*R. Uscita a tempo {MAX_BARS} barre. "
             f"Sessione UTC {SESSION_START}-{SESSION_END}. expectancy_R>0 con costi sotto soglia = potenziale edge.")
    L.append("")
    L.append("## Expectancy in R (target 2R), confronto compressione vs breakout, per sessione e meta'")
    L.append("")
    L.append("| profilo | set | sessione | campione | n | expectancy R (2R) | win rate |")
    L.append("|---|---|---|---|---|---|---|")
    for prof in PROFILES:
        for set_name in ("compression_expansion", "breakout_only"):
            for sess in ("all", "session", "off"):
                for sample in ("all", "h1", "h2"):
                    k = "|".join((prof.name, set_name, sess, sample))
                    cell = res.get(k, {}).get("2.0", {})
                    L.append(f"| {prof.name} | {set_name} | {sess} | {sample} | "
                             f"{cell.get('n')} | {cell.get('expectancy_R')} | {cell.get('win_rate')} |")
    L.append("")
    L.append("## Expectancy per target (compressione, sessione attiva, tutto il campione)")
    L.append("")
    L.append("| profilo | target | n | expectancy R | win rate |")
    L.append("|---|---|---|---|---|")
    for prof in PROFILES:
        k = "|".join((prof.name, "compression_expansion", "session", "all"))
        for tk in TARGETS:
            cell = res.get(k, {}).get(str(tk), {})
            L.append(f"| {prof.name} | {tk}R | {cell.get('n')} | {cell.get('expectancy_R')} | {cell.get('win_rate')} |")
    L.append("")
    path = os.path.join(out_dir, "compression_rr.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(L) + "\n")
    return path


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--oanda", action="store_true")
    ap.add_argument("--fixtures-h1")
    ap.add_argument("--count", type=int, default=4000)
    ap.add_argument("--out", default="reports/comprr")
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
        times, _closes, ohlc = CE.aligned_ohlc(candles)
        n_bars = len(next(iter(ohlc.values())))
        res, half = run(ohlc, times, n_bars)
    except Exception as exc:  # noqa: BLE001
        print(f"ERRORE: {exc}")
        return 2
    path = write_report(res, n_bars, half, args.out, source)
    print(f"Compressione R+sessione -> {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
