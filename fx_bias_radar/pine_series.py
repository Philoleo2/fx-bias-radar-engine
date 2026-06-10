"""Pine-equivalent series primitives.

Semantics mirror TradingView Pine v6 built-ins as used by
FX_Bias_Radar_Production_v1_1.pine. ``None`` plays the role of Pine ``na``.

Conventions (documented deviations: NONE intended):
- Rolling windows (sma/stdev/highest/lowest) return None until ``length``
  values exist AND the window contains no None. TradingView computes on the
  full chart history, so with the recommended fetch of >= 400 H4 bars all
  operationally relevant recent bars are unaffected by warmup.
- ta.stdev uses the POPULATION standard deviation (divides by N), matching
  Pine's biased default.
- ta.ema seeds with the first valid value, then ema = alpha*x + (1-alpha)*ema.
- Comparisons against None are False (Pine: comparisons with na are false).
"""

from __future__ import annotations

import math
from typing import List, Optional

Num = Optional[float]


def nz(x: Num, repl: float = 0.0) -> float:
    """Pine nz()."""
    return repl if x is None else x


def _window(xs: List[Num], i: int, length: int) -> Optional[List[float]]:
    if i + 1 < length:
        return None
    w = xs[i + 1 - length : i + 1]
    if any(v is None for v in w):
        return None
    return w  # type: ignore[return-value]


def sma_at(xs: List[Num], i: int, length: int) -> Num:
    w = _window(xs, i, length)
    return None if w is None else sum(w) / length


def stdev_at(xs: List[Num], i: int, length: int) -> Num:
    """Population stdev (Pine ta.stdev biased default)."""
    w = _window(xs, i, length)
    if w is None:
        return None
    m = sum(w) / length
    return math.sqrt(sum((v - m) ** 2 for v in w) / length)


def highest_at(xs: List[Num], i: int, length: int) -> Num:
    w = _window(xs, i, length)
    return None if w is None else max(w)


def lowest_at(xs: List[Num], i: int, length: int) -> Num:
    w = _window(xs, i, length)
    return None if w is None else min(w)


def sma(xs: List[Num], length: int) -> List[Num]:
    return [sma_at(xs, i, length) for i in range(len(xs))]


def stdev(xs: List[Num], length: int) -> List[Num]:
    return [stdev_at(xs, i, length) for i in range(len(xs))]


def ema(xs: List[Num], length: int) -> List[Num]:
    """Pine ta.ema: seeds with the first valid value."""
    alpha = 2.0 / (length + 1)
    out: List[Num] = []
    state: Num = None
    for x in xs:
        if x is None:
            out.append(None)
            continue
        state = x if state is None else alpha * x + (1 - alpha) * state
        out.append(state)
    return out


def crossover_point(a_now: Num, a_prev: Num, b_now: Num, b_prev: Num) -> bool:
    """Pine ta.crossover(a, b) evaluated at one bar."""
    if a_now is None or a_prev is None or b_now is None or b_prev is None:
        return False
    return a_now > b_now and a_prev <= b_prev


def crossunder_point(a_now: Num, a_prev: Num, b_now: Num, b_prev: Num) -> bool:
    """Pine ta.crossunder(a, b) evaluated at one bar."""
    if a_now is None or a_prev is None or b_now is None or b_prev is None:
        return False
    return a_now < b_now and a_prev >= b_prev


def at(xs: List[Num], i: int, back: int = 0) -> Num:
    """Pine history access xs[back] at bar i; None outside range."""
    j = i - back
    if j < 0 or j >= len(xs):
        return None
    return xs[j]
