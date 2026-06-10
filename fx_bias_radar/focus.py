"""Focus list from REAL per-pair engine state (Work Item B, brief section 11).

Unlike Pine v1.3 (lightweight live ranking forced by Pine limits), here the
focus list derives from the full v1.1 engine state of every pair, so there is
no second source of truth. Criteria per brief: actionable state first,
freshness over raw spread, cluster cap (max rows per currency), no pinning
of any pair. These ranking heuristics are DISPLAY-layer (engine untouched)
and can be tuned with Leonardo during live use.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List

from .engine import BarResult


@dataclass
class FocusRow:
    rank: int
    pair: str
    bias: str
    tipo: str
    stato: str
    score: int
    forte: str
    debole: str
    spread: float
    note: str


_STATE_PRIORITY = {"NUOVO": 3, "ATTIVO": 2, "ESTESO": 1}


def _note(r: BarResult, new_bars: int = 2) -> str:
    if r.display_age is not None and r.display_age <= new_bars:
        return "fresh"
    if r.panel_spread is not None and r.panel_spread >= 2.0:
        return "strong"
    return "watch"


def build_focus(last_by_pair: Dict[str, BarResult], max_rows: int = 5,
                cluster_cap: int = 2) -> List[FocusRow]:
    candidates = [(pair, r) for pair, r in last_by_pair.items() if r.display_active]
    candidates.sort(key=lambda t: (
        -_STATE_PRIORITY.get(t[1].display_state, 0),
        -(t[1].display_score or 0.0),
        -(t[1].panel_spread or 0.0),
        t[0],
    ))
    rows: List[FocusRow] = []
    ccy_count: Dict[str, int] = {}
    for pair, r in candidates:
        if len(rows) >= max_rows:
            break
        base, quote = pair[:3], pair[3:]
        if ccy_count.get(base, 0) >= cluster_cap or ccy_count.get(quote, 0) >= cluster_cap:
            continue
        ccy_count[base] = ccy_count.get(base, 0) + 1
        ccy_count[quote] = ccy_count.get(quote, 0) + 1
        rows.append(FocusRow(
            rank=len(rows) + 1, pair=pair, bias=r.display_dir,
            tipo=r.display_type, stato=r.display_state,
            score=int(round(r.display_score or 0.0)),
            forte=r.panel_forte, debole=r.panel_debole,
            spread=round(r.panel_spread or 0.0, 2), note=_note(r),
        ))
    return rows
