"""Test logger ed evaluator shadow d1w (5,6)."""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))

import eval_shadow_56 as EVAL
import update_shadow_56 as SHADOW
from fx_bias_radar import pairs as P
from fx_bias_radar.candles import Candle


def _candle(time, close=1.0):
    return Candle(
        time=time,
        o=close,
        h=close,
        l=close,
        c=close,
        volume=1,
        complete=True,
    )


class Shadow56Tests(unittest.TestCase):
    def test_shadow_uses_explicit_5_6_parameters(self):
        bars = {
            pair: [_candle("2026-07-30T10:00:00+00:00")]
            for pair in P.PAIRS
        }
        with patch.object(
            SHADOW.COMP,
            "daily_weekly_aligned_breakouts",
            return_value=[{"pair": "EURUSD", "dir": "LONG"}],
        ) as mocked:
            h1_bar, rows = SHADOW.shadow_signals(bars, {}, {})
        self.assertEqual(h1_bar, "2026-07-30T10:00:00+00:00")
        self.assertEqual(rows[0]["pair"], "EURUSD")
        self.assertEqual(mocked.call_args.kwargs["k_d"], 5)
        self.assertEqual(mocked.call_args.kwargs["k_w"], 6)
        self.assertEqual(mocked.call_args.kwargs["h1_window"], 12)

    def test_run_shadow_is_idempotent_for_same_h1_bar(self):
        bars = {
            pair: [_candle("2026-07-30T10:00:00+00:00")]
            for pair in P.PAIRS
        }
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, "shadow.csv")
            with patch.object(
                SHADOW,
                "shadow_signals",
                return_value=(
                    "2026-07-30T10:00:00+00:00",
                    [{"pair": "EURUSD", "dir": "LONG"}],
                ),
            ):
                first = SHADOW.run_shadow(bars, {}, {}, path)
                second = SHADOW.run_shadow(bars, {}, {}, path)
        self.assertEqual(first["written"], 1)
        self.assertEqual(second["written"], 0)

    def test_evaluator_requires_48_future_h1_bars(self):
        start = datetime(2026, 7, 1, tzinfo=timezone.utc)
        candles = []
        for index in range(60):
            time = start + timedelta(hours=index)
            candles.append(_candle(time.isoformat(), 1.0 + index / 1000))
        rows = [
            {
                "h1_bar_utc": candles[5].time,
                "pair": "EURUSD",
                "dir": "LONG",
            },
            {
                "h1_bar_utc": candles[20].time,
                "pair": "EURUSD",
                "dir": "LONG",
            },
        ]
        result = EVAL.evaluate_rows(
            rows,
            {"EURUSD": candles},
            start,
            start + timedelta(days=3),
        )
        self.assertEqual(result["horizons"]["12"]["n"], 1)
        self.assertEqual(result["excluded_without_48_h1"], 1)


if __name__ == "__main__":
    unittest.main()
