"""Compressione + espansione su TIMEFRAME diversi (H4, D1).

Stessa logica del backtest H1 di Codex, ma su barre piu' grandi: i trend
persistono di piu' e c'e' meno rumore, quindi le rotture da compressione
potrebbero reggere meglio. Entrata alla CHIUSURA della barra (no-repaint): se
entrare a chiusura H4 e' gia' tardi, l'edge esce ~0 (test della lateness).

Riusa CE (rilevamento) e CL.walk_forward (out-of-sample). Research-only, motore intatto.

Uso:
  python scripts/backtest_compression_tf.py --oanda --granularity H4 --count 20000 --out reports/comp_h4
  python scripts/backtest_compression_tf.py --oanda --granularity D --count 4000 --out reports/comp_d1
  python scripts/backtest_compression_tf.py --fixtures-h1 tests/fixtures/golden_2026H1 --train-bars 300 --test-bars 100
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import backtest_compression_expansion as CE
import backtest_compression_expansion_long as CL
from fx_bias_radar import candles as C
from fx_bias_radar import pairs as P
from fx_bias_radar.candles import Candle
from fx_bias_radar.oanda import OandaError
from fx_bias_radar.oanda_fetch import _client_for, _is_transient_oanda_error, env_credentials

PAGE_SIZE = 5000


def _as_oanda_time(dt):
    return dt.isoformat().replace("+00:00", "Z")


def _to_candle(raw):
    return Candle(time=raw.time.isoformat(), o=raw.open, h=raw.high, l=raw.low,
                  c=raw.close, volume=raw.volume, complete=raw.complete)


def fetch_history(instrument, token, env, granularity, count, page_size=PAGE_SIZE, retries=2):
    client = _client_for(token, env)
    by_time = {}
    cursor = None
    seen_oldest = None
    while len(by_time) < count:
        for attempt in range(retries + 1):
            try:
                page = client.candles(instrument, granularity=granularity,
                                      count=min(page_size, count),
                                      to_time=cursor, price="M", include_incomplete=False)
                break
            except OandaError as exc:
                if attempt >= retries or not _is_transient_oanda_error(exc):
                    raise
                time.sleep(0.25 * (2 ** attempt))
        page = [c for c in page if c.complete]
        if not page:
            break
        for c in page:
            by_time[c.time.isoformat()] = _to_candle(c)
        oldest = min(c.time for c in page)
        if seen_oldest is not None and oldest >= seen_oldest:
            break
        seen_oldest = oldest
        cursor = _as_oanda_time(oldest)
    rows = [by_time[t] for t in sorted(by_time)]
    return rows[-count:] if len(rows) > count else rows


def fetch_all(token, env, granularity, count, max_workers=8):
    out = {}
    workers = max(1, min(max_workers, len(P.PAIRS)))

    def one(pair):
        return pair, fetch_history(P.oanda_instrument(pair), token, env, granularity, count)

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futs = {pool.submit(one, p): p for p in P.PAIRS}
        for fut in as_completed(futs):
            pair, rows = fut.result()
            out[pair] = rows
    return out


def write_report(wf, n_bars, out_dir, source, granularity):
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "compression_tf.json"), "w", encoding="utf-8") as f:
        json.dump({"source": source, "granularity": granularity, "n_bars": n_bars,
                   "horizons_bars": CE.HORIZONS, "walk_forward": wf}, f, indent=2)
    sel = wf["selected_strategy"]
    ce = sel["compression_expansion"]
    bo = sel["breakout_only"]
    L = [f"# Compressione + espansione {granularity} - walk-forward", ""]
    L.append(f"Fonte: {source} | granularita': {granularity} | barre: {n_bars} | "
             f"fold: {wf['n_folds']} (train {wf['train_bars']}, test {wf['test_bars']})")
    L.append(f"Orizzonti in barre {granularity}: {CE.HORIZONS} (su {granularity} = piu' tempo per barra). "
             "Entrata a CHIUSURA barra. edge = compressione - breakout liscio.")
    L.append("")
    L.append("## Strategia selezionata (walk-forward, out-of-sample)")
    L.append("| set | n(+12) | hit +4 | hit +12 | hit +24 | medio% +12 |")
    L.append("|---|---|---|---|---|---|")
    L.append(f"| compressione | {ce.get(12,{}).get('n')} | {ce.get(4,{}).get('hit')} | "
             f"{ce.get(12,{}).get('hit')} | {ce.get(24,{}).get('hit')} | {ce.get(12,{}).get('mean_pct')} |")
    L.append(f"| breakout liscio | {bo.get(12,{}).get('n')} | {bo.get(4,{}).get('hit')} | "
             f"{bo.get(12,{}).get('hit')} | {bo.get(24,{}).get('hit')} | {bo.get(12,{}).get('mean_pct')} |")
    ce12 = ce.get(12, {}).get("hit")
    bo12 = bo.get(12, {}).get("hit")
    edge = round(ce12 - bo12, 3) if (ce12 is not None and bo12 is not None) else None
    L.append("")
    L.append(f"**Edge hit +12 (compressione vs breakout): {edge}**")
    L.append("")
    L.append("## Profili fissi sul TEST")
    L.append("| profilo | n(+12) | hit +12 | medio% +12 | edge +12 |")
    L.append("|---|---|---|---|---|")
    for name in sorted(wf["fixed_profiles"]):
        m = wf["fixed_profiles"][name]
        c12 = m["compression_expansion"].get(12, {})
        b12 = m["breakout_only"].get(12, {})
        e = (round(c12.get("hit") - b12.get("hit"), 3)
             if c12.get("hit") is not None and b12.get("hit") is not None else None)
        L.append(f"| {name} | {c12.get('n')} | {c12.get('hit')} | {c12.get('mean_pct')} | {e} |")
    L.append("")
    path = os.path.join(out_dir, "compression_tf.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(L) + "\n")
    return path


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--oanda", action="store_true")
    ap.add_argument("--fixtures-h1")
    ap.add_argument("--granularity", default="H4")
    ap.add_argument("--count", type=int, default=20000)
    ap.add_argument("--train-bars", type=int, default=CL.TRAIN_BARS)
    ap.add_argument("--test-bars", type=int, default=CL.TEST_BARS)
    ap.add_argument("--out", default="reports/comp_tf")
    args = ap.parse_args()
    try:
        if args.oanda:
            token, env = env_credentials()
            candles = fetch_all(token, env, args.granularity, args.count)
            source = f"OANDA {args.granularity}"
        elif args.fixtures_h1:
            candles = C.load_fixture_dir(args.fixtures_h1)
            source = f"fixtures {args.fixtures_h1}"
        else:
            ap.error("specificare --oanda oppure --fixtures-h1 DIR")
            return 2
        _, closes, ohlc = CE.aligned_ohlc(candles)
        n_bars = len(next(iter(ohlc.values())))
        wf = CL.walk_forward(ohlc, closes, n_bars, train_bars=args.train_bars,
                             test_bars=args.test_bars)
        if wf["n_folds"] == 0:
            raise RuntimeError("storico insufficiente per il walk-forward richiesto")
    except Exception as exc:  # noqa: BLE001
        print(f"ERRORE: {exc}")
        return 2
    path = write_report(wf, n_bars, args.out, source, args.granularity)
    print(f"Compressione {args.granularity} -> {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
