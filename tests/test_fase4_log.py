"""Test Fase 4 logger (M4 rotazioni): build_log_rows + idempotenza CSV."""

from __future__ import annotations

import os
import sys
import importlib.util

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_SPEC = importlib.util.spec_from_file_location(
    "log_fase4",
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                 "scripts", "log_fase4.py"),
)
LF = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(LF)


def _report_h4():
    return {
        "last_complete_bar_close_utc": "2026-06-23T14:00:00+00:00",
        "pairs": [
            {"pair": "AUDNZD", "bias": "LONG", "tipo": "RESUME", "stato": "ESTESO",
             "score": 100, "spread": 1.02, "attention_event": False},
            {"pair": "CADCHF", "bias": "SHORT", "tipo": "RESUME", "stato": "ATTIVO",
             "score": 100, "spread": 2.61, "attention_event": True},
            {"pair": "NZDCHF", "bias": "NESSUNO", "tipo": "NESSUNO", "stato": "NESSUNO",
             "score": 0, "spread": 0.23, "attention_event": False},
        ],
    }


def _payload_pr():
    return {
        "generated_at_utc": "2026-06-23T14:06:00+00:00",
        "h1_last_bar_utc": "2026-06-23T13:00:00+00:00",
        "rotazioni": [
            {"pair": "AUDNZD", "dir": "SHORT", "forte": "AUD", "debole": "NZD",
             "spread_h1": 2.31},
        ],
    }


def test_rows_include_rotation_and_active_exclude_flat():
    rows = LF.build_log_rows(_report_h4(), _payload_pr())
    by = {r["pair"]: r for r in rows}
    assert "NZDCHF" not in by                     # piatta senza segnale -> esclusa
    assert set(by) == {"AUDNZD", "CADCHF"}

    a = by["AUDNZD"]
    assert a["h1_state"] == "ROTAZIONE" and a["h1_dir"] == "SHORT"
    assert a["h1_down_run"] == "AUD>NZD" and a["h1_gap_h4"] == 2.31
    assert a["h4_stato"] == "ESTESO"

    c = by["CADCHF"]                              # H4 attivo senza rotazione H1
    assert c["h1_state"] == "-" and c["h4_event"] == "1"

    assert a["h1_bar_utc"] == "2026-06-23T13:00:00+00:00"
    assert a["h4_bar_close_utc"] == "2026-06-23T14:00:00+00:00"


def test_dash_tipo_is_inactive_without_h1_signal():
    report = _report_h4()
    report["pairs"].append({
        "pair": "USDJPY",
        "bias": "-",
        "tipo": "-",
        "stato": "NESSUNO",
        "score": 5,
        "spread": 0.04,
        "attention_event": False,
    })
    rows = LF.build_log_rows(report, _payload_pr())
    assert "USDJPY" not in {r["pair"] for r in rows}


def test_append_header_once_and_idempotent_helper(tmp_path):
    path = os.path.join(str(tmp_path), "fase4_log.csv")
    LF.append_rows(path, LF.build_log_rows(_report_h4(), _payload_pr()))
    assert LF.last_logged_h1_bar(path) == "2026-06-23T13:00:00+00:00"
    rows2 = [dict(r, h1_bar_utc="2026-06-23T14:00:00+00:00")
             for r in LF.build_log_rows(_report_h4(), _payload_pr())]
    LF.append_rows(path, rows2)
    with open(path, encoding="utf-8") as f:
        content = f.read()
    assert content.count("ts_utc,h1_bar_utc") == 1
    assert LF.last_logged_h1_bar(path) == "2026-06-23T14:00:00+00:00"
