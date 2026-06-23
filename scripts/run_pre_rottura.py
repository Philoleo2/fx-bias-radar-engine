"""Run the Pre-Rottura (M3) scan and write the JSON result.

Pensato per il cron ORARIO (HH:05, barra H1 appena chiusa = no-repaint).
Usage:
  python scripts/run_pre_rottura.py --oanda --out reports/prerottura
  python scripts/run_pre_rottura.py --fixtures-h4 DIR --fixtures-h1 DIR --out OUT

Solo radar di attenzione. Nessun ordine, nessun alert automatico.
"""

from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fx_bias_radar import candles as C
from fx_bias_radar import pre_rottura as PR


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--oanda", action="store_true", help="fetch live from OANDA")
    ap.add_argument("--fixtures-h4", help="dir candele H4 (offline)")
    ap.add_argument("--fixtures-h1", help="dir candele H1 (offline)")
    ap.add_argument("--out", default="reports/prerottura", help="output directory")
    ap.add_argument("--n-rientro", type=int, default=3)
    ap.add_argument("--window", type=int, default=PR.SH.DEFAULT_CHART_WINDOW)
    ap.add_argument("--snapshot", action="store_true",
                    help="scrivi anche una copia con timestamp (default: solo latest)")
    args = ap.parse_args()

    try:
        if args.oanda:
            payload = PR.run_from_oanda(n_rientro=args.n_rientro, window=args.window)
        elif args.fixtures_h4 and args.fixtures_h1:
            h4 = C.load_fixture_dir(args.fixtures_h4)
            h1 = C.load_fixture_dir(args.fixtures_h1)
            payload = PR.build_pre_rottura(h4, h1, n_rientro=args.n_rientro,
                                           window=args.window)
        else:
            ap.error("specificare --oanda oppure --fixtures-h4 + --fixtures-h1")
            return 2
    except Exception as exc:  # noqa: BLE001 - runner CLI
        print(f"ERRORE: {exc}")
        return 2

    os.makedirs(args.out, exist_ok=True)
    data = PR.to_json(payload)
    latest = os.path.join(args.out, "pre_rottura_latest.json")
    with open(latest, "w", encoding="utf-8") as f:
        f.write(data)
    if args.snapshot:
        stamp = (payload["generated_at_utc"].replace(":", "")
                 .replace("+00:00", "Z").replace("+0000", "Z"))
        with open(os.path.join(args.out, f"pre_rottura_{stamp}.json"), "w", encoding="utf-8") as f:
            f.write(data)

    print(f"Pre-Rottura: {latest}")
    print(f"  rotazioni: {len(payload.get('rotazioni', []))}")
    for r in payload.get("rotazioni", []):
        print(f"  ROTAZIONE {r['pair']} {r['dir']} ({r['forte']} molla, {r['debole']} recupera) spreadH1={r['spread_h1']}")
    print(f"  riprese: {len(payload['riprese'])}  rientri: {len(payload['rientri'])}")
    for r in payload["riprese"]:
        print(f"  RIPRESA {r['pair']} {r['dir']} gapH4={r['gap_h4']}")
    for r in payload["rientri"]:
        print(f"  RIENTRO {r['pair']} {r['dir']} down_run={r['h1_down_run']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
