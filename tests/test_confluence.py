import unittest

from fx_bias_radar import confluence as CF


def _h4():
    # AUD forte, CAD debole -> AUDCAD LONG; EUR forte, USD debole -> EURUSD LONG.
    z = {c: 0.0 for c in ["GBP", "NZD", "CHF", "JPY"]}
    z.update({"AUD": 2.0, "CAD": -2.0, "EUR": 1.5, "USD": -1.5})
    return z


def _h1():
    zero = [0.0] * 10
    # AUD: upturn fresco in coda (.., 0.5, 0.3, 0.4) -> RIPRESA per le coppie AUD-LONG
    aud = [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.5, 0.3, 0.4]
    # EUR: discesa per 4 barre (.., 0.9, 0.7, 0.5, 0.3, 0.1) -> RIENTRO per EUR-LONG
    eur = [0.0, 0.0, 0.0, 0.0, 0.0, 0.9, 0.7, 0.5, 0.3, 0.1]
    return {"AUD": aud, "EUR": eur, "CAD": list(zero), "USD": list(zero),
            "GBP": list(zero), "NZD": list(zero), "CHF": list(zero), "JPY": list(zero)}


class TestConfluence(unittest.TestCase):
    def test_ripresa_and_rientro(self):
        res = CF.classify_confluence(_h4(), _h1(), n_rientro=3, cluster_cap=99)
        riprese = [r["pair"] for r in res["riprese"]]
        rientri = [r["pair"] for r in res["rientri"]]
        self.assertIn("AUDCAD", riprese)
        self.assertIn("EURUSD", rientri)
        # mutuamente esclusivi
        self.assertEqual(set(riprese) & set(rientri), set())
        # tutte le righe Ripresa hanno stato giusto e una direzione
        for r in res["riprese"]:
            self.assertEqual(r["stato"], CF.RIPRESA)
            self.assertIn(r["dir"], ("LONG", "SHORT"))

    def test_neutral_pair_excluded(self):
        # GBPCHF: gap 0 -> NEUTRO -> in nessuna lista
        res = CF.classify_confluence(_h4(), _h1(), n_rientro=3, cluster_cap=99)
        allp = [r["pair"] for r in res["riprese"] + res["rientri"]]
        self.assertNotIn("GBPCHF", allp)

    def test_n_rientro_threshold(self):
        # con N=5 il down_run=4 di EUR non basta -> EURUSD fuori dai rientri
        res = CF.classify_confluence(_h4(), _h1(), n_rientro=5, cluster_cap=99)
        self.assertNotIn("EURUSD", [r["pair"] for r in res["rientri"]])

    def test_cluster_cap_limits_per_currency(self):
        res = CF.classify_confluence(_h4(), _h1(), n_rientro=3, cluster_cap=2)
        for lst in (res["riprese"], res["rientri"]):
            cnt = {}
            for r in lst:
                cnt[r["base"]] = cnt.get(r["base"], 0) + 1
                cnt[r["quote"]] = cnt.get(r["quote"], 0) + 1
            for ccy, k in cnt.items():
                self.assertLessEqual(k, 2, f"{ccy} oltre il cap")

    def test_from_strength_payloads_adapter(self):
        h4_payload = {"currencies": [{"ccy": c, "z": z} for c, z in _h4().items()]}
        h1_payload = {"currencies": [{"ccy": c, "series": s} for c, s in _h1().items()]}
        res = CF.from_strength_payloads(h4_payload, h1_payload, n_rientro=3, cluster_cap=99)
        self.assertIn("AUDCAD", [r["pair"] for r in res["riprese"]])
        self.assertIn("EURUSD", [r["pair"] for r in res["rientri"]])


if __name__ == "__main__":
    unittest.main()
