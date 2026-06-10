"""Canonical FX universe for the Garlando radar."""

from __future__ import annotations


CURRENCIES: tuple[str, ...] = ("AUD", "CAD", "CHF", "EUR", "GBP", "JPY", "NZD", "USD")

PAIRS_28: tuple[str, ...] = (
    "AUD_CAD",
    "AUD_CHF",
    "AUD_JPY",
    "AUD_NZD",
    "AUD_USD",
    "CAD_CHF",
    "CAD_JPY",
    "CHF_JPY",
    "EUR_AUD",
    "EUR_CAD",
    "EUR_CHF",
    "EUR_GBP",
    "EUR_JPY",
    "EUR_NZD",
    "EUR_USD",
    "GBP_AUD",
    "GBP_CAD",
    "GBP_CHF",
    "GBP_JPY",
    "GBP_NZD",
    "GBP_USD",
    "NZD_CAD",
    "NZD_CHF",
    "NZD_JPY",
    "NZD_USD",
    "USD_CAD",
    "USD_CHF",
    "USD_JPY",
)


def normalize_instrument(symbol: str) -> str:
    cleaned = symbol.strip().upper().replace("/", "_").replace("-", "_")
    if "_" in cleaned:
        return cleaned
    if len(cleaned) == 6:
        return f"{cleaned[:3]}_{cleaned[3:]}"
    return cleaned
