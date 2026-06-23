"""Test breakout 9 candele del Test #4."""
from __future__ import annotations
import os, sys, importlib.util
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_S = importlib.util.spec_from_file_location("rotbreak",
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                 "scripts", "backtest_rotation_breakout.py"))
RB = importlib.util.module_from_spec(_S); _S.loader.exec_module(RB)


def test_breakout_up_down_inside():
    base = [1.0] * 9
    assert RB.is_breakout(base + [1.5], 9, "LONG")      # close sopra max 9
    assert not RB.is_breakout(base + [1.5], 9, "SHORT")
    assert RB.is_breakout(base + [0.5], 9, "SHORT")     # close sotto min 9
    assert not RB.is_breakout([1.0, 1.1, 1.2] * 3 + [1.05], 9, "LONG")  # dentro range


def test_breakout_needs_lookback():
    assert not RB.is_breakout([1.0, 2.0], 1, "LONG")    # storia insufficiente
