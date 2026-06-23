"""M3 Fase 0 - Orchestrazione "Pre-Rottura" (H4 direzione + H1 timing).

Display/selezione, NON tocca il motore H4. Pensato per girare ORARIO (cron):
- fetch H4 (chiuse) e H1 (chiuse) delle 28 coppie;
- calcola la forza valutaria su entrambi i timeframe (compute_strength, math
  validata currency_index);
- classifica la confluenza (RIPRESA / RIENTRO, N=3, gated dalla direzione H4);
- impacchetta un payload JSON pronto per la dashboard (8 linee H1 + liste).
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Dict, List, Optional

from . import confluence as CF
from . import rotation as ROT
from . import strength_h1 as SH
from .candles import Candle

DEFAULT_H4_COUNT = 500
DISCLAIMER = "Radar di attenzione: la decisione e' sulle linee manuali."


def build_pre_rottura(h4_candles_by_pair: Dict[str, List[Candle]],
                      h1_candles_by_pair: Dict[str, List[Candle]],
                      *, window: int = SH.DEFAULT_CHART_WINDOW,
                      n_rientro: int = 3, h4_dir_min: float = 1.0,
                      cluster_cap: int = 2,
                      run_time_utc: Optional[str] = None) -> dict:
    """Builder PURO: dai due panieri di candele al payload Pre-Rottura."""
    h4_strength = SH.compute_strength(h4_candles_by_pair, window=window)
    h4_strength["timeframe"] = "H4"
    h1_strength = SH.compute_strength(h1_candles_by_pair, window=window)

    conf = CF.from_strength_payloads(
        h4_strength, h1_strength,
        h4_dir_min=h4_dir_min, n_rientro=n_rientro, cluster_cap=cluster_cap)

    # ROTAZIONI (M4): segnale primario H1, rilevatore calibrato dal backtest.
    rotazioni = ROT.rotations_from_strength(h1_strength, cluster_cap=cluster_cap)

    stamp = run_time_utc or datetime.now(timezone.utc).isoformat(timespec="seconds")
    return {
        "ok": True,
        "kind": "pre_rottura",
        "generated_at_utc": stamp,
        "dir_timeframe": "H4",
        "timing_timeframe": "H1",
        "h4_last_bar_utc": h4_strength.get("last_bar_utc"),
        "h1_last_bar_utc": h1_strength.get("last_bar_utc"),
        "params": {"n_rientro": n_rientro, "h4_dir_min": h4_dir_min,
                   "window": window, "cluster_cap": cluster_cap},
        "rotazioni": rotazioni,             # M4: segnale primario (display)
        "riprese": conf["riprese"],
        "rientri": conf["rientri"],
        "lines_h1": h1_strength,            # 8 serie z H1 per il grafico sovrapposto
        "ranking_h4": h4_strength.get("ranking", []),
        "h4_strength": h4_strength,         # contesto (classifica/forza H4)
        "disclaimer": DISCLAIMER,
    }


def run_from_oanda(*, token: Optional[str] = None, env: Optional[str] = None,
                   h4_count: int = DEFAULT_H4_COUNT,
                   h1_count: int = SH.DEFAULT_H1_COUNT,
                   window: int = SH.DEFAULT_CHART_WINDOW,
                   n_rientro: int = 3, h4_dir_min: float = 1.0,
                   cluster_cap: int = 2) -> dict:
    """Pipeline live: fetch H4+H1 da OANDA -> payload Pre-Rottura."""
    from .oanda_fetch import env_credentials, fetch_all_pairs
    if token is None:
        token, resolved_env = env_credentials()
        env = env or resolved_env
    env = env or "practice"
    h4 = fetch_all_pairs(token, env=env, count=h4_count)   # H4 complete
    h1 = SH.fetch_all_h1(token, env=env, count=h1_count)   # H1 complete
    return build_pre_rottura(h4, h1, window=window, n_rientro=n_rientro,
                             h4_dir_min=h4_dir_min, cluster_cap=cluster_cap)


def to_json(payload: dict) -> str:
    return json.dumps(payload, indent=2)
