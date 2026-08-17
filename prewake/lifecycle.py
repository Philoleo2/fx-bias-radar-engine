"""Frozen PAIR_PREWAKE_V1 lifecycle.

Two implementations that must always agree:

* ``batch_lifecycle_events`` — a byte-faithful port of ``lifecycle_events`` in
  the frozen ``research/fx_pressure_evaluation.py``. Used by the parity test.
* ``advance`` — the incremental form used in production, carrying state across
  hourly runs so a live run is identical to a full replay from the origin.

Semantics that are easy to get wrong and must not be "fixed":

* ``NEW_WAKE`` is the first lifecycle start EVER observed for a given
  (pair, direction) over the whole scored series — not the first after a reset.
  Every later start is ``REAWAKENING``. The flag is consumed even when the
  start falls outside the emission window.
* A reset is: direction change, OR four consecutive H1 with score below
  0.70 * threshold, OR a non-finite score.
* Reset and "above threshold" can never coincide on the same bar, because
  threshold > 0.70 * threshold.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from fx_bias_radar import pairs as P

NEW_WAKE = "NEW_WAKE"
REAWAKENING = "REAWAKENING"
SIGNS = (-1, 1)


def batch_lifecycle_events(score: np.ndarray, direction: np.ndarray, threshold: float,
                           allowed: np.ndarray, breakout: np.ndarray,
                           reset_ratio: float = 0.70, reset_bars: int = 4) -> list[dict]:
    """Vectorised direction-specific lifecycle with four-bar reset (frozen)."""
    events: list[dict] = []
    reset_threshold = threshold * reset_ratio
    for pair_index, pair in enumerate(P.PAIRS):
        s = score[:, pair_index]
        d = direction[:, pair_index]
        for sign in SIGNS:
            finite = np.isfinite(s)
            low = finite & (s < reset_threshold) & (d == sign)
            low_run = np.zeros(len(s), dtype=bool)
            if reset_bars == 1:
                low_run = low
            elif len(s) >= reset_bars:
                slices = [low[offset:len(s) - reset_bars + offset + 1] for offset in range(reset_bars)]
                low_run[reset_bars - 1:] = np.logical_and.reduce(slices)
            reset = (d != sign) | low_run | ~finite
            reset_indices = np.flatnonzero(reset)
            high_indices = np.flatnonzero(finite & (d == sign) & (s >= threshold))
            if not len(high_indices):
                continue
            groups = np.searchsorted(reset_indices, high_indices, side="right")
            first = np.r_[True, groups[1:] != groups[:-1]]
            starts = high_indices[first]
            seen = False
            for t in starts:
                event_type = REAWAKENING if seen else NEW_WAKE
                seen = True
                if not allowed[t]:
                    continue
                events.append({
                    "t": int(t),
                    "pair_index": pair_index,
                    "pair": pair,
                    "direction": int(sign),
                    "type": event_type,
                    "score": float(s[t]),
                    "late_same_breakout": bool(breakout[t, pair_index] == sign),
                })
    events.sort(key=lambda row: (row["t"], row["pair_index"], row["direction"]))
    return events


@dataclass
class LifecycleState:
    """Per (pair, direction) lifecycle state, persisted between runs."""
    armed: dict = field(default_factory=dict)
    seen: dict = field(default_factory=dict)
    low_streak: dict = field(default_factory=dict)

    @staticmethod
    def _key(pair: str, sign: int) -> str:
        return f"{pair}:{'LONG' if sign > 0 else 'SHORT'}"

    @classmethod
    def fresh(cls) -> "LifecycleState":
        state = cls()
        for pair in P.PAIRS:
            for sign in SIGNS:
                key = cls._key(pair, sign)
                state.armed[key] = True
                state.seen[key] = False
                state.low_streak[key] = 0
        return state

    @classmethod
    def from_dict(cls, payload: dict) -> "LifecycleState":
        state = cls.fresh()
        for key, value in (payload or {}).items():
            if key in state.armed:
                state.armed[key] = bool(value["armed"])
                state.seen[key] = bool(value["seen"])
                state.low_streak[key] = int(value["low_streak"])
        return state

    def to_dict(self) -> dict:
        return {key: {"armed": self.armed[key], "seen": self.seen[key], "low_streak": self.low_streak[key]}
                for key in sorted(self.armed)}


def advance(state: LifecycleState, score: np.ndarray, direction: np.ndarray, threshold: float,
            breakout: np.ndarray, emit_from: int = 0,
            reset_ratio: float = 0.70, reset_bars: int = 4) -> list[dict]:
    """Advance the lifecycle bar by bar, emitting starts at index >= emit_from.

    State is mutated in place. Bars before ``emit_from`` still update state (so
    seeding a warm-up consumes NEW_WAKE exactly as the frozen research does)
    but produce no events.
    """
    reset_threshold = threshold * reset_ratio
    events: list[dict] = []
    n = len(score)
    for t in range(n):
        for pair_index, pair in enumerate(P.PAIRS):
            s = float(score[t, pair_index])
            d = int(direction[t, pair_index])
            finite = np.isfinite(s)
            for sign in SIGNS:
                key = LifecycleState._key(pair, sign)
                low = bool(finite and (s < reset_threshold) and (d == sign))
                state.low_streak[key] = state.low_streak[key] + 1 if low else 0
                low_run = state.low_streak[key] >= reset_bars
                if (d != sign) or low_run or not finite:
                    state.armed[key] = True
                    continue
                if s >= threshold and state.armed[key]:
                    event_type = REAWAKENING if state.seen[key] else NEW_WAKE
                    state.seen[key] = True
                    state.armed[key] = False
                    if t >= emit_from:
                        events.append({
                            "t": int(t),
                            "pair_index": pair_index,
                            "pair": pair,
                            "direction": int(sign),
                            "type": event_type,
                            "score": s,
                            "late_same_breakout": bool(breakout[t, pair_index] == sign),
                        })
    events.sort(key=lambda row: (row["t"], row["pair_index"], row["direction"]))
    return events
