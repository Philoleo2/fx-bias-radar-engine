"""Compressione + espansione H1 su storico lungo con walk-forward.

Research-only. Scarica OANDA H1 a pagine, poi valuta la logica
compressione+espansione scegliendo il profilo sul TRAIN di ogni fold e misurando
solo il TEST successivo.

Uso:
  python scripts/backtest_compression_expansion_long.py --oanda --count 30000 --out reports/compexp_long
  python scripts/backtest_compression_expansion_long.py --fixtures-h1 tests/fixtures/golden_2026H1 --train-bars 300 --test-bars 100
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
from fx_bias_radar import candles as C
from fx_bias_radar import pairs as P
from fx_bias_radar.candles import Candle
from fx_bias_radar.oanda import OandaError
from fx_bias_radar.oanda_fetch import _client_for, _is_transient_oanda_error, env_credentials

DEFAULT_COUNT = 30000
PAGE_SIZE = 5000
TRAIN_BARS = 6000
TEST_BARS = 2000
MIN_TRAIN_N = 50


def _as_oanda_time(dt) -> str:
    return dt.isoformat().replace("+00:00", "Z")


def _to_candle(raw) -> Candle:
    return Candle(
        time=raw.time.isoformat(),
        o=raw.open,
        h=raw.high,
        l=raw.low,
        c=raw.close,
        volume=raw.volume,
        complete=raw.complete,
    )


def _request_page(client, instrument, *, env_cursor, page_size, retries):
    max_attempts = max(1, retries + 1)
    for attempt in range(max_attempts):
        try:
            return client.candles(
                instrument,
                granularity="H1",
                count=page_size,
                to_time=env_cursor,
                price="M",
                include_incomplete=False,
            )
        except OandaError as exc:
            if attempt >= max_attempts - 1 or not _is_transient_oanda_error(exc):
                raise
            time.sleep(0.25 * (2 ** attempt))
    return []


def merge_unique_pages(pages, count):
    by_time = {}
    for page in pages:
        for candle in page:
            if candle.complete:
                by_time[candle.time.isoformat()] = _to_candle(candle)
    rows = [by_time[t] for t in sorted(by_time)]
    return rows[-count:] if count and len(rows) > count else rows


def fetch_h1_history(instrument, token, env="practice", *, count=DEFAULT_COUNT,
                     page_size=PAGE_SIZE, retries=2):
    """Fetch latest complete H1 candles by paging backwards from now."""
    client = _client_for(token, env)
    pages = []
    cursor = None
    seen_oldest = None
    while True:
        remaining = count - sum(len(p) for p in pages)
        if remaining <= 0:
            break
        request_size = min(page_size, max(remaining, min(page_size, count)))
        had_cursor = cursor is not None
        page = _request_page(client, instrument, env_cursor=cursor,
                             page_size=request_size, retries=retries)
        page = [c for c in page if c.complete]
        if not page:
            break
        pages.append(page)
        oldest = min(c.time for c in page)
        if seen_oldest is not None and oldest >= seen_oldest:
            break
        seen_oldest = oldest
        cursor = _as_oanda_time(oldest)
        if had_cursor and len(page) < request_size:
            break
    return merge_unique_pages(pages, count)


def fetch_all_h1_history(token, env="practice", *, count=DEFAULT_COUNT,
                         page_size=PAGE_SIZE, max_workers=8):
    out = {}
    workers = max(1, min(max_workers, len(P.PAIRS)))

    def fetch_pair(pair):
        return pair, fetch_h1_history(P.oanda_instrument(pair), token, env=env,
                                      count=count, page_size=page_size)

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(fetch_pair, pair): pair for pair in P.PAIRS}
        for future in as_completed(futures):
            pair, rows = future.result()
            out[pair] = rows
    return out


def _empty_h():
    return {h: [] for h in CE.HORIZONS}


def _fwd_limited(prices, t, h, direction, outcome_end):
    if t + h >= outcome_end or t + h >= len(prices):
        return None
    return CE._fwd(prices, t, h, direction)


def measure_interval(ohlc_by_pair, closes, profile, start, end):
    buckets = {"compression_expansion": _empty_h(), "breakout_only": _empty_h()}
    start = max(start, profile.window + CE.RANK_WINDOW)
    for pair, rows in ohlc_by_pair.items():
        prices = closes.get(pair) if isinstance(closes, dict) else None
        if not prices:
            continue
        stop = min(end, len(rows))
        for t in range(start, stop):
            for set_name, direction in (
                ("breakout_only", CE.is_new_breakout(rows, t, profile.window)),
                ("compression_expansion", CE.compression_expansion_dir(rows, t, profile)),
            ):
                if direction is None:
                    continue
                for h in CE.HORIZONS:
                    fr = _fwd_limited(prices, t, h, direction, stop)
                    if fr is not None:
                        buckets[set_name][h].append(fr)
    return {name: CE._agg(vals) for name, vals in buckets.items()}


def _edge_at_12(metrics):
    ce = metrics["compression_expansion"].get(12, {})
    bo = metrics["breakout_only"].get(12, {})
    if ce.get("hit") is None or bo.get("hit") is None:
        return None
    return round(ce["hit"] - bo["hit"], 3)


def _choose_profile(train_metrics):
    candidates = []
    for name, metrics in train_metrics.items():
        n12 = metrics["compression_expansion"].get(12, {}).get("n", 0)
        edge = _edge_at_12(metrics)
        if edge is None or n12 < MIN_TRAIN_N:
            continue
        hit12 = metrics["compression_expansion"][12]["hit"]
        candidates.append((edge, hit12, n12, name))
    if not candidates:
        return None
    candidates.sort(reverse=True)
    return candidates[0][3]


def _interval_returns(ohlc_by_pair, closes, profile, start, end, set_name):
    out = _empty_h()
    start = max(start, profile.window + CE.RANK_WINDOW)
    for pair, rows in ohlc_by_pair.items():
        prices = closes.get(pair) if isinstance(closes, dict) else None
        if not prices:
            continue
        stop = min(end, len(rows))
        for t in range(start, stop):
            if set_name == "compression_expansion":
                direction = CE.compression_expansion_dir(rows, t, profile)
            else:
                direction = CE.is_new_breakout(rows, t, profile.window)
            if direction is None:
                continue
            for h in CE.HORIZONS:
                fr = _fwd_limited(prices, t, h, direction, stop)
                if fr is not None:
                    out[h].append(fr)
    return out


def _merge_returns(dst, src):
    for h, vals in src.items():
        dst[h].extend(vals)


def walk_forward(ohlc_by_pair, closes, n_bars, *, train_bars=TRAIN_BARS,
                 test_bars=TEST_BARS):
    selected_returns = {"compression_expansion": _empty_h(), "breakout_only": _empty_h()}
    fixed_returns = {
        profile.name: {"compression_expansion": _empty_h(), "breakout_only": _empty_h()}
        for profile in CE.PROFILES
    }
    folds = []
    fold_id = 1
    train_start = 0
    while train_start + train_bars + test_bars <= n_bars:
        train_end = train_start + train_bars
        test_end = train_end + test_bars
        train_metrics = {
            profile.name: measure_interval(ohlc_by_pair, closes, profile, train_start, train_end)
            for profile in CE.PROFILES
        }
        best_name = _choose_profile(train_metrics)
        fold = {
            "fold": fold_id,
            "train": [train_start, train_end],
            "test": [train_end, test_end],
            "selected_profile": best_name,
            "train_metrics": train_metrics,
            "test_metrics": {},
        }
        if best_name:
            best_profile = next(p for p in CE.PROFILES if p.name == best_name)
            test_metrics = measure_interval(ohlc_by_pair, closes, best_profile, train_end, test_end)
            fold["test_metrics"][best_name] = test_metrics
            for set_name in selected_returns:
                vals = _interval_returns(ohlc_by_pair, closes, best_profile,
                                         train_end, test_end, set_name)
                _merge_returns(selected_returns[set_name], vals)
        for profile in CE.PROFILES:
            for set_name in fixed_returns[profile.name]:
                vals = _interval_returns(ohlc_by_pair, closes, profile,
                                         train_end, test_end, set_name)
                _merge_returns(fixed_returns[profile.name][set_name], vals)
        folds.append(fold)
        fold_id += 1
        train_start += test_bars
    return {
        "train_bars": train_bars,
        "test_bars": test_bars,
        "n_folds": len(folds),
        "selected_strategy": {name: CE._agg(vals) for name, vals in selected_returns.items()},
        "fixed_profiles": {
            name: {set_name: CE._agg(vals) for set_name, vals in sets.items()}
            for name, sets in fixed_returns.items()
        },
        "folds": folds,
    }


def _metric(metrics, set_name, h, field):
    return metrics[set_name].get(h, {}).get(field)


def _edge(metrics):
    return _edge_at_12(metrics)


def _row(name, metrics):
    ce = metrics["compression_expansion"]
    bo = metrics["breakout_only"]
    return (
        f"| {name} | {ce.get(12, {}).get('n')} | {ce.get(4, {}).get('hit')} | "
        f"{ce.get(12, {}).get('hit')} | {ce.get(24, {}).get('hit')} | "
        f"{ce.get(12, {}).get('mean_pct')} | {bo.get(12, {}).get('hit')} | "
        f"{bo.get(12, {}).get('mean_pct')} | {_edge(metrics)} |"
    )


def _fold_row(fold):
    selected = fold["selected_profile"] or "-"
    train_edge = _edge(fold["train_metrics"][selected]) if selected != "-" else None
    test_metrics = fold["test_metrics"].get(selected) if selected != "-" else None
    test_edge = _edge(test_metrics) if test_metrics else None
    test_n = _metric(test_metrics, "compression_expansion", 12, "n") if test_metrics else None
    test_hit = _metric(test_metrics, "compression_expansion", 12, "hit") if test_metrics else None
    return (
        f"| {fold['fold']} | {fold['train'][0]}-{fold['train'][1]} | "
        f"{fold['test'][0]}-{fold['test'][1]} | {selected} | {train_edge} | "
        f"{test_n} | {test_hit} | {test_edge} |"
    )


def write_report(wf, n_bars, out_dir, source, count, page_size):
    os.makedirs(out_dir, exist_ok=True)
    payload = {
        "source": source,
        "requested_count": count,
        "page_size": page_size,
        "n_bars": n_bars,
        "timeframe": "H1",
        "rank_window": CE.RANK_WINDOW,
        "horizons_h1": CE.HORIZONS,
        "walk_forward": wf,
    }
    json_path = os.path.join(out_dir, "compression_expansion_long.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)

    L = ["# Compressione + espansione H1 - storico lungo walk-forward", ""]
    L.append(f"Fonte: {source} | barre H1 allineate: {n_bars} | richieste: {count} | page_size: {page_size}")
    L.append(f"Walk-forward: train {wf['train_bars']} barre, test {wf['test_bars']} barre, fold: {wf['n_folds']}.")
    L.append("Compressione = range ultime N barre <= percentile storico su 120 finestre precedenti.")
    L.append("Espansione = nuova chiusura fuori dal range. Baseline = breakout da solo.")
    L.append("")
    L.append("## Strategia selezionata dal TRAIN di ogni fold")
    L.append("")
    L.append("| strategia | n(+12) | hit +4 | hit +12 | hit +24 | medio% +12 | baseline hit +12 | baseline medio% +12 | edge hit +12 |")
    L.append("|---|---|---|---|---|---|---|---|---|")
    L.append(_row("walk-forward selected", wf["selected_strategy"]))
    L.append("")
    L.append("## Profili fissi sul TEST walk-forward")
    L.append("")
    L.append("| profilo | n(+12) | hit +4 | hit +12 | hit +24 | medio% +12 | baseline hit +12 | baseline medio% +12 | edge hit +12 |")
    L.append("|---|---|---|---|---|---|---|---|---|")
    for name in sorted(wf["fixed_profiles"]):
        L.append(_row(name, wf["fixed_profiles"][name]))
    L.append("")
    L.append("## Fold")
    L.append("")
    L.append("| fold | train | test | profilo scelto | edge train +12 | n test +12 | hit test +12 | edge test +12 |")
    L.append("|---|---|---|---|---|---|---|---|")
    for fold in wf["folds"]:
        L.append(_fold_row(fold))
    L.append("")
    md_path = os.path.join(out_dir, "compression_expansion_long.md")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write("\n".join(L) + "\n")
    return md_path


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--oanda", action="store_true")
    ap.add_argument("--fixtures-h1")
    ap.add_argument("--count", type=int, default=DEFAULT_COUNT)
    ap.add_argument("--page-size", type=int, default=PAGE_SIZE)
    ap.add_argument("--max-workers", type=int, default=8)
    ap.add_argument("--train-bars", type=int, default=TRAIN_BARS)
    ap.add_argument("--test-bars", type=int, default=TEST_BARS)
    ap.add_argument("--out", default="reports/compexp_long")
    args = ap.parse_args()
    try:
        if args.oanda:
            token, env = env_credentials()
            candles = fetch_all_h1_history(token, env=env, count=args.count,
                                           page_size=args.page_size,
                                           max_workers=args.max_workers)
            source = "OANDA H1 paginated"
        elif args.fixtures_h1:
            candles = C.load_fixture_dir(args.fixtures_h1)
            source = f"fixtures {args.fixtures_h1}"
        else:
            ap.error("specificare --oanda oppure --fixtures-h1 DIR")
            return 2
        _, closes, ohlc = CE.aligned_ohlc(candles)
        n_bars = len(next(iter(ohlc.values())))
        wf = walk_forward(ohlc, closes, n_bars,
                          train_bars=args.train_bars,
                          test_bars=args.test_bars)
        if wf["n_folds"] == 0:
            raise RuntimeError("storico insufficiente per il walk-forward richiesto")
    except Exception as exc:  # noqa: BLE001
        print(f"ERRORE: {exc}")
        return 2
    path = write_report(wf, n_bars, args.out, source, args.count, args.page_size)
    print(f"Compressione+espansione long -> {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
