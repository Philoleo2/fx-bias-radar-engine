"""One-time PAIR_PREWAKE_V1 warm-up seed (SS20).

The frozen EWMA is recursive and never reset, and NEW_WAKE means "first ever
for this (pair, direction) over the whole scored series". Both therefore depend
on where the scored history starts. Seeding replays the full frozen history
once, so every later hourly run is numerically identical to a replay from the
research origin.

Preferred source is the frozen Phase 1/2 dataset, which ends at the freeze
moment and gives exact continuity with the research. An OANDA seed is also
supported for a rebuild without the frozen files, at the cost of a shallower
origin (documented in the produced state file).

Historical events may be written to the ledger as BACKFILL. They are never
emailed (SS21) and are never PROSPECTIVE (SS22).
"""
from __future__ import annotations

import argparse
import gzip
import os
import pickle
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fx_bias_radar import pairs as P
from prewake import config, market, store
from prewake.engine import evaluate
from prewake.lifecycle import LifecycleState
from prewake.model import load_model
from prewake.primitives import parse_utc
from prewake.state import PrewakeState


def load_frozen_grid(mid_path: str, ba_path: str) -> market.Grid:
    with gzip.open(mid_path, "rb") as handle:
        mid = pickle.load(handle)["h1"]
    with gzip.open(ba_path, "rb") as handle:
        ba = pickle.load(handle)["pairs"]
    iso = lambda v: parse_utc(v).isoformat(timespec="seconds")
    common_mid = set.intersection(*[{iso(r.time) for r in mid[p]} for p in P.PAIRS])
    common_ba = set.intersection(*[{iso(r[0]) for r in ba[p]} for p in P.PAIRS])
    times = sorted(common_mid & common_ba)
    n, k = len(times), len(P.PAIRS)
    o, h, low, c = (np.empty((n, k), dtype=np.float64) for _ in range(4))
    for j, pair in enumerate(P.PAIRS):
        rows = {iso(r.time): r for r in mid[pair] if r.complete}
        for i, stamp in enumerate(times):
            row = rows[stamp]
            o[i, j], h[i, j], low[i, j], c[i, j] = row.o, row.h, row.l, row.c
    return market.Grid(times=times, close=c, high=h, low=low, open=o)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--from-frozen", nargs=2, metavar=("MID", "BA"),
                        help="frozen research MID and BID/ASK pickles (preferred)")
    parser.add_argument("--oanda", action="store_true")
    parser.add_argument("--count", type=int, default=5000)
    parser.add_argument("--backfill-from", default=None,
                        help="ISO date; store events at/after this bar date as BACKFILL (no email)")
    parser.add_argument("--base", default=store.BASE_DIR)
    parser.add_argument("--force", action="store_true", help="overwrite an existing seeded state")
    args = parser.parse_args()

    config.assert_no_model_overrides()
    model = load_model()
    existing = PrewakeState.load(model, args.base)
    if existing.is_seeded and not args.force:
        print(f"state already seeded up to {existing.last_bar_time_utc}; use --force to redo")
        return 1

    if args.from_frozen:
        grid = load_frozen_grid(*args.from_frozen)
        origin = "frozen Phase 1/2 dataset"
    elif args.oanda:
        from fx_bias_radar.oanda_fetch import env_credentials
        token, env = env_credentials()
        grid = market.fetch_grid(token, env=env, count=args.count)
        origin = f"OANDA H1 MID, {args.count} bars"
    else:
        parser.error("choose --from-frozen MID BA or --oanda")

    print(f"seed source: {origin}")
    print(f"grid: {len(grid.times)} H1 x {len(P.PAIRS)} pairs, {grid.times[0]} -> {grid.times[-1]}")
    if len(grid.times) < model.minimum_bars:
        print(f"ERROR: need at least {model.minimum_bars} bars")
        return 1

    emit_from = len(grid.times)
    if args.backfill_from:
        emit_from = next((i for i, t in enumerate(grid.times) if t[:10] >= args.backfill_from),
                         len(grid.times))

    result = evaluate(grid.times, grid.close, grid.high, grid.low,
                      lifecycle_state=LifecycleState.fresh(), emit_from=emit_from, model=model)

    records = []
    for event in result.events:
        records.append({
            "event_id": store.event_id(model.model_version, event["pair"], event["bar_time_utc"],
                                       event["type"], event["direction"]),
            "model_version": model.model_version,
            "model_fingerprint": model.research_fingerprint,
            "artifact_hash": model.artifact_hash,
            "pair": event["pair"],
            "direction": "LONG" if event["direction"] > 0 else "SHORT",
            "direction_sign": event["direction"],
            "event_type": event["type"],
            "bar_time_utc": event["bar_time_utc"],
            "generated_at_utc": store.now_utc(),
            "score": event["score"],
            "threshold": model.threshold,
            "state_before": "ARMED",
            "state_after": "ACTIVE",
            "fx_bias_same": event["fx_bias_same"],
            "same_bar_raw_breakout": event["same_bar_raw_breakout"],
            "is_backfill": True,
            "is_prospective": False,
            "features": event["features"],
            "direction_source_value": event["direction_source_value"],
            "ewma4_gap": event["ewma4_gap"],
            "ols_lopo_gap": event["ols_lopo_gap"],
            "gap_robust_z": event["gap_robust_z"],
        })
    stored = store.append_events(records, args.base)
    print(f"backfilled events stored: {len(stored)} (no email will ever be sent for these)")

    state = PrewakeState(
        model_version=model.model_version,
        model_fingerprint=model.research_fingerprint,
        artifact_hash=model.artifact_hash,
        ewma_state=result.features.ewma_state,
        ewma_ready=result.features.ewma_ready,
        lifecycle=result.lifecycle_state,
        last_bar_time_utc=grid.times[-1],
        seeded_from_utc=grid.times[0],
        seeded_at_utc=store.now_utc(),
        prospective_start_at=existing.prospective_start_at,
    )
    state.save(args.base)
    fired = sum(1 for v in state.lifecycle.seen.values() if v)
    print(f"state written: origin {grid.times[0]}, last bar {grid.times[-1]}")
    print(f"lifecycle: {fired}/{len(state.lifecycle.seen)} (pair,direction) slots have already fired "
          f"-> their next live start is REAWAKENING, as in the frozen research")
    return 0


if __name__ == "__main__":
    sys.exit(main())
