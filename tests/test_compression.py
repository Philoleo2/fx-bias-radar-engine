"""Test rilevatore rottura da compressione (package)."""
from __future__ import annotations
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from fx_bias_radar.candles import Candle
from fx_bias_radar import compression as COMP


def _c(o, h, l, cl):
    return Candle(time="t", o=o, h=h, l=l, c=cl, volume=1, complete=True)


def _compressed_series(n=140):
    # n candele in range strettissimo e stabile, poi una rottura long
    base = [_c(0.995, 1.0, 0.99, 0.995) for _ in range(n - 1)]
    return base + [_c(1.0, 1.06, 1.0, 1.05)]   # chiude sopra il max (1.0)


def test_compression_breakout_long():
    cs = _compressed_series()
    t = len(cs) - 1
    assert COMP.compression_breakout(cs, t, window=12, percentile=0.20) == "LONG"


def test_no_breakout_inside_range():
    cs = [_c(0.995, 1.0, 0.99, 0.995) for _ in range(140)]   # mai fuori dal range
    t = len(cs) - 1
    assert COMP.compression_breakout(cs, t, window=12, percentile=0.20) is None


def test_compressioni_from_candles_shape():
    cs = _compressed_series()
    # tutte le coppie con la stessa serie -> tutte rompono long
    from fx_bias_radar import pairs as P
    h1 = {p: cs for p in P.PAIRS}
    out = COMP.compressioni_from_candles(h1)
    assert out and all(r["dir"] == "LONG" for r in out)
    assert {"pair", "dir", "base", "quote"} <= set(out[0])
