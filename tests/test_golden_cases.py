"""Golden tests on real OANDA history (docs/ACCEPTANCE_TESTS_M1.md).

These tests need candle fixtures built once with:
    python scripts/build_fixtures.py --start 2026-01-01 --out tests/fixtures/golden_2026H1
and committed to the repo. Without fixtures they SKIP (CI stays green until
M1.4 fixtures land). A FAILING golden test is a HARD STOP (brief section 14):
do not change engine behavior to make it pass without Leonardo's approval.

Dates are UTC calendar days; assertions are at signal level (state/direction),
not decimals, per the acceptance document.
"""

import os
import unittest

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures", "golden_2026H1")

_cache = {}


def _results(pair):
    if pair in _cache:
        return _cache[pair]
    from fx_bias_radar import candles as C
    from fx_bias_radar import currency_index as CI
    from fx_bias_radar import engine as E
    if "::cd" not in _cache:
        candles = C.load_fixture_dir(FIXTURES)
        times, closes, _ = C.align(candles)
        _cache["::cd"] = CI.build(times, closes)
    cd = _cache["::cd"]
    res = E.run_pair(pair, CI.pair_frames(cd, pair))
    _cache[pair] = res
    return res


def day(results, date):
    return [r for r in results if r.time.startswith(date)]


@unittest.skipUnless(os.path.isdir(FIXTURES),
                     "golden fixtures missing: run scripts/build_fixtures.py")
class TestGoldenEURUSD(unittest.TestCase):
    def test_long_31_march_present(self):
        bars = day(_results("EURUSD"), "2026-03-31")
        self.assertTrue(any(r.attention_event and r.raw_dir == "LONG" for r in bars))

    def test_long_13_april_present(self):
        bars = day(_results("EURUSD"), "2026-04-13")
        self.assertTrue(any(r.attention_event and r.raw_dir == "LONG" for r in bars))

    def test_weak_short_17_and_21_april_hidden(self):
        for d in ("2026-04-17", "2026-04-21"):
            bars = day(_results("EURUSD"), d)
            self.assertFalse(
                any(r.attention_event and r.raw_dir == "SHORT" for r in bars),
                f"SHORT attention on {d} must stay hidden")

    def test_short_22_april_true_takeover_accepted(self):
        bars = day(_results("EURUSD"), "2026-04-22")
        self.assertTrue(any(r.attention_event and r.raw_dir == "SHORT" for r in bars))


@unittest.skipUnless(os.path.isdir(FIXTURES),
                     "golden fixtures missing: run scripts/build_fixtures.py")
class TestGoldenStrongOpposite(unittest.TestCase):
    WINDOW = ("2026-06-05", "2026-06-06", "2026-06-07", "2026-06-08")

    def test_usdchf_strong_opposite_long_shows(self):
        res = _results("USDCHF")
        bars = [r for r in res if r.time[:10] in self.WINDOW]
        self.assertTrue(any(
            (r.attention_event and r.raw_dir == "LONG") or
            (r.display_active and r.display_dir == "LONG")
            for r in bars), "USDCHF strong-opposite LONG must show (FR024/FR025)")

    def test_chfjpy_strong_opposite_short_shows(self):
        res = _results("CHFJPY")
        bars = [r for r in res if r.time[:10] in self.WINDOW]
        self.assertTrue(any(
            (r.attention_event and r.raw_dir == "SHORT") or
            (r.display_active and r.display_dir == "SHORT")
            for r in bars), "CHFJPY strong-opposite SHORT must show (FR024/FR025)")


@unittest.skipUnless(os.path.isdir(FIXTURES),
                     "golden fixtures missing: run scripts/build_fixtures.py")
class TestGoldenEURNZD(unittest.TestCase):
    def test_early_june_long_reactive(self):
        res = _results("EURNZD")
        bars = [r for r in res if "2026-06-01" <= r.time[:10] <= "2026-06-09"]
        self.assertTrue(any(r.display_active and r.display_dir == "LONG" for r in bars))


@unittest.skipUnless(os.path.isdir(FIXTURES),
                     "golden fixtures missing: run scripts/build_fixtures.py")
class TestGoldenFlatNegatives(unittest.TestCase):
    """Validated flat dates (FR009/FR019): panel must be NESSUNO.

    NOTA (review Codex): la validazione storica e' su screenshot puntuali,
    questi test coprono l'intera giornata UTC (piu' larghi dell'evidenza).
    Con spread valutario ~0.1-0.35 il display non puo' attivarsi (floor 0.70),
    quindi l'assert giornaliero dovrebbe reggere; se un flat-test fallisce
    con fixtures reali, PRIMA verificare l'ampiezza del test (barra/timezone),
    POI sospettare il motore. Resta valido l'hard stop sui casi EURUSD.
    """

    def test_nzdchf_flat_2026_06_03(self):
        bars = day(_results("NZDCHF"), "2026-06-03")
        self.assertTrue(bars)
        self.assertTrue(all(not r.display_active for r in bars))

    def test_gbpjpy_flat_2026_06_04(self):
        bars = day(_results("GBPJPY"), "2026-06-04")
        self.assertTrue(bars)
        self.assertTrue(all(not r.display_active for r in bars))

    def test_audcad_flat_2026_06_04(self):
        bars = day(_results("AUDCAD"), "2026-06-04")
        self.assertTrue(bars)
        self.assertTrue(all(not r.display_active for r in bars))


if __name__ == "__main__":
    unittest.main()
