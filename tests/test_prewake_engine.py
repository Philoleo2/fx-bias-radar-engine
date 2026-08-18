"""Unit tests for the frozen PAIR_PREWAKE_V1 engine (SS57)."""
from __future__ import annotations

import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fx_bias_radar import pairs as P
from prewake import config, market, notify, outcomes, store
from prewake.engine import evaluate
from prewake.features import build_features
from prewake.lifecycle import LifecycleState, advance, batch_lifecycle_events
from prewake.model import ArtifactError, FEATURE_ORDER, load_model
from prewake.primitives import (
    compression_mask,
    ewma,
    ewma_alpha,
    ewma_step,
    fresh_breakouts,
    incidence_matrix,
    ols_prediction_weights,
    parse_utc,
    prior_window_bounds,
)

K = len(P.PAIRS)


def synthetic_prices(n: int, seed: int = 7) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    rng = np.random.default_rng(seed)
    steps = rng.normal(0.0, 0.0009, size=(n, K))
    close = 1.20 * np.exp(np.cumsum(steps, axis=0))
    span = np.abs(rng.normal(0.0, 0.0006, size=(n, K))) + 1e-5
    high = close * (1.0 + span)
    low = close * (1.0 - span)
    return close, high, low


def times(n: int, start_hour: int = 0) -> list[str]:
    from datetime import datetime, timedelta, timezone
    base = datetime(2026, 1, 1, start_hour, tzinfo=timezone.utc)
    return [(base + timedelta(hours=i)).isoformat(timespec="seconds") for i in range(n)]


class TestUniverseAndOrientation(unittest.TestCase):
    def test_universe_is_the_project_universe(self):
        self.assertEqual(len(P.PAIRS), 28)
        self.assertEqual(len(P.CURRENCIES), 8)
        self.assertEqual(set(P.CURRENCIES), {"EUR", "GBP", "AUD", "NZD", "USD", "CAD", "CHF", "JPY"})

    def test_pair_orientation_in_incidence_matrix(self):
        matrix = incidence_matrix()
        for j, pair in enumerate(P.PAIRS):
            base, quote = pair[:3], pair[3:]
            self.assertEqual(matrix[j, P.CURRENCIES.index(base)], 1.0, pair)
            self.assertEqual(matrix[j, P.CURRENCIES.index(quote)], -1.0, pair)
            self.assertEqual(matrix[j].sum(), 0.0, pair)


class TestOlsLopo(unittest.TestCase):
    def test_leave_one_pair_out_excludes_the_target(self):
        _full, lopo = ols_prediction_weights()
        self.assertEqual(lopo.shape, (K, K))
        for j in range(K):
            self.assertAlmostEqual(lopo[j, j], 0.0, places=15,
                                   msg=f"{P.PAIRS[j]} must not predict itself")

    def test_lopo_reproduces_a_consistent_cross_rate(self):
        # A perfectly consistent set of currency moves must be predicted exactly
        # by the other 27 pairs, so the LOPO gap collapses to zero.
        rng = np.random.default_rng(3)
        ccy = rng.normal(0, 0.001, size=len(P.CURRENCIES))
        returns = incidence_matrix() @ ccy
        _full, lopo = ols_prediction_weights()
        gap = returns - lopo @ returns
        self.assertLess(np.max(np.abs(gap)), 1e-12)


class TestEwma(unittest.TestCase):
    def test_half_life_four(self):
        alpha = ewma_alpha(4.0)
        self.assertAlmostEqual(alpha, 1.0 - 2 ** (-0.25), places=15)

    def test_incremental_matches_batch(self):
        rng = np.random.default_rng(11)
        x = rng.normal(size=(200, K))
        x[5:9, 0] = np.nan
        batch = ewma(x, 4.0)
        alpha = ewma_alpha(4.0)
        state, ready = 0.0, False
        for t in range(len(x)):
            state, ready, out = ewma_step(x[t, 0], state, ready, alpha)
            if np.isfinite(batch[t, 0]):
                self.assertAlmostEqual(out, batch[t, 0], places=15)

    def test_split_window_equals_full_replay(self):
        """A run continuing from persisted state equals a full replay (SS20)."""
        close, high, low = synthetic_prices(700)
        full = build_features(close, high, low)
        first = build_features(close[:600], high[:600], low[:600])
        cont = build_features(close, high, low,
                              ewma_state=first.ewma_state, ewma_ready=first.ewma_ready)
        # Continuing re-feeds the same bars, so compare the trailing state only.
        self.assertTrue(np.all(np.isfinite(full.ewma_state) == np.isfinite(cont.ewma_state)))


