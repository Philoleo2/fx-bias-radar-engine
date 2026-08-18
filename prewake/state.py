"""Persisted PREWAKE state: recursive EWMA + lifecycle + prospective marker.

The frozen EWMA is recursive and never reset, and NEW_WAKE is 'first ever for
this (pair, direction)'. Both therefore depend on the whole scored history.
Production seeds this state once from a full historical replay
(scripts/prewake_seed.py) and then advances it one H1 at a time, which is
numerically identical to replaying from the origin on every run.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from fx_bias_radar import pairs as P

from . import store
from .lifecycle import LifecycleState

STATE_VERSION = 1


@dataclass
class PrewakeState:
    model_version: str
    model_fingerprint: str
    artifact_hash: str
    ewma_state: np.ndarray = field(default_factory=lambda: np.zeros(len(P.PAIRS)))
    ewma_ready: np.ndarray = field(default_factory=lambda: np.zeros(len(P.PAIRS), dtype=bool))
    lifecycle: LifecycleState = field(default_factory=LifecycleState.fresh)
    last_bar_time_utc: str | None = None
    seeded_from_utc: str | None = None
    seeded_at_utc: str | None = None
    prospective_start_at: str | None = None
    state_version: int = STATE_VERSION

    @classmethod
    def load(cls, model, base: str = store.BASE_DIR) -> "PrewakeState":
        payload = store.read_json(store.STATE, base)
        if not payload:
            return cls(model_version=model.model_version,
                       model_fingerprint=model.research_fingerprint,
                       artifact_hash=model.artifact_hash)
        if payload.get("artifact_hash") not in (None, model.artifact_hash):
            raise RuntimeError(
                "persisted PREWAKE state was produced by a different model artifact "
                f"({payload.get('artifact_hash')} != {model.artifact_hash}); a new model "
                "version must not reuse pair-prewake-v1 state (SS69)")
        order = payload.get("pair_order") or list(P.PAIRS)
        ewma = np.zeros(len(P.PAIRS))
        ready = np.zeros(len(P.PAIRS), dtype=bool)
        for i, pair in enumerate(order):
            if pair in P.PAIRS:
                j = P.PAIRS.index(pair)
                ewma[j] = float(payload["ewma_state"][i])
                ready[j] = bool(payload["ewma_ready"][i])
        return cls(
            model_version=payload.get("model_version", model.model_version),
            model_fingerprint=payload.get("model_fingerprint", model.research_fingerprint),
            artifact_hash=payload.get("artifact_hash", model.artifact_hash),
            ewma_state=ewma, ewma_ready=ready,
            lifecycle=LifecycleState.from_dict(payload.get("lifecycle")),
            last_bar_time_utc=payload.get("last_bar_time_utc"),
            seeded_from_utc=payload.get("seeded_from_utc"),
            seeded_at_utc=payload.get("seeded_at_utc"),
            prospective_start_at=payload.get("prospective_start_at"),
            state_version=int(payload.get("state_version", STATE_VERSION)),
        )

    def save(self, base: str = store.BASE_DIR) -> None:
        store.write_json(store.STATE, {
            "state_version": self.state_version,
            "model_version": self.model_version,
            "model_fingerprint": self.model_fingerprint,
            "artifact_hash": self.artifact_hash,
            "pair_order": list(P.PAIRS),
            "ewma_state": [float(v) for v in self.ewma_state],
            "ewma_ready": [bool(v) for v in self.ewma_ready],
            "lifecycle": self.lifecycle.to_dict(),
            "last_bar_time_utc": self.last_bar_time_utc,
            "seeded_from_utc": self.seeded_from_utc,
            "seeded_at_utc": self.seeded_at_utc,
            "prospective_start_at": self.prospective_start_at,
            "updated_at_utc": store.now_utc(),
        }, base)

    @property
    def is_seeded(self) -> bool:
        return self.last_bar_time_utc is not None
