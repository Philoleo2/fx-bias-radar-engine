import unittest

from fx_bias_radar.dashboard import is_authorized, pairs_to_csv, sanitize_error


class TestDashboardSecurity(unittest.TestCase):
    def test_bearer_auth(self):
        self.assertTrue(is_authorized("Bearer secret-token", "secret-token"))
        self.assertFalse(is_authorized("Bearer wrong", "secret-token"))
        self.assertFalse(is_authorized("secret-token", "secret-token"))
        self.assertFalse(is_authorized("Bearer secret-token", ""))
        self.assertFalse(is_authorized(None, "secret-token"))

    def test_sanitize_error_redacts_known_secret(self):
        msg = sanitize_error("OANDA failed for tok-123", ["tok-123"])
        self.assertNotIn("tok-123", msg)
        self.assertIn("<redacted>", msg)

    def test_pairs_to_csv(self):
        csv = pairs_to_csv([
            {
                "pair": "EURAUD",
                "bias": "LONG",
                "tipo": "RESUME",
                "stato": "ATTIVO",
                "score": 100,
                "forte": "EUR +",
                "debole": "AUD -",
                "spread": 1.9,
                "note": "watch",
                "age": 5,
            }
        ])
        self.assertIn("pair,bias,tipo,stato,score", csv)
        self.assertIn("EURAUD", csv)


if __name__ == "__main__":
    unittest.main()
