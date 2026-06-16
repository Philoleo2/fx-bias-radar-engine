"""Fase 4 - logger ORARIO di validazione M3 "Pre-Rottura".

Registra, a ogni chiusura H1, una riga CSV per ogni coppia "interessante"
(segnale H1 RIPRESA/RIENTRO oppure evento/attivo sul motore H4), cosi' offline
si misura l'ANTICIPO RIPRESA -> RESUME H4 senza falsa fiducia.

Display/validazione: NON tocca il motore H4, ne' soglie, ne' la macchina a stati.
Riusa scan_service (stato H4) e pre_rottura (confluenza H1) con UN solo fetch H4.
Idempotente: se la barra H1 corrente e' gia' loggata, non riscrive (evita doppioni
quando schedule GitHub e cron-job.org scattano nella stessa ora).

Usage (cron HH:05, barra H1 appena chiusa = no-repaint):
  python scripts/log_fase4.py --oanda --out reports/prerottura/fase4_log.csv
  python scripts/log_fase4.py --fixtures-h4 DIR --fixtures-h1 DIR --out OUT
"""

from __future__ import annotations

import argparse
import csv
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fx_bias_radar import candles as C
from fx_bias_radar import pre_rottura as PR
from fx_bias_radar import scan_service as SS

FIELDS = [
    "ts_utc", "h1_bar_utc", "h4_bar_close_utc", "pair",
    "h1_state", "h1_dir", "h1_gap_h4", "h1_down_run",
    "h4_bias", "h4_tipo", "h4_stato", "h4_score", "h4_spread", "h4_event",
]

_INACTIVE = ("", "-", "NESSUNO", "NONE", "FLAT", "PIATTO")


def build_log_rows(report_h4: dict, payload_pr: dict) -> list:
    """Riga per coppia con segnale H1 o stato H4 attivo. Funzione PURA (testabile)."""
    h4_by_pair = {r.get("pair"): r for r in report_h4.get("pairs", [])}
    h1_sig = {}
    for r in payload_pr.get("riprese", []):
        h1_sig[r["pair"]] = ("RIPRESA", r)
    for r in payload_pr.get("rientri", []):
        h1_sig[r["pair"]] = ("RIENTRO", r)

    ts = payload_pr.get("generated_at_utc")
    h1_bar = payload_pr.get("h1_last_bar_utc")
    h4_bar = (report_h4.get("last_complete_bar_close_utc")
              or report_h4.get("last_closed_bar_utc")
              or report_h4.get("analyzed_bar_close_utc"))

    rows = []
    for pair in sorted(set(h4_by_pair) | set(h1_sig)):
        h4 = h4_by_pair.get(pair, {})
        tipo = str(h4.get("tipo") or "").upper()
        sig = h1_sig.get(pair)
        active_h4 = tipo not in _INACTIVE
        if not sig and not active_h4:
            continue
        state = sig[0] if sig else "-"
        s = sig[1] if sig else {}
        rows.append({
            "ts_utc": ts,
            "h1_bar_utc": h1_bar,
            "h4_bar_close_utc": h4_bar,
            "pair": pair,
            "h1_state": state,
            "h1_dir": s.get("dir", "") if sig else "",
            "h1_gap_h4": s.get("gap_h4", "") if sig else "",
            "h1_down_run": s.get("h1_down_run", "") if sig else "",
            "h4_bias": h4.get("bias", ""),
            "h4_tipo": h4.get("tipo", ""),
            "h4_stato": h4.get("stato", ""),
            "h4_score": h4.get("score", ""),
            "h4_spread": h4.get("spread", ""),
            "h4_event": "1" if h4.get("attention_event") else "",
        })
    return rows


def last_logged_h1_bar(path: str):
    if not os.path.isfile(path):
        return None
    last = None
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            last = row.get("h1_bar_utc") or last
    return last


def append_rows(path: str, rows: list) -> None:
    is_new = not os.path.isfile(path)
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(path, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        if is_new:
            writer.writeheader()
        for row in rows:
            writer.writerow(row)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--oanda", action="store_true", help="fetch live from OANDA")
    ap.add_argument("--fixtures-h4", help="dir candele H4 (offline)")
    ap.add_argument("--fixtures-h1", help="dir candele H1 (offline)")
    ap.add_argument("--out", default="reports/prerottura/fase4_log.csv")
    ap.add_argument("--n-rientro", type=int, default=3)
    ap.add_argument("--window", type=int, default=PR.SH.DEFAULT_CHART_WINDOW)
    args = ap.parse_args()

    try:
        if args.oanda:
            from fx_bias_radar.oanda_fetch import env_credentials, fetch_all_pairs
            token, env = env_credentials()
            h4 = fetch_all_pairs(token, env=env, count=PR.DEFAULT_H4_COUNT)
            h1 = PR.SH.fetch_all_h1(token, env=env, count=PR.SH.DEFAULT_H1_COUNT)
        elif args.fixtures_h4 and args.fixtures_h1:
            h4 = C.load_fixture_dir(args.fixtures_h4)
            h1 = C.load_fixture_dir(args.fixtures_h1)
        else:
            ap.error("specificare --oanda oppure --fixtures-h4 + --fixtures-h1")
            return 2
        report_h4 = SS.build_scan_report(h4)
        payload_pr = PR.build_pre_rottura(h4, h1, n_rientro=args.n_rientro,
                                          window=args.window)
    except Exception as exc:  # noqa: BLE001 - runner CLI
        print(f"ERRORE: {exc}")
        return 2

    h1_bar = payload_pr.get("h1_last_bar_utc")
    if h1_bar is not None and last_logged_h1_bar(args.out) == h1_bar:
        print(f"Fase4 log: barra H1 {h1_bar} gia' registrata, skip.")
        return 0

    rows = build_log_rows(report_h4, payload_pr)
    append_rows(args.out, rows)
    print(f"Fase4 log: +{len(rows)} righe -> {args.out} (barra H1 {h1_bar})")
    for r in rows:
        print(f"  {r['pair']:7} H1={r['h1_state']:8} {r['h1_dir']:5} | "
              f"H4 {r['h4_bias']:7} {r['h4_tipo']:7} {r['h4_stato']:7} "
              f"score={r['h4_score']} spread={r['h4_spread']} ev={r['h4_event']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