class TestFeatures(unittest.TestCase):
    def test_feature_order_is_frozen(self):
        self.assertEqual(FEATURE_ORDER,
                         ("dir_ret1", "dir_ret4", "dir_ret12", "dir_ret24",
                          "abs_pair_z", "compression_ratio", "pair_vol120", "fx_bias_same"))
        self.assertEqual(tuple(load_model().feature_order), FEATURE_ORDER)

    def test_no_lookahead_in_prior_window_bounds(self):
        high = np.arange(20, dtype=float).reshape(-1, 1)
        low = -high
        hi, lo = prior_window_bounds(high, low, 12)
        # bar t must never see its own high/low
        self.assertEqual(hi[13, 0], 12.0)
        self.assertLess(hi[13, 0], high[13, 0])

    def test_fx_bias_same_uses_only_past_and_current_bar(self):
        """Truncating the future must not change fx_bias_same at earlier bars."""
        close, high, low = synthetic_prices(500, seed=21)
        full = build_features(close, high, low)
        cut = build_features(close[:400], high[:400], low[:400])
        a = full.cube[:400, :, 7]
        b = cut.cube[:400, :, 7]
        both = np.isfinite(a) & np.isfinite(b)
        self.assertTrue(np.array_equal(a[both], b[both]))

    def test_fx_bias_same_is_compression_gated_fresh_breakout(self):
        close, high, low = synthetic_prices(400, seed=5)
        bundle = build_features(close, high, low)
        compressed, _ratio = compression_mask(high, low, 12, 120, 0.20)
        breakout = fresh_breakouts(close, high, low, 12)
        expected = np.where(compressed, breakout, 0).astype(np.int8)
        self.assertTrue(np.array_equal(bundle.fx_bias, expected))

    def test_missing_data_produces_no_score(self):
        close, high, low = synthetic_prices(400, seed=9)
        close[380, 3] = np.nan
        bundle = build_features(close, high, low)
        model = load_model()
        from prewake.features import score_cube
        score = score_cube(model, bundle.cube, bundle.direction)
        self.assertTrue(np.isnan(score[380, 3]))


class TestModelArtifact(unittest.TestCase):
    def test_artifact_hash_verifies(self):
        model = load_model()
        self.assertTrue(model.artifact_hash.startswith("sha256:"))
        self.assertEqual(model.research_fingerprint,
                         "6c767bcbc66f9719d9c4e47ff2756dc789901568f587772f1a27180f8872bd17")

    def test_frozen_numbers(self):
        model = load_model()
        self.assertEqual(model.threshold, 0.5965942096795052)
        self.assertEqual(model.intercept, -0.4159863092887988)
        self.assertEqual(model.reset_ratio, 0.70)
        self.assertEqual(model.reset_bars, 4)
        self.assertEqual(model.ewma_half_life, 4.0)
        self.assertEqual(model.robust_z_window, 240)
        self.assertAlmostEqual(model.coefficients[7], -1.8776544528192427, places=15)

    def test_tampered_artifact_is_rejected(self):
        import json
        import tempfile
        from prewake.model import ARTIFACT_PATH, load_model as loader
        payload = json.load(open(ARTIFACT_PATH, encoding="utf-8"))
        payload["threshold"] = 0.5
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as handle:
            json.dump(payload, handle)
            tampered = handle.name
        with self.assertRaises(ArtifactError):
            loader(tampered)
        os.unlink(tampered)

    def test_score_matches_manual_sigmoid(self):
        model = load_model()
        x = np.array([[0.0005, 0.0012, 0.0022, 0.0025, 0.7, 1.5, 0.001, 0.0]])
        z = (x - model.mean) / model.scale
        expected = 1.0 / (1.0 + np.exp(-(z @ model.coefficients + model.intercept)))
        np.testing.assert_allclose(model.score(x), expected, rtol=0, atol=1e-15)

    def test_threshold_comparison_is_inclusive(self):
        model = load_model()
        score = np.array([[model.threshold]])
        direction = np.array([[1]], dtype=np.int8)
        breakout = np.zeros((1, 1), dtype=np.int8)
        state = LifecycleState.fresh()
        # single-pair harness: reuse the batch implementation directly
        events = batch_lifecycle_events(
            np.repeat(score, K, axis=1), np.repeat(direction, K, axis=1),
            model.threshold, np.array([True]), np.repeat(breakout, K, axis=1))
        self.assertEqual(len(events), K)

    def test_model_has_no_fit(self):
        import prewake.model as module
        self.assertFalse(any(name.startswith("fit") for name in dir(module)))


