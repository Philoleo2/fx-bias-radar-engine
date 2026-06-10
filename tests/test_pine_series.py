import math
import unittest

from fx_bias_radar.pine_series import (crossover_point, crossunder_point, ema,
                                       highest_at, lowest_at, nz, sma_at,
                                       stdev_at)


class TestPineSeries(unittest.TestCase):
    def test_nz(self):
        self.assertEqual(nz(None), 0.0)
        self.assertEqual(nz(None, 5.0), 5.0)
        self.assertEqual(nz(1.5), 1.5)

    def test_sma_warmup_and_value(self):
        xs = [1.0, 2.0, 3.0, 4.0]
        self.assertIsNone(sma_at(xs, 1, 3))
        self.assertAlmostEqual(sma_at(xs, 2, 3), 2.0)
        self.assertAlmostEqual(sma_at(xs, 3, 3), 3.0)
        self.assertIsNone(sma_at([None, 2.0, 3.0], 2, 3))

    def test_stdev_is_population(self):
        # Pine ta.stdev biased default: sqrt(sum((x-m)^2)/N)
        xs = [2.0, 4.0, 4.0, 4.0, 5.0, 5.0, 7.0, 9.0]
        self.assertAlmostEqual(stdev_at(xs, 7, 8), 2.0)  # classic population example

    def test_ema_seed_and_recursion(self):
        xs = [None, 10.0, 20.0]
        out = ema(xs, 19)  # alpha = 0.1
        self.assertIsNone(out[0])
        self.assertAlmostEqual(out[1], 10.0)          # seed with first valid
        self.assertAlmostEqual(out[2], 0.1 * 20 + 0.9 * 10)

    def test_extremes(self):
        xs = [1.0, 5.0, 3.0, 2.0]
        self.assertAlmostEqual(highest_at(xs, 3, 3), 5.0)
        self.assertAlmostEqual(lowest_at(xs, 3, 3), 2.0)
        self.assertIsNone(highest_at(xs, 1, 3))

    def test_cross_points(self):
        # crossover: now above, previously at-or-below
        self.assertTrue(crossover_point(1.0, -1.0, 0.0, 0.0))
        self.assertFalse(crossover_point(1.0, 1.0, 0.0, 0.0))
        self.assertTrue(crossunder_point(-1.0, 0.0, 0.0, 0.0))
        self.assertFalse(crossunder_point(-1.0, -2.0, 0.0, 0.0))
        self.assertFalse(crossover_point(None, -1.0, 0.0, 0.0))


if __name__ == "__main__":
    unittest.main()
