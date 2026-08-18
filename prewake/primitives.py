"""Frozen numerical primitives for PAIR_PREWAKE_V1.

Every function in this module is a byte-faithful port of the corresponding
function in the frozen research engine:

    research/fx_pressure_engine.py
    sha256 b1a76be38b468bdecc5ca180c33c271cdc2c99753f768f693551ebcb1249bed6
    at research/prewake-phase2 @ bfadfc98b2bed21377287d16b2eab5745f0fe8c3

DO NOT "improve", vectorise differently, or change any constant here. Any edit
changes the candidate under prospective validation. Parity against the frozen
research ledger is enforced by tests/test_prewake_parity.py.
"""
from __future__ import annotations

import math
from datetime import datetime, timezone

import numpy as np
from numpy.lib.stride_tricks import sliding_window_view

from fx_bias_radar import pairs as P

EPS = 1e-12

CCY_INDEX = {ccy: i for i, ccy in enumerate(P.CURRENCIES)}


def parse_utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def incidence_matrix() -> np.ndarray:
    matrix = np.zeros((len(P.PAIRS), len(P.CURRENCIES)), dtype=np.float64)
    for j, pair in enumerate(P.PAIRS):
        matrix[j, CCY_INDEX[pair[:3]]] = 1.0
        matrix[j, CCY_INDEX[pair[3:]]] = -1.0
    return matrix


def constrained_coefficients(rows: np.ndarray, weights: np.ndarray | None = None) -> np.ndarray:
    if weights is None:
        weighted_rows = rows
        left = rows.T @ rows
    else:
        weighted_rows = weights[:, None] * rows
        left = rows.T @ weighted_rows
    k = rows.shape[1]
    augmented = np.block([[left, np.ones((k, 1))], [np.ones((1, k)), np.zeros((1, 1))]])
    right = np.vstack([weighted_rows.T, np.zeros((1, rows.shape[0]))])
    solution = np.linalg.pinv(augmented) @ right
    return solution[:k]


def ols_prediction_weights() -> tuple[np.ndarray, np.ndarray]:
    """Full and leave-one-pair-out cross-currency prediction weights."""
    a = incidence_matrix()
    full_b = constrained_coefficients(a)
    full = a @ full_b
    lopo = np.zeros((len(P.PAIRS), len(P.PAIRS)), dtype=np.float64)
    for target in range(len(P.PAIRS)):
        keep = np.arange(len(P.PAIRS)) != target
        b = constrained_coefficients(a[keep])
        lopo[target, keep] = a[target] @ b
    return full, lopo


def lag_return(close: np.ndarray, lag: int) -> np.ndarray:
    out = np.full_like(close, np.nan, dtype=np.float64)
    out[lag:] = np.log(close[lag:] / close[:-lag])
    return out


