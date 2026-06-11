import os
import tempfile
import unittest
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import patch

from fx_bias_radar import oanda_fetch
from fx_bias_radar.config import (
    DEFAULT_PRACTICE_URL,
    OandaConfig,
    load_oanda_config,
    mask_secret,
)
from fx_bias_radar.oanda import OandaClient
from fx_bias_radar.pairs import PAIRS_28, normalize_instrument


def _raw_candle(time: str, complete: bool):
    return SimpleNamespace(
        time=datetime.fromisoformat(time),
        open=1.0,
        high=1.1,
        low=0.9,
        close=1.0,
        volume=100,
        complete=complete,
    )


class _FakeOandaClient:
    def __init__(self, candles):
        self.candles_out = candles
        self.calls = []

    def candles(self, *args, **kwargs):
        self.calls.append(kwargs)
        return self.candles_out


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

    def test_oanda_client_sends_to_time_with_count(self) -> None:
        client = OandaClient(OandaConfig("practice", DEFAULT_PRACTICE_URL, "token"))
        with patch.object(client, "_request_json", return_value={"candles": []}) as request:
            client.candles("USD_CHF", count=6, to_time="2026-06-11T20:00:00Z")

        params = request.call_args.kwargs["params"]
        self.assertEqual(params["count"], "6")
        self.assertEqual(params["to"], "2026-06-11T20:00:00Z")

    def test_fetch_h4_intrabar_keeps_incomplete_candle(self) -> None:
        fake_client = _FakeOandaClient([
            _raw_candle("2026-06-11T09:00:00+00:00", True),
            _raw_candle("2026-06-11T13:00:00+00:00", True),
            _raw_candle("2026-06-11T17:00:00+00:00", False),
        ])

        with patch.object(oanda_fetch, "_client_for", return_value=fake_client):
            candles = oanda_fetch.fetch_h4(
                "USD_CHF",
                "token",
                count=2,
                include_incomplete=True,
            )

        self.assertEqual(fake_client.calls[0]["count"], 3)
        self.assertIsNotNone(fake_client.calls[0]["to_time"])
        self.assertEqual(len(candles), 3)
        self.assertFalse(candles[-1].complete)

    def test_fetch_h4_intrabar_trims_extra_complete_candle(self) -> None:
        fake_client = _FakeOandaClient([
            _raw_candle("2026-06-11T05:00:00+00:00", True),
            _raw_candle("2026-06-11T09:00:00+00:00", True),
            _raw_candle("2026-06-11T13:00:00+00:00", True),
        ])

        with patch.object(oanda_fetch, "_client_for", return_value=fake_client):
            candles = oanda_fetch.fetch_h4(
                "USD_CHF",
                "token",
                count=2,
                include_incomplete=True,
            )

        self.assertEqual(len(candles), 2)
        self.assertEqual(candles[0].time, "2026-06-11T09:00:00+00:00")


if __name__ == "__main__":
    unittest.main()
