"""Offline shadow replay — STEP C of the rollout (SS50).

Simulates N consecutive hourly production runs against a frozen grid, going
through the real production path (persisted state -> JSON -> reload -> advance
-> idempotent append), and compares the resulting ledger with a single
full-history replay of the same engine.

They must coincide exactly. This is the check that live incremental operation
equals offline execution, without needing an OANDA connection.
"""
from __future__ import annotations

import argparse
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fx_bias_radar import pairs as P
from prewake import store
from prewake.engine import evaluate
from prewake.lifecycle import LifecycleState
from prewake.model import load_model
from prewake.state import PrewakeState

from prewake_seed import load_frozen_grid  # noqa: E402


def key(event, times=None):
    bar = event.get("bar_time_utc") or times[event["t"]]
    return (bar, event["pair"], event.get("direction_sign", event.get("direction")),
            event.get("event_type", event.get("type")))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mid", required=True)
    parser.add_argument("--ba", required=True)
    parser.add_argument("--bars", type=int, default=48, help="how many hourly runs to simulate")
    parser.add_argument("--window", type=int, default=400, help="bars fetched per simulated run")
    args = parser.parse_args()

    model = load_model()
    grid = load_frozen_grid(args.mid, args.ba)
    n = len(grid.times)
    cutover = n - args.bars
    print(f"grid {n} bars; seeding through {grid.times[cutover - 1]}, "
          f"then {args.bars} simulated hourly runs")

    # ---- reference: one full replay, emitting over the shadow window --------
    reference = evaluate(grid.times, grid.close, grid.high, grid.low,
                         lifecycle_state=LifecycleState.fresh(), emit_from=cutover, model=model)
    ref_keys = sorted(key(e, grid.times) for e in reference.events)
    print(f"full-replay events over the window : {len(ref_keys)}")

    # ---- shadow: seed, then advance one bar at a time through the real store -
    base = tempfile.mkdtemp(prefix="prewake-shadow-")
    try:
        seed = evaluate(grid.times[:cutover], grid.close[:cutover], grid.high[:cutover],
                        grid.low[:cutover], lifecycle_state=LifecycleState.fresh(),
                        emit_from=cutover, model=model)
        PrewakeState(model_version=model.model_version, model_fingerprint=model.research_fingerprint,
                     artifact_hash=model.artifact_hash, ewma_state=seed.features.ewma_state,
                     ewma_ready=seed.features.ewma_ready, lifecycle=seed.lifecycle_state,
                     last_bar_time_utc=grid.times[cutover - 1],
                     seeded_from_utc=grid.times[0], seeded_at_utc=store.now_utc()).save(base)

        duplicate_runs = 0
        for step in range(args.bars):
            end = cutover + step + 1
            start = max(0, end - args.window)
            # every bar is processed twice, to prove idempotency (SS24, case I)
            for repeat in range(2):
                state = PrewakeState.load(model, base)
                emit_from = next((i for i, t in enumerate(grid.times[start:end])
                                  if t > state.last_bar_time_utc), None)
                if emit_from is None:
                    duplicate_runs += 1
                    continue
                result = evaluate(grid.times[start:end], grid.close[start:end], grid.high[start:end],
                                  grid.low[start:end], lifecycle_state=state.lifecycle,
                                  ewma_state=state.ewma_state, ewma_ready=state.ewma_ready,
                                  emit_from=emit_from, model=model)
                records = [{
                    "event_id": store.event_id(model.model_version, e["pair"], e["bar_time_utc"],
                                              e["type"], e["direction"]),
                    "model_version": model.model_version, "pair": e["pair"],
                    "direction": "LONG" if e["direction"] > 0 else "SHORT",
                    "direction_sign": e["direction"], "event_type": e["type"],
                    "bar_time_utc": e["bar_time_utc"], "score": e["score"],
                    "threshold": model.threshold, "fx_bias_same": e["fx_bias_same"],
                    "same_bar_raw_breakout": e["same_bar_raw_breakout"],
                    "is_backfill": False, "is_prospective": True,
                } for e in result.events]
                store.append_events(records, base)
                state.lifecycle = result.lifecycle_state
                state.ewma_state = result.features.ewma_state
                state.ewma_ready = result.features.ewma_ready
                state.last_bar_time_utc = grid.times[end - 1]
                state.save(base)

        shadow = store.read_jsonl(store.EVENTS, base)
        shadow_keys = sorted(key(e) for e in shadow)
        print(f"shadow incremental events          : {len(shadow_keys)}")
        print(f"second passes correctly skipped    : {duplicate_runs}/{args.bars}")

        only_ref = sorted(set(ref_keys) - set(shadow_keys))
        only_shadow = sorted(set(shadow_keys) - set(ref_keys))
        print(f"  only_full_replay={len(only_ref)} only_shadow={len(only_shadow)} "
              f"duplicates={len(shadow_keys) - len(set(shadow_keys))}")
        for k in (only_ref + only_shadow)[:10]:
            print("   ", k)

        score_ok = True
        ref_by_key = {key(e, grid.times): e for e in reference.events}
        for row in shadow:
            ref = ref_by_key.get(key(row))
            if ref is None:
                continue
            if abs(ref["score"] - row["score"]) > 1e-12:
                score_ok = False
                print(f"    score drift on {key(row)}: {abs(ref['score'] - row['score']):.3e}")

        ok = (not only_ref and not only_shadow and score_ok
              and len(shadow_keys) == len(set(shadow_keys)))
        print("\nSHADOW RESULT:", "IDENTICAL TO OFFLINE REPLAY" if ok else "DIVERGENCE")
        return 0 if ok else 1
    finally:
        shutil.rmtree(base, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
