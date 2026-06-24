"""M3 Fase 0 - Orchestrazione "Pre-Rottura" (H1 timing + D/W filter).

Display/selezione, NON tocca il motore H4 legacy. Pensato per girare ORARIO:
- fetch H1, D1 e W chiuse delle 28 coppie;
- calcola la forza valutaria H1 per il grafico a 8 linee;
- seleziona rotture H1 allineate a compressioni daily + weekly.
Il calcolo H4 resta disponibile solo se le candele H4 sono passate esplicitamente
da test/logger legacy.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Dict, List, Optional

from . import compression as COMP
from . import confluence as CF
from . import rotation as ROT
from . import strength_h1 as SH
from .candles import Candle

DEFAULT_H4_COUNT = 500
DISCLAIMER = "Radar di attenzione: la decisione e' sulle linee manuali."


def build_pre_rottura(h4_candles_by_pair: Optional[Dict[str, List[Candle]]],
                      h1_candles_by_pair: Dict[str, List[Candle]],
                      d1_candles_by_pair: Optional[Dict[str, List[Candle]]] = None,
                      w_candles_by_pair: Optional[Dict[str, List[Candle]]] = None,
                      *, window: int = SH.DEFAULT_CHART_WINDOW,
                      n_rientro: int = 3, h4_dir_min: float = 1.0,
                      cluster_cap: int = 2,
                      run_time_utc: Optional[str] = None) -> dict:
    """Builder PURO: dai due panieri di candele al payload Pre-Rottura."""
    h1_strength = SH.compute_strength(h1_candles_by_pair, window=window)

    # Direzione/Forza H4 rimosse dalla UI: H4 si calcola solo se le candele
    # vengono fornite da test/logger legacy. La pipeline live non lo scarica piu'.
    if h4_candles_by_pair:
        h4_strength = SH.compute_strength(h4_candles_by_pair, window=window)
        h4_strength["timeframe"] = "H4"
        conf = CF.from_strength_payloads(
            h4_strength, h1_strength,
            h4_dir_min=h4_dir_min, n_rientro=n_rientro, cluster_cap=cluster_cap)
    else:
        h4_strength = {}
        conf = {"riprese": [], "rientri": []}

    # ROTAZIONI (M4): segnale primario H1, rilevatore calibrato dal backtest.
    rotazioni = ROT.rotations_from_strength(h1_strength, cluster_cap=cluster_cap)
    # COMPRESSIONI: rottura da squeeze sull'ultima barra H1 (profilo w12_p20).
    compressioni = COMP.compressioni_from_candles(h1_candles_by_pair)
    # ALLINEATE DAILY+WEEKLY: rottura H1 nella direzione di una compressione D1 E W
    # attive (coorte d1w del backtest: hit ~53-55%, ritorno medio positivo, net-positiva).
    allineate = (COMP.daily_weekly_aligned_breakouts(
                     h1_candles_by_pair, d1_candles_by_pair, w_candles_by_pair)
                 if (d1_candles_by_pair and w_candles_by_pair) else [])

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
        "allineate": allineate,             # rottura H1 allineata a daily+weekly (PRIMARIO)
        "rotazioni": rotazioni,             # M4: legacy (non mostrato)
        "compressioni": compressioni,       # legacy (non mostrato)
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
    """Pipeline live: fetch H1+D1+W da OANDA -> payload Pre-Rottura."""
    from .oanda_fetch import env_credentials
    if token is None:
        token, resolved_env = env_credentials()
        env = env or resolved_env
    env = env or "practice"
    h1 = SH.fetch_all_h1(token, env=env, count=h1_count)   # H1 complete
    d1 = SH.fetch_all_daily(token, env=env, count=300)     # D1 per allineamento
    w1 = SH.fetch_all_weekly(token, env=env, count=200)    # Weekly per allineamento
    return build_pre_rottura(None, h1, d1, w1, window=window, n_rientro=n_rientro,
                             h4_dir_min=h4_dir_min, cluster_cap=cluster_cap)


def to_json(payload: dict) -> str:
    return json.dumps(payload, indent=2)
