"""Append-only JSONL persistence for PAIR_PREWAKE_V1.

FX Bias Radar has no database: production state is JSON/CSV committed to the
repository by the hourly GitHub Action and served read-only by the Vercel
functions. PREWAKE follows the same substrate.

Design rules:

* ``prewake_events.jsonl`` is APPEND-ONLY and IMMUTABLE (SS41). An event is never
  rewritten because it failed, reversed, or was not traded. Corrections are new
  append-only records in ``prewake_corrections.jsonl`` carrying the corrected
  event_id and a reason.
* Anything mutable about an event (email delivery, outcome maturation, FX Bias
  linking) lives in its own append-only log where the newest record per
  event_id wins. That keeps the event ledger immutable while still allowing
  retries and late-arriving outcomes.
* ``prewake_state.json`` is the only mutable file: it carries the recursive EWMA
  and lifecycle state so an hourly run equals a full replay from the origin.
"""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
from datetime import datetime, timezone

BASE_DIR = os.path.join("reports", "prewake")

EVENTS = "prewake_events.jsonl"
RUNS = "prewake_runs.jsonl"
EMAIL_LOG = "prewake_email.jsonl"
OUTCOMES = "prewake_outcomes.jsonl"
LINKS = "prewake_fx_bias_links.jsonl"
CORRECTIONS = "prewake_corrections.jsonl"
STATE = "prewake_state.json"
LATEST = "prewake_latest.json"
HEALTH = "prewake_health.json"


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def path(name: str, base: str = BASE_DIR) -> str:
    return os.path.join(base, name)


def event_id(model_version: str, pair: str, bar_time_utc: str, event_type: str, direction: int) -> str:
    """Idempotency key (SS24). Same H1 bar can never produce two identical events."""
    raw = f"{model_version}|{pair}|{bar_time_utc}|{event_type}|{'LONG' if direction > 0 else 'SHORT'}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def email_idempotency_key(model_version: str, eid: str) -> str:
    return f"prewake:{model_version}:{eid}"


# ---------------------------------------------------------------- jsonl io

def read_jsonl(name: str, base: str = BASE_DIR) -> list[dict]:
    target = path(name, base)
    if not os.path.exists(target):
        return []
    out = []
    with open(target, "r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out


def append_jsonl(name: str, records: list[dict], base: str = BASE_DIR) -> int:
    if not records:
        return 0
    target = path(name, base)
    os.makedirs(os.path.dirname(target), exist_ok=True)
    with open(target, "a", encoding="utf-8", newline="\n") as handle:
        for record in records:
            handle.write(json.dumps(record, sort_keys=True, ensure_ascii=False, allow_nan=False) + "\n")
    return len(records)


def write_json(name: str, payload, base: str = BASE_DIR) -> None:
    """Atomic write for the few mutable/derived files."""
    target = path(name, base)
    os.makedirs(os.path.dirname(target), exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(target), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False)
            handle.write("\n")
        os.replace(tmp, target)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def read_json(name: str, base: str = BASE_DIR, default=None):
    target = path(name, base)
    if not os.path.exists(target):
        return default
    with open(target, "r", encoding="utf-8") as handle:
        return json.load(handle)


# ---------------------------------------------------------------- events

def existing_event_ids(base: str = BASE_DIR) -> set[str]:
    return {row["event_id"] for row in read_jsonl(EVENTS, base)}


def append_events(records: list[dict], base: str = BASE_DIR) -> list[dict]:
    """Append only events whose event_id is not already stored (SS24)."""
    known = existing_event_ids(base)
    fresh = [r for r in records if r["event_id"] not in known]
    append_jsonl(EVENTS, fresh, base)
    return fresh


def latest_by_event(name: str, base: str = BASE_DIR) -> dict:
    """Collapse an append-only side log to the newest record per event_id."""
    out: dict[str, dict] = {}
    for row in read_jsonl(name, base):
        out[row["event_id"]] = row
    return out


def events_with_status(base: str = BASE_DIR) -> list[dict]:
    """Immutable events joined with their newest email / outcome / link records."""
    emails = latest_by_event(EMAIL_LOG, base)
    outcomes = latest_by_event(OUTCOMES, base)
    links = latest_by_event(LINKS, base)
    rows = []
    for event in read_jsonl(EVENTS, base):
        eid = event["event_id"]
        row = dict(event)
        email = emails.get(eid, {})
        row["email_status"] = email.get("status", "PENDING" if event.get("is_prospective") else "SUPPRESSED_BACKFILL")
        row["email_sent_at"] = email.get("sent_at")
        row["email_attempts"] = email.get("attempts", 0)
        row["outcomes"] = outcomes.get(eid, {}).get("outcomes")
        row["fx_bias_link"] = links.get(eid)
        rows.append(row)
    return rows
