"""Test outcome in R del backtest compressione (win/loss su stop e target)."""
from __future__ import annotations
import os, sys, importlib.util
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
import backtest_compression_expansion as CE
_S = importlib.util.spec_from_file_location("comprr",
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                 "scripts", "backtest_compression_rr.py"))
RR = importlib.util.module_from_spec(_S); _S.loader.exec_module(RR)
Row = CE.Row


def test_trade_outcome_target_and_stop():
    base = [Row(0.95, 1.0, 0.9, 0.95)] * 3   # range hi=1.0 lo=0.9
    # LONG vincente: entry 1.0, risk 0.1, target 2R = 1.2; barra dopo high 1.25
    win = base + [Row(1.0, 1.0, 1.0, 1.0), Row(1.1, 1.25, 1.05, 1.2), Row(1.2, 1.2, 1.2, 1.2)]
    assert RR.trade_outcome(win, 3, "LONG", 3, 2.0) == 2.0
    # LONG perdente: barra dopo low 0.85 <= stop 0.9
    loss = base + [Row(1.0, 1.0, 1.0, 1.0), Row(0.95, 0.98, 0.85, 0.88), Row(0.9, 0.9, 0.9, 0.9)]
    assert RR.trade_outcome(loss, 3, "LONG", 3, 2.0) == -1.0
