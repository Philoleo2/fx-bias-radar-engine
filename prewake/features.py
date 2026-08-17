"""The eight frozen PAIR_PREWAKE_V1 features, plus direction and breakout state.

Pure functions over a (n_bars, 28) OHLC grid. No IO, no side effects.
Column order of every array is fx_bias_radar.pairs.PAIRS.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from fx_bias_radar import pairs as P

from .primitives import (
    compression_mask,
    ewma,
    ewma_alpha,
    fresh_breakouts,
    lag_return,
    ols_prediction_weights,
    raw_breakout_state,
    robust_z_prior,
    rolling_mean_std_prior,
    zscore_prior,
)

BREAKOUT_WINDOW = 12
COMPRESSION_RANK_WINDOW = 120
COMPRESSION_QUANTILE = 0.20
PAIR_Z_WINDOW = 120
PAIR_VOL_WINDOW = 120
ROBUST_Z_WINDOW = 240
EWMA_HALF_LIFE = 4.0


@dataclass(frozen=True)
class FeatureBundle:
    """Everything a scoring pass and an audit snapshot need."""
    cube: np.ndarray             # (n, 28, 8) model features, in FEATURE_ORDER
    direction: np.ndarray        # (n, 28) int8 in {-1, 0, 1}
    ewma4: np.ndarray            # (n, 28) direction source value
    ols_lopo: np.ndarray         # (n, 28) cross-currency gap
    gap_z: np.ndarray            # (n, 28) robust z of the gap
    breakout: np.ndarray         # (n, 28) RAW FRESH BREAKOUT, int8
    raw_state: np.ndarray        # (n, 28) non-fresh raw breakout state, int8
    fx_bias: np.ndarray          # (n, 28) compressed fresh breakout, int8
    compression_ratio: np.ndarray
    ewma_state: np.ndarray       # (28,) EWMA state after the last bar
    ewma_ready: np.ndarray       # (28,) bool


def build_features(close: np.ndarray, high: np.ndarray, low: np.ndarray,
                   ewma_state: np.ndarray | None = None,
                   ewma_ready: np.ndarray | None = None) -> FeatureBundle:
    """Build the frozen feature cube.

    ``ewma_state``/``ewma_ready`` continue a previously persisted recursive EWMA
    so that an incremental production run is numerically identical to a full
    replay from the series origin. When omitted the EWMA is seeded from this
    window's first finite observation (full-replay / seeding mode).
    """
    close = np.asarray(close, dtype=np.float64)
    high = np.asarray(high, dtype=np.float64)
    low = np.asarray(low, dtype=np.float64)
    k = len(P.PAIRS)
    if close.shape[1] != k:
        raise ValueError(f"expected {k} pair columns, got {close.shape[1]}")

    returns = {lag: lag_return(close, lag) for lag in (1, 4, 12, 24)}
    _full_w, lopo_w = ols_prediction_weights()
    ols_lopo = returns[1] @ lopo_w.T
    gap_z = robust_z_prior(ols_lopo, ROBUST_Z_WINDOW)

    if ewma_state is None:
        ewma4 = ewma(gap_z, EWMA_HALF_LIFE)
        state = np.zeros(k, dtype=np.float64)
        ready = np.zeros(k, dtype=bool)
        for j in range(k):
            col = ewma4[:, j]
            finite = np.flatnonzero(np.isfinite(col))
            if len(finite):
                ready[j] = True
                state[j] = col[finite[-1]]
    else:
        ewma4, state, ready = _ewma_continued(gap_z, np.asarray(ewma_state, dtype=np.float64),
                                              np.asarray(ewma_ready, dtype=bool))

    breakout = fresh_breakouts(close, high, low, BREAKOUT_WINDOW)
    raw_state = raw_breakout_state(close, high, low, BREAKOUT_WINDOW)
    compressed, compression_ratio = compression_mask(
        high, low, BREAKOUT_WINDOW, COMPRESSION_RANK_WINDOW, COMPRESSION_QUANTILE)
    fx_bias = np.where(compressed, breakout, 0).astype(np.int8)

    pair_z = zscore_prior(returns[1], PAIR_Z_WINDOW)
    _vol_mean, pair_vol120 = rolling_mean_std_prior(returns[1], PAIR_VOL_WINDOW)

    with np.errstate(invalid="ignore"):
        direction = np.sign(np.nan_to_num(ewma4, nan=0.0)).astype(np.int8)
    direction[~np.isfinite(ewma4)] = 0

    oriented = lambda x: direction * x
    cube = np.stack(
        [
            oriented(returns[1]), oriented(returns[4]), oriented(returns[12]), oriented(returns[24]),
            np.abs(pair_z), compression_ratio, pair_vol120,
            (fx_bias == direction).astype(float),
        ],
        axis=2,
    )
    return FeatureBundle(cube=cube, direction=direction, ewma4=ewma4, ols_lopo=ols_lopo, gap_z=gap_z,
                         breakout=breakout, raw_state=raw_state, fx_bias=fx_bias,
                         compression_ratio=compression_ratio, ewma_state=state, ewma_ready=ready)


def _ewma_continued(x: np.ndarray, state: np.ndarray, ready: np.ndarray):
    """Recursive EWMA continuing from a persisted state, step-for-step identical
    to primitives.ewma over the concatenated history."""
    alpha = ewma_alpha(EWMA_HALF_LIFE)
    state = state.copy()
    ready = ready.copy()
    out = np.full_like(x, np.nan, dtype=np.float64)
    for t in range(len(x)):
        valid = np.isfinite(x[t])
        init = valid & ~ready
        state[init] = x[t, init]
        ready[init] = True
        update = valid & ready & ~init
        state[update] = alpha * x[t, update] + (1.0 - alpha) * state[update]
        out[t, ready] = state[ready]
    return out, state, ready


def score_cube(model, cube: np.ndarray, direction: np.ndarray) -> np.ndarray:
    """Score every (bar, pair) cell. NaN where a feature is missing or dir == 0."""
    score = np.full(direction.shape, np.nan)
    valid = np.all(np.isfinite(cube), axis=2) & (direction != 0)
    if valid.any():
        score[valid] = model.score(cube[valid])
    return score