def rolling_mean_std_prior(x: np.ndarray, window: int) -> tuple[np.ndarray, np.ndarray]:
    """Mean/std of x[t-window:t], excluding x[t]."""
    finite = np.isfinite(x)
    clean = np.where(finite, x, 0.0)
    cs = np.vstack([np.zeros((1, x.shape[1])), np.cumsum(clean, axis=0)])
    cq = np.vstack([np.zeros((1, x.shape[1])), np.cumsum(clean * clean, axis=0)])
    cn = np.vstack([np.zeros((1, x.shape[1])), np.cumsum(finite.astype(float), axis=0)])
    mean = np.full_like(x, np.nan, dtype=np.float64)
    std = np.full_like(x, np.nan, dtype=np.float64)
    sums = cs[window:-1] - cs[:-window - 1]
    sums2 = cq[window:-1] - cq[:-window - 1]
    counts = cn[window:-1] - cn[:-window - 1]
    valid = counts >= max(20, window // 2)
    m = np.divide(sums, counts, out=np.zeros_like(sums), where=counts > 0)
    var = np.divide(sums2, counts, out=np.zeros_like(sums2), where=counts > 0) - m * m
    mean[window:] = np.where(valid, m, np.nan)
    std[window:] = np.where(valid, np.sqrt(np.maximum(var, EPS)), np.nan)
    return mean, std


def zscore_prior(x: np.ndarray, window: int) -> np.ndarray:
    mean, std = rolling_mean_std_prior(x, window)
    return (x - mean) / std


def robust_z_prior(x: np.ndarray, window: int) -> np.ndarray:
    """Exact rolling median/MAD, sequential by pair to bound memory."""
    out = np.full_like(x, np.nan, dtype=np.float64)
    for j in range(x.shape[1]):
        column = x[:, j]
        if len(column) <= window:
            continue
        windows = sliding_window_view(column, window + 1)
        history = windows[:, :-1]
        med = np.nanmedian(history, axis=1)
        mad = np.nanmedian(np.abs(history - med[:, None]), axis=1)
        scale = np.maximum(1.4826 * mad, EPS)
        values = (windows[:, -1] - med) / scale
        valid_counts = np.sum(np.isfinite(history), axis=1)
        values[valid_counts < window // 2] = np.nan
        out[window:, j] = values
    return out


def rolling_quantile_prior_1d(x: np.ndarray, window: int, q: float) -> np.ndarray:
    out = np.full(len(x), np.nan, dtype=np.float64)
    if len(x) <= window:
        return out
    windows = sliding_window_view(x, window + 1)
    history = windows[:, :-1]
    out[window:] = np.nanquantile(history, q, axis=1, method="linear")
    return out


def prior_window_bounds(high: np.ndarray, low: np.ndarray, window: int) -> tuple[np.ndarray, np.ndarray]:
    hi = np.full_like(high, np.nan)
    lo = np.full_like(low, np.nan)
    for lag in range(1, window + 1):
        shifted_h = np.full_like(high, np.nan)
        shifted_l = np.full_like(low, np.nan)
        shifted_h[lag:] = high[:-lag]
        shifted_l[lag:] = low[:-lag]
        hi = np.fmax(hi, shifted_h)
        lo = np.fmin(lo, shifted_l)
    return hi, lo


def fresh_breakouts(close: np.ndarray, high: np.ndarray, low: np.ndarray, window: int = 12) -> np.ndarray:
    """RAW FRESH BREAKOUT, exactly as defined by the frozen research."""
    hi, lo = prior_window_bounds(high, low, window)
    raw = np.where(close > hi, 1, np.where(close < lo, -1, 0)).astype(np.int8)
    raw[:window] = 0
    fresh = raw.copy()
    fresh[1:][raw[1:] == raw[:-1]] = 0
    return fresh


def raw_breakout_state(close: np.ndarray, high: np.ndarray, low: np.ndarray, window: int = 12) -> np.ndarray:
    """Non-fresh raw state; diagnostic only (same_bar_raw_breakout, SS27)."""
    hi, lo = prior_window_bounds(high, low, window)
    raw = np.where(close > hi, 1, np.where(close < lo, -1, 0)).astype(np.int8)
    raw[:window] = 0
    return raw


def compression_mask(high: np.ndarray, low: np.ndarray, window: int = 12,
                     rank_window: int = 120, q: float = 0.20) -> tuple[np.ndarray, np.ndarray]:
    hi, lo = prior_window_bounds(high, low, window)
    ranges = hi - lo
    threshold = np.full_like(ranges, np.nan)
    for j in range(ranges.shape[1]):
        threshold[:, j] = rolling_quantile_prior_1d(ranges[:, j], rank_window, q)
    ratio = ranges / np.maximum(threshold, EPS)
    return ranges <= threshold, ratio


def ewma(x: np.ndarray, half_life: float) -> np.ndarray:
    """Recursive EWMA, seeded at the first finite observation, never reset."""
    alpha = 1.0 - math.exp(math.log(0.5) / half_life)
    out = np.full_like(x, np.nan, dtype=np.float64)
    state = np.zeros(x.shape[1], dtype=np.float64)
    ready = np.zeros(x.shape[1], dtype=bool)
    for t in range(len(x)):
        valid = np.isfinite(x[t])
        init = valid & ~ready
        state[init] = x[t, init]
        ready[init] = True
        update = valid & ready & ~init
        state[update] = alpha * x[t, update] + (1.0 - alpha) * state[update]
        out[t, ready] = state[ready]
    return out


def ewma_alpha(half_life: float) -> float:
    return 1.0 - math.exp(math.log(0.5) / half_life)


def ewma_step(value: float, state: float, ready: bool, alpha: float) -> tuple[float, bool, float]:
    """One incremental EWMA step, bit-identical to the batch loop above.

    Returns (new_state, new_ready, output). Output is NaN while not ready; once
    ready it is carried forward even on a NaN input, exactly like the batch
    version's `out[t, ready] = state[ready]`.
    """
    if np.isfinite(value):
        if not ready:
            state = float(value)
            ready = True
        else:
            state = alpha * float(value) + (1.0 - alpha) * state
    return state, ready, (state if ready else float("nan"))
