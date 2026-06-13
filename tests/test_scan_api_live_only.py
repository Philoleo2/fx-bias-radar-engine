import os
import unittest
from unittest.mock import patch

from api import scan as scan_api


class TestScanApiLiveOnly(unittest.TestCase):
    def setUp(self):
        self._env = dict(os.environ)
        scan_api._CACHE.update({"key": None, "created": 0.0, "payload": None})

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self._env)
        scan_api._CACHE.update({"key": None, "created": 0.0, "payload": None})

    def test_missing_oanda_token_does_not_return_actions_fallback(self):
        os.environ.pop("OANDA_ACCESS_TOKEN", None)
        os.environ["CACHE_SECONDS"] = "0"
        with self.assertRaisesRegex(RuntimeError, "OANDA_ACCESS_TOKEN"):
            scan_api.build_scan_payload()

    def test_oanda_failure_does_not_return_actions_fallback(self):
        os.environ["OANDA_ACCESS_TOKEN"] = "secret-token"
        os.environ["OANDA_ENV"] = "practice"
        os.environ["CACHE_SECONDS"] = "0"
        with patch.object(
            scan_api.S,
            "run_scan_from_oanda",
            side_effect=RuntimeError("network down"),
        ), patch.object(scan_api.S, "load_latest_actions_report") as fallback:
            with self.assertRaisesRegex(RuntimeError, "OANDA live non disponibile"):
                scan_api.build_scan_payload()
            fallback.assert_not_called()

    def test_default_dashboard_scan_uses_closed_oanda(self):
        # FR039: il default operativo torna alla barra H4 CHIUSA (no repaint).
        # L'intrabar resta raggiungibile solo via mode="intrabar".
        os.environ["OANDA_ACCESS_TOKEN"] = "secret-token"
        os.environ["OANDA_ENV"] = "practice"
        os.environ["CACHE_SECONDS"] = "0"
        report = {
            "run_time_utc": "2026-06-11T19:30:00+00:00",
            "analyzed_bar_utc": "2026-06-11T13:00:00+00:00",
            "analyzed_bar_close_utc": "2026-06-11T17:00:00+00:00",
            "bar_status": "closed",
            "last_complete_bar_utc": "2026-06-11T13:00:00+00:00",
            "last_complete_bar_close_utc": "2026-06-11T17:00:00+00:00",
            "last_aligned_bar_utc": "2026-06-11T13:00:00+00:00",
            "last_closed_bar_utc": "2026-06-11T17:00:00+00:00",
            "misaligned_pairs": [],
            "focus": [],
            "events_this_bar": [],
            "hidden_this_bar": [],
            "pairs": [],
            "disclaimer": "Radar di attenzione: decisione sulle linee manuali.",
        }
        with patch.object(scan_api.S, "run_scan_from_oanda", return_value=report) as run:
            payload = scan_api.build_scan_payload()
        run.assert_called_once()
        self.assertFalse(run.call_args.kwargs["include_incomplete"])
        self.assertEqual(payload["requested_mode"], "closed")
        self.assertEqual(payload["bar_status"], "closed")

    def test_intrabar_mode_still_available_opt_in(self):
        # L'anteprima intrabar resta disponibile esplicitamente.
        os.environ["OANDA_ACCESS_TOKEN"] = "secret-token"
        os.environ["OANDA_ENV"] = "practice"
        os.environ["CACHE_SECONDS"] = "0"
        report = {
            "run_time_utc": "2026-06-11T19:30:00+00:00",
            "analyzed_bar_utc": "2026-06-11T17:00:00+00:00",
            "analyzed_bar_close_utc": "2026-06-11T21:00:00+00:00",
            "bar_status": "forming",
            "last_complete_bar_utc": "2026-06-11T13:00:00+00:00",
            "last_complete_bar_close_utc": "2026-06-11T17:00:00+00:00",
            "last_aligned_bar_utc": "2026-06-11T17:00:00+00:00",
            "last_closed_bar_utc": "2026-06-11T17:00:00+00:00",
            "misaligned_pairs": [],
            "focus": [],
            "events_this_bar": [],
            "hidden_this_bar": [],
            "pairs": [],
            "disclaimer": "Radar di attenzione: decisione sulle linee manuali.",
        }
        with patch.object(scan_api.S, "run_scan_from_oanda", return_value=report) as run:
            payload = scan_api.build_scan_payload(mode="intrabar")
        run.assert_called_once()
        self.assertTrue(run.call_args.kwargs["include_incomplete"])
        self.assertEqual(payload["requested_mode"], "intrabar")
        self.assertEqual(payload["bar_status"], "forming")

    def test_closed_mode_keeps_incomplete_bars_out(self):
        os.environ["OANDA_ACCESS_TOKEN"] = "secret-token"
        os.environ["OANDA_ENV"] = "practice"
        os.environ["CACHE_SECONDS"] = "0"
        report = {
            "run_time_utc": "2026-06-11T19:30:00+00:00",
            "analyzed_bar_utc": "2026-06-11T13:00:00+00:00",
            "analyzed_bar_close_utc": "2026-06-11T17:00:00+00:00",
            "bar_status": "closed",
            "last_complete_bar_utc": "2026-06-11T13:00:00+00:00",
            "last_complete_bar_close_utc": "2026-06-11T17:00:00+00:00",
            "last_aligned_bar_utc": "2026-06-11T13:00:00+00:00",
            "last_closed_bar_utc": "2026-06-11T17:00:00+00:00",
            "misaligned_pairs": [],
            "focus": [],
            "events_this_bar": [],
            "hidden_this_bar": [],
            "pairs": [],
            "disclaimer": "Radar di attenzione: decisione sulle linee manuali.",
        }
        with patch.object(scan_api.S, "run_scan_from_oanda", return_value=report) as run:
            payload = scan_api.build_scan_payload(mode="closed")
        run.assert_called_once()
        self.assertFalse(run.call_args.kwargs["include_incomplete"])
        self.assertEqual(payload["requested_mode"], "closed")
        self.assertEqual(payload["bar_status"], "closed")


if __name__ == "__main__":
    unittest.main()
