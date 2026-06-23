"""Test rotture H1 allineate alla direzione daily."""
from __future__ import annotations
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from fx_bias_radar.candles import Candle
from fx_bias_radar import compression as COMP
from fx_bias_radar import pairs as P


def _c(cl, h=None, l=None):
    return Candle(time="t", o=cl, h=h if h is not None else cl,
                  l=l if l is not None else cl, c=cl, volume=1, complete=True)


def _d1_long():
    base = [_c(1.0, 1.0, 0.99) for _ in range(139)]
    return base + [_c(1.05, 1.06, 1.0)]      # breakout LONG sull'ultima D1


def _h1_breakout_long():
    base = [_c(1.0, 1.0, 0.99) for _ in range(20)]
    return base + [_c(1.05, 1.06, 1.0)]      # rottura LONG sull'ultima H1


def test_aligned_long_detected():
    d1 = {p: _d1_long() for p in P.PAIRS}
    h1 = {p: _h1_breakout_long() for p in P.PAIRS}
    out = COMP.daily_aligned_breakouts(h1, d1)
    assert out and all(r["dir"] == "LONG" for r in out)
    assert {"pair", "dir", "base", "quote"} <= set(out[0])


def test_not_aligned_when_h1_opposite():
    d1 = {p: _d1_long() for p in P.PAIRS}        # daily attivo LONG
    # H1 rottura SHORT -> non allineata
    base = [_c(1.0, 1.01, 1.0) for _ in range(20)]
    h1 = {p: base + [_c(0.98, 0.99, 0.94)] for p in P.PAIRS}
    out = COMP.daily_aligned_breakouts(h1, d1)
    assert out == []
