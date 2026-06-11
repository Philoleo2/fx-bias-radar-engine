import json
import os
import subprocess
import sys
import tempfile
import unittest

from fx_bias_radar import scan_service as S


FIXTURES = os.path.join(
    os.path.dirname(__file__),
    "fixtures",
    "golden_2026H1",
)
ROOT = os.path.dirname(os.path.dirname(__file__))


class TestScanServiceDashboard(unittest.TestCase):
    def test_dashboard_payload_contract(self):
        report = S.run_scan_from_fixtures(FIXTURES, run_time_utc="2026-06-11T00:00:00+00:00")
        payload = S.dashboard_payload(report, source="fixtures")

        self.assertTrue(payload["ok"])
        self.assertEqual(payload["generated_at_utc"], report["run_time_utc"])
        self.assertEqual(payload["last_closed_h4_utc"], report["last_aligned_bar_utc"])
        self.assertEqual(payload["focus"], report["focus"])
        self.assertEqual(payload["pairs"], report["pairs"])
        self.assertIn("Radar di attenzione", payload["disclaimer"])
        self.assertIn("## Focus list", payload["markdown"])

    def test_cli_and_service_focus_match_on_fixtures(self):
        service_report = S.run_scan_from_fixtures(FIXTURES, run_time_utc="2026-06-11T00:00:00+00:00")
        with tempfile.TemporaryDirectory() as tmp:
            result = subprocess.run(
                [
                    sys.executable,
                    os.path.join(ROOT, "scripts", "run_h4_scan.py"),
                    "--fixtures",
                    FIXTURES,
                    "--out",
                    tmp,
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            json_files = [name for name in os.listdir(tmp) if name.endswith(".json")]
            self.assertEqual(len(json_files), 1)
            with open(os.path.join(tmp, json_files[0]), "r", encoding="utf-8") as f:
                cli_report = json.load(f)
        self.assertEqual(cli_report["focus"], service_report["focus"])


if __name__ == "__main__":
    unittest.main()
