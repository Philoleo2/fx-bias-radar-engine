from __future__ import annotations

import os
import sys
from http.server import BaseHTTPRequestHandler

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from fx_bias_radar.dashboard import json_bytes


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        payload = {
            "ok": True,
            "service": "fx-bias-radar-dashboard",
            "has_oanda_token": bool(os.environ.get("OANDA_ACCESS_TOKEN", "").strip()),
            "has_dashboard_token": bool(os.environ.get("DASHBOARD_TOKEN", "").strip()),
            "disclaimer": "Radar di attenzione: decisione sulle linee manuali.",
        }
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(json_bytes(payload))
