"""Registro chiamate d1w + classifica ultimi N giorni.

DISPLAY-only: conta a valle le chiamate (coppie nella sezione "Allineate
daily+weekly"). NON tocca i motori di calcolo (compressione/d1w). Idempotente per
barra H1: un doppio trigger nella stessa ora non gonfia i conteggi.
"""

from __future__ import annotations

import csv
import os
from datetime import datetime, timedelta, timezone

FIELDS = ["ts_utc", "h1_bar_utc", "pair", "dir"]
WINDOW_DAYS = 20


def _parse(s):
    if not s:
        return None
    try:
        t = datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except Exception:
        return None
    return t.replace(tzinfo=timezone.utc) if t.tzinfo is None else t


def logged_bars(log_path):
    if not os.path.isfile(log_path):
        return set()
    out = set()
    with open(log_path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            b = row.get("h1_bar_utc")
            if b:
                out.add(b)
    return out


def append_calls(log_path, h1_bar_utc, allineate, ts_utc=None):
    """Accoda una riga per coppia chiamata sulla barra H1. Idempotente per barra.
    Ritorna il numero di righe scritte (0 se barra gia' loggata o nessuna chiamata)."""
    if not h1_bar_utc or h1_bar_utc in logged_bars(log_path):
        return 0
    rows = [{"ts_utc": ts_utc or h1_bar_utc, "h1_bar_utc": h1_bar_utc,
             "pair": r.get("pair"), "dir": r.get("dir", "")}
            for r in (allineate or []) if r.get("pair")]
    if not rows:
        return 0
    parent = os.path.dirname(log_path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    is_new = not os.path.isfile(log_path)
    with open(log_path, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        if is_new:
            w.writeheader()
        for row in rows:
            w.writerow(row)
    return len(rows)


def build_classifica(log_path, now=None, window_days=WINDOW_DAYS):
    """Classifica per numero di chiamate negli ultimi window_days.
    - nuove: coppie con UNA sola chiamata (debutto, finche' non arriva la 2a).
    - classifica: coppie con >=2 chiamate, ordinate per numero (desc)."""
    now = now or datetime.now(timezone.utc)
    cutoff = now - timedelta(days=window_days)
    by_pair = {}
    if os.path.isfile(log_path):
        with open(log_path, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                t = _parse(row.get("h1_bar_utc") or row.get("ts_utc"))
                if t is None or t < cutoff:
                    continue
                by_pair.setdefault(row.get("pair"), []).append((t, row.get("dir", "")))
    entries = []
    for pair, calls in by_pair.items():
        if not pair:
            continue
        calls.sort(key=lambda x: x[0])
        entries.append({
            "pair": pair, "count": len(calls), "dir": calls[-1][1],
            "first_call_utc": calls[0][0].isoformat(),
            "last_call_utc": calls[-1][0].isoformat(),
        })
    nuove = sorted([e for e in entries if e["count"] == 1],
                   key=lambda e: e["first_call_utc"], reverse=True)
    classifica = sorted([e for e in entries if e["count"] >= 2],
                        key=lambda e: (e["count"], e["last_call_utc"]), reverse=True)
    return {"window_days": window_days, "nuove": nuove, "classifica": classifica}
