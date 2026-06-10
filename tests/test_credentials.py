"""Credential resolution tests (review Codex, Finding 2)."""

import os
import tempfile
import unittest

from fx_bias_radar import oanda_fetch as OF


class TestCredentials(unittest.TestCase):
    def setUp(self):
        self._cwd = os.getcwd()
        self._env = {k: os.environ.pop(k) for k in
                     ("OANDA_ACCESS_TOKEN", "OANDA_ENV") if k in os.environ}

    def tearDown(self):
        os.chdir(self._cwd)
        for k in ("OANDA_ACCESS_TOKEN", "OANDA_ENV"):
            os.environ.pop(k, None)
        os.environ.update(self._env)

    def test_env_vars_win(self):
        os.environ["OANDA_ACCESS_TOKEN"] = "tok-env"
        os.environ["OANDA_ENV"] = "practice"
        self.assertEqual(OF.env_credentials(), ("tok-env", "practice"))

    def _skip_if_repo_provides_credentials(self):
        # Dopo il merge il repo puo' avere config.py M0 e/o .env reale:
        # in quel caso il fallback risolve per design e questi test si skippano.
        if OF._try_m0_config_loader() is not None:
            self.skipTest("config M0 presente: loader attivo per design")
        repo_root = os.path.dirname(os.path.dirname(os.path.abspath(OF.__file__)))
        if os.path.isfile(os.path.join(repo_root, ".env")):
            self.skipTest(".env nel repo: fallback attivo per design")

    def test_dotenv_fallback(self):
        self._skip_if_repo_provides_credentials()
        with tempfile.TemporaryDirectory() as d:
            try:
                with open(os.path.join(d, ".env"), "w", encoding="utf-8") as f:
                    f.write("# commento\nOANDA_ACCESS_TOKEN=tok-file\nOANDA_ENV=practice\n")
                os.chdir(d)
                self.assertEqual(OF.env_credentials(), ("tok-file", "practice"))
            finally:
                os.chdir(self._cwd)

    def test_missing_raises(self):
        self._skip_if_repo_provides_credentials()
        with tempfile.TemporaryDirectory() as d:
            try:
                os.chdir(d)
                with self.assertRaises(RuntimeError):
                    OF.env_credentials()
            finally:
                os.chdir(self._cwd)


if __name__ == "__main__":
    unittest.main()
