"""Pure PAIR_PREWAKE_V1 engine.

Deterministic: same inputs -> same outputs. No network, no database, no email,
no filesystem writes. Side effects live in scripts/run_prewake.py and in
prewake/store.py.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from fx_bias_radar import pairs as P

from .features import FeatureBundle, build_features, score_cube
from .lifecycle import LifecycleState, advance
from .model import FEATURE_ORDER, load_model


@dataclass(frozen=True)
class Evaluation:
    """Per (bar, pair) audit record — SS26/SS30. One per evaluated cell."""
    bar_time_utc: str
    pair: str
    direction: int
    score: float
    threshold: float
    state_before: str
    state_after: str
    event_emitted: bool
    event_type: str | None
    reason: str
    features: dict
    direction_source_value: float
    ewma4_gap: float
    same_bar_raw_breakout: bool
    fx_bias_same: float


@dataclass(frozen=True)
class EngineResult:
    model_version: str
    model_fingerprint: str
    artifact_hash: str
    threshold: float
    bar_times: list[str]
    events: list[dict]
    evaluations: list[Evaluation]
    features: FeatureBundle
    score: np.ndarray
    lifecycle_state: LifecycleState
    skipped_reason: str | None = None


def evaluate(bar_times, close, high, low,
             lifecycle_state: LifecycleState | None = None,
             ewma_state=None, ewma_ready=None,
             emit_from: int | None = None,
             model=None) -> EngineResult:
    """Evaluate the frozen candidate over a window of complete H1 bars.

    ``bar_times``  ISO-8601 UTC bar-open timestamps, ascending, len == n.
    ``close/high/low``  (n, 28) float arrays, column order fx_bias_radar.pairs.PAIRS.
    ``emit_from``  first index whose events are returned; earlier bars advance
                   state silently (warm-up / seeding). Defaults to n-1, i.e.
                   only the newest bar emits.
    """
    model = model or load_model()
    bar_times = list(bar_times)
    n = len(bar_times)
    if emit_from is None:
        emit_from = max(0, n - 1)
    state = lifecycle_state if lifecycle_state is not None else LifecycleState.fresh()

    if n < model.minimum_bars:
        return EngineResult(
            model_version=model.model_version, model_fingerprint=model.research_fingerprint,
            artifact_hash=model.artifact_hash, threshold=model.threshold, bar_times=bar_times,
            events=[], evaluations=[], features=None, score=np.zeros((0, len(P.PAIRS))),
            lifecycle_state=state,
            skipped_reason=f"SKIPPED_INCOMPLETE_INPUT: {n} bars < {model.minimum_bars} required",
        )

    # Two modes. Full replay (seed / parity): the window IS the whole history,
    # so every bar feeds the recursive EWMA and the lifecycle from index 0.
    # Incremental (hourly production): the leading bars of the window were
    # already consumed by an earlier run and are lookback only.
    incremental = ewma_state is not None
    consumed_from = emit_from if incremental else 0

    features = build_features(close, high, low, ewma_state=ewma_state, ewma_ready=ewma_ready,
                              ewma_from=consumed_from)
    score = score_cube(model, features.cube, features.direction)

    before = {k: dict(armed=state.armed[k], seen=state.seen[k]) for k in state.armed}
    events = advance(state, score, features.direction, model.threshold, features.breakout,
                     emit_from=emit_from, start=consumed_from,
                     reset_ratio=model.reset_ratio, reset_bars=model.reset_bars)

    emitted = {(e["t"], e["pair_index"], e["direction"]) for e in events}
    evaluations = _build_evaluations(model, bar_times, features, score, events, emitted, emit_from, before, state)

    for event in events:
        event["bar_time_utc"] = bar_times[event["t"]]
        # Frozen definition (SS27, forensic audit): a same-bar RAW FRESH BREAKOUT
        # in the alert direction. Diagnostic only - it never suppresses the signal.
        event["same_bar_raw_breakout"] = bool(event["late_same_breakout"])
        event["same_bar_raw_state"] = int(features.raw_state[event["t"], event["pair_index"]])
        event["fx_bias_same"] = float(features.cube[event["t"], event["pair_index"], 7])
        event["features"] = {name: float(features.cube[event["t"], event["pair_index"], i])
                             for i, name in enumerate(FEATURE_ORDER)}
        event["direction_source_value"] = float(features.ewma4[event["t"], event["pair_index"]])
        event["ewma4_gap"] = float(features.ewma4[event["t"], event["pair_index"]])
        event["ols_lopo_gap"] = float(features.ols_lopo[event["t"], event["pair_index"]])
        event["gap_robust_z"] = float(features.gap_z[event["t"], event["pair_index"]])

    return EngineResult(
        model_version=model.model_version, model_fingerprint=model.research_fingerprint,
        artifact_hash=model.artifact_hash, threshold=model.threshold, bar_times=bar_times,
        events=events, evaluations=evaluations, features=features, score=score, lifecycle_state=state,
    )


def _label(armed: bool, seen: bool) -> str:
    if not seen:
        return "NEVER_FIRED"
    return "ARMED" if armed else "ACTIVE"


def _build_evaluations(model, bar_times, features, score, events, emitted, emit_from, before, state):
    """Audit records for the emitting bars only (SS26). One row per pair."""
    out: list[Evaluation] = []
    for t in range(emit_from, len(bar_times)):
        for pair_index, pair in enumerate(P.PAIRS):
            s = float(score[t, pair_index])
            d = int(features.direction[t, pair_index])
            key = f"{pair}:{'LONG' if d > 0 else 'SHORT'}" if d != 0 else f"{pair}:LONG"
            fired = next((e for e in events
                          if (e["t"], e["pair_index"]) == (t, pair_index)), None)
            if not np.isfinite(s):
                reason = "NO_SCORE_INSUFFICIENT_OR_MISSING_INPUT"
            elif d == 0:
                reason = "NO_DIRECTION"
            elif fired is not None:
                reason = "THRESHOLD_CROSSED_AND_LIFECYCLE_ARMED"
            elif s >= model.threshold:
                reason = "ABOVE_THRESHOLD_BUT_LIFECYCLE_NOT_ARMED"
            elif s < model.threshold * model.reset_ratio:
                reason = "BELOW_RESET_BAND"
            else:
                reason = "BELOW_THRESHOLD"
            out.append(Evaluation(
                bar_time_utc=bar_times[t], pair=pair, direction=d, score=s, threshold=model.threshold,
                state_before=_label(before[key]["armed"], before[key]["seen"]) if key in before else "UNKNOWN",
                state_after=_label(state.armed[key], state.seen[key]) if key in state.armed else "UNKNOWN",
                event_emitted=fired is not None,
                event_type=fired["type"] if fired else None,
                reason=reason,
                features={name: float(features.cube[t, pair_index, i]) for i, name in enumerate(FEATURE_ORDER)},
                direction_source_value=float(features.ewma4[t, pair_index]),
                ewma4_gap=float(features.ewma4[t, pair_index]),
                same_bar_raw_breakout=bool(features.breakout[t, pair_index] == d and d != 0),
                fx_bias_same=float(features.cube[t, pair_index, 7]),
            ))
    return out
