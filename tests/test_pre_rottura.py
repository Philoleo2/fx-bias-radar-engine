import json
import os
import unittest

from fx_bias_radar import candles as C
from fx_bias_radar import pairs as P
from fx_bias_radar import pre_rottura as PR

FIX = os.path.join(os.path.dirname(__file__), "fixtures", "golden_2026H1")


def _fixtures_ready():
    if not os.path.isdir(FIX):
        return False
    return all(os.path.isfile(os.path.join(FIX, f"{pair}.json")) for pair in P.PAIRS)


@unittest.skipUnless(_fixtures_ready(), "golden fixtures missing: run scripts/build_fixtures.py")
class TestPreRottura(unittest.TestCase):
    def test_build_structure_on_real_fixtures(self):
        candles = C.load_fixture_dir(FIX)
        # usa gli stessi candele come H4 e H1 solo per verificare il cablaggio
        payload = PR.build_pre_rottura(candles, candles, window=80, n_rientro=3)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["kind"], "pre_rottura")
        self.assertEqual(payload["dir_timeframe"], "H4")
        self.assertEqual(payload["timing_timeframe"], "H1")
        self.assertIsInstance(payload["riprese"], list)
        self.assertIsInstance(payload["rientri"], list)
        self.assertEqual(len(payload["lines_h1"]["currencies"]), 8)
        self.assertEqual(payload["lines_h1"]["timeframe"], "H1")
        self.assertEqual(payload["h4_strength"]["timeframe"], "H4")
        self.assertEqual(len(payload["ranking_h4"]), 8)
        self.assertEqual(payload["params"]["n_rientro"], 3)
        # serie pronte per il grafico 8 linee
        for c in payload["lines_h1"]["currencies"]:
            self.assertEqual(len(c["series"]), 80)
        # payload serializzabile JSON
        json.loads(PR.to_json(payload))

    def test_riprese_rientri_disjoint(self):
        candles = C.load_fixture_dir(FIX)
        payload = PR.build_pre_rottura(candles, candles, window=80, n_rientro=3,
                                       cluster_cap=99)
        rip = {r["pair"] for r in payload["riprese"]}
        rie = {r["pair"] for r in payload["rientri"]}
        self.assertEqual(rip & rie, set())


if __name__ == "__main__":
    unittest.main()
