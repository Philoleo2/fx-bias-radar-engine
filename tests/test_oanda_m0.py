import os
import tempfile
import unittest
from unittest.mock import patch

from fx_bias_radar.config import DEFAULT_PRACTICE_URL, load_oanda_config, mask_secret
from fx_bias_radar.pairs import PAIRS_28, normalize_instrument


class OandaM0Tests(unittest.TestCase):
    def test_pair_universe_has_28_unique_pairs(self) -> None:
        self.assertEqual(len(PAIRS_28), 28)
        self.assertEqual(len(set(PAIRS_28)), 28)

    def test_normalize_instrument(self) -> None:
        self.assertEqual(normalize_instrument("eurusd"), "EUR_USD")
        self.assertEqual(normalize_instrument("EUR/USD"), "EUR_USD")
        self.assertEqual(normalize_instrument("usd-chf"), "USD_CHF")

    def test_load_config_defaults_to_practice(self) -> None:
        clean_env = {
            key: value
            for key, value in os.environ.items()
            if not key.startswith("OANDA_")
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(os.environ, clean_env, clear=True):
                config = load_oanda_config(os.path.join(tmpdir, ".env"))

        self.assertEqual(config.env, "practice")
        self.assertEqual(config.base_url, DEFAULT_PRACTICE_URL)
        self.assertIsNone(config.account_id)
        self.assertEqual(config.access_token, "")

    def test_mask_secret(self) -> None:
        self.assertEqual(mask_secret(""), "<missing>")
        self.assertEqual(mask_secret("abcd1234wxyz"), "abcd...wxyz")


if __name__ == "__main__":
    unittest.main()
