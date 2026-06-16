import math
import unittest
from datetime import datetime, timedelta, timezone

from fx_bias_radar import pairs as P
from fx_bias_radar import strength_h1 as SH
from fx_bias_radar.candles import Candle


def _grid(n):
    t0 = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    return [(t0 + timedelta(hours=i)).isoformat() for i in range(n)]


def _synth(n=150):
    """28 coppie con chiusure deterministiche (nessun random) su griglia H1 comune."""
    times = _grid(n)
    out = {}
    for j, pair in enumerate(P.PAIRS):
        base = 1.0 + 0.1 * j
        closes = [base + 0.01 * math.sin((i + j) / 9.0) + 0.0005 * i * ((j % 5) - 2)
                  for i in range(n)]
        out[pair] = [Candle(time=times[i], o=closes[i], h=closes[i], l=closes[i],
                            c=closes[i], volume=100, complete=True) for i in range(n)]
    return out


class TestStrengthH1(unittest.TestCase):
    def test_structure_and_window(self):
        res = SH.compute_strength(_synth(150), window=120)
        self.assertEqual(res["timeframe"], "H1")
        self.assertEqual(len(res["currencies"]), 8)
        self.assertEqual(set(res["ranking"]), set(P.CURRENCIES))
        self.assertEqual(res["bars"], 120)
        self.assertIsNotNone(res["last_bar_utc"])
        self.assertEqual(len(res["times"]), 120)
        for c in res["currencies"]:
            self.assertIn(c["dir"], ("up", "down", "flat"))
            self.assertEqual(len(c["series"]), 120)
        # con 150 barre (>lenZ=100) lo z dell'ultima barra deve esistere
        self.assertTrue(any(c["z"] is not None for c in res["currencies"]))

    def test_ranking_sorted_by_strength(self):
        res = SH.compute_strength(_synth(150), window=60)
        zmap = {c["ccy"]: c["z"] for c in res["currencies"]}
        zs = [zmap[ccy] for ccy in res["ranking"] if zmap[ccy] is not None]
        self.assertEqual(zs, sorted(zs, reverse=True))

    def test_window_clamped_to_history(self):
        res = SH.compute_strength(_synth(110), window=120)
        self.assertEqual(res["bars"], 110)
        self.assertEqual(len(res["currencies"][0]["series"]), 110)

    def test_missing_pairs_raises(self):
        synth = _synth(120)
        synth.pop(P.PAIRS[0])
        with self.assertRaises(ValueError):
            SH.compute_strength(synth)


if __name__ == "__main__":
    unittest.main()
