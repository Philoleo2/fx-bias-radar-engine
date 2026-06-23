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


def active_daily_dir(d1, k=10, window=DEFAULT_WINDOW, percentile=DEFAULT_PERCENTILE):
    """Direzione 'attiva' all'ultima barra D1: da un breakout da compressione D1
    avvenuto entro k barre. None se nessun breakout recente."""
    last_dir, last_bar = None, -10 ** 9
    for i in range(len(d1)):
        d = compression_breakout(d1, i, window, percentile)
        if d is not None:
            last_dir, last_bar = d, i
    if last_dir is not None and (len(d1) - 1 - last_bar) <= k:
        return last_dir
    return None


def daily_aligned_breakouts(h1_by_pair, d1_by_pair, k=10, h1_window=DEFAULT_WINDOW):
    """Rotture H1 (window 12) sull'ultima barra, ALLINEATE alla direzione daily attiva.
    Segnale validato dal backtest (hit ~51%, ritorno medio positivo)."""
    from . import pairs as P
    out = []
    for pair in P.PAIRS:
        h1 = h1_by_pair.get(pair)
        d1 = d1_by_pair.get(pair)
        if not h1 or not d1 or len(d1) < DEFAULT_WINDOW + RANK_WINDOW + 1:
            continue
        adir = active_daily_dir(d1, k)
        if adir is None:
            continue
        t = len(h1) - 1
        if t < h1_window:
            continue
        d = is_new_breakout(h1, t, h1_window)
        if d is not None and d == adir:
            base, quote = P.base_quote(pair)
            out.append({"pair": pair, "dir": d, "base": base, "quote": quote})
    return out


def daily_weekly_aligned_breakouts(h1_by_pair, d1_by_pair, w_by_pair,
                                   k_d=10, k_w=8, h1_window=DEFAULT_WINDOW):
    """Rotture H1 allineate SIA al daily SIA al weekly (coorte d1w del backtest:
    hit ~53-55%, ritorno medio positivo e net-positivo dopo i costi). Il piu' selettivo."""
    from . import pairs as P
    out = []
    for pair in P.PAIRS:
        h1 = h1_by_pair.get(pair)
        d1 = d1_by_pair.get(pair)
        w1 = w_by_pair.get(pair)
        if not h1 or not d1 or not w1:
            continue
        if len(d1) < DEFAULT_WINDOW + RANK_WINDOW + 1 or len(w1) < DEFAULT_WINDOW + RANK_WINDOW + 1:
            continue
        adir = active_daily_dir(d1, k_d)
        wdir = active_daily_dir(w1, k_w)
        if adir is None or wdir is None or adir != wdir:
            continue
        t = len(h1) - 1
        if t < h1_window:
            continue
        d = is_new_breakout(h1, t, h1_window)
        if d is not None and d == adir:
            base, quote = P.base_quote(pair)
            out.append({"pair": pair, "dir": d, "base": base, "quote": quote})
    return out
