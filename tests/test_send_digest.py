"""Test del digest email (composizione pura + gate orario). Niente SMTP reale."""

from __future__ import annotations

import os
import sys
import importlib.util

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_SPEC = importlib.util.spec_from_file_location(
    "send_digest",
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                 "scripts", "send_digest.py"))
SD = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(SD)


def _payload():
    return {
        "generated_at_utc": "2026-06-23T06:05:00+00:00",
        "h1_last_bar_utc": "2026-06-23T05:00:00+00:00",
        "ranking_h4": ["AUD", "EUR", "CHF", "NZD", "GBP", "JPY", "USD", "CAD"],
        "rotazioni": [
            {"pair": "AUDNZD", "dir": "SHORT", "forte": "AUD", "debole": "NZD", "spread_h1": 2.31},
        ],
    }


def test_gate_hours():
    assert SD.should_send(8) and SD.should_send(15)
    assert not SD.should_send(9) and not SD.should_send(0)


def test_compose_contains_rotations():
    subject, body = SD.compose(_payload(), 8)
    assert "1 rotazione" in subject
    assert "AUDNZD SHORT" in body
    assert "AUD molla, NZD recupera" in body
    assert "Forza H4: AUD > EUR" in body
    assert "non e' un consiglio di trade" in body.lower() or "consiglio di trade" in body


def test_compose_empty():
    p = _payload(); p["rotazioni"] = []
    subject, body = SD.compose(p, 15)
    assert "0 rotazioni" in subject
    assert "Nessuna rotazione" in body
