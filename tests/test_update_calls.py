"""Test del marker che rende il digest idempotente per barra H1."""
from __future__ import annotations

import importlib.util
import json
import os
import tempfile
import unittest
from unittest import mock


_SPEC = importlib.util.spec_from_file_location(
    "update_calls",
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                 "scripts", "update_calls.py"),
)
UC = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(UC)


class TestUpdateCallsMarker(unittest.TestCase):
    def test_nuove_allineate_only_on_first_run_for_h1_bar(self):
        with tempfile.TemporaryDirectory() as tmp:
            snapshot = os.path.join(tmp, "snapshot.json")
            calls_log = os.path.join(tmp, "calls.csv")
            payload = {
                "h1_last_bar_utc": "2026-07-31T20:00:00+00:00",
                "generated_at_utc": "2026-08-01T05:05:00+00:00",
                "allineate": [{"pair": "CHFJPY", "dir": "SHORT"}],
            }
            with open(snapshot, "w", encoding="utf-8") as f:
                json.dump(payload, f)
            with (mock.patch.object(UC, "SNAPSHOT", snapshot),
                  mock.patch.object(UC, "CALLS_LOG", calls_log)):
                self.assertEqual(UC.main(), 0)
                with open(snapshot, encoding="utf-8") as f:
                    first = json.load(f)
                self.assertEqual(first["nuove_allineate"], payload["allineate"])

                self.assertEqual(UC.main(), 0)
                with open(snapshot, encoding="utf-8") as f:
                    repeated = json.load(f)
                self.assertEqual(repeated["nuove_allineate"], [])
