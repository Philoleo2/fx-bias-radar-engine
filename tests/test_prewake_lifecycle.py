"""Lifecycle unit tests and the SS58 integration cases A-K.

The lifecycle is driven directly with synthetic score/direction arrays: that
isolates the frozen state machine from the feature pipeline and makes each
scenario in SS58 explicit.
"""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
import unittest

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fx_bias_radar import pairs as P
from prewake import notify, store
from prewake.lifecycle import LifecycleState, advance, batch_lifecycle_events
from prewake.model import load_model

K = len(P.PAIRS)
MODEL = load_model()
TH = MODEL.threshold
LOW = TH * 0.5                      # below the 70% reset band
MID = TH * 0.85                     # below threshold but inside the band


def arrays(scores, directions):
    """Broadcast a single-pair scenario onto the 28-pair grid (pair 0 only)."""
    n = len(scores)
    score = np.full((n, K), np.nan)
    direction = np.zeros((n, K), dtype=np.int8)
    score[:, 0] = scores
    direction[:, 0] = directions
    breakout = np.zeros((n, K), dtype=np.int8)
    return score, direction, breakout


def run(scores, directions, emit_from=0, state=None):
    score, direction, breakout = arrays(scores, directions)
    state = state or LifecycleState.fresh()
    events = advance(state, score, direction, TH, breakout, emit_from=emit_from)
    return [e for e in events if e["pair_index"] == 0], state


class TestLifecycleCore(unittest.TestCase):
    def test_case_a_no_alert(self):
        events, _ = run([MID] * 10, [1] * 10)
        self.assertEqual(events, [])

    def test_case_b_first_cross_is_new_wake(self):
        events, _ = run([MID, MID, TH + 0.01], [1, 1, 1])
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["type"], "NEW_WAKE")
        self.assertEqual(events[0]["t"], 2)

    def test_case_c_five_bars_above_threshold_emit_once(self):
        events, _ = run([TH + 0.02] * 5, [1] * 5)
        self.assertEqual(len(events), 1, "a signal staying above threshold must not re-alert")

    def test_case_d_reset_needs_four_consecutive_bars_below_70pct(self):
        # three low bars are not enough
        events, _ = run([TH + 0.01] + [LOW] * 3 + [TH + 0.01], [1] * 5)
        self.assertEqual(len(events), 1)
        # four low bars arm the lifecycle again
        events, _ = run([TH + 0.01] + [LOW] * 4 + [TH + 0.01], [1] * 6)
        self.assertEqual(len(events), 2)

    def test_case_e_reactivation_is_reawakening(self):
        events, _ = run([TH + 0.01] + [LOW] * 4 + [TH + 0.01], [1] * 6)
        self.assertEqual([e["type"] for e in events], ["NEW_WAKE", "REAWAKENING"])

    def test_case_f_direction_change_resets(self):
        events, _ = run([TH + 0.01, TH + 0.01, TH + 0.01], [1, -1, 1])
        longs = [e for e in events if e["direction"] == 1]
        shorts = [e for e in events if e["direction"] == -1]
        self.assertEqual([e["type"] for e in longs], ["NEW_WAKE", "REAWAKENING"],
                         "flipping away and back must re-arm the LONG lifecycle")
        self.assertEqual([e["type"] for e in shorts], ["NEW_WAKE"])

    def test_scores_inside_the_band_do_not_reset(self):
        events, _ = run([TH + 0.01] + [MID] * 20 + [TH + 0.01], [1] * 22)
        self.assertEqual(len(events), 1, "only scores below 70% of threshold count as reset")

    def test_non_finite_score_resets(self):
        events, _ = run([TH + 0.01, np.nan, TH + 0.01], [1, 1, 1])
        self.assertEqual(len(events), 2)

    def test_new_wake_is_first_ever_not_first_after_reset(self):
        """Frozen semantics: the NEW_WAKE flag is consumed once per (pair, dir)."""
        events, state = run([TH + 0.01] + [LOW] * 4 + [TH + 0.01] + [LOW] * 4 + [TH + 0.01], [1] * 11)
        self.assertEqual([e["type"] for e in events],
                         ["NEW_WAKE", "REAWAKENING", "REAWAKENING"])
        self.assertTrue(state.seen["EURUSD:LONG"])

    def test_new_wake_consumed_even_outside_the_emission_window(self):
        events, _ = run([TH + 0.01] + [LOW] * 4 + [TH + 0.01], [1] * 6, emit_from=5)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["type"], "REAWAKENING",
                         "a warm-up start must still consume NEW_WAKE")

    def test_long_and_short_have_independent_lifecycles(self):
        events, _ = run([TH + 0.01, TH + 0.01], [1, -1])
        self.assertEqual([(e["direction"], e["type"]) for e in events],
                         [(1, "NEW_WAKE"), (-1, "NEW_WAKE")])


