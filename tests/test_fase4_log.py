"""Test Fase 4 logger: build_log_rows + idempotenza CSV (motore non toccato)."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import importlib.util

_SPEC = importlib.util.spec_from_file_location(
    "log_fase4",
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                 "scripts", "log_fase4.py"),
)
LF = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(LF)


def _report_h4():
    return {
        "last_complete_bar_close_utc": "2026-06-16T14:00:00+00:00",
        "pairs": [
            # H1 RIPRESA + H4 RESUME ESTESO
            {"pair": "AUDJPY", "bias": "LONG", "tipo": "RESUME", "stato": "ESTESO",
             "score": 100, "spread": 1.35, "attention_event": False},
            # H1 RIENTRO + H4 NESSUNO (deve comparire per il segnale H1)
            {"pair": "EURUSD", "bias": "NESSUNO", "tipo": "NESSUNO", "stato": "NESSUNO",
             "score": 0, "spread": 1.34, "attention_event": False},
            # H4 RESUME ATTIVO senza segnale H1 (deve comparire per stato H4)
            {"pair": "CADCHF", "bias": "SHORT", "tipo": "RESUME", "stato": "ATTIVO",
             "score": 100, "spread": 1.64, "attention_event": True},
            # piatta, nessun segnale -> esclusa
            {"pair": "NZDCHF", "bias": "NESSUNO", "tipo": "NESSUNO", "stato": "NESSUNO",
             "score": 0, "spread": 0.23, "attention_event": False},
        ],
    }


def _payload_pr():
    return {
        "generated_at_utc": "2026-06-16T14:38:00+00:00",
        "h1_last_bar_utc": "2026-06-16T13:00:00+00:00",
        "riprese": [
            {"pair": "AUDJPY", "dir": "LONG", "gap_h4": 1.35, "h1_down_run": 0},
        ],
        "rientri": [
            {"pair": "EURUSD", "dir": "LONG", "gap_h4": 1.34, "h1_down_run": 3},
        ],
    }


def test_rows_include_signals_and_active_exclude_flat():
    rows = LF.build_log_rows(_report_h4(), _payload_pr())
    by_pair = {r["pair"]: r for r in rows}
    # piatta senza segnale esclusa
    assert "NZDCHF" not in by_pair
    # le tre interessanti presenti
    assert set(by_pair) == {"AUDJPY", "EURUSD", "CADCHF"}

    # RIPRESA su trend H4 gia' ESTESO
    a = by_pair["AUDJPY"]
    assert a["h1_state"] == "RIPRESA" and a["h1_dir"] == "LONG"
    assert a["h4_tipo"] == "RESUME" and a["h4_stato"] == "ESTESO"

    # RIENTRO con H4 senza evento
    e = by_pair["EURUSD"]
    assert e["h1_state"] == "RIENTRO" and e["h1_down_run"] == 3
    assert e["h4_tipo"] == "NESSUNO"

    # H4 attivo senza segnale H1
    c = by_pair["CADCHF"]
    assert c["h1_state"] == "-" and c["h4_stato"] == "ATTIVO" and c["h4_event"] == "1"

    # timestamp propagati
    assert a["h1_bar_utc"] == "2026-06-16T13:00:00+00:00"
    assert a["h4_bar_close_utc"] == "2026-06-16T14:00:00+00:00"


def test_append_writes_header_once_and_idempotent_helper(tmp_path):
    path = os.path.join(str(tmp_path), "fase4_log.csv")
    rows = LF.build_log_rows(_report_h4(), _payload_pr())
    LF.append_rows(path, rows)
    assert LF.last_logged_h1_bar(path) == "2026-06-16T13:00:00+00:00"

    # secondo append (nuova barra) non riscrive l'header
    rows2 = [dict(r, h1_bar_utc="2026-06-16T14:00:00+00:00") for r in rows]
    LF.append_rows(path, rows2)
    with open(path, encoding="utf-8") as f:
        content = f.read()
    assert content.count("ts_utc,h1_bar_utc") == 1
    assert LF.last_logged_h1_bar(path) == "2026-06-16T14:00:00+00:00"
