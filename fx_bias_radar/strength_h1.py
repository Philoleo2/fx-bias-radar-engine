"""H1 currency-strength layer (M3 Fase 1) - SELEZIONE, display-only.

Layer separato e PARALLELO: scarica candele H1 delle 28 coppie e calcola la
forza valutaria (z-score) delle 8 valute riusando la stessa matematica
VALIDATA (currency_index) applicata alle chiusure H1. NON tocca il motore H4,
ne' le soglie, ne' la macchina a stati. E' uno strato "dove guardare" a bassa
confidenza, subordinato alla direzione H4 (vedi PIANO M3).

No-repaint: si usano solo candele H1 COMPLETE (chiuse).
"""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List, Optional

from . import candles as C
from . import currency_index as CI
from . import pairs as P
from .candles import Candle
from .oanda import OandaError
from .oanda_fetch import _client_for, _is_transient_oanda_error, env_credentials

# Storia H1 sufficiente per lo z-score (lenZ=100) + finestra del grafico.
DEFAULT_H1_COUNT = 300
# Barre H1 mostrate nel grafico a 8 linee.
DEFAULT_CHART_WINDOW = 120


def fetch_h1(instrument: str, token: str, env: str = "practice",
             count: int = DEFAULT_H1_COUNT, retries: int = 2) -> List[Candle]:
    """Scarica candele H1 midpoint COMPLETE per uno strumento (con retry)."""
    client = _client_for(token, env)
    max_attempts = max(1, retries + 1)
    raw = None
    for attempt in range(max_attempts):
        try:
            raw = client.candles(
                instrument,
                granularity="H1",
                count=count,
                price="M",
                include_incomplete=False,
            )
            break
        except OandaError as exc:
            if attempt >= max_attempts - 1 or not _is_transient_oanda_error(exc):
                raise
            time.sleep(0.25 * (2 ** attempt))
    return [
        Candle(time=c.time.isoformat(), o=c.open, h=c.high, l=c.low,
               c=c.close, volume=c.volume, complete=c.complete)
        for c in raw
        if c.complete
    ]


def fetch_all_h1(token: str, env: str = "practice",
                 count: int = DEFAULT_H1_COUNT,
                 max_workers: int = 28) -> Dict[str, List[Candle]]:
    """Scarica H1 per tutte le 28 coppie in concorrenza."""
    out: Dict[str, List[Candle]] = {}
    workers = max(1, min(max_workers, len(P.PAIRS)))

    def fetch_pair(pair: str):
        return pair, fetch_h1(P.oanda_instrument(pair), token, env=env, count=count)

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(fetch_pair, pair): pair for pair in P.PAIRS}
        for future in as_completed(futures):
            pair, cs = future.result()
            out[pair] = cs
    return out


def _round(value, ndigits=4):
    return round(value, ndigits) if value is not None else None


def compute_strength(candles_by_pair: Dict[str, List[Candle]], *,
                     window: int = DEFAULT_CHART_WINDOW) -> dict:
    """Calcola le 8 linee di forza valutaria su H1 (chiuse).

    Riusa candles.align + currency_index.build (matematica validata). Ritorna
    un payload pronto per il grafico a 8 linee + classifica per forza.
    """
    missing = [pair for pair in P.PAIRS if pair not in candles_by_pair]
    if missing:
        raise ValueError(f"coppie H1 mancanti: {missing}")

    times, closes, _align = C.align(candles_by_pair, include_incomplete=False)
    cd = CI.build(times, closes)

    n = len(times)
    w = max(1, min(window, n))
    last = n - 1

    currencies = []
    for ccy in P.CURRENCIES:
        z = cd.z[ccy]
        sl = cd.sl[ccy]
        cur_z = z[last]
        cur_sl = sl[last]
        slope = cur_sl if cur_sl is not None else 0.0
        currencies.append({
            "ccy": ccy,
            "z": _round(cur_z),
            "slope": _round(cur_sl),
            "dir": "up" if slope > 0 else ("down" if slope < 0 else "flat"),
            "rank": cd.rank[ccy][last],
            "series": [_round(v) for v in z[-w:]],
        })

    ranking = [c["ccy"] for c in sorted(
        currencies, key=lambda c: (c["z"] is None, -(c["z"] or 0.0)))]

    return {
        "timeframe": "H1",
        "bars": w,
        "times": times[-w:],
        "last_bar_utc": times[-1] if times else None,
        "currencies": currencies,
        "ranking": ranking,
    }


def run_strength_h1_from_oanda(*, token: Optional[str] = None,
                               env: Optional[str] = None,
                               count: int = DEFAULT_H1_COUNT,
                               window: int = DEFAULT_CHART_WINDOW) -> dict:
    """Pipeline live: fetch H1 OANDA -> forza valute H1."""
    if token is None:
        token, resolved_env = env_credentials()
        env = env or resolved_env
    candles_by_pair = fetch_all_h1(token, env=env or "practice", count=count)
    return compute_strength(candles_by_pair, window=window)
