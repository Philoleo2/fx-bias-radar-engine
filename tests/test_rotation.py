"""Test del rilevatore di rotazione (M4). Serie sintetiche, motore non toccato."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fx_bias_radar.rotation import (
    RotParams, detect_at, detect_rotations, label_pivots,
)


def _ramp(a, b, n):
    if n <= 1:
        return [float(b)]
    return [a + (b - a) * i / (n - 1) for i in range(n)]


def _top_series():
    """AUDNZD-like: base sale poi molla, quote scende poi recupera -> sp picco e gira giu'."""
    # 0..15 salita, 16..27 discesa
    zb = _ramp(0.0, 2.6, 16) + _ramp(2.6, 1.4, 12)[1:]
    zq = _ramp(0.0, -2.6, 16) + _ramp(-2.6, -1.4, 12)[1:]
    sp = [b - q for b, q in zip(zb, zq)]
    return sp, zb, zq


def _bottom_series():
    zb = _ramp(0.0, -2.6, 16) + _ramp(-2.6, -1.4, 12)[1:]
    zq = _ramp(0.0, 2.6, 16) + _ramp(2.6, 1.4, 12)[1:]
    sp = [b - q for b, q in zip(zb, zq)]
    return sp, zb, zq


def test_top_rotation_gives_short_centered():
    sp, zb, zq = _top_series()
    pivots = label_pivots(sp, swing=5, ext_min=2.0)
    assert any(p["dir"] == "SHORT" for p in pivots)
    peak_bar = [p["bar"] for p in pivots if p["dir"] == "SHORT"][0]

    sig = detect_rotations(sp, zb, zq, RotParams(ext_min=2.0, k_window=12,
                                                 recent=4, conf_bars=2,
                                                 method="slope_both"))
    shorts = [s for s in sig if s["dir"] == "SHORT"]
    assert shorts, "nessun segnale SHORT sul top"
    first = shorts[0]["bar"]
    # centrato: vicino al picco vero, non troppo presto ne' troppo tardi
    assert peak_bar - 1 <= first <= peak_bar + 4, (first, peak_bar)


def test_bottom_rotation_gives_long():
    sp, zb, zq = _bottom_series()
    sig = detect_rotations(sp, zb, zq, RotParams(ext_min=2.0, method="slope_both"))
    longs = [s for s in sig if s["dir"] == "LONG"]
    assert longs, "nessun segnale LONG sul bottom"


def test_flat_no_signal():
    # spread che oscilla piccolo, sotto ext_min -> nessuna rotazione
    sp = [0.2 * ((-1) ** i) for i in range(40)]
    zb = [0.1 * ((-1) ** i) for i in range(40)]
    zq = [-0.1 * ((-1) ** i) for i in range(40)]
    sig = detect_rotations(sp, zb, zq, RotParams(ext_min=2.0))
    assert sig == []


def test_methods_all_detect_top():
    sp, zb, zq = _top_series()
    for m in ("slope_both", "ema_cross", "drop"):
        sig = detect_rotations(sp, zb, zq, RotParams(ext_min=2.0, method=m,
                                                     drop_min=0.4, ema_len=6))
        assert any(s["dir"] == "SHORT" for s in sig), f"metodo {m} non rileva il top"


def test_detect_at_none_before_extreme():
    sp, zb, zq = _top_series()
    # in piena salita (prima del picco) NON deve esserci ancora un giro
    assert detect_at(sp, zb, zq, 10, RotParams(ext_min=2.0)) is None


def _top_at_end():
    """Serie con picco vicino alla FINE: rotazione sull'ultima barra."""
    zb = _ramp(0.0, 2.8, 26) + [2.7, 2.4]
    zq = _ramp(0.0, -2.8, 26) + [-2.7, -2.4]
    return zb, zq


def test_rotations_from_strength_top_short():
    from fx_bias_radar.rotation import rotations_from_strength
    zb, zq = _top_at_end()
    flat = [0.0] * len(zb)
    payload = {"currencies": [
        {"ccy": "AUD", "series": zb}, {"ccy": "NZD", "series": zq},
        {"ccy": "EUR", "series": flat}, {"ccy": "GBP", "series": flat},
        {"ccy": "USD", "series": flat}, {"ccy": "CAD", "series": flat},
        {"ccy": "CHF", "series": flat}, {"ccy": "JPY", "series": flat},
    ]}
    rot = rotations_from_strength(payload)
    by = {r["pair"]: r for r in rot}
    assert "AUDNZD" in by, by
    assert by["AUDNZD"]["dir"] == "SHORT"
    assert by["AUDNZD"]["forte"] == "AUD" and by["AUDNZD"]["debole"] == "NZD"
