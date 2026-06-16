"""API endpoint Pre-Rottura (M3): serve l'ultimo snapshot orario calcolato dal
cron (reports/prerottura/pre_rottura_latest.json). Auth bearer come le altre
API; no-store. Non calcola live (lo fa il cron): qui si LEGGE lo snapshot.
"""

from __future__ import annotations

import json
import os
import sys
from http.server import BaseHTTPRequestHandler

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from fx_bias_radar.dashboard import is_authorized, json_bytes, sanitize_error

REL_PATH = os.path.join("reports", "prerottura", "pre_rottura_latest.json")
DISCLAIMER = "Radar di attenzione: la decisione e' sulle linee manuali."


def _load_latest():
    """Carica lo snapshot piu' recente; risolve anche contro il root del repo
    (cwd serverless puo' non essere il root, cfr. review M2C)."""
    candidates = [os.path.join(ROOT, REL_PATH), REL_PATH]
    for path in candidates:
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (FileNotFoundError, ValueError):
            continue
    return None


class handler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Cache-Control", "no-store")
        self.end_headers()

    def do_GET(self):
        expected = os.environ.get("DASHBOARD_TOKEN", "").strip()
        if not is_authorized(self.headers.get("Authorization"), expected):
            self._send_json({"ok": False, "error": "unauthorized"}, status=401)
            return
        try:
            payload = _load_latest()
            if not payload:
                self._send_json({
                    "ok": False,
                    "error": "no_data",
                    "detail": "Pre-Rottura non ancora calcolata (cron orario non eseguito).",
                    "disclaimer": DISCLAIMER,
                }, status=200)
                return
            self._send_json(payload, status=200)
        except Exception as exc:  # noqa: BLE001
            self._send_json({
                "ok": False,
                "error": "read_failed",
                "detail": sanitize_error(str(exc)),
                "disclaimer": DISCLAIMER,
            }, status=502)

    def _send_json(self, payload: dict, status: int):
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(json_bytes(payload))
