"""Test della mappa attiva D1 (finestra dopo un breakout da compressione)."""
from __future__ import annotations
import os, sys, importlib.util
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
from fx_bias_radar.candles import Candle
_S = importlib.util.spec_from_file_location("h1d1",
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                 "scripts", "backtest_h1_d1_align.py"))
HD = importlib.util.module_from_spec(_S); _S.loader.exec_module(HD)


def _c(cl, h=None, l=None):
    return Candle(time="t", o=cl, h=h if h is not None else cl,
                  l=l if l is not None else cl, c=cl, volume=1, complete=True)


def test_d1_active_window_after_breakout():
    # 139 candele compresse + 1 rottura long -> attiva LONG per K barre dopo
    base = [_c(1.0, 1.0, 0.99) for _ in range(139)]
    d1 = base + [_c(1.05, 1.06, 1.0)]      # chiude sopra il range -> breakout LONG
    active = HD.d1_active_map(d1, k=10)
    assert active[-1] == "LONG"            # attivo sulla barra del breakout
    # se aggiungo barre piatte dopo, resta attivo per k poi torna None
    d1b = d1 + [_c(1.05, 1.05, 1.04) for _ in range(15)]
    active2 = HD.d1_active_map(d1b, k=10)
    assert active2[139 + 10] == "LONG" and active2[139 + 12] is None
