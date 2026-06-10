"""Synthetic regression tests for every validated engine mechanism.

Each test isolates one rule of the v1.1 engine (FR006..FR025 history):
RESUME trigger, anti-flip, strong-opposite bypass (live + post-death),
post-death TTL + net takeover *1.10, protective ESTESO peak across TTL
expiry (the FR017/FR018 case), ROT bypass, differentiated death floors,
and display-only dedup. Thresholds are the validated defaults: any change
that breaks these tests is an engine regression.
"""

import unittest

from fx_bias_radar.engine import EngineParams, run_pair
from helpers_synthetic import flat, make_frames, ramp


def run(specs):
    return run_pair("EURUSD", make_frames(specs))


def attention_bars(results, direction=None, ev_type=None):
    out = []
    for r in results:
        if not r.attention_event:
            continue
        if direction and r.raw_dir != direction:
            continue
        if ev_type and r.raw_type != ev_type:
            continue
        out.append(r)
    return out


def ramp_steps(start, stop, step):
    vals = []
    v = start
    while (step > 0 and v <= stop + 1e-9) or (step < 0 and v >= stop - 1e-9):
        vals.append(round(v, 4))
        v += step
    return vals


class TestResumeTrigger(unittest.TestCase):
    def test_resume_long_fires_and_panel_follows(self):
        specs = (flat(14) + ramp([0.6, 1.0, 1.4, 1.8, 2.05])
                 + ramp([1.9, 1.75, 1.6]) + ramp([1.95]))
        res = run(specs)
        events = attention_bars(res, "LONG", "RESUME")
        self.assertTrue(events, "no LONG RESUME attention event fired")
        last = res[-1]
        self.assertTrue(last.display_active)
        self.assertEqual(last.display_dir, "LONG")
        self.assertEqual(last.panel_bias, "LONG")
        self.assertIn(last.panel_stato, ("NUOVO", "ATTIVO", "ESTESO"))

    def test_flat_pair_stays_nessuno(self):
        res = run(flat(60, s=0.2))
        self.assertFalse(any(r.attention_event for r in res))
        self.assertEqual(res[-1].panel_stato, "NESSUNO")
        self.assertEqual(res[-1].panel_bias, "-")


class TestAntiFlip(unittest.TestCase):
    """FR008/FR010: opposite RESUME below the regime peak is blocked."""

    def _base_long_regime(self):
        # slow ramp 0.2 -> 3.5: never ESTESO (extension stays < 1.20)
        return flat(14) + ramp(ramp_steps(0.35, 3.5, 0.15))

    def test_weak_opposite_resume_blocked(self):
        specs = self._base_long_regime() + [
            {"s": 0.9}, {"s": -1.2, "fav": "SHORT"}, {"s": -1.5, "fav": "SHORT"}]
        res = run(specs)
        last = res[-1]
        self.assertEqual(last.raw_dir, "SHORT")
        self.assertEqual(last.raw_type, "RESUME")
        self.assertTrue(last.anti_flip_block)
        self.assertFalse(last.attention_event)
        self.assertEqual(last.hidden_reason, "anti-flip")

    def test_strong_opposite_live_bypasses_anti_flip(self):
        # FR022/FR024: spread 3.2 >= strongOppositeFloor 3.0 but < peak 3.5
        specs = self._base_long_regime() + [
            {"s": 0.9}, {"s": -1.2, "fav": "SHORT"}, {"s": -3.2, "fav": "SHORT"}]
        res = run(specs)
        last = res[-1]
        self.assertEqual(last.raw_dir, "SHORT")
        self.assertTrue(last.strong_live_opposite)
        self.assertFalse(last.anti_flip_block)
        self.assertFalse(last.takeover_ok, "3.2 < peak 3.5: must pass via strong bypass")
        self.assertTrue(last.attention_event)

    def test_opposite_rot_always_free(self):
        specs = self._base_long_regime() + [
            {"s": -0.5, "zq": -0.7, "rot": "SHORT"}]
        res = run(specs)
        last = res[-1]
        self.assertEqual(last.raw_type, "ROT")
        self.assertEqual(last.raw_dir, "SHORT")
        self.assertFalse(last.anti_flip_block)
        self.assertTrue(last.attention_event)


