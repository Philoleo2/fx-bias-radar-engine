"""OANDA REST v20 candle fetch adapter (data endpoints ONLY).

Hard rule: no order/trade endpoints, ever (brief section 14).
This module keeps the M1 interface but routes requests through the M0
``OandaClient`` so there is one low-level REST client in the merged repo.
"""

from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List, Optional

from .candles import Candle
from .config import (
    DEFAULT_LIVE_URL,
    DEFAULT_PRACTICE_URL,
    OandaConfig,
    load_oanda_config,
)
from .oanda import OandaClient
from . import pairs as P

_BASE = {
    "practice": DEFAULT_PRACTICE_URL,
    "live": DEFAULT_LIVE_URL,
}


def _client_for(token: str, env: str) -> OandaClient:
    env_name = (env or "practice").strip().lower()
    base_url = _BASE.get(env_name, DEFAULT_PRACTICE_URL)
    account_id = None
    try:
        cfg = load_oanda_config()
    except Exception:
        cfg = None
    if cfg and cfg.access_token == token:
        env_name = cfg.env
        base_url = cfg.base_url
        account_id = cfg.account_id
    return OandaClient(
        OandaConfig(
            env=env_name,
            base_url=base_url.rstrip("/"),
            access_token=token,
            account_id=account_id,
        ),
        timeout_seconds=30,
    )


def fetch_h4(instrument: str, token: str, env: str = "practice",
             count: Optional[int] = 500, from_time: Optional[str] = None,
             to_time: Optional[str] = None) -> List[Candle]:
    """Fetch H4 midpoint candles; only complete=True are returned."""
    raw = _client_for(token, env).candles(
        instrument,
        granularity="H4",
        count=count,
        from_time=from_time,
        to_time=to_time,
        price="M",
    )
    return [
        Candle(
            time=c.time.isoformat(),
            o=c.open,
            h=c.high,
            l=c.low,
            c=c.close,
            volume=c.volume,
            complete=c.complete,
        )
        for c in raw
        if c.complete
    ]


def fetch_all_pairs(token: str, env: str = "practice", count: int = 500,
                    from_time: Optional[str] = None,
                    to_time: Optional[str] = None,
                    max_workers: int = 8) -> Dict[str, List[Candle]]:
    """Fetch all 28 pairs concurrently to keep dashboard/API latency bounded."""
    out: Dict[str, List[Candle]] = {}
    workers = max(1, min(max_workers, len(P.PAIRS)))

    def fetch_pair(pair: str):
        return pair, fetch_h4(P.oanda_instrument(pair), token, env=env,
                              count=count, from_time=from_time, to_time=to_time)

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(fetch_pair, pair): pair for pair in P.PAIRS}
        for future in as_completed(futures):
            pair, candles = future.result()
            out[pair] = candles
    return out


def _try_m0_config_loader():
    """Try the M0 config loader (Codex's fx_bias_radar.config), if merged."""
    try:
        cfg = load_oanda_config()
    except Exception:
        return None
    if isinstance(cfg, dict):
        token = (cfg.get("token") or cfg.get("access_token")
                 or cfg.get("OANDA_ACCESS_TOKEN"))
        env = (cfg.get("env") or cfg.get("environment")
               or cfg.get("OANDA_ENV") or "practice")
    else:
        token = getattr(cfg, "token", None) or getattr(cfg, "access_token", None)
        env = (getattr(cfg, "env", None) or getattr(cfg, "environment", None)
               or "practice")
    return (token, env) if token else None


def _try_dotenv_file():
    """Minimal .env reader (KEY=VALUE), searched in cwd and repo root."""
    candidates = [
        os.path.join(os.getcwd(), ".env"),
        os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"),
    ]
    for path in candidates:
        if not os.path.isfile(path):
            continue
        values = {}
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, _, v = line.partition("=")
                values[k.strip()] = v.strip().strip('"').strip("'")
        token = values.get("OANDA_ACCESS_TOKEN", "")
        if token:
            return token, values.get("OANDA_ENV", "practice")
    return None


def env_credentials():
    """Resolve OANDA credentials (review Codex, Finding 2).

    Order: (1) environment variables (GitHub Actions secrets win);
    (2) M0 config loader `fx_bias_radar.config.load_oanda_config()` if the
    module is present in the merged repo; (3) `.env` file in cwd/repo root.
    In locale basta il `.env` gia' compilato da Leonardo per M0.
    """
    token = os.environ.get("OANDA_ACCESS_TOKEN", "")
    if token:
        return token, os.environ.get("OANDA_ENV", "practice")
    found = _try_m0_config_loader() or _try_dotenv_file()
    if found:
        return found
    raise RuntimeError(
        "credenziali OANDA non trovate: definire OANDA_ACCESS_TOKEN (env), "
        "oppure fx_bias_radar/config.py (M0), oppure un file .env nel repo")