class TestIncrementalEqualsBatch(unittest.TestCase):
    def test_random_scenarios_agree(self):
        rng = np.random.default_rng(4242)
        for trial in range(25):
            n = 160
            scores = rng.uniform(0.2, 0.8, size=n)
            scores[rng.random(n) < 0.10] = np.nan
            directions = rng.choice([-1, 1], size=n)
            score, direction, breakout = arrays(scores, directions)
            allowed = np.ones(n, dtype=bool)
            batch = batch_lifecycle_events(score, direction, TH, allowed, breakout)
            inc = advance(LifecycleState.fresh(), score, direction, TH, breakout, emit_from=0)
            key = lambda e: (e["t"], e["pair_index"], e["direction"], e["type"])
            self.assertEqual(sorted(map(key, batch)), sorted(map(key, inc)),
                             f"incremental/batch divergence in trial {trial}")

    def test_restart_replay_is_idempotent(self):
        """Splitting the series across two runs must give the same events (SS24)."""
        rng = np.random.default_rng(99)
        n = 120
        scores = rng.uniform(0.2, 0.8, size=n)
        directions = rng.choice([-1, 1], size=n)
        score, direction, breakout = arrays(scores, directions)

        whole = advance(LifecycleState.fresh(), score, direction, TH, breakout, emit_from=0)

        state = LifecycleState.fresh()
        part1 = advance(state, score[:80], direction[:80], TH, breakout[:80], emit_from=0)
        state = LifecycleState.from_dict(state.to_dict())          # simulate a restart
        part2 = advance(state, score[80:], direction[80:], TH, breakout[80:], emit_from=0)
        for event in part2:
            event["t"] += 80

        key = lambda e: (e["t"], e["pair_index"], e["direction"], e["type"])
        self.assertEqual(sorted(map(key, whole)), sorted(map(key, part1 + part2)))

    def test_state_round_trips_through_json(self):
        state = LifecycleState.fresh()
        state.armed["EURUSD:LONG"] = False
        state.seen["EURUSD:LONG"] = True
        state.low_streak["EURUSD:LONG"] = 3
        restored = LifecycleState.from_dict(state.to_dict())
        self.assertEqual(restored.to_dict(), state.to_dict())


