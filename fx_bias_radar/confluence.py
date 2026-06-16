"""M3 Fase 2 - Classificatore di confluenza (H4 direzione + H1 timing).

Display/selezione, NON tocca il motore H4. Combina:
- DIREZIONE H4: segno del gap di forza valutaria (z_base - z_quote) con soglia
  h4_dir_min (la direzione e' precoce: e' uno stato, non l'evento RESUME).
- TIMING H1: pendenza/persistenza dello spread H1 nella direzione H4.

Mostra SOLO due stati (scelta di Leonardo):
- RIPRESA: lo spread H1 in direzione D ha appena ripreso a salire dopo una pausa
  (upturn fresco) = continuazione allineata, il caso d'oro.
- RIENTRO: lo spread H1 va CONTRO D per >= n_rientro barre H1 consecutive
  = mean-reversion / pullback.
'In attesa' e 'rumore' non vengono prodotti. Strato a BASSA confidenza,
subordinato a H4; la verita' resta H4 + le linee manuali.
"""

from __future__ import annotations

from typing import Dict, List, Optional

from . import pairs as P

RIPRESA = "RIPRESA"
RIENTRO = "RIENTRO"


def _tail_runs(series: List[Optional[float]]):
    """Lunghezza della corsa monotona finale (up_run, down_run)."""
    up = 0
    i = len(series) - 1
    while i >= 1 and series[i] is not None and series[i - 1] is not None and series[i] > series[i - 1]:
        up += 1
        i -= 1
    down = 0
    i = len(series) - 1
    while i >= 1 and series[i] is not None and series[i - 1] is not None and series[i] < series[i - 1]:
        down += 1
        i -= 1
    return up, down


def _sort(rows):
    return sorted(rows, key=lambda r: -abs(r["gap_h4"]))


def _dedup(rows, cap):
    out = []
    cnt: Dict[str, int] = {}
    for r in rows:
        b, q = r["base"], r["quote"]
        if cnt.get(b, 0) >= cap or cnt.get(q, 0) >= cap:
            continue
        cnt[b] = cnt.get(b, 0) + 1
        cnt[q] = cnt.get(q, 0) + 1
        out.append(r)
    return out


def classify_confluence(h4_z_by_ccy: Dict[str, Optional[float]],
                        h1_series_by_ccy: Dict[str, List[Optional[float]]],
                        *, h4_dir_min: float = 1.0, n_rientro: int = 3,
                        cluster_cap: int = 2) -> dict:
    """Classifica le 28 coppie in RIPRESA / RIENTRO (le altre non sono prodotte)."""
    riprese = []
    rientri = []
    for pair in P.PAIRS:
        base, quote = P.base_quote(pair)
        zb = h4_z_by_ccy.get(base)
        zq = h4_z_by_ccy.get(quote)
        if zb is None or zq is None:
            continue
        gap = zb - zq
        if gap >= h4_dir_min:
            D = "LONG"
        elif -gap >= h4_dir_min:
            D = "SHORT"
        else:
            continue  # NEUTRO -> non mostrato

        sb = h1_series_by_ccy.get(base)
        sq = h1_series_by_ccy.get(quote)
        if not sb or not sq or len(sb) != len(sq) or len(sb) < 3:
            continue
        spread_long = [(sb[i] - sq[i]) if (sb[i] is not None and sq[i] is not None) else None
                       for i in range(len(sb))]
        spD = spread_long if D == "LONG" else [(-v if v is not None else None) for v in spread_long]
        if any(v is None for v in spD[-3:]):
            continue

        up, down = _tail_runs(spD)
        stato = None
        if down >= n_rientro:
            stato = RIENTRO
        elif spD[-1] > spD[-2] and spD[-2] <= spD[-3]:
            stato = RIPRESA
        if stato is None:
            continue

        row = {
            "pair": pair, "dir": D, "stato": stato,
            "gap_h4": round(gap, 4),
            "h1_spread": round(spD[-1], 4),
            "h1_up_run": up, "h1_down_run": down,
            "base": base, "quote": quote,
        }
        (riprese if stato == RIPRESA else rientri).append(row)

    return {
        "n_rientro": n_rientro,
        "h4_dir_min": h4_dir_min,
        "riprese": _dedup(_sort(riprese), cluster_cap),
        "rientri": _dedup(_sort(rientri), cluster_cap),
    }


def from_strength_payloads(h4_payload: dict, h1_payload: dict, **kwargs) -> dict:
    """Adapter: estrae z H4 (ultimo) e serie H1 dai payload di compute_strength."""
    h4_z = {c["ccy"]: c["z"] for c in h4_payload.get("currencies", [])}
    h1_series = {c["ccy"]: c["series"] for c in h1_payload.get("currencies", [])}
    return classify_confluence(h4_z, h1_series, **kwargs)
