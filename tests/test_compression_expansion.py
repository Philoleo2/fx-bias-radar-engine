"""Test per backtest compressione + espansione."""
from __future__ import annotations

import importlib.util
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_S = importlib.util.spec_from_file_location(
    "compexp",
    os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "scripts",
        "backtest_compression_expansion.py",
    ),
)
CE = importlib.util.module_from_spec(_S)
sys.modules[_S.name] = CE
_S.loader.exec_module(CE)


def _row(price, pad=0.1):
    return CE.Row(price, price + pad, price - pad, price)


def test_new_breakout_only_first_close_outside_range():
    rows = [_row(1.0) for _ in range(12)] + [_row(1.5), _row(1.6)]
    assert CE.is_new_breakout(rows, 12, 12) == "LONG"
    assert CE.is_new_breakout(rows, 13, 12) is None


def test_compression_uses_percentile_of_prior_ranges():
    wide = [CE.Row(1.0, 2.0, 0.0, 1.0) for _ in range(20)]
    narrow = [CE.Row(1.0, 1.02, 0.98, 1.0) for _ in range(4)]
    rows = wide + narrow
    profile = CE.Profile(window=4, percentile=0.30)
    assert CE.is_compressed(rows, 24, profile, rank_window=10)


def test_compression_expansion_requires_compression_before_breakout():
    wide = [CE.Row(1.0, 2.0, 0.0, 1.0) for _ in range(130)]
    narrow = [CE.Row(1.0, 1.02, 0.98, 1.0) for _ in range(4)]
    breakout = [CE.Row(1.1, 1.12, 1.08, 1.1)]
    rows = wide + narrow + breakout
    profile = CE.Profile(window=4, percentile=0.30)
    assert CE.compression_expansion_dir(rows, 134, profile) == "LONG"
