"""Digest email dello scanner Pre-Rottura, 2 volte al giorno (08:00 / 15:00 CEST).

Pensato per girare DENTRO il workflow orario (trigger affidabile cron-job.org): lo
step parte ogni ora, ma invia SOLO se l'ora locale Europe/Rome e' 8 o 15. Legge lo
snapshot gia' committato (reports/prerottura/pre_rottura_latest.json), compone il
digest e invia via SMTP (Gmail app password nei secret; Claude non la vede).

Lo scanner non ha edge meccanico: il digest dice solo DOVE guardare; la decisione e'
sulle linee manuali. Non e' un consiglio di trade.
"""

from __future__ import annotations

import json
import os
import smtplib
import sys
from datetime import datetime, timedelta, timezone
from email.mime.text import MIMEText

SEND_HOURS = {8, 15}
PAGE_URL = "https://fx-bias-radar-engine.vercel.app/pre_rottura.html"
SNAPSHOT = os.path.join("reports", "prerottura", "pre_rottura_latest.json")


def rome_hour(now_utc: datetime | None = None) -> int:
    now = now_utc or datetime.now(timezone.utc)
    try:
        from zoneinfo import ZoneInfo
        return now.astimezone(ZoneInfo("Europe/Rome")).hour
    except Exception:
        # fallback grezzo (CEST estivo): UTC+2
        return (now.astimezone(timezone.utc) + timedelta(hours=2)).hour


def should_send(hour: int, hours=SEND_HOURS) -> bool:
    return hour in hours


def _fmt_rome(iso_utc: str | None, add_hours: int = 0) -> str:
    if not iso_utc:
        return "-"
    try:
        t = datetime.fromisoformat(iso_utc.replace("Z", "+00:00")) + timedelta(hours=add_hours)
        from zoneinfo import ZoneInfo
        return t.astimezone(ZoneInfo("Europe/Rome")).strftime("%d/%m %H:%M")
    except Exception:
        return iso_utc


def compose(payload: dict, hour: int) -> tuple[str, str]:
    """Funzione PURA: dal payload Pre-Rottura a (subject, body). Testabile."""
    rot = payload.get("rotazioni", []) or []
    ranking = payload.get("ranking_h4", []) or []
    subject = f"FX Bias Radar - digest {hour:02d}:00 ({len(rot)} rotazion{'e' if len(rot)==1 else 'i'})"

    lines = []
    lines.append(f"Scanner Pre-Rottura - aggiornato {_fmt_rome(payload.get('generated_at_utc'))} (Rome)")
    lines.append(f"Barra H1 chiusa: {_fmt_rome(payload.get('h1_last_bar_utc'), 1)}")
    if ranking:
        lines.append("Forza H4: " + " > ".join(ranking))
    lines.append("")
    lines.append("ROTAZIONI (dove guardare):")
    if rot:
        for r in rot:
            lines.append(f"  - {r.get('pair')} {r.get('dir')} | {r.get('forte')} molla, "
                         f"{r.get('debole')} recupera | spread H1 {r.get('spread_h1')}")
    else:
        lines.append("  Nessuna rotazione a questa chiusura.")
    lines.append("")
    lines.append("Promemoria: lo scanner indica DOVE guardare; la decisione e l'ingresso")
    lines.append("sono sulle tue linee (rottura/ritest). Non e' un consiglio di trade.")
    lines.append(PAGE_URL)
    return subject, "\n".join(lines)


def send_email(subject: str, body: str) -> bool:
    user = os.environ.get("FXBR_GMAIL_USER", "").strip()
    pwd = os.environ.get("FXBR_GMAIL_APP_PASSWORD", "").strip()
    to = (os.environ.get("FXBR_DIGEST_TO", "").strip() or user)
    if not user or not pwd:
        print("Digest: credenziali email mancanti (FXBR_GMAIL_USER/APP_PASSWORD), salto invio.")
        return False
    msg = MIMEText(body, _charset="utf-8")
    msg["Subject"] = subject
    msg["From"] = user
    msg["To"] = to
    with smtplib.SMTP("smtp.gmail.com", 587, timeout=30) as s:
        s.starttls()
        s.login(user, pwd)
        s.sendmail(user, [to], msg.as_string())
    print(f"Digest inviato a {to}: {subject}")
    return True


def main() -> int:
    force = "--force" in sys.argv
    hour = rome_hour()
    if not force and not should_send(hour):
        print(f"Digest: ora locale {hour} non in {sorted(SEND_HOURS)}, niente invio.")
        return 0
    if not os.path.isfile(SNAPSHOT):
        print(f"Digest: snapshot assente ({SNAPSHOT}), niente invio.")
        return 0
    try:
        with open(SNAPSHOT, encoding="utf-8") as f:
            payload = json.load(f)
    except Exception as exc:  # noqa: BLE001 - non far fallire il workflow
        print(f"Digest: snapshot illeggibile ({exc}), niente invio.")
        return 0
    subject, body = compose(payload, hour)
    send_email(subject, body)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
