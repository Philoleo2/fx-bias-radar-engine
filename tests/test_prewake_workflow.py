"""Contratto del workflow PREWAKE: isolamento da FX Bias e persistenza git.

Non esiste un database: lo stato di produzione sono file committati. Con due
workflow orari che scrivono, le proprieta' di concorrenza vanno testate come
qualunque altra invariante, non lasciate alla buona volonta' dello YAML.
"""
from __future__ import annotations

import os
import re
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PREWAKE_WF = os.path.join(ROOT, ".github", "workflows", "prewake.yml")
FXBIAS_WF = os.path.join(ROOT, ".github", "workflows", "pre_rottura.yml")


def read(path):
    with open(path, "r", encoding="utf-8") as handle:
        return handle.read()


class TestWorkflowIsolation(unittest.TestCase):
    def setUp(self):
        self.prewake = read(PREWAKE_WF)
        self.fxbias = read(FXBIAS_WF)

    def test_prewake_is_a_separate_workflow(self):
        self.assertTrue(os.path.exists(PREWAKE_WF))
        self.assertNotIn("prewake", self.fxbias.lower(),
                         "il workflow FX Bias non deve sapere nulla di PREWAKE")

    def test_prewake_runs_after_fx_bias(self):
        self.assertIn('cron: "10 * * * *"', self.prewake)
        self.assertIn('cron: "5 * * * *"', self.fxbias)

    def test_prewake_serialises_with_itself(self):
        self.assertIn("concurrency:", self.prewake)
        self.assertIn("group: prewake-h1", self.prewake)
        self.assertIn("cancel-in-progress: false", self.prewake)

    def test_flags_default_off_and_are_not_secrets(self):
        self.assertIn("vars.PREWAKE_ENGINE_ENABLED", self.prewake)
        self.assertIn("vars.PREWAKE_EMAIL_ENABLED", self.prewake)
        self.assertNotIn("secrets.PREWAKE_ENGINE_ENABLED", self.prewake)

    def test_no_model_parameter_reaches_the_workflow(self):
        for banned in ("PREWAKE_THRESHOLD", "PREWAKE_EWMA", "PREWAKE_RESET",
                       "PREWAKE_COEFFICIENTS", "PREWAKE_INTERCEPT"):
            self.assertNotIn(banned, self.prewake)


class TestGitPersistenceConcurrency(unittest.TestCase):
    """Le quattro modalita' di guasto chieste esplicitamente."""

    def setUp(self):
        self.prewake = read(PREWAKE_WF)

    def test_prewake_never_pushes_to_main(self):
        """Due scrittori sullo stesso ref = un push perso. Ref separati."""
        pushes = [line.strip() for line in self.prewake.splitlines()
                  if "git push" in line and not line.strip().startswith("#")]
        self.assertTrue(pushes, "il workflow deve pushare da qualche parte")
        for line in pushes:
            self.assertIn("prewake-data", line, f"push non isolato: {line}")
            self.assertNotIn("origin main", line)

    def test_never_force_push(self):
        for token in ("--force", "-f origin", "+refs/", "--force-with-lease"):
            self.assertNotIn(token, self.prewake, f"force-push vietato: {token}")

    def test_non_fast_forward_is_retried_not_swallowed(self):
        """Un push respinto deve ritentare, mai finire in `|| true`."""
        self.assertIn("for attempt in", self.prewake)
        self.assertIn("git pull --rebase", self.prewake)
        self.assertNotIn("git pull --rebase --autostash origin main || true", self.prewake)
        push_lines = [l for l in self.prewake.splitlines()
                      if "git push" in l and not l.strip().startswith("#")]
        for line in push_lines:
            self.assertNotIn("|| true", line, "un push fallito non puo' essere ignorato")

    def test_failure_is_loud(self):
        """Se dopo i retry non passa, il job fallisce: niente perdita silenziosa."""
        self.assertIn('echo "push non riuscito dopo 5 tentativi"; exit 1', self.prewake)

    def test_ledger_is_published_even_when_the_engine_fails(self):
        self.assertIn("if: always()", self.prewake)

    def test_state_is_restored_before_running(self):
        """Senza restore, ogni run ripartirebbe da uno stato vecchio."""
        self.assertIn("Restore PREWAKE ledger", self.prewake)
        restore = self.prewake.index("Restore PREWAKE ledger")
        run = self.prewake.index("Run PREWAKE engine")
        publish = self.prewake.index("Publish PREWAKE ledger")
        self.assertLess(restore, run, "il restore deve precedere il motore")
        self.assertLess(run, publish, "la pubblicazione deve seguire il motore")

    def test_fx_bias_workflow_is_untouched_by_this_branch(self):
        """PREWAKE non deve aver modificato il commit step di FX Bias."""
        fxbias = read(FXBIAS_WF)
        self.assertIn("Pre-Rottura H1 scan + Fase4 log [skip ci]", fxbias)
        self.assertNotIn("prewake-data", fxbias)


class TestStaleDataPolicy(unittest.TestCase):
    """A HH:10 i dati possono non essere pronti: SKIP/RETRY, mai dati vecchi."""

    def test_runner_skips_instead_of_using_stale_bars(self):
        source = read(os.path.join(ROOT, "scripts", "run_prewake.py"))
        self.assertIn("SKIPPED_INCOMPLETE_INPUT", source)
        self.assertIn("NO_NEW_BAR", source)
        self.assertIn("newest <= state.last_bar_time_utc", source.replace("\n", " ")
                      .replace("  ", " ") if "newest <= state.last_bar_time_utc" in source
                      else "newest <= state.last_bar_time_utc")

    def test_market_module_refuses_partial_grids(self):
        from prewake import market
        self.assertTrue(issubclass(market.IncompleteInput, RuntimeError))

    def test_warmup_gap_is_detected(self):
        source = read(os.path.join(ROOT, "scripts", "run_prewake.py"))
        self.assertIn("WARMUP_GAP", source)


if __name__ == "__main__":
    unittest.main()