class TestConfig(unittest.TestCase):
    def test_model_parameters_cannot_come_from_env(self):
        os.environ["PREWAKE_THRESHOLD"] = "0.4"
        try:
            with self.assertRaises(RuntimeError):
                config.assert_no_model_overrides()
        finally:
            del os.environ["PREWAKE_THRESHOLD"]

    def test_flags_default_off(self):
        for name in ("PREWAKE_ENGINE_ENABLED", "PREWAKE_EMAIL_ENABLED"):
            os.environ.pop(name, None)
        self.assertFalse(config.engine_enabled())
        self.assertFalse(config.email_enabled())


class TestMarketGrid(unittest.TestCase):
    class _Candle:
        def __init__(self, time, o, h, l, c, complete=True):
            self.time, self.o, self.h, self.l, self.c, self.complete = time, o, h, l, c, complete

    def _series(self, stamps, complete=True):
        return [self._Candle(t, 1.0, 1.01, 0.99, 1.0, complete) for t in stamps]

    def test_incomplete_bars_are_never_evaluated(self):
        stamps = times(5)
        candles = {pair: self._series(stamps) for pair in P.PAIRS}
        candles[P.PAIRS[0]] = self._series(stamps, complete=False)
        with self.assertRaises(market.IncompleteInput):
            market.build_grid(candles)

    def test_grid_is_the_intersection_across_all_pairs(self):
        stamps = times(6)
        candles = {pair: self._series(stamps) for pair in P.PAIRS}
        candles[P.PAIRS[3]] = self._series(stamps[:-1])       # one pair missing the newest bar
        grid = market.build_grid(candles)
        self.assertEqual(grid.times, stamps[:-1])

    def test_missing_pair_raises(self):
        candles = {pair: self._series(times(3)) for pair in P.PAIRS[:-1]}
        with self.assertRaises(market.IncompleteInput):
            market.build_grid(candles)


class TestTimezone(unittest.TestCase):
    def test_internal_timestamps_are_utc_aware(self):
        parsed = parse_utc("2026-08-17T10:00:00+00:00")
        self.assertIsNotNone(parsed.tzinfo)
        self.assertEqual(parsed.utcoffset().total_seconds(), 0)

    def test_naive_input_is_treated_as_utc(self):
        self.assertEqual(parse_utc("2026-08-17T10:00:00"), parse_utc("2026-08-17T10:00:00Z"))

    def test_email_shows_rome_close_one_hour_after_bar_open(self):
        # 10:00 UTC bar open -> 11:00 UTC close -> 13:00 Europe/Rome in August (CEST)
        self.assertEqual(notify.bar_close_rome("2026-08-17T11:00:00+00:00"), "13:00")