class TestPostDeath(unittest.TestCase):
    """FR013/FR015/FR016: ESTESO death memory, TTL, net takeover *1.10."""

    def _dead_long_3(self):
        # fast ramp -> ESTESO touch with peak 3.0, then 4 bars < neutralFloor
        return (flat(14) + ramp([0.5, 1.0, 1.6, 2.2, 2.8, 3.0])
                + flat(4, s=0.2))

    def test_weak_opposite_hidden_in_ttl(self):
        specs = self._dead_long_3() + [
            {"s": -1.0, "fav": "SHORT"}, {"s": -1.6, "fav": "SHORT"}]
        res = run(specs)
        last = res[-1]
        self.assertEqual(last.raw_dir, "SHORT")
        self.assertTrue(last.post_death_hidden)
        self.assertFalse(last.attention_event)
        self.assertAlmostEqual(last.effective_dead_peak, 3.0, places=6)
        self.assertAlmostEqual(last.post_death_takeover_level, 3.3, places=6)

    def test_strong_post_death_bypass_between_3_and_takeover(self):
        # FR024: 3.1 >= 3.0 (strong) but < 3.3 (takeover): must show via bypass
        specs = self._dead_long_3() + [
            {"s": -1.6, "fav": "SHORT"}, {"s": -2.2, "fav": "SHORT"},
            {"s": -3.1, "fav": "SHORT"}]
        res = run(specs)
        last = res[-1]
        self.assertTrue(last.strong_post_death_opposite)
        self.assertFalse(last.post_death_takeover_ok)
        self.assertTrue(last.attention_event)

    def test_net_takeover_accepted(self):
        specs = self._dead_long_3() + [
            {"s": -1.6, "fav": "SHORT"}, {"s": -2.4, "fav": "SHORT"},
            {"s": -3.4, "fav": "SHORT"}]
        res = run(specs)
        last = res[-1]
        self.assertTrue(last.post_death_takeover_ok)
        self.assertTrue(last.attention_event)


class TestProtectivePeak(unittest.TestCase):
    """FR017/FR018: a weak later ESTESO death must NOT lower the bar after
    the dead-peak TTL expired; the protective peak keeps the 3.0 reference."""

    def test_protective_peak_survives_ttl_gap(self):
        specs = (flat(14) + ramp([0.5, 1.0, 1.6, 2.2, 2.8, 3.0])  # strong ESTESO
                 + flat(4, s=0.2)                                   # death 1 (peak 3.0)
                 + flat(40, s=0.2)                                  # > TTL 36 quiet
                 + ramp([0.5, 1.0, 1.45])                           # weak LONG, ESTESO touch
                 + flat(4, s=0.2)                                   # death 2 (peak 1.45)
                 + [{"s": -1.0, "fav": "SHORT"}, {"s": -2.5, "fav": "SHORT"}])
        res = run(specs)
        last = res[-1]
        self.assertEqual(last.raw_dir, "SHORT")
        # dead high-water TTL expired between deaths -> deadLongPeak rewritten
        # to 1.45, but protective peak must keep the 3.0 reference (v0.13 fix)
        self.assertAlmostEqual(last.effective_dead_peak, 3.0, places=6)
        self.assertTrue(last.post_death_hidden,
                        "2.5 < 3.3 must stay hidden thanks to protective peak")
        self.assertFalse(last.attention_event)


class TestDeathFloors(unittest.TestCase):
    """FR011/FR012: ESTESO regimes die only below neutralFloor 0.35;
    non-ESTESO regimes die below removeFloor 0.70."""

    def test_non_esteso_dies_at_remove_floor(self):
        specs = (flat(14) + ramp(ramp_steps(0.35, 2.0, 0.15))  # no ESTESO
                 + flat(6, s=0.5))                              # 0.5 < 0.70
        res = run(specs)
        self.assertEqual(res[-1].regime_dir, "")

    def test_esteso_survives_above_neutral_floor(self):
        specs = (flat(14) + ramp([0.5, 1.0, 1.6, 2.2, 2.8, 3.0])  # ESTESO touch
                 + flat(10, s=0.5))                                # 0.5 > 0.35
        res = run(specs)
        last = res[-1]
        self.assertEqual(last.regime_dir, "LONG")
        self.assertTrue(last.regime_touched_extended)
        self.assertFalse(last.regime_dead)


class TestDisplayDedup(unittest.TestCase):
    """FR018/FR020: dedup is display-only; engine events unaffected."""

    def test_same_direction_follow_up_label_hidden(self):
        specs = (flat(14) + ramp([0.6, 1.0, 1.4])
                 + ramp([1.3, 1.25, 1.2, 1.35, 1.45]))
        res = run(specs)
        shown = [r for r in res if r.label_shown]
        self.assertTrue(shown, "first label must be shown")
        last = res[-1]
        self.assertTrue(last.attention_event, "engine event must still fire")
        self.assertFalse(last.label_shown,
                         "same-direction follow-up without upgrade must be deduped")


if __name__ == "__main__":
    unittest.main()
