"""Operational feature flags for PREWAKE (SS49).

Only operational switches live in the environment. Model parameters
(threshold, EWMA, reset, coefficients) are NOT configurable: they live in the
immutable artifact prewake/models/pair_prewake_v1.json.
"""
from __future__ import annotations

import os

FORBIDDEN_ENV = (
    "PREWAKE_THRESHOLD", "PREWAKE_EWMA", "PREWAKE_RESET",
    "PREWAKE_COEFFICIENTS", "PREWAKE_INTERCEPT", "PREWAKE_FEATURES",
)


def _flag(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def engine_enabled() -> bool:
    return _flag("PREWAKE_ENGINE_ENABLED", False)


def email_enabled() -> bool:
    return _flag("PREWAKE_EMAIL_ENABLED", False)


def ui_enabled() -> bool:
    return _flag("PREWAKE_UI_ENABLED", True)


def assert_no_model_overrides() -> None:
    """Fail closed if anyone tries to tune the frozen model through the env."""
    present = [name for name in FORBIDDEN_ENV if os.environ.get(name)]
    if present:
        raise RuntimeError(
            "the PAIR_PREWAKE_V1 model is frozen and cannot be configured through the "
            f"environment; remove: {', '.join(present)}"
        )
