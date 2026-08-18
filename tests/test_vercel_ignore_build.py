"""Vercel Ignored Build Step: un commit di dati non deve deployare, un commit
di codice deve sempre deployare.

Semantica Vercel, facilissima da invertire per sbaglio:
    exit 0 -> IGNORA il build
    exit 1 -> ESEGUI il build

Il criterio e' il confronto dei FILE modificati, non il messaggio di commit:
"[skip ci]" nel testo non deve poter impedire il deploy di codice.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(ROOT, "scripts", "vercel_ignore_build.sh")

IGNORE = 0
BUILD = 1


def classify(*paths: str) -> int:
    return subprocess.run(["bash", SCRIPT, *paths], capture_output=True, text=True).returncode


class TestSemantics(unittest.TestCase):
    def test_script_exists_and_is_wired_into_vercel_json(self):
        import json
        self.assertTrue(os.path.exists(SCRIPT))
        with open(os.path.join(ROOT, "vercel.json"), encoding="utf-8") as handle:
            config = json.load(handle)
        self.assertEqual(config.get("ignoreCommand"), "bash scripts/vercel_ignore_build.sh")

    def test_exit_codes_are_not_inverted(self):
        """0 = ignora, 1 = builda. Se qualcuno li inverte, il deploy si ferma."""
        self.assertEqual(classify("reports/prerottura/fase4_log.csv"), IGNORE)
        self.assertEqual(classify("prewake/model.py"), BUILD)

    def test_decision_does_not_depend_on_the_commit_message(self):
        """Lo script non deve nemmeno leggere il messaggio di commit."""
        with open(SCRIPT, encoding="utf-8") as handle:
            code = [l for l in handle.read().splitlines() if not l.strip().startswith("#")]
        code = "\n".join(code)
        for forbidden in ("git log", "git show", "--format", "%B", "%s\"",
                          "COMMIT_MESSAGE", "VERCEL_GIT_COMMIT_MESSAGE"):
            self.assertNotIn(forbidden, code,
                             f"la decisione non deve dipendere dal messaggio: {forbidden}")
        self.assertIn("git diff --name-only", code, "la decisione deve venire dai file")


class TestCases(unittest.TestCase):
    """I casi A-I richiesti."""

    def test_case_a_only_pre_rottura_latest(self):
        self.assertEqual(classify("reports/prerottura/pre_rottura_latest.json"), IGNORE)

    def test_case_b_only_fase4_log(self):
        self.assertEqual(classify("reports/prerottura/fase4_log.csv"), IGNORE)

    def test_case_c_both_reports(self):
        self.assertEqual(classify("reports/prerottura/pre_rottura_latest.json",
                                  "reports/prerottura/fase4_log.csv"), IGNORE)

    def test_case_d_api_code(self):
        self.assertEqual(classify("api/prewake.py"), BUILD)

    def test_case_e_public_ui(self):
        self.assertEqual(classify("public/prewake.html"), BUILD)

    def test_case_f_vercel_json(self):
        self.assertEqual(classify("vercel.json"), BUILD)

    def test_case_g_dependency_manifests(self):
        for manifest in ("requirements.txt", "requirements-prewake.txt", ".python-version"):
            self.assertEqual(classify(manifest), BUILD, manifest)

    def test_case_h_report_plus_code(self):
        self.assertEqual(classify("reports/prerottura/fase4_log.csv", "api/scan.py"), BUILD)
        self.assertEqual(classify("api/scan.py", "reports/prerottura/fase4_log.csv"), BUILD)

    def test_case_i_unknown_path_builds(self):
        for unknown in ("Makefile", "README.md", "reports/rotation/rotation_backtest.json",
                        "reports/", "docs/PREWAKE_V1_PRODUCTION.md", "some/new/thing.py"):
            self.assertEqual(classify(unknown), BUILD, unknown)


class TestRuntimeAndConfigPathsAlwaysBuild(unittest.TestCase):
    def test_every_declared_build_required_path_builds(self):
        for path in ("api/health.py", "api/scan.py", "api/pre_rottura.py",
                     "public/index.html", "public/app.js", "public/styles.css",
                     "public/pre_rottura.js", "vercel.json",
                     "requirements.txt", "requirements-prewake.txt", ".python-version",
                     "prewake/engine.py", "prewake/models/pair_prewake_v1.json",
                     "fx_bias_radar/engine.py", "fx_bias_radar/pairs.py",
                     "scripts/run_prewake.py", "scripts/run_pre_rottura.py",
                     ".github/workflows/prewake.yml", ".github/workflows/pre_rottura.yml",
                     "tests/test_prewake_engine.py", "pyproject.toml", ".gitignore"):
            self.assertEqual(classify(path), BUILD, path)

    def test_only_the_two_data_directories_are_ignored(self):
        self.assertEqual(classify("reports/prerottura/anything.json"), IGNORE)
        self.assertEqual(classify("reports/prewake/prewake_state.json"), IGNORE)
        # tutto il resto sotto reports/ deve buildare: la whitelist non e' "reports/"
        self.assertEqual(classify("reports/h4events/h4_events_edge.json"), BUILD)
        self.assertEqual(classify("reports/actions/latest.json"), BUILD)

    def test_path_traversal_is_refused(self):
        self.assertEqual(classify("reports/prerottura/../../api/scan.py"), BUILD)


class TestGitMode(unittest.TestCase):
    """Senza argomenti lo script ricava i file dal range git, come su Vercel."""

    def setUp(self):
        self.repo = tempfile.mkdtemp(prefix="ignore-build-")
        self.git("git", "init", "-q")
        self.git("git", "config", "user.email", "t@t")
        self.git("git", "config", "user.name", "t")
        os.makedirs(os.path.join(self.repo, "reports", "prerottura"), exist_ok=True)
        os.makedirs(os.path.join(self.repo, "api"), exist_ok=True)
        self.write("README.md", "base")
        self.commit("base")

    def tearDown(self):
        shutil.rmtree(self.repo, ignore_errors=True)

    def git(self, *args):
        return subprocess.run(args, cwd=self.repo, capture_output=True, text=True)

    def write(self, rel, text):
        path = os.path.join(self.repo, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(text)

    def commit(self, message):
        self.git("git", "add", "-A")
        self.git("git", "commit", "-q", "-m", message)
        return self.git("git", "rev-parse", "HEAD").stdout.strip()

    def ignore_step(self, **env):
        environment = dict(os.environ, **env)
        return subprocess.run(["bash", SCRIPT], cwd=self.repo, env=environment,
                              capture_output=True, text=True)

    def test_data_only_commit_is_ignored(self):
        self.write("reports/prerottura/fase4_log.csv", "a,b\n1,2\n")
        self.commit("Pre-Rottura H1 scan + Fase4 log [skip ci]")
        self.assertEqual(self.ignore_step().returncode, IGNORE)

    def test_code_commit_builds_even_with_skip_ci_in_the_message(self):
        self.write("api/scan.py", "print('x')\n")
        self.commit("Pre-Rottura H1 scan + Fase4 log [skip ci]")
        result = self.ignore_step()
        self.assertEqual(result.returncode, BUILD)
        self.assertIn("api/scan.py", result.stdout)

    def test_previous_successful_deployment_is_the_comparison_base(self):
        """Dopo N commit dati saltati, un commit di codice deve buildare."""
        deployed = self.git("git", "rev-parse", "HEAD").stdout.strip()
        for i in range(3):
            self.write("reports/prerottura/fase4_log.csv", f"row {i}\n")
            self.commit(f"data {i}")
        self.assertEqual(self.ignore_step(VERCEL_GIT_PREVIOUS_SHA=deployed).returncode, IGNORE)
        self.write("api/scan.py", "print('new')\n")
        self.commit("code")
        result = self.ignore_step(VERCEL_GIT_PREVIOUS_SHA=deployed)
        self.assertEqual(result.returncode, BUILD)
        self.assertIn("ultimo deployment", result.stdout)

    def test_unreachable_previous_sha_falls_back_then_still_decides(self):
        self.write("reports/prerottura/fase4_log.csv", "x\n")
        self.commit("data")
        result = self.ignore_step(VERCEL_GIT_PREVIOUS_SHA="0" * 40)
        self.assertEqual(result.returncode, IGNORE)
        self.assertIn("commit precedente", result.stdout)

    def test_no_comparison_commit_available_builds(self):
        """Root commit senza padre: nessun confronto possibile -> fail-safe."""
        fresh = tempfile.mkdtemp(prefix="ignore-build-root-")
        try:
            subprocess.run(["git", "init", "-q"], cwd=fresh)
            subprocess.run(["git", "config", "user.email", "t@t"], cwd=fresh)
            subprocess.run(["git", "config", "user.name", "t"], cwd=fresh)
            with open(os.path.join(fresh, "a.txt"), "w") as handle:
                handle.write("a")
            subprocess.run(["git", "add", "-A"], cwd=fresh)
            subprocess.run(["git", "commit", "-q", "-m", "root"], cwd=fresh)
            result = subprocess.run(["bash", SCRIPT], cwd=fresh, capture_output=True, text=True)
            self.assertEqual(result.returncode, BUILD)
        finally:
            shutil.rmtree(fresh, ignore_errors=True)

    def test_empty_diff_builds(self):
        head = self.git("git", "rev-parse", "HEAD").stdout.strip()
        result = self.ignore_step(VERCEL_GIT_PREVIOUS_SHA=head)
        self.assertEqual(result.returncode, BUILD)
        self.assertIn("fail-safe", result.stdout)


if __name__ == "__main__":
    unittest.main()
