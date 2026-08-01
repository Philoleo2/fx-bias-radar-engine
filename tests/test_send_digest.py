"""Test avviso email allineate (composizione pura + gate event-driven)."""
from __future__ import annotations
import importlib.util
import json
import os
import sys
import tempfile
import unittest
from unittest import mock
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


class TestSendDigestGate(unittest.TestCase):
    def test_main_skips_already_notified_bar(self):
        with tempfile.TemporaryDirectory() as tmp:
            snapshot = os.path.join(tmp, "snapshot.json")
            with open(snapshot, "w", encoding="utf-8") as f:
                json.dump({
                    "allineate": [{"pair": "CHFJPY", "dir": "SHORT"}],
                    "nuove_allineate": [],
                }, f)
            with (mock.patch.object(SD, "SNAPSHOT", snapshot),
                  mock.patch.object(sys, "argv", ["send_digest.py"]),
                  mock.patch.object(SD, "send_email") as send):
                self.assertEqual(SD.main(), 0)
                send.assert_not_called()

    def test_main_sends_once_for_new_bar(self):
        calls = [{"pair": "CHFJPY", "dir": "SHORT"}]
        with tempfile.TemporaryDirectory() as tmp:
            snapshot = os.path.join(tmp, "snapshot.json")
            with open(snapshot, "w", encoding="utf-8") as f:
                json.dump({"allineate": calls, "nuove_allineate": calls}, f)
            with (mock.patch.object(SD, "SNAPSHOT", snapshot),
                  mock.patch.object(sys, "argv", ["send_digest.py"]),
                  mock.patch.object(SD, "send_email") as send):
                self.assertEqual(SD.main(), 0)
                send.assert_called_once()
                self.assertIn("CHFJPY SHORT", send.call_args.args[1])
