"""Run the M0 OANDA sanity check.

This command checks credentials, reads the account summary, and fetches recent
closed H4 candles for a small sample of instruments.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import argparse
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from fx_bias_radar.config import load_oanda_config, mask_secret
from fx_bias_radar.oanda import OandaClient, OandaError
from fx_bias_radar.pairs import normalize_instrument


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="OANDA M0 sanity check")
    parser.add_argument(
        "--instrument",
        action="append",
        default=[],
        help="Instrument to fetch, e.g. EUR_USD. Can be repeated.",
    )
    parser.add_argument("--count", type=int, default=12, help="Candles to request per instrument.")
    parser.add_argument("--dotenv", default=".env", help="Path to local dotenv file.")
    parser.add_argument("--report", default="", help="Optional markdown report path.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    instruments = [normalize_instrument(item) for item in args.instrument]
    if not instruments:
        instruments = ["EUR_USD", "USD_CHF", "CHF_JPY"]

    config = load_oanda_config(args.dotenv)
    lines: list[str] = []
    lines.append("# OANDA M0 sanity check")
    lines.append("")
    lines.append(f"- Run UTC: {datetime.now(timezone.utc).isoformat(timespec='seconds')}")
    lines.append(f"- Env: {config.env}")
    lines.append(f"- Base URL: {config.base_url}")
    lines.append(f"- Token: {mask_secret(config.access_token)}")
    lines.append(f"- Account ID configured: {mask_secret(config.account_id or '') if config.account_id else '<auto>'}")
    lines.append("")

    try:
        client = OandaClient(config)
        accounts = client.list_accounts()
        lines.append(f"- Accounts returned: {len(accounts)}")

        account = client.account_summary()
        if account:
            lines.append(f"- Account currency: {account.get('currency', '<unknown>')}")
            lines.append(f"- NAV: {account.get('NAV', '<unknown>')}")
        lines.append("")

        for instrument in instruments:
            lines.append(f"## {instrument} H4")
            candles = client.candles(instrument, count=args.count)
            if not candles:
                lines.append("- No complete candles returned.")
                lines.append("")
                continue
            for candle in candles[-3:]:
                lines.append(
                    "- {time} O={open:.5f} H={high:.5f} L={low:.5f} C={close:.5f} V={volume}".format(
                        time=candle.time.isoformat(),
                        open=candle.open,
                        high=candle.high,
                        low=candle.low,
                        close=candle.close,
                        volume=candle.volume,
                    )
                )
            lines.append("")
    except OandaError as exc:
        lines.append(f"ERROR: {exc}")
        output = "\n".join(lines)
        print(output)
        if args.report:
            write_report(Path(args.report), output)
        return 2

    output = "\n".join(lines)
    print(output)
    if args.report:
        write_report(Path(args.report), output)
    return 0


def write_report(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content + "\n", encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
