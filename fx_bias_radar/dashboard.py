"""Dashboard security and serialization helpers."""

from __future__ import annotations

import csv
import hmac
import io
import json
from typing import Iterable


def is_authorized(authorization_header: str | None, expected_token: str | None) -> bool:
    """Validate a dashboard bearer token without leaking timing information."""
    expected = (expected_token or "").strip()
    if not expected or not authorization_header:
        return False
    prefix = "Bearer "
    if not authorization_header.startswith(prefix):
        return False
    provided = authorization_header[len(prefix):].strip()
    return hmac.compare_digest(provided, expected)


def sanitize_error(message: str, secrets: Iterable[str | None] = ()) -> str:
    """Remove known secret values from an error string."""
    out = str(message)
    for secret in secrets:
        if secret:
            out = out.replace(secret, "<redacted>")
    return out[:500]


def json_bytes(payload: dict) -> bytes:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def pairs_to_csv(rows: list[dict]) -> str:
    fields = ["pair", "bias", "tipo", "stato", "score", "forte", "debole", "spread", "note", "age"]
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=fields, extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        writer.writerow(row)
    return buffer.getvalue()
