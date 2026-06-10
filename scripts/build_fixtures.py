"""Build golden-test fixtures from OANDA history (run locally with token).

Usage (in locale basta il file .env gia' compilato per M0; in alternativa
una variabile d'ambiente OANDA_ACCESS_TOKEN):
  python scripts/build_fixtures.py --start 2026-01-01 --out tests/fixtures/golden_2026H1

Fetches all 28 pairs from --start to now (H4, midpoint, complete only) and
saves one JSON per pair. Commit the fixture directory so CI golden tests run
deterministically. ~700 bars/pair from January: small files, no secrets inside.
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fx_bias_radar.candles import save_fixture_dir
from fx_bias_radar.oanda_fetch import env_credentials, fetch_all_pairs


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="2026-01-01", help="UTC date YYYY-MM-DD")
    ap.add_argument("--out", default="tests/fixtures/golden_2026H1")
    args = ap.parse_args()

    token, env = env_credentials()
    from_time = f"{args.start}T00:00:00Z"
    to_time = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    print(f"Fetch 28 coppie H4 da {from_time} a {to_time} ({env})...")
    candles = fetch_all_pairs(token, env=env, count=None,
                              from_time=from_time, to_time=to_time)
    for pair, cs in sorted(candles.items()):
        print(f"  {pair}: {len(cs)} barre, ultima {cs[-1].time if cs else '-'}")
    save_fixture_dir(args.out, candles)
    print(f"Fixtures salvate in {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
