"""Common 28-pair H1 grid for PREWAKE, from the existing FX Bias OANDA pipeline.

PREWAKE does NOT create a second downloader (SS16). It reuses
fx_bias_radar.strength_h1.fetch_all_h1, which already requests
granularity=H1, price=M (MID) and complete candles only (SS17).

Alignment policy is the research policy (SS19): the grid is the INTERSECTION of
bar-open timestamps across all 28 pairs. If the newest closed H1 is not present
for every pair the run records SKIPPED_INCOMPLETE_INPUT and the next hourly job
retries; no signal is ever produced from partial data.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass

import numpy as np

from fx_bias_radar import pairs as P

from .primitives import parse_utc


class IncompleteInput(RuntimeError):
    """Raised when the common grid cannot cover the requested bar."""


@dataclass(frozen=True)
class Grid:
    times: list[str]
    close: np.ndarray
    high: np.ndarray
    low: np.ndarray
    open: np.ndarray

    def fingerprint(self) -> str:
        digest = hashlib.sha256()
        digest.update("|".join(self.times).encode("utf-8"))
        for arr in (self.open, self.high, self.low, self.close):
            digest.update(np.ascontiguousarray(arr, dtype=np.float64).tobytes())
        return "sha256:" + digest.hexdigest()


def _iso(value) -> str:
    return parse_utc(value).isoformat(timespec="seconds")


def build_grid(candles_by_pair: dict) -> Grid:
    """Intersect complete H1 candles across all 28 pairs into an aligned grid."""
    missing = [pair for pair in P.PAIRS if not candles_by_pair.get(pair)]
    if missing:
        raise IncompleteInput(f"SKIPPED_INCOMPLETE_INPUT: no candles for {', '.join(sorted(missing))}")

    per_pair = {}
    for pair in P.PAIRS:
        rows = {}
        for candle in candles_by_pair[pair]:
            complete = getattr(candle, "complete", True)
            if not complete:
                continue
            rows[_iso(getattr(candle, "time"))] = candle
        per_pair[pair] = rows

    common = set.intersection(*[set(rows) for rows in per_pair.values()])
    if not common:
        raise IncompleteInput("SKIPPED_INCOMPLETE_INPUT: no common H1 timestamp across the 28 pairs")
    times = sorted(common)

    n, k = len(times), len(P.PAIRS)
    o = np.empty((n, k), dtype=np.float64)
    h = np.empty_like(o)
    low = np.empty_like(o)
    c = np.empty_like(o)
    for j, pair in enumerate(P.PAIRS):
        rows = per_pair[pair]
        for i, stamp in enumerate(times):
            candle = rows[stamp]
            o[i, j] = float(candle.o)
            h[i, j] = float(candle.h)
            low[i, j] = float(candle.l)
            c[i, j] = float(candle.c)
    if not np.all(np.isfinite(c)) or not np.all(np.isfinite(h)) or not np.all(np.isfinite(low)):
        raise IncompleteInput("SKIPPED_INCOMPLETE_INPUT: non-finite OHLC in the common grid")
    return Grid(times=times, close=c, high=h, low=low, open=o)


def fetch_grid(token: str, env: str = "practice", count: int = 400) -> Grid:
    from fx_bias_radar import strength_h1 as SH
    return build_grid(SH.fetch_all_h1(token, env=env, count=count))
