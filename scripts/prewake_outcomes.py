"""Prospective outcome tracking job (SS38-SS40). Separate from the live engine.

Outcomes are appended as their own records; the event ledger stays immutable.
Nothing computed here can change the model, the threshold or any past event.
"""
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fx_bias_radar import pairs as P
from prewake import config, market, outcomes, store
from prewake.model import load_model
from prewake.primitives import fresh_breakouts


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--oanda", action="store_true")
    parser.add_argument("--count", type=int, default=400)
    parser.add_argument("--base", default=store.BASE_DIR)
    args = parser.parse_args()

    config.assert_no_model_overrides()
    model = load_model()
    events = store.read_jsonl(store.EVENTS, args.base)
    if not events:
        print("no PREWAKE events yet")
        return 0

    if not args.oanda:
        parser.error("run with --oanda")
    from fx_bias_radar.oanda_fetch import env_credentials
    token, env = env_credentials()
    grid = market.fetch_grid(token, env=env, count=args.count)
    breakout = fresh_breakouts(grid.close, grid.high, grid.low, 12)
    index = {t: i for i, t in enumerate(grid.times)}

    done = store.latest_by_event(store.OUTCOMES, args.base)
    records = []
    for event in events:
        t = index.get(event["bar_time_utc"])
        if t is None:
            continue                                   # outside the fetched window
        pair_index = P.PAIRS.index(event["pair"])
        computed = outcomes.compute(grid, breakout, t, pair_index, int(event["direction_sign"]))
        previous = done.get(event["event_id"], {}).get("outcomes") or {}
        if previous.get("matured_through_h1", -1) >= computed["matured_through_h1"]:
            continue                                   # nothing new matured
        records.append({
            "event_id": event["event_id"],
            "model_version": event["model_version"],
            "bar_time_utc": event["bar_time_utc"],
            "pair": event["pair"],
            "outcomes": computed,
            "recorded_at": store.now_utc(),
        })
    store.append_jsonl(store.OUTCOMES, records, args.base)
    print(f"outcome records appended: {len(records)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
