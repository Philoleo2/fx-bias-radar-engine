"""Test rotture H1 allineate a daily E weekly (coorte premium)."""
from __future__ import annotations
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from fx_bias_radar.candles import Candle
from fx_bias_radar import compression as COMP
from fx_bias_radar import pairs as P


def _c(cl, h=None, l=None):
    return Candle(time="t", o=cl, h=h if h is not None else cl,
                  l=l if l is not None else cl, c=cl, volume=1, complete=True)


def _compress_then_long():
    base = [_c(1.0, 1.0, 0.99) for _ in range(139)]
    return base + [_c(1.05, 1.06, 1.0)]


def _h1_long():
    base = [_c(1.0, 1.0, 0.99) for _ in range(20)]
    return base + [_c(1.05, 1.06, 1.0)]


def test_d1w_aligned_long():
    d1 = {p: _compress_then_long() for p in P.PAIRS}
    w1 = {p: _compress_then_long() for p in P.PAIRS}
    h1 = {p: _h1_long() for p in P.PAIRS}
    out = COMP.daily_weekly_aligned_breakouts(h1, d1, w1)
    assert out and all(r["dir"] == "LONG" for r in out)


def test_d1w_excluded_when_weekly_missing():
    d1 = {p: _compress_then_long() for p in P.PAIRS}
    # weekly piatto -> nessuna direzione attiva -> escluso
    w1 = {p: [_c(1.0, 1.0, 0.99) for _ in range(140)] for p in P.PAIRS}
    h1 = {p: _h1_long() for p in P.PAIRS}
    assert COMP.daily_weekly_aligned_breakouts(h1, d1, w1) == []
