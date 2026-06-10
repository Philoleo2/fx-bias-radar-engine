"""Small OANDA REST v20 client used by M0 sanity checks."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
import json

from .config import OandaConfig


class OandaError(RuntimeError):
    """Raised when OANDA returns an error or the response cannot be parsed."""


@dataclass(frozen=True)
class Candle:
    instrument: str
    time: datetime
    complete: bool
    open: float
    high: float
    low: float
    close: float
    volume: int


class OandaClient:
    def __init__(self, config: OandaConfig, timeout_seconds: int = 20) -> None:
        if not config.access_token:
            raise OandaError("Missing OANDA_ACCESS_TOKEN. Create a local .env from .env.example.")
        self.config = config
        self.timeout_seconds = timeout_seconds

    def list_accounts(self) -> list[dict[str, Any]]:
        payload = self._request_json("GET", "/v3/accounts")
        return list(payload.get("accounts", []))

    def account_summary(self, account_id: str | None = None) -> dict[str, Any]:
        selected = account_id or self.config.account_id
        if not selected:
            accounts = self.list_accounts()
            if not accounts:
                raise OandaError("No OANDA accounts returned for this token.")
            selected = str(accounts[0]["id"])
        payload = self._request_json("GET", f"/v3/accounts/{selected}/summary")
        return dict(payload.get("account", {}))

    def candles(
        self,
        instrument: str,
        *,
        granularity: str = "H4",
        count: int = 10,
        price: str = "M",
        include_incomplete: bool = False,
    ) -> list[Candle]:
        params = {
            "granularity": granularity,
            "count": str(count),
            "price": price,
        }
        payload = self._request_json(
            "GET",
            f"/v3/instruments/{instrument}/candles",
            params=params,
        )
        candles = [
            self._parse_candle(instrument, item)
            for item in payload.get("candles", [])
        ]
        if include_incomplete:
            return candles
        return [candle for candle in candles if candle.complete]

    def _request_json(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        query = f"?{urlencode(params)}" if params else ""
        url = f"{self.config.base_url}{path}{query}"
        request = Request(
            url=url,
            method=method,
            headers={
                "Authorization": f"Bearer {self.config.access_token}",
                "Accept-Datetime-Format": "RFC3339",
                "Content-Type": "application/json",
            },
        )

        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                raw = response.read().decode("utf-8")
        except HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise OandaError(f"OANDA HTTP {exc.code}: {body}") from exc
        except URLError as exc:
            raise OandaError(f"OANDA connection error: {exc.reason}") from exc

        try:
            return dict(json.loads(raw))
        except json.JSONDecodeError as exc:
            raise OandaError(f"OANDA returned invalid JSON: {raw[:200]}") from exc

    @staticmethod
    def _parse_candle(instrument: str, payload: dict[str, Any]) -> Candle:
        midpoint = payload.get("mid")
        if not isinstance(midpoint, dict):
            raise OandaError("Expected midpoint candle data. Use price='M'.")

        return Candle(
            instrument=instrument,
            time=datetime.fromisoformat(str(payload["time"]).replace("Z", "+00:00")),
            complete=bool(payload.get("complete", False)),
            open=float(midpoint["o"]),
            high=float(midpoint["h"]),
            low=float(midpoint["l"]),
            close=float(midpoint["c"]),
            volume=int(payload.get("volume", 0)),
        )
