"""Rottura da COMPRESSIONE (squeeze) - segnale di SELEZIONE per lo scanner H1.

Profilo calibrato sul backtest walk-forward: window=12, percentile=0.20 (w12_p20).
Compressione = range delle ultime N barre <= percentile storico (120 finestre
precedenti). Rottura = nuova chiusura fuori dal range. Puro prezzo (OHLC H1):
e' un "dove guardare", nessun edge meccanico, la decisione e' sulle linee manuali.
NON tocca il motore H4.
"""

from __future__ import annotations

from typing import List, Optional

RANK_WINDOW = 120
DEFAULT_WINDOW = 12
DEFAULT_PERCENTILE = 0.20


def _quantile(values, q):
    if not values:
        return None
    xs = sorted(values)
    pos = (len(xs) - 1) * q
    lo = int(pos)
    hi = min(lo + 1, len(xs) - 1)
    frac = pos - lo
    return xs[lo] * (1.0 - frac) + xs[hi] * frac


def window_bounds(candles, end, window):
    """(range, high, low) di candles[end-window:end] usando high/low."""
    if end < window:
        return None
    chunk = candles[end - window:end]
    hi = max(c.h for c in chunk)
    lo = min(c.l for c in chunk)
    return hi - lo, hi, lo


def is_compressed(candles, t, window=DEFAULT_WINDOW, percentile=DEFAULT_PERCENTILE,
                  rank_window=RANK_WINDOW):
    cur = window_bounds(candles, t, window)
    if cur is None or t < window + rank_window:
        return False
    history = []
    for end in range(t - rank_window, t):
        b = window_bounds(candles, end, window)
        if b is not None:
            history.append(b[0])
    threshold = _quantile(history, percentile)
    return threshold is not None and cur[0] <= threshold


def breakout_dir(candles, t, window):
    b = window_bounds(candles, t, window)
    if b is None:
        return None
    _, hi, lo = b
    c = candles[t].c
    if c > hi:
        return "LONG"
    if c < lo:
        return "SHORT"
    return None


def is_new_breakout(candles, t, window):
    d = breakout_dir(candles, t, window)
    if d is None:
        return None
    prev = breakout_dir(candles, t - 1, window) if t > 0 else None
    return d if d != prev else None


def compression_breakout(candles, t, window=DEFAULT_WINDOW,
                         percentile=DEFAULT_PERCENTILE) -> Optional[str]:
    """Rottura FRESCA da compressione alla barra t: 'LONG'/'SHORT'/None."""
    d = is_new_breakout(candles, t, window)
    if d is None:
        return None
    return d if is_compressed(candles, t, window, percentile) else None


def compressioni_from_candles(h1_by_pair, window=DEFAULT_WINDOW,
                              percentile=DEFAULT_PERCENTILE) -> List[dict]:
    """Per ogni coppia: rottura da compressione sull'ultima barra H1 chiusa."""
    from . import pairs as P
    out: List[dict] = []
    for pair in P.PAIRS:
        cs = h1_by_pair.get(pair)
        if not cs or len(cs) < window + RANK_WINDOW + 1:
            continue
        t = len(cs) - 1
        d = compression_breakout(cs, t, window, percentile)
        if d:
            base, quote = P.base_quote(pair)
            out.append({"pair": pair, "dir": d, "base": base, "quote": quote})
    return out
