"""A/B research: Ichimoku D1+W direction vs compression D1+W for H1 breakouts.

Research-only. Non tocca motore live, scanner, dashboard o email.

Question:
- H1 event = nuova rottura del range a 12 barre.
- Baseline = rottura H1 allineata alla direzione compressione D1 e W attiva.
- Test = rottura H1 allineata alla direzione Ichimoku D1 e/o W.

No lookahead:
- per ogni evento H1 si usa solo la barra D1/W con data strettamente precedente;
- la nuvola Ichimoku alla barra t usa Senkou A/B calcolate a t-26.
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
HORIZONS = (4, 12, 24, 48)
TRAIN_BARS = 6000
TEST_BARS = 2000
MIN_USABLE_EVENTS = 150

MAIN_COHORTS = (
    "all",
    "compr_d1w",
    "ichimoku_d1w",
    "ichimoku_d1_only",
    "ichimoku_w_only",
)
KIJUN_COHORTS = (
    "kijun_d1w",
    "kijun_d1_only",
    "kijun_w_only",
)
COHORTS = MAIN_COHORTS + KIJUN_COHORTS


def active_compression_map(candles, k):
    """Same state logic as compression.active_daily_dir(), but per bar."""
    active = [None] * len(candles)
    last_dir = None
    last_bar = -10**9
    for i in range(len(candles)):
        direction = COMP.compression_breakout(candles, i)
        if direction is not None:
            last_dir, last_bar = direction, i
        if last_dir is not None and (i - last_bar) <= k:
            active[i] = last_dir
    return active


def _date_key(candle):
    return str(candle.time)[:10]


def prior_state(date_keys, states, h1_date):
    """Return higher-timeframe state with date strictly preceding h1_date."""
    idx = bisect.bisect_left(date_keys, h1_date) - 1
    return states[idx] if 0 <= idx < len(states) else None


def _midpoint(candles, idx, length):
    if idx < length - 1:
        return None
    chunk = candles[idx - length + 1: idx + 1]
    return (max(c.h for c in chunk) + min(c.l for c in chunk)) / 2.0


def ichimoku_direction_map(candles):
    """Ichimoku state with standard params and no forward cloud lookahead.

    Tenkan: 9, Kijun: 26, Senkou B: 52. The cloud at index t uses values
    calculated at t-26, i.e. projected to t by normal Ichimoku convention.
    """
    n = len(candles)
    tenkan = [_midpoint(candles, i, 9) for i in range(n)]
    kijun = [_midpoint(candles, i, 26) for i in range(n)]
    span_a_raw = [
        (tenkan[i] + kijun[i]) / 2.0
        if tenkan[i] is not None and kijun[i] is not None
        else None
        for i in range(n)
    ]
    span_b_raw = [_midpoint(candles, i, 52) for i in range(n)]

    out = [None] * n
    for i in range(n):
        cloud_src = i - 26
        if cloud_src < 0:
            continue
        span_a = span_a_raw[cloud_src]
        span_b = span_b_raw[cloud_src]
        if (
            span_a is None
            or span_b is None
            or tenkan[i] is None
            or kijun[i] is None
        ):
            continue
        top = max(span_a, span_b)
        bot = min(span_a, span_b)
        close = candles[i].c
        if close > top and tenkan[i] > kijun[i]:
            out[i] = "LONG"
        elif close < bot and tenkan[i] < kijun[i]:
            out[i] = "SHORT"
    return out


def kijun_direction_map(candles):
    """Optional simple variant: close above/below Kijun."""
    out = [None] * len(candles)
    for i in range(len(candles)):
        kijun = _midpoint(candles, i, 26)
        if kijun is None:
            continue
        close = candles[i].c
        if close > kijun:
            out[i] = "LONG"
        elif close < kijun:
            out[i] = "SHORT"
    return out


def _empty_returns():
    return {
        cohort: {
            "train": {h: [] for h in HORIZONS},
            "test": {h: [] for h in HORIZONS},
        }
        for cohort in COHORTS
    }


def _new_fold_bucket(fold_id, train_start, train_end, test_end):
    return {
        "fold": fold_id,
        "train": [train_start, train_end],
        "test": [train_end, test_end],
        "returns": _empty_returns(),
    }


def _fwd_limited(closes, t, h, direction, outcome_end):
    if t + h >= outcome_end or t + h >= len(closes):
        return None
    p0, p1 = closes[t], closes[t + h]
    if p0 is None or p1 is None or p0 == 0:
        return None
    ret = (p1 - p0) / p0
    return ret if direction == "LONG" else -ret


def _add_event(buckets, cohort, sample, closes, t, direction, outcome_end):
    for h in HORIZONS:
        ret = _fwd_limited(closes, t, h, direction, outcome_end)
        if ret is not None:
            buckets[cohort][sample][h].append(ret)


def _merge_returns(dst, src):
    for cohort in COHORTS:
        for sample in ("train", "test"):
            for h in HORIZONS:
                dst[cohort][sample][h].extend(src[cohort][sample][h])


def _classify_event(
    buckets,
    sample,
    closes,
    t,
    direction,
    outcome_end,
    h1_date,
    d1_dates,
    w_dates,
    d1_compr,
    w_compr,
    d1_ichi,
    w_ichi,
    d1_kijun,
    w_kijun,
):
    d1_compr_dir = prior_state(d1_dates, d1_compr, h1_date)
    w_compr_dir = prior_state(w_dates, w_compr, h1_date)
    d1_ichi_dir = prior_state(d1_dates, d1_ichi, h1_date)
    w_ichi_dir = prior_state(w_dates, w_ichi, h1_date)
    d1_kijun_dir = prior_state(d1_dates, d1_kijun, h1_date)
    w_kijun_dir = prior_state(w_dates, w_kijun, h1_date)

    _add_event(buckets, "all", sample, closes, t, direction, outcome_end)

    if d1_compr_dir == direction and w_compr_dir == direction:
        _add_event(buckets, "compr_d1w", sample, closes, t, direction, outcome_end)
    if d1_ichi_dir == direction:
        _add_event(buckets, "ichimoku_d1_only", sample, closes, t, direction, outcome_end)
        if w_ichi_dir == direction:
            _add_event(buckets, "ichimoku_d1w", sample, closes, t, direction, outcome_end)
    if w_ichi_dir == direction:
        _add_event(buckets, "ichimoku_w_only", sample, closes, t, direction, outcome_end)

    if d1_kijun_dir == direction:
        _add_event(buckets, "kijun_d1_only", sample, closes, t, direction, outcome_end)
        if w_kijun_dir == direction:
            _add_event(buckets, "kijun_d1w", sample, closes, t, direction, outcome_end)
    if w_kijun_dir == direction:
        _add_event(buckets, "kijun_w_only", sample, closes, t, direction, outcome_end)


def process_pair(h1, d1, w1, overall, folds, *, train_bars, test_bars):
    if len(h1) < H1_WINDOW + COMP.RANK_WINDOW + train_bars + test_bars:
        return 0
    if not d1 or not w1:
        return 0

    closes = [c.c for c in h1]
    d1_dates = [_date_key(c) for c in d1]
    w_dates = [_date_key(c) for c in w1]
    d1_compr = active_compression_map(d1, D1_K)
    w_compr = active_compression_map(w1, W_K)
    d1_ichi = ichimoku_direction_map(d1)
    w_ichi = ichimoku_direction_map(w1)
    d1_kijun = kijun_direction_map(d1)
    w_kijun = kijun_direction_map(w1)

    pair_events = 0
    fold_id = 1
    train_start = 0
    while train_start + train_bars + test_bars <= len(h1):
        train_end = train_start + train_bars
        test_end = train_end + test_bars
        fold = folds.setdefault(fold_id, _new_fold_bucket(fold_id, train_start, train_end, test_end))
        fold_bucket = fold["returns"]

        for sample, start, end, outcome_end in (
            ("train", train_start, train_end, train_end),
            ("test", train_end, test_end, test_end),
        ):
            start = max(start, H1_WINDOW + 1)
            for t in range(start, end):
                direction = COMP.is_new_breakout(h1, t, H1_WINDOW)
                if direction is None:
                    continue
                pair_events += 1
                h1_date = _date_key(h1[t])
                _classify_event(
                    overall,
                    sample,
                    closes,
                    t,
                    direction,
                    outcome_end,
                    h1_date,
                    d1_dates,
                    w_dates,
                    d1_compr,
                    w_compr,
                    d1_ichi,
                    w_ichi,
                    d1_kijun,
                    w_kijun,
                )
                _classify_event(
                    fold_bucket,
                    sample,
                    closes,
                    t,
                    direction,
                    outcome_end,
                    h1_date,
                    d1_dates,
                    w_dates,
                    d1_compr,
                    w_compr,
                    d1_ichi,
                    w_ichi,
                    d1_kijun,
                    w_kijun,
                )

        fold_id += 1
        train_start += test_bars
    return pair_events


def _agg(values):
    if not values:
        return {"n": 0, "hit": None, "mean_pct": None}
    return {
        "n": len(values),
        "hit": round(sum(1 for v in values if v > 0) / len(values), 3),
        "mean_pct": round(100.0 * sum(values) / len(values), 4),
    }


def aggregate_returns(returns):
    return {
        cohort: {
            sample: {str(h): _agg(returns[cohort][sample][h]) for h in HORIZONS}
            for sample in ("train", "test")
        }
        for cohort in COHORTS
    }


def _metric(agg, cohort, sample, h, field):
    return agg.get(cohort, {}).get(sample, {}).get(str(h), {}).get(field)


def _edge(value, baseline):
    if value is None or baseline is None:
        return None
    return round(value - baseline, 4)


def _edge_vs_baseline(agg, cohort, sample, h):
    return {
        "hit": _edge(
            _metric(agg, cohort, sample, h, "hit"),
            _metric(agg, "compr_d1w", sample, h, "hit"),
        ),
        "mean_pct": _edge(
            _metric(agg, cohort, sample, h, "mean_pct"),
            _metric(agg, "compr_d1w", sample, h, "mean_pct"),
        ),
    }


def fold_summaries(folds):
    rows = []
    comparable = 0
    wins_both = 0
    for fold_id in sorted(folds):
        fold = folds[fold_id]
        agg = aggregate_returns(fold["returns"])
        base = agg["compr_d1w"]["test"]["12"]
        ichi = agg["ichimoku_d1w"]["test"]["12"]
        edge = _edge_vs_baseline(agg, "ichimoku_d1w", "test", 12)
        beats_both = False
        if (
            base["hit"] is not None
            and base["mean_pct"] is not None
            and ichi["hit"] is not None
            and ichi["mean_pct"] is not None
        ):
            comparable += 1
            beats_both = ichi["hit"] > base["hit"] and ichi["mean_pct"] > base["mean_pct"]
            if beats_both:
                wins_both += 1
        rows.append(
            {
                "fold": fold_id,
                "train": fold["train"],
                "test": fold["test"],
                "compr_d1w_n": base["n"],
                "compr_d1w_hit": base["hit"],
                "compr_d1w_mean_pct": base["mean_pct"],
                "ichimoku_d1w_n": ichi["n"],
                "ichimoku_d1w_hit": ichi["hit"],
                "ichimoku_d1w_mean_pct": ichi["mean_pct"],
                "edge_hit": edge["hit"],
                "edge_mean_pct": edge["mean_pct"],
                "beats_both": beats_both,
            }
        )
    return {
        "rows": rows,
        "comparable_folds": comparable,
        "ichimoku_wins_both": wins_both,
    }


def decision_text(agg, fold_info):
    base = agg["compr_d1w"]["test"]["12"]
    ichi = agg["ichimoku_d1w"]["test"]["12"]
    if base["n"] < MIN_USABLE_EVENTS or ichi["n"] < MIN_USABLE_EVENTS:
        return (
            "INCONCLUSIVO: campione sotto la soglia minima ~150 eventi su baseline "
            "o Ichimoku D1+W. Non adottare Ichimoku solo su questo test."
        )
    overall_win = (
        ichi["hit"] is not None
        and base["hit"] is not None
        and ichi["mean_pct"] is not None
        and base["mean_pct"] is not None
        and ichi["hit"] > base["hit"]
        and ichi["mean_pct"] > base["mean_pct"]
    )
    comparable = fold_info["comparable_folds"]
    wins = fold_info["ichimoku_wins_both"]
    coherent = comparable > 0 and wins > comparable / 2
    if overall_win and coherent:
        return (
            "CANDIDATO: Ichimoku D1+W batte compr_d1w su hit e ritorno medio "
            "con coerenza tra i fold. Da validare qualitativamente prima di adottare."
        )
    return (
        "NON ADOTTARE: Ichimoku D1+W non batte compr_d1w in modo coerente "
        "su hit e ritorno medio. Tenere la compressione D1+W attuale."
    )


def write_report(overall, folds, out_dir, source, counts, pair_events, train_bars, test_bars):
    os.makedirs(out_dir, exist_ok=True)
    agg = aggregate_returns(overall)
    fold_info = fold_summaries(folds)
    payload = {
        "source": source,
        "requested_counts": counts,
        "h1_window": H1_WINDOW,
        "d1_k": D1_K,
        "w_k": W_K,
        "horizons_h1": list(HORIZONS),
        "train_bars": train_bars,
        "test_bars": test_bars,
        "cohorts": list(COHORTS),
        "pair_events_seen_across_folds": pair_events,
        "agg": agg,
        "edges_vs_compr_d1w": {
            cohort: {
                sample: {str(h): _edge_vs_baseline(agg, cohort, sample, h) for h in HORIZONS}
                for sample in ("train", "test")
            }
            for cohort in COHORTS
        },
        "folds": fold_info,
        "decision": decision_text(agg, fold_info),
    }
    json_path = os.path.join(out_dir, "ichimoku_align.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)

    lines = [
        "# Backtest Ichimoku D1+W vs Compressione D1+W",
        "",
        f"Fonte: {source}. H1={counts['H1']}, D={counts['D']}, W={counts['W']}.",
        f"Walk-forward: train {train_bars} barre H1, test {test_bars} barre H1, fold: {len(folds)}.",
        "Evento H1: nuova rottura del range a 12 barre. Orizzonte primario: +12 H1.",
        "No lookahead: ogni H1 usa solo D/W con data strettamente precedente; nuvola Ichimoku da t-26.",
        "",
        "## Regola di decisione",
        "",
        "Adottare Ichimoku solo se `ichimoku_d1w` batte `compr_d1w` su TEST in hit e ritorno medio,",
        "con coerenza tra fold e almeno ~150 eventi utilizzabili. In caso contrario resta la compressione D1+W.",
        "",
        f"**Verdetto automatico:** {payload['decision']}",
        "",
        "## TEST out-of-sample",
        "",
        "| coorte | n +12 | hit +4 | hit +12 | hit +24 | hit +48 | medio% +12 | edge hit vs compr | edge medio% vs compr |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for cohort in COHORTS:
        row = agg[cohort]["test"]
        edge12 = payload["edges_vs_compr_d1w"][cohort]["test"]["12"]
        lines.append(
            f"| {cohort} | {row['12']['n']} | {row['4']['hit']} | {row['12']['hit']} | "
            f"{row['24']['hit']} | {row['48']['hit']} | {row['12']['mean_pct']} | "
            f"{edge12['hit']} | {edge12['mean_pct']} |"
        )

    lines.extend(
        [
            "",
            "## Fold: Ichimoku D1+W vs compr_d1w a +12 H1",
            "",
            "| fold | test | n compr | hit compr | medio% compr | n ichi | hit ichi | medio% ichi | edge hit | edge medio% | vince entrambi |",
            "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---|",
        ]
    )
    for row in fold_info["rows"]:
        lines.append(
            f"| {row['fold']} | {row['test'][0]}-{row['test'][1]} | "
            f"{row['compr_d1w_n']} | {row['compr_d1w_hit']} | {row['compr_d1w_mean_pct']} | "
            f"{row['ichimoku_d1w_n']} | {row['ichimoku_d1w_hit']} | {row['ichimoku_d1w_mean_pct']} | "
            f"{row['edge_hit']} | {row['edge_mean_pct']} | {row['beats_both']} |"
        )
    lines.extend(
        [
            "",
            f"Fold comparabili: {fold_info['comparable_folds']}; "
            f"Ichimoku vince hit+medio in {fold_info['ichimoku_wins_both']} fold.",
            "",
            "## Note",
            "",
            "- `compr_d1w` e' la baseline live attuale: direzione compressione D1 e W attiva.",
            "- `ichimoku_d1w` richiede prezzo fuori nuvola e Tenkan/Kijun concordi su D1 e W.",
            "- `kijun_*` e' solo variante esplorativa close-vs-Kijun, non parte della decisione primaria.",
            "- Il report e' research-only: non modifica scanner, dashboard o motore operativo.",
            "",
        ]
    )
    md_path = os.path.join(out_dir, "ichimoku_align.md")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    return md_path


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--oanda", action="store_true")
    ap.add_argument("--h1-count", type=int, default=20000)
    ap.add_argument("--d-count", type=int, default=1500)
    ap.add_argument("--w-count", type=int, default=800)
    ap.add_argument("--train-bars", type=int, default=TRAIN_BARS)
    ap.add_argument("--test-bars", type=int, default=TEST_BARS)
    ap.add_argument("--out", default="reports/ichimoku_align")
    args = ap.parse_args()
    if not args.oanda:
        ap.error("serve --oanda")
        return 2

    try:
        from fx_bias_radar.oanda_fetch import env_credentials

        token, env = env_credentials()
        h1_all = TF.fetch_all(token, env, "H1", args.h1_count)
        d1_all = TF.fetch_all(token, env, "D", args.d_count)
        w_all = TF.fetch_all(token, env, "W", args.w_count)
        overall = _empty_returns()
        folds = {}
        pair_events = 0
        for pair in P.PAIRS:
            pair_events += process_pair(
                h1_all.get(pair, []),
                d1_all.get(pair, []),
                w_all.get(pair, []),
                overall,
                folds,
                train_bars=args.train_bars,
                test_bars=args.test_bars,
            )
    except Exception as exc:  # noqa: BLE001
        print(f"ERRORE: {exc}")
        return 2

    path = write_report(
        overall,
        folds,
        args.out,
        "OANDA H1+D1+W",
        {"H1": args.h1_count, "D": args.d_count, "W": args.w_count},
        pair_events,
        args.train_bars,
        args.test_bars,
    )
    print(f"Ichimoku alignment -> {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
