"""Prospective outcome tracking (SS38-SS40) and PREWAKE -> FX Bias linking (SS36, SS37).

This is a research job, deliberately separate from the live engine. Outcomes
never feed back into scoring, the lifecycle, or the model (SS38). They are
computed only once the future bars have actually elapsed — no lookahead is ever
written into the original event (SS39).

The definitions below are ports of the frozen research outcome functions in
research/pair_prewake_audit.py at the Phase 2 parent.
"""
from __future__ import annotations

import math

import numpy as np

HORIZONS = (1, 2, 3, 4, 6, 8, 12, 24)
BREAKOUT_HORIZON = 12


def time_to_breakout(breakout: np.ndarray, t: int, pair_index: int, direction: int,
                     horizon: int = BREAKOUT_HORIZON, include_same_bar: bool = True) -> int | None:
    """First same-direction RAW FRESH BREAKOUT delay (SS39).

    Delay zero means the breakout was on the signal bar itself. It is a
    diagnostic only and is never a pre-wake success.
    """
    start = 0 if include_same_bar else 1
    for lead in range(start, horizon + 1):
        index = t + lead
        if index >= len(breakout):
            return None
        if int(breakout[index, pair_index]) == direction:
            return lead
    return None


def future_directional_return(open_, close, t: int, pair_index: int,
                              direction: int, horizon: int) -> float:
    """Frozen-study outcome: Open[t+1] to Close[t+horizon]."""
    entry = t + 1
    exit_index = t + horizon
    if entry >= len(close) or exit_index >= len(close):
        return math.nan
    return float(direction * math.log(close[exit_index, pair_index] / open_[entry, pair_index]))


def future_mfe_mae(open_, high, low, t: int, pair_index: int,
                   direction: int, horizon: int) -> tuple[float, float]:
    entry_index = t + 1
    if entry_index >= len(high) or t + horizon >= len(high):
        return math.nan, math.nan
    entry = float(open_[entry_index, pair_index])
    highs = high[entry_index:t + horizon + 1, pair_index]
    lows = low[entry_index:t + horizon + 1, pair_index]
    if direction > 0:
        return float(np.max(highs) / entry - 1.0), float(np.min(lows) / entry - 1.0)
    return float(entry / np.min(lows) - 1.0), float(entry / np.max(highs) - 1.0)


def _clean(value):
    return None if value is None or (isinstance(value, float) and not math.isfinite(value)) else value


def compute(grid, breakout: np.ndarray, t: int, pair_index: int, direction: int) -> dict:
    """All matured outcomes for one event. Missing horizons stay None."""
    delay_with_same = time_to_breakout(breakout, t, pair_index, direction, BREAKOUT_HORIZON, True)
    delay_prewake = time_to_breakout(breakout, t, pair_index, direction, BREAKOUT_HORIZON, False)
    same_bar = delay_with_same == 0

    breakout_time = None
    if delay_prewake is not None and t + delay_prewake < len(grid.times):
        breakout_time = grid.times[t + delay_prewake]

    horizons = {}
    for horizon in HORIZONS:
        if t + horizon >= len(grid.times):
            continue
        mfe, mae = future_mfe_mae(grid.open, grid.high, grid.low, t, pair_index, direction, horizon)
        horizons[str(horizon)] = {
            "directional_return": _clean(
                future_directional_return(grid.open, grid.close, t, pair_index, direction, horizon)),
            "mfe": _clean(mfe),
            "mae": _clean(mae),
            "raw_breakout_by_horizon": bool(
                delay_prewake is not None and 1 <= delay_prewake <= horizon),
        }

    return {
        "fresh_breakout_same_direction": bool(delay_prewake is not None and 1 <= delay_prewake <= BREAKOUT_HORIZON),
        "breakout_time": breakout_time,
        "time_to_breakout": delay_prewake,
        "same_bar_raw_breakout": same_bar,
        "primary_hit_plus1_plus12": bool(
            not same_bar and delay_prewake is not None and 1 <= delay_prewake <= BREAKOUT_HORIZON),
        "horizons": horizons,
        "matured_through_h1": max((h for h in HORIZONS if t + h < len(grid.times)), default=0),
    }


def link_fx_bias(event_bar_time: str, fx_bias_events: list[dict]) -> dict | None:
    """SS36/SS37: first later FX Bias call on the same pair and direction.

    ``fx_bias_events`` are the production FX Bias calls, each with
    ``bar_time_utc``, ``pair`` and ``direction``. The link is recorded, never
    used to modify the PREWAKE event retroactively.
    """
    later = [e for e in fx_bias_events if e["bar_time_utc"] > event_bar_time]
    if not later:
        return None
    first = min(later, key=lambda e: e["bar_time_utc"])
    from .primitives import parse_utc
    lead = (parse_utc(first["bar_time_utc"]) - parse_utc(event_bar_time)).total_seconds() / 3600.0
    return {
        "fx_bias_event_id": first.get("event_id"),
        "fx_bias_time": first["bar_time_utc"],
        "lead_hours": lead,
        "time_to_fx_bias": lead,
    }
