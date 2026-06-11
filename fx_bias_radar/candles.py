"""Candle model, UTC alignment across the 28-pair universe, fixtures I/O."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, asdict
from typing import Dict, List


@dataclass
class Candle:
    time: str  # ISO-8601 UTC of bar open, e.g. "2026-06-10T09:00:00+00:00"
    o: float
    h: float
    l: float
    c: float
    volume: int = 0
    complete: bool = True


@dataclass
class AlignInfo:
    times: List[str]
    latest_by_pair: Dict[str, str]
    misaligned_pairs: List[str]  # pairs whose own latest != global aligned latest
    latest_complete_by_pair: Dict[str, str] | None = None
    latest_aligned_is_complete: bool = True


def align(candles_by_pair: Dict[str, List[Candle]], *, include_incomplete: bool = False):
    """Align complete candles on the common UTC timestamp grid.

    Returns (times, closes_by_pair, AlignInfo). M1.1 requirement: report the
    latest complete H4 timestamp per pair and flag misalignment.
    """
    sets = []
    latest = {}
    latest_complete = {}
    for pair, cs in candles_by_pair.items():
        complete_ts = [c.time for c in cs if c.complete]
        if not complete_ts:
            raise ValueError(f"no complete candles for {pair}")
        latest_complete[pair] = max(complete_ts)
        ts = [c.time for c in cs if include_incomplete or c.complete]
        if not ts:
            raise ValueError(f"no candles for {pair}")
        sets.append(set(ts))
        latest[pair] = max(ts)
    common = set.intersection(*sets)
    times = sorted(common)
    if not times:
        raise ValueError("no common timestamps across pairs")
    closes = {}
    complete_by_pair = {}
    for pair, cs in candles_by_pair.items():
        by_t = {c.time: c.c for c in cs if include_incomplete or c.complete}
        complete_by_pair[pair] = {c.time: c.complete for c in cs}
        closes[pair] = [by_t[t] for t in times]
    aligned_latest = times[-1]
    misaligned = sorted(p for p, t in latest.items() if t != aligned_latest)
    aligned_complete = all(complete_by_pair[p].get(aligned_latest, False) for p in candles_by_pair)
    return times, closes, AlignInfo(times=times, latest_by_pair=latest,
                                    misaligned_pairs=misaligned,
                                    latest_complete_by_pair=latest_complete,
                                    latest_aligned_is_complete=aligned_complete)


def save_fixture_dir(path: str, candles_by_pair: Dict[str, List[Candle]]) -> None:
    os.makedirs(path, exist_ok=True)
    for pair, cs in candles_by_pair.items():
        with open(os.path.join(path, f"{pair}.json"), "w", encoding="utf-8") as f:
            json.dump([asdict(c) for c in cs], f)


def load_fixture_dir(path: str) -> Dict[str, List[Candle]]:
    out: Dict[str, List[Candle]] = {}
    for name in sorted(os.listdir(path)):
        if not name.endswith(".json"):
            continue
        pair = name[:-5]
        with open(os.path.join(path, name), "r", encoding="utf-8") as f:
            out[pair] = [Candle(**row) for row in json.load(f)]
    return out
