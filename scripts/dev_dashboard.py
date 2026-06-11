"""Local stdlib dashboard server.

Default mode uses fixtures so the UI can be reviewed without network or
secrets. Use --live to call OANDA through the same scan service.
"""

from __future__ import annotations

import argparse
import mimetypes
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fx_bias_radar import scan_service as S
from fx_bias_radar.dashboard import is_authorized, json_bytes, sanitize_error


def _load_local_env(path: Path) -> None:
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def make_handler(fixtures: Path, live: bool):
    public_dir = ROOT / "public"

    class DevHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            parsed = urlparse(self.path)
            if parsed.path == "/api/health":
                self._json({
                    "ok": True,
                    "service": "fx-bias-radar-dashboard-dev",
                    "has_oanda_token": bool(os.environ.get("OANDA_ACCESS_TOKEN", "").strip()),
                    "has_dashboard_token": bool(os.environ.get("DASHBOARD_TOKEN", "").strip()),
                    "disclaimer": "Radar di attenzione: decisione sulle linee manuali.",
                })
                return
            if parsed.path == "/api/scan":
                self._scan(parsed)
                return
            self._static(parsed.path)

        def _scan(self, parsed):
            token = os.environ.get("DASHBOARD_TOKEN", "dev").strip()
            if not is_authorized(self.headers.get("Authorization"), token):
                self._json({"ok": False, "error": "unauthorized"}, status=401)
                return
            try:
                qs = parse_qs(parsed.query)
                count = int((qs.get("count") or [S.DEFAULT_COUNT])[0])
                if live:
                    rep = S.run_scan_from_oanda(count=count)
                    payload = S.dashboard_payload(rep, source="OANDA local live")
                else:
                    rep = S.run_scan_from_fixtures(str(fixtures))
                    payload = S.dashboard_payload(rep, source="Local fixtures")
                self._json(payload)
            except Exception as exc:
                self._json(
                    {"ok": False, "error": "scan_failed", "detail": sanitize_error(str(exc))},
                    status=502,
                )

        def _static(self, path):
            rel = "index.html" if path in ("", "/") else path.lstrip("/")
            target = (public_dir / rel).resolve()
            if public_dir.resolve() not in target.parents and target != public_dir.resolve():
                self.send_error(404)
                return
            if not target.is_file():
                self.send_error(404)
                return
            data = target.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", mimetypes.guess_type(str(target))[0] or "application/octet-stream")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)

        def _json(self, payload, status=200):
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(json_bytes(payload))

    return DevHandler


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--live", action="store_true", help="fetch OANDA instead of fixtures")
    ap.add_argument("--fixtures", default=str(ROOT / "tests" / "fixtures" / "golden_2026H1"))
    args = ap.parse_args()

    _load_local_env(ROOT / ".env")
    _load_local_env(ROOT.parent / ".env")
    os.environ.setdefault("DASHBOARD_TOKEN", "dev")
    server = ThreadingHTTPServer((args.host, args.port), make_handler(Path(args.fixtures), args.live))
    print(f"Dashboard locale: http://{args.host}:{args.port} (token dev se DASHBOARD_TOKEN non e' impostato)")
    server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