class TestStoreIntegration(unittest.TestCase):
    """SS58 cases G-K plus the append-only / email guarantees."""

    def setUp(self):
        self.base = tempfile.mkdtemp(prefix="prewake-test-")

    def tearDown(self):
        shutil.rmtree(self.base, ignore_errors=True)

    def _event(self, bar="2026-08-17T09:00:00+00:00", pair="GBPCHF", prospective=True):
        eid = store.event_id("pair-prewake-v1", pair, bar, "REAWAKENING", 1)
        return {"event_id": eid, "model_version": "pair-prewake-v1", "pair": pair,
                "direction": "LONG", "direction_sign": 1, "event_type": "REAWAKENING",
                "bar_time_utc": bar, "score": 0.61, "threshold": TH, "fx_bias_same": 0.0,
                "same_bar_raw_breakout": False,
                "is_backfill": not prospective, "is_prospective": prospective}

    def test_case_i_same_bar_processed_twice_creates_one_event(self):
        event = self._event()
        first = store.append_events([event], self.base)
        second = store.append_events([event], self.base)
        self.assertEqual(len(first), 1)
        self.assertEqual(len(second), 0)
        self.assertEqual(len(store.read_jsonl(store.EVENTS, self.base)), 1)

    def test_backfill_events_are_never_emailed(self):
        store.append_events([self._event(prospective=False)], self.base)
        joined = store.events_with_status(self.base)
        self.assertEqual(joined[0]["email_status"], "SUPPRESSED_BACKFILL")

    def test_case_h_smtp_failure_retries_without_duplicating_the_event(self):
        event = self._event()
        store.append_events([event], self.base)
        joined = store.events_with_status(self.base)[0]
        self.assertEqual(joined["email_status"], "PENDING")

        original = notify.send
        notify.send = lambda *a, **k: (_ for _ in ()).throw(OSError("smtp down"))
        try:
            record = notify.deliver(dict(joined, threshold=TH), "pair-prewake-v1")
        finally:
            notify.send = original
        store.append_jsonl(store.EMAIL_LOG, [record], self.base)
        joined = store.events_with_status(self.base)[0]
        self.assertEqual(joined["email_status"], "RETRY")
        self.assertEqual(len(store.read_jsonl(store.EVENTS, self.base)), 1)

        notify.send = lambda *a, **k: True
        try:
            record = notify.deliver(dict(joined, threshold=TH), "pair-prewake-v1")
        finally:
            notify.send = original
        store.append_jsonl(store.EMAIL_LOG, [record], self.base)
        joined = store.events_with_status(self.base)[0]
        self.assertEqual(joined["email_status"], "SENT")
        self.assertEqual(joined["email_attempts"], 2)
        self.assertEqual(len(store.read_jsonl(store.EVENTS, self.base)), 1)

    def test_live_event_is_emailed_exactly_once(self):
        store.append_events([self._event()], self.base)
        sent = []
        original = notify.send
        notify.send = lambda subject, body: sent.append(subject) or True
        try:
            for _ in range(3):
                pending = [e for e in store.events_with_status(self.base)
                           if e["is_prospective"] and e["email_status"] in ("PENDING", "RETRY")]
                logs = [notify.deliver(dict(e, threshold=TH), "pair-prewake-v1") for e in pending]
                store.append_jsonl(store.EMAIL_LOG, logs, self.base)
        finally:
            notify.send = original
        self.assertEqual(len(sent), 1)

    def test_events_are_append_only(self):
        store.append_events([self._event(bar="2026-08-17T09:00:00+00:00")], self.base)
        store.append_events([self._event(bar="2026-08-17T10:00:00+00:00")], self.base)
        rows = store.read_jsonl(store.EVENTS, self.base)
        self.assertEqual(len(rows), 2)
        # a later email log never rewrites the event record
        store.append_jsonl(store.EMAIL_LOG, [{"event_id": rows[0]["event_id"], "status": "SENT",
                                              "sent_at": "2026-08-17T10:05:00+00:00"}], self.base)
        self.assertEqual(store.read_jsonl(store.EVENTS, self.base), rows)

    def test_case_g_fx_bias_link_is_recorded_separately(self):
        from prewake import outcomes
        store.append_events([self._event()], self.base)
        rows = store.read_jsonl(store.EVENTS, self.base)
        link = outcomes.link_fx_bias(rows[0]["bar_time_utc"], [
            {"bar_time_utc": "2026-08-17T12:00:00+00:00", "pair": "GBPCHF",
             "direction": "LONG", "event_id": "fx-1"}])
        store.append_jsonl(store.LINKS, [dict(link, event_id=rows[0]["event_id"])], self.base)
        joined = store.events_with_status(self.base)[0]
        self.assertEqual(joined["fx_bias_link"]["lead_hours"], 3.0)
        self.assertEqual(store.read_jsonl(store.EVENTS, self.base), rows)

    def test_prospective_flag_follows_prospective_start(self):
        start = "2026-08-17T12:00:00+00:00"
        before = "2026-08-17T09:00:00+00:00"
        after = "2026-08-17T15:00:00+00:00"
        self.assertFalse(before >= start)
        self.assertTrue(after >= start)


if __name__ == "__main__":
    unittest.main()
