"""Avviso email EVENT-DRIVEN: invia quando compaiono rotture H1 ALLINEATE a daily+weekly.

Gira dentro il workflow orario (trigger affidabile cron-job.org): a ogni ciclo legge
lo snapshot aggiornato e, se ci sono nuove rotture allineate a daily+weekly, manda una mail
con le coppie. Niente orari fissi: avviso a ogni nuova barra. Tollerante (snapshot/credenziali
mancanti -> salta senza far fallire il job).

Il segnale (rottura H1 nella direzione di compressioni daily E weekly attive) e' un FILTRO di
qualita': dice DOVE guardare; la decisione e l'ingresso sono sulle linee. Non e' un
consiglio di trade.
"""

from __future__ import annotations

import json
import os
import smtplib
import sys
from email.mime.text import MIMEText

PAGE_URL = "https://fx-bias-radar-engine.vercel.app/pre_rottura.html"
SNAPSHOT = os.path.join("reports", "prerottura", "pre_rottura_latest.json")


def compose(payload: dict) -> tuple[str, str]:
    """Funzione PURA: dallo snapshot a (subject, body). Testabile."""
    al = payload.get("allineate", []) or []
    n = len(al)
    subject = f"FX Bias Radar - {n} rottur{'a' if n == 1 else 'e'} allineat{'a' if n == 1 else 'e'} daily+weekly"
    lines = []
    lines.append("Rotture H1 nella direzione di una compressione daily E weekly attive (segnale piu' selettivo):")
    lines.append("")
    for r in al:
        lines.append(f"  - {r.get('pair')} {r.get('dir')}  (daily+weekly {r.get('dir')})")
    lines.append("")
    lines.append("E' un filtro di QUALITA': dice dove guardare. Incrocia con la tua linea,")
    lines.append("entra a rottura o ritest. Non e' un consiglio di trade.")
    lines.append(PAGE_URL)
    return subject, "\n".join(lines)


def send_email(subject: str, body: str) -> bool:
    user = os.environ.get("FXBR_GMAIL_USER", "").strip()
    pwd = os.environ.get("FXBR_GMAIL_APP_PASSWORD", "").strip()
    to = (os.environ.get("FXBR_DIGEST_TO", "").strip() or user)
    if not user or not pwd:
        print("Avviso: credenziali email mancanti, salto invio.")
        return False
    msg = MIMEText(body, _charset="utf-8")
    msg["Subject"] = subject
    msg["From"] = user
    msg["To"] = to
    with smtplib.SMTP("smtp.gmail.com", 587, timeout=30) as s:
        s.starttls()
        s.login(user, pwd)
        s.sendmail(user, [to], msg.as_string())
    print(f"Avviso inviato a {to}: {subject}")
    return True


def main() -> int:
    force = "--force" in sys.argv
    if not os.path.isfile(SNAPSHOT):
        print(f"Avviso: snapshot assente ({SNAPSHOT}), niente invio.")
        return 0
    try:
        with open(SNAPSHOT, encoding="utf-8") as f:
            payload = json.load(f)
    except Exception as exc:  # noqa: BLE001
        print(f"Avviso: snapshot illeggibile ({exc}), niente invio.")
        return 0
    al = payload.get("allineate", []) or []
    nuove = payload.get("nuove_allineate")  # None sugli snapshot vecchi
    # Event-driven vero: invia solo se in QUESTO ciclo e' comparsa una barra H1 nuova
    # con rotture allineate. A mercato chiuso la barra e' ferma -> nuove vuoto -> niente
    # email ripetute a ogni ora. Con --force (test) si invia comunque.
    trigger = al if force else (nuove if nuove is not None else al)
    if not trigger and not force:
        print("Avviso: nessuna nuova rottura allineata in questo ciclo "
              "(barra gia' notificata o mercato chiuso), niente invio.")
        return 0
    subject, body = compose(payload)
    send_email(subject, body)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
