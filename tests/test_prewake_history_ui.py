from __future__ import annotations

import json
import os
import unittest


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def read(*parts: str) -> str:
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as handle:
        return handle.read()


class TestPrewakeHistoryUi(unittest.TestCase):
    def test_online_home_page_links_the_history(self):
        home = read("public", "pre_rottura.html")
        self.assertIn('href="/prewake_history.html"', home)
        self.assertIn("PREWAKE &middot; 20 giorni", home)

    def test_main_prewake_page_links_the_history(self):
        self.assertIn('href="/prewake_history.html"', read("public", "prewake.html"))

    def test_history_reuses_the_protected_prewake_api(self):
        page = read("public", "prewake_history.html")
        script = read("public", "prewake_history.js")
        self.assertIn('src="/prewake_history.js"', page)
        self.assertIn('fetch("/api/prewake"', script)
        self.assertIn('localStorage.getItem("fxbr.dashboardToken")', script)
        self.assertIn('Authorization: "Bearer " + saved', script)

    def test_history_is_exactly_twenty_days_and_prospective_only(self):
        script = read("public", "prewake_history.js")
        self.assertIn("20 * 24 * 60 * 60 * 1000", script)
        self.assertIn("event.is_prospective === true", script)
        self.assertIn("event.is_backfill !== true", script)
        self.assertIn("opened >= windowStart", script)
        self.assertIn("opened <= windowEnd", script)

    def test_history_shows_required_call_fields(self):
        script = read("public", "prewake_history.js")
        for field in ("pair", "direction", "event_type", "bar_time_utc", "email_status"):
            self.assertIn("event." + field, script)
        self.assertIn('timeZone: "Europe/Rome"', script)

    def test_new_assets_are_never_cached(self):
        config = json.loads(read("vercel.json"))
        sources = [header["source"] for header in config["headers"]]
        joined = "\n".join(sources)
        self.assertIn("prewake_history.html", joined)
        self.assertIn("prewake_history.js", joined)


if __name__ == "__main__":
    unittest.main()
