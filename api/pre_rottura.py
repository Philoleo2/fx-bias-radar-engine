"""API endpoint Pre-Rottura (M3): serve l'ultimo snapshot orario calcolato dal
cron. Auth bearer come le altre API; no-store.

Freschezza (FR/M3): il cron committa pre_rottura_latest.json su GitHub ogni ora,
ma Vercel servirebbe il file del bundle del deploy precedente. Per avere il dato
fresco SENZA redeploy ogni ora, l'endpoint legge il JSON dal RAW di GitHub (repo
privato -> serve un token di sola lettura nelle env di Vercel), con cache breve
in memoria; in mancanza di token/rete, fallback al file incluso nel bundle.

ENV (Vercel, opzionali ma necessarie per la freschezza oraria):
  FXBR_GH_REPO   = "Philoleo2/fx-bias-radar-engine"
  FXBR_GH_TOKEN  = <PAT fine-grained, sola lettura "contents" su quel repo>
  FXBR_GH_REF    = "main"   (branch su cui il cron committa; default "main")
  FXBR_GH_PATH   = "reports/prerottura/pre_rottura_latest.json" (default)
  FXBR_GH_TTL    = "120"    (secondi di cache, default 120)
Il token resta SOLO lato server, mai esposto al client.
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.request

from http.server import BaseHTTPRequestHandler

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from fx_bias_radar.dashboard import is_authorized, json_bytes, sanitize_error

REL_PATH = os.path.join("reports", "prerottura", "pre_rottura_latest.json")
DISCLAIMER = "Radar di attenzione: la decisione e' sulle linee manuali."

_GH_CACHE = {"ts": 0.0, "payload": None}


def _gh_fetch():
    """Legge il JSON dal raw GitHub (repo privato, token read-only). Cache breve.
    Ritorna il dict, oppure None se non configurato / errore."""
    repo = os.environ.get("FXBR_GH_REPO", "").strip()
    token = os.environ.get("FXBR_GH_TOKEN", "").strip()
    if not repo or not token:
        return None
    ttl = int(os.environ.get("FXBR_GH_TTL", "120") or "120")
    now = time.time()
    if _GH_CACHE["payload"] is not None and now - float(_GH_CACHE["ts"]) <= ttl:
        return _GH_CACHE["payload"]
    ref = os.environ.get("FXBR_GH_REF", "main").strip() or "main"
    path = os.environ.get("FXBR_GH_PATH", REL_PATH.replace(os.sep, "/")).strip()
    url = f"https://api.github.com/repos/{repo}/contents/{path}?ref={ref}"
    req = urllib.request.Request(url, headers={
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github.raw+json",
        "User-Agent": "fx-bias-radar",
        "X-GitHub-Api-Version": "2022-11-28",
    })
    try:
        with urllib.request.urlopen(req, timeout=6) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except Exception:
        return None
    _GH_CACHE["payload"] = payload
    _GH_CACHE["ts"] = now
    return payload


def _load_bundled():
    """Fallback: file incluso nel bundle del deploy (o repo root)."""
    for path in (os.path.join(ROOT, REL_PATH), REL_PATH):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (FileNotFoundError, ValueError):
            continue
    return None


def _load_latest():
    """GitHub raw (fresco) -> fallback bundle."""
    return _gh_fetch() or _load_bundled()


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
                "detail": sanitize_error(str(exc), [os.environ.get("FXBR_GH_TOKEN")]),
                "disclaimer": DISCLAIMER,
            }, status=502)

    def _send_json(self, payload: dict, status: int):
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(json_bytes(payload))
