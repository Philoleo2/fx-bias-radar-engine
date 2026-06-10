"""28-pair universe and symmetric currency-index formulas.

1:1 with FX_Bias_Radar_Production_v1_1.pine lines 226-265.
"""

from __future__ import annotations

# Pine order, lines 226-253.
PAIRS = [
    "EURUSD", "GBPUSD", "AUDUSD", "NZDUSD", "USDJPY", "USDCHF", "USDCAD",
    "EURGBP", "EURJPY", "EURCHF", "EURAUD", "EURCAD", "EURNZD",
    "GBPJPY", "GBPCHF", "GBPAUD", "GBPCAD", "GBPNZD",
    "CHFJPY", "AUDJPY", "CADJPY", "NZDJPY",
    "AUDCHF", "CADCHF", "NZDCHF",
    "AUDCAD", "AUDNZD", "NZDCAD",
]

# M0 compatibility: the OANDA sanity check uses underscore instruments.
PAIRS_28 = tuple(pair[:3] + "_" + pair[3:] for pair in PAIRS)

# Pine f_idx order, lines 196-206. Index in this list == Pine array index.
CURRENCIES = ["EUR", "GBP", "AUD", "NZD", "USD", "CAD", "CHF", "JPY"]

# Pine lines 258-265: index = sum(sign * pair_momentum) / 7.
INDEX_TERMS = {
    "USD": [("EURUSD", -1), ("GBPUSD", -1), ("AUDUSD", -1), ("NZDUSD", -1),
            ("USDJPY", +1), ("USDCHF", +1), ("USDCAD", +1)],
    "EUR": [("EURUSD", +1), ("EURGBP", +1), ("EURJPY", +1), ("EURCHF", +1),
            ("EURAUD", +1), ("EURCAD", +1), ("EURNZD", +1)],
    "GBP": [("GBPUSD", +1), ("EURGBP", -1), ("GBPJPY", +1), ("GBPCHF", +1),
            ("GBPAUD", +1), ("GBPCAD", +1), ("GBPNZD", +1)],
    "JPY": [("USDJPY", -1), ("EURJPY", -1), ("GBPJPY", -1), ("CHFJPY", -1),
            ("AUDJPY", -1), ("CADJPY", -1), ("NZDJPY", -1)],
    "CHF": [("USDCHF", -1), ("EURCHF", -1), ("GBPCHF", -1), ("CHFJPY", +1),
            ("AUDCHF", -1), ("CADCHF", -1), ("NZDCHF", -1)],
    "AUD": [("AUDUSD", +1), ("EURAUD", -1), ("GBPAUD", -1), ("AUDJPY", +1),
            ("AUDCHF", +1), ("AUDCAD", +1), ("AUDNZD", +1)],
    "CAD": [("USDCAD", -1), ("EURCAD", -1), ("GBPCAD", -1), ("CADJPY", +1),
            ("CADCHF", +1), ("AUDCAD", -1), ("NZDCAD", -1)],
    "NZD": [("NZDUSD", +1), ("EURNZD", -1), ("GBPNZD", -1), ("NZDJPY", +1),
            ("NZDCHF", +1), ("AUDNZD", -1), ("NZDCAD", +1)],
}


def oanda_instrument(pair: str) -> str:
    """'EURUSD' -> 'EUR_USD'."""
    return normalize_instrument(pair)


def pair_from_instrument(instrument: str) -> str:
    return instrument.replace("_", "")


def normalize_instrument(symbol: str) -> str:
    cleaned = symbol.strip().upper().replace("/", "_").replace("-", "_")
    if "_" in cleaned:
        return cleaned
    if len(cleaned) == 6:
        return f"{cleaned[:3]}_{cleaned[3:]}"
    return cleaned


def base_quote(pair: str):
    return pair[:3], pair[3:]


def currency_index_of(ccy: str) -> int:
    return CURRENCIES.index(ccy)
