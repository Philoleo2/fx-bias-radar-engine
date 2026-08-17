"""Immutable PAIR_PREWAKE_V1 model artifact — load and score only.

The artifact is a versioned file on disk. It is deliberately NOT configurable
through the UI or through environment variables: threshold, coefficients, EWMA
and lifecycle parameters are part of the frozen candidate under prospective
validation, and changing any of them creates a different model that must get a
new model_version (see docs/PREWAKE_V1_PRODUCTION.md).

Production never fits. There is no `fit` in this module by design.
"""
from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from functools import lru_cache

import numpy as np

ARTIFACT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "models", "pair_prewake_v1.json")

FEATURE_ORDER = ("dir_ret1", "dir_ret4", "dir_ret12", "dir_ret24",
                 "abs_pair_z", "compression_ratio", "pair_vol120", "fx_bias_same")


class ArtifactError(RuntimeError):
    """Raised when the on-disk model artifact does not match its own hash."""


@dataclass(frozen=True)
class PrewakeModel:
    model_name: str
    model_version: str
    research_fingerprint: str
    artifact_hash: str
    feature_order: tuple[str, ...]
    coefficients: np.ndarray
    intercept: float
    mean: np.ndarray
    scale: np.ndarray
    threshold: float
    reset_ratio: float
    reset_bars: int
    ewma_half_life: float
    robust_z_window: int
    minimum_bars: int
    raw: dict

    def score(self, x: np.ndarray) -> np.ndarray:
        """Sigmoid probability for a (..., 8) feature array. Predict only."""
        x = np.asarray(x, dtype=np.float64)
        if x.shape[-1] != len(self.feature_order):
            raise ValueError(f"expected {len(self.feature_order)} features, got {x.shape[-1]}")
        linear = ((x - self.mean) / self.scale) @ self.coefficients + self.intercept
        linear = np.clip(linear, -40, 40)
        return 1.0 / (1.0 + np.exp(-linear))


def _verify(payload: dict) -> str:
    declared = payload.get("artifact_hash")
    if not declared:
        raise ArtifactError("model artifact has no artifact_hash")
    body = {k: v for k, v in payload.items() if k != "artifact_hash"}
    recomputed = "sha256:" + hashlib.sha256(
        json.dumps(body, indent=2, sort_keys=False, ensure_ascii=False).encode("utf-8")
    ).hexdigest()
    if recomputed != declared:
        raise ArtifactError(f"model artifact hash mismatch: declared {declared}, recomputed {recomputed}")
    return declared


@lru_cache(maxsize=1)
def load_model(path: str = ARTIFACT_PATH) -> PrewakeModel:
    with open(path, "r", encoding="utf-8") as handle:
        payload = json.load(handle)
    artifact_hash = _verify(payload)
    feature_order = tuple(payload["feature_order"])
    if feature_order != FEATURE_ORDER:
        raise ArtifactError(f"unexpected feature order: {feature_order}")
    scaler = payload["scaler_parameters"]
    return PrewakeModel(
        model_name=payload["model_name"],
        model_version=payload["model_version"],
        research_fingerprint=payload["research_fingerprint"],
        artifact_hash=artifact_hash,
        feature_order=feature_order,
        coefficients=np.asarray(payload["coefficients"], dtype=np.float64),
        intercept=float(payload["intercept"]),
        mean=np.asarray(scaler["mean"], dtype=np.float64),
        scale=np.asarray(scaler["scale"], dtype=np.float64),
        threshold=float(payload["threshold"]),
        reset_ratio=float(payload["reset_parameters"]["reset_ratio"]),
        reset_bars=int(payload["reset_parameters"]["reset_bars"]),
        ewma_half_life=float(payload["ewma_parameters"]["half_life"]),
        robust_z_window=int(payload["direction"]["robust_z_window"]),
        minimum_bars=int(payload["feature_windows"]["minimum_bars_for_valid_score"]),
        raw=payload,
    )
