"""Test per storico lungo compression+expansion."""
from __future__ import annotations

import importlib.util
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_S = importlib.util.spec_from_file_location(
    "compexp_long",
    os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "scripts",
        "backtest_compression_expansion_long.py",
    ),
)
CL = importlib.util.module_from_spec(_S)
sys.modules[_S.name] = CL
_S.loader.exec_module(CL)


class Raw:
    def __init__(self, t, close=1.0):
        self.instrument = "EUR_USD"
        self.time = datetime(2026, 1, 1, t, tzinfo=timezone.utc)
        self.complete = True
        self.open = close
        self.high = close + 0.1
        self.low = close - 0.1
        self.close = close
        self.volume = 1


def test_merge_unique_pages_dedupes_and_keeps_latest_count():
    rows = CL.merge_unique_pages([[Raw(0), Raw(1)], [Raw(1), Raw(2), Raw(3)]], 3)
    assert [r.time for r in rows] == [
        "2026-01-01T01:00:00+00:00",
        "2026-01-01T02:00:00+00:00",
        "2026-01-01T03:00:00+00:00",
    ]


def test_choose_profile_prefers_train_edge_with_min_sample():
    good = {
        "compression_expansion": {12: {"n": 60, "hit": 0.56}},
        "breakout_only": {12: {"n": 100, "hit": 0.50}},
    }
    better_but_small = {
        "compression_expansion": {12: {"n": 10, "hit": 0.90}},
        "breakout_only": {12: {"n": 100, "hit": 0.50}},
    }
    assert CL._choose_profile({"good": good, "small": better_but_small}) == "good"
