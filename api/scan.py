from __future__ import annotations

import os
import sys
import time
from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from fx_bias_radar import scan_service as S
from fx_bias_radar.dashboard import is_authorized, json_bytes, sanitize_error

_CACHE = {
    "key": None,
    "created": 0.0,
    "payload": None,
}


def _int_query(value, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return max(minimum, min(maximum, parsed))


def _cache_seconds() -> int:
    return _int_query(os.environ.get("CACHE_SECONDS"), 0, 0, 600)


def _scan_mode(value) -> str:
    mode = str(value or "intrabar").strip().lower()
    if mode in {"closed", "close", "h4close"}:
        return "closed"
    return "intrabar"


def build_scan_payload(count: int = S.DEFAULT_COUNT, mode: str = "intrabar") -> dict:
    mode = _scan_mode(mode)
    ttl = _cache_seconds()
    cache_key = f"oanda:{mode}:{count}"
    now = time.time()
    if ttl > 0 and _CACHE["key"] == cache_key and _CACHE["payload"] is not None:
        if now - float(_CACHE["created"]) <= ttl:
            cached = dict(_CACHE["payload"])
            cached["cache"] = {"hit": True}
            return cached

    token = os.environ.get("OANDA_ACCESS_TOKEN", "").strip()
    env = os.environ.get("OANDA_ENV", "practice").strip() or "practice"
    if not token:
        raise RuntimeError("OANDA_ACCESS_TOKEN mancante: dati live non disponibili")

    try:
        report = S.run_scan_from_oanda(
            token=token,
            env=env,
            count=count,
            include_incomplete=(mode == "intrabar"),
        )
        payload = S.dashboard_payload(
            report,
            source=f"OANDA {env}",
            cache_hit=False,
            requested_mode=mode,
        )
    except Exception as exc:
        detail = sanitize_error(str(exc), [token])
        raise RuntimeError(f"OANDA live non disponibile: {detail}") from exc

    if ttl > 0:
        _CACHE["key"] = cache_key
        _CACHE["created"] = now
        _CACHE["payload"] = payload
    return payload


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

        parsed = urlparse(self.path)
        qs = parse_qs(parsed.query)
        count = _int_query((qs.get("count") or [S.DEFAULT_COUNT])[0], S.DEFAULT_COUNT, 400, 800)
        mode = _scan_mode((qs.get("mode") or ["intrabar"])[0])
        try:
            payload = build_scan_payload(count=count, mode=mode)
            self._send_json(payload, status=200)
        except Exception as exc:
            self._send_json(
                {
                    "ok": False,
                    "error": "scan_failed",
                    "detail": sanitize_error(str(exc), [os.environ.get("OANDA_ACCESS_TOKEN")]),
                    "disclaimer": "Radar di attenzione: decisione sulle linee manuali.",
                },
                status=502,
            )

    def _send_json(self, payload: dict, status: int):
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(json_bytes(payload))