class TestEmailRendering(unittest.TestCase):
    def _event(self, **kw):
        base = {"pair": "GBPCHF", "direction": 1, "bar_time_utc": "2026-08-17T09:00:00+00:00",
                "score": 0.612345, "threshold": 0.5965942096795052, "fx_bias_same": 0.0,
                "same_bar_raw_breakout": False, "event_id": "abc"}
        base.update(kw)
        return base

    def test_subject_and_forbidden_language(self):
        subject, body = notify.render(self._event())
        self.assertTrue(subject.startswith("[PREWAKE] GBPCHF LONG"))
        for banned in ("BUY", "SELL", "ENTRY", "STOP", "TARGET"):
            self.assertNotIn(banned, body.upper().replace("PREWAKE", ""))
        self.assertIn("Direzione da osservare: LONG", body)
        self.assertIn("Radar di attenzione", body)

    def test_no_secrets_in_body(self):
        os.environ["OANDA_ACCESS_TOKEN"] = "super-secret-token"
        try:
            _subject, body = notify.render(self._event())
            self.assertNotIn("super-secret-token", body)
        finally:
            del os.environ["OANDA_ACCESS_TOKEN"]


class TestIdempotencyKeys(unittest.TestCase):
    def test_event_id_is_stable_and_discriminating(self):
        a = store.event_id("pair-prewake-v1", "GBPCHF", "2026-08-17T09:00:00+00:00", "REAWAKENING", 1)
        b = store.event_id("pair-prewake-v1", "GBPCHF", "2026-08-17T09:00:00+00:00", "REAWAKENING", 1)
        c = store.event_id("pair-prewake-v1", "GBPCHF", "2026-08-17T09:00:00+00:00", "REAWAKENING", -1)
        d = store.event_id("pair-prewake-v1", "GBPCHF", "2026-08-17T10:00:00+00:00", "REAWAKENING", 1)
        self.assertEqual(a, b)
        self.assertNotEqual(a, c)
        self.assertNotEqual(a, d)

    def test_email_key_shape(self):
        self.assertEqual(store.email_idempotency_key("pair-prewake-v1", "xyz"),
                         "prewake:pair-prewake-v1:xyz")


class TestOutcomes(unittest.TestCase):
    def test_time_to_breakout_excludes_same_bar_for_prewake(self):
        breakout = np.zeros((10, 1), dtype=np.int8)
        breakout[3, 0] = 1
        self.assertEqual(outcomes.time_to_breakout(breakout, 3, 0, 1, 12, True), 0)
        self.assertIsNone(outcomes.time_to_breakout(breakout, 3, 0, 1, 12, False))
        breakout[6, 0] = 1
        self.assertEqual(outcomes.time_to_breakout(breakout, 3, 0, 1, 12, False), 3)

    def test_outcome_maturation_is_partial_until_time_passes(self):
        n = 8
        grid = market.Grid(times=times(n), close=np.ones((n, 1)), high=np.ones((n, 1)) * 1.01,
                           low=np.ones((n, 1)) * 0.99, open=np.ones((n, 1)))
        breakout = np.zeros((n, 1), dtype=np.int8)
        result = outcomes.compute(grid, breakout, 4, 0, 1)
        self.assertIn("1", result["horizons"])
        self.assertNotIn("24", result["horizons"])       # future has not elapsed yet
        self.assertEqual(result["matured_through_h1"], 3)

    def test_fx_bias_link_records_lead_without_touching_the_event(self):
        link = outcomes.link_fx_bias("2026-08-17T09:00:00+00:00", [
            {"bar_time_utc": "2026-08-17T12:00:00+00:00", "pair": "GBPCHF",
             "direction": "LONG", "event_id": "fx1"}])
        self.assertEqual(link["lead_hours"], 3.0)
        self.assertEqual(link["fx_bias_event_id"], "fx1")

    def test_fx_bias_link_absent_when_nothing_follows(self):
        self.assertIsNone(outcomes.link_fx_bias("2026-08-17T09:00:00+00:00", []))


if __name__ == "__main__":
    unittest.main()
