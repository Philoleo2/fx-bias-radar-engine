"""PREWAKE email rendering and idempotent delivery.

Reuses the FX Bias Gmail SMTP credentials (FXBR_GMAIL_USER /
FXBR_GMAIL_APP_PASSWORD / FXBR_DIGEST_TO). No second SMTP system.

FX Bias emails are NOT touched (SS35): PREWAKE alerts are separate messages.

Presentation note (agreed with Leonardo): the frozen lifecycle label
(NEW_WAKE / REAWAKENING) is recorded in the event ledger for audit and parity,
but the email uses a single neutral label. In the frozen candidate NEW_WAKE
means "first ever for this pair+direction over the whole scored series", so
after seeding from full history essentially every live alert is REAWAKENING and
a "riparte" subject would be misleading.

Language rules (SS32): never BUY / SELL / ENTRY / STOP / TARGET, never a trade
recommendation. Never leak tokens, credentials or stack traces (SS62).
"""
from __future__ import annotations

import os
import smtplib
from email.mime.text import MIMEText
from zoneinfo import ZoneInfo

from .primitives import parse_utc
from .store import email_idempotency_key

ROME = ZoneInfo("Europe/Rome")
PAGE_URL = "https://fx-bias-radar-engine.vercel.app/prewake.html"


def bar_close_rome(bar_open_utc: str) -> str:
    """Alerts refer to the H1 CLOSE, which is one hour after the bar open."""
    opened = parse_utc(bar_open_utc)
    closed = opened.replace(minute=0, second=0, microsecond=0)
    closed = closed.astimezone(ROME)
    return closed.strftime("%H:%M")


def bar_close_rome_full(bar_open_utc: str) -> str:
    opened = parse_utc(bar_open_utc)
    return opened.astimezone(ROME).strftime("%d/%m/%Y %H:%M")


def _side(event: dict) -> str:
    """Accept both the engine's int direction and the stored LONG/SHORT string."""
    raw = event.get("direction_sign", event.get("direction"))
    if isinstance(raw, str):
        return "LONG" if raw.upper() == "LONG" else "SHORT"
    return "LONG" if int(raw) > 0 else "SHORT"


def render(event: dict) -> tuple[str, str]:
    """Return (subject, body) for one PREWAKE event."""
    side = _side(event)
    hhmm = bar_close_rome(event["bar_time_utc"])
    subject = f"[PREWAKE] {event['pair']} — {hhmm}"

    dual = event.get("dual_leg")
    lines = [
        "PAIR_PREWAKE_V1",
        "",
        event["pair"],
        f"Pressione sperimentale registrata: {side}",
        "Non e' un segnale direzionale.",
        "",
        f"H1 chiusa: {hhmm} Europe/Rome ({bar_close_rome_full(event['bar_time_utc'])})",
        "",
        f"Score: {event['score']:.6f}",
        f"Threshold: {event['threshold']:.6f}",
        "",
        f"FX Bias al momento: {'YES' if event.get('fx_bias_same') else 'NO'}",
    ]
    if dual is not None:
        lines.append(f"Dual-leg: {'YES' if dual else 'NO'}")
    if event.get("same_bar_raw_breakout"):
        lines.append("Nota: rottura grezza gia' presente sulla stessa H1 (diagnostica).")
    lines += [
        "",
        "Radar di attenzione: verificare direzione e contesto con ValutaVision e grafico.",
        "",
        PAGE_URL,
    ]
    return subject, "\n".join(lines)


def send(subject: str, body: str) -> bool:
    user = os.environ.get("FXBR_GMAIL_USER", "").strip()
    pwd = os.environ.get("FXBR_GMAIL_APP_PASSWORD", "").strip()
    to = (os.environ.get("FXBR_PREWAKE_TO", "").strip()
          or os.environ.get("FXBR_DIGEST_TO", "").strip() or user)
    if not user or not pwd:
        raise RuntimeError("missing email credentials")
    msg = MIMEText(body, _charset="utf-8")
    msg["Subject"] = subject
    msg["From"] = user
    msg["To"] = to
    with smtplib.SMTP("smtp.gmail.com", 587, timeout=30) as server:
        server.starttls()
        server.login(user, pwd)
        server.sendmail(user, [to], msg.as_string())
    return True


def deliver(event: dict, model_version: str, dry_run: bool = False) -> dict:
    """Send one alert, returning an append-only email-log record.

    Never raises: an SMTP failure leaves the event in the ledger and marks the
    email for retry on the next run (SS34). No duplicate event is created.
    """
    from .store import now_utc

    key = email_idempotency_key(model_version, event["event_id"])
    subject, body = render(event)
    record = {
        "event_id": event["event_id"],
        "idempotency_key": key,
        "model_version": model_version,
        "subject": subject,
        "attempts": int(event.get("email_attempts", 0)) + 1,
        "recorded_at": now_utc(),
    }
    if dry_run:
        record.update(status="DRY_RUN", sent_at=None)
        return record
    try:
        send(subject, body)
        record.update(status="SENT", sent_at=now_utc())
    except Exception as exc:                                   # noqa: BLE001
        # SS62: never leak credentials or stack traces into stored artefacts.
        record.update(status="RETRY", sent_at=None, error_code=type(exc).__name__)
    return record
