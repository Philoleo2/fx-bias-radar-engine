"""Synthetic PairFrame builder for engine mechanism tests.

Builds controlled spread paths: ``z_base - z_quote`` follows the given
``s`` values; ``fav`` makes slope/vel/rank gates favorable to one side only,
so RESUME can fire only in that direction. ROT flags are injected directly.
"""

from __future__ import annotations

from typing import List, Optional

from fx_bias_radar.currency_index import PairFrame


def make_frames(specs: List[dict]) -> List[PairFrame]:
    frames = []
    for sp in specs:
        s = sp["s"]
        fav = sp.get("fav")
        rot = sp.get("rot")
        zq = sp.get("zq", 0.0)
        zb = s + zq
        if fav == "LONG":
            slb, slq, vb, vq, rb, rq = 0.4, -0.4, 0.1, -0.1, 6, 2
        elif fav == "SHORT":
            slb, slq, vb, vq, rb, rq = -0.4, 0.4, -0.1, 0.1, 2, 6
        else:
            slb = slq = vb = vq = 0.0
            rb = rq = 4
        strong_b = weak_b = strong_q = weak_q = False
        scwb = scsb = scwq = scsq = 0.0
        if rot == "SHORT":
            strong_q, weak_b, scsq, scwb = True, True, 2.0, 2.0
        elif rot == "LONG":
            strong_b, weak_q, scsb, scwq = True, True, 2.0, 2.0
        frames.append(PairFrame(
            time=f"bar{len(frames):04d}", valid=True,
            z_base=zb, z_quote=zq,
            sl_base=slb, sl_quote=slq, v_base=vb, v_quote=vq,
            rank_base=rb, rank_quote=rq,
            strong_base=strong_b, weak_base=weak_b,
            strong_quote=strong_q, weak_quote=weak_q,
            sc_weak_base=scwb, sc_strong_base=scsb,
            sc_weak_quote=scwq, sc_strong_quote=scsq,
        ))
    return frames


def flat(n: int, s: float = 0.2, fav: Optional[str] = None) -> List[dict]:
    return [{"s": s, "fav": fav} for _ in range(n)]


def ramp(values: List[float], fav: Optional[str] = "LONG") -> List[dict]:
    return [{"s": v, "fav": fav} for v in values]
