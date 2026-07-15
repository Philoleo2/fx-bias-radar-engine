"""Post-processing orario: registra le chiamate d1w e aggiunge la classifica 20gg
allo snapshot. NON tocca i motori: legge solo 'allineate' dallo snapshot gia' scritto
da run_pre_rottura, accoda al registro (idempotente) e reinietta 'classifica_chiamate'.
"""

from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fx_bias_radar import calls as CALLS

SNAPSHOT = os.path.join("reports", "prerottura", "pre_rottura_latest.json")
CALLS_LOG = os.path.join("reports", "prerottura", "calls_log.csv")


def main() -> int:
    if not os.path.isfile(SNAPSHOT):
        print(f"update_calls: snapshot assente ({SNAPSHOT}).")
        return 0
    try:
        with open(SNAPSHOT, encoding="utf-8") as f:
            payload = json.load(f)
    except Exception as exc:  # noqa: BLE001
        print(f"update_calls: snapshot illeggibile ({exc}).")
        return 0
    h1_bar = payload.get("h1_last_bar_utc")
    allineate = payload.get("allineate", []) or []
    ts = payload.get("generated_at_utc")
    n = CALLS.append_calls(CALLS_LOG, h1_bar, allineate, ts)
    classifica = CALLS.build_classifica(CALLS_LOG)
    payload["classifica_chiamate"] = classifica
    with open(SNAPSHOT, "w", encoding="utf-8") as f:
        f.write(json.dumps(payload, indent=2))
    print(f"update_calls: +{n} righe | nuove={len(classifica['nuove'])} "
          f"classifica={len(classifica['classifica'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
