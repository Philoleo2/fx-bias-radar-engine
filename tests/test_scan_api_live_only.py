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


if __name__ == "__main__":
    unittest.main()
