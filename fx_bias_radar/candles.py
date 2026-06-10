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


def align(candles_by_pair: Dict[str, List[Candle]]):
    """Align complete candles on the common UTC timestamp grid.

    Returns (times, closes_by_pair, AlignInfo). M1.1 requirement: report the
    latest complete H4 timestamp per pair and flag misalignment.
    """
    sets = []
    latest = {}
    for pair, cs in candles_by_pair.items():
        ts = [c.time for c in cs if c.complete]
        if not ts:
            raise ValueError(f"no complete candles for {pair}")
        sets.append(set(ts))
        latest[pair] = max(ts)
    common = set.intersection(*sets)
    times = sorted(common)
    if not times:
        raise ValueError("no common timestamps across pairs")
    closes = {}
    for pair, cs in candles_by_pair.items():
        by_t = {c.time: c.c for c in cs if c.complete}
        closes[pair] = [by_t[t] for t in times]
    aligned_latest = times[-1]
    misaligned = sorted(p for p, t in latest.items() if t != aligned_latest)
    return times, closes, AlignInfo(times=times, latest_by_pair=latest,
                                    misaligned_pairs=misaligned)


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
