"""Configuration helpers for local and CI runs.

Secrets are read from environment variables or a local .env file. The .env file
is intentionally ignored by Git.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os


DEFAULT_PRACTICE_URL = "https://api-fxpractice.oanda.com"
DEFAULT_LIVE_URL = "https://api-fxtrade.oanda.com"


@dataclass(frozen=True)
class OandaConfig:
    env: str
    base_url: str
    access_token: str
    account_id: str | None = None

    @property
    def is_ready(self) -> bool:
        return bool(self.access_token)


def load_dotenv(path: str | Path = ".env") -> None:
    env_path = Path(path)
    if not env_path.exists():
        return

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def load_oanda_config(dotenv_path: str | Path = ".env") -> OandaConfig:
    load_dotenv(dotenv_path)

    env = os.environ.get("OANDA_ENV", "practice").strip().lower()
    base_url = os.environ.get("OANDA_BASE_URL", "").strip()
    if not base_url:
        base_url = DEFAULT_LIVE_URL if env == "live" else DEFAULT_PRACTICE_URL

    return OandaConfig(
        env=env,
        base_url=base_url.rstrip("/"),
        access_token=os.environ.get("OANDA_ACCESS_TOKEN", "").strip(),
        account_id=os.environ.get("OANDA_ACCOUNT_ID", "").strip() or None,
    )


def mask_secret(value: str, keep: int = 4) -> str:
    if not value:
        return "<missing>"
    if len(value) <= keep * 2:
        return "*" * len(value)
    return f"{value[:keep]}...{value[-keep:]}"
