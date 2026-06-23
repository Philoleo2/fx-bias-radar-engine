"""Test avviso email allineate (composizione pura + gate event-driven)."""
from __future__ import annotations
import os, sys, importlib.util
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_S = importlib.util.spec_from_file_location("send_digest",
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                 "scripts", "send_digest.py"))
SD = importlib.util.module_from_spec(_S); _S.loader.exec_module(SD)


def test_compose_lists_aligned():
    payload = {"allineate": [{"pair": "AUDNZD", "dir": "LONG"},
                             {"pair": "EURUSD", "dir": "SHORT"}]}
    subject, body = SD.compose(payload)
    assert "2 rotture allineate" in subject
    assert "AUDNZD LONG" in body and "EURUSD SHORT" in body
    assert "consiglio di trade" in body


def test_compose_singular():
    subject, _ = SD.compose({"allineate": [{"pair": "AUDNZD", "dir": "LONG"}]})
    assert "1 rottura allineata" in subject
