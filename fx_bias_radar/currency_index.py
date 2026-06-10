"""Data layer: 28 pair momenta -> 8 currency z/slope/vel/state/score series.

1:1 port of FX_Bias_Radar_Production_v1_1.pine lines 141-348 (data part).
Pine line references are noted as P:<line>.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from . import pairs as P
from .pine_series import (Num, at, crossover_point, crossunder_point, ema,
                          highest_at, lowest_at, nz, sma_at, stdev_at)


@dataclass
class DataParams:
    # P:81-83 Core
    len_z: int = 100          # lenZ
    slope_len: int = 5        # slopeLen
    vel_len: int = 2          # velLen
    mom_ema_len: int = 20     # P:149 hardcoded ta.ema(r, 20)
    # P:100-112 ROT trigger machinery
    z_band_len: int = 50      # zBandLen
    k_outer: float = 2.0      # kOuter
    k_inner: float = 1.0      # kInner
    arm_window: int = 15      # armWindow
    hold_bars: int = 20       # holdBars
    slope_min: float = 0.1    # slopeMin
    score_win: int = 35       # scoreWin
    w_extreme: float = 1.0    # wExtreme
    w_slope: float = 1.0      # wSlope
    w_accel: float = 1.0      # wAccel


@dataclass
class CurrencyData:
    times: List[str]
    z: Dict[str, List[Num]] = field(default_factory=dict)
    sl: Dict[str, List[Num]] = field(default_factory=dict)
    v: Dict[str, List[Num]] = field(default_factory=dict)
    is_weak: Dict[str, List[bool]] = field(default_factory=dict)
    is_strong: Dict[str, List[bool]] = field(default_factory=dict)
    sc_weak: Dict[str, List[Num]] = field(default_factory=dict)
    sc_strong: Dict[str, List[Num]] = field(default_factory=dict)
    rank: Dict[str, List[int]] = field(default_factory=dict)


@dataclass
class PairFrame:
    """Per-bar engine inputs for one pair (Pine lines 332-348)."""
    time: str
    valid: bool
    z_base: Num
    z_quote: Num
    sl_base: Num
    sl_quote: Num
    v_base: Num
    v_quote: Num
    rank_base: int
    rank_quote: int
    strong_base: bool
    weak_base: bool
    strong_quote: bool
    weak_quote: bool
    sc_weak_base: Num
    sc_strong_base: Num
    sc_weak_quote: Num
    sc_strong_quote: Num


def momentum(closes: List[float], p: DataParams) -> List[Num]:
    """P:146-149 f_mom: r = log(c/c[1]) * 100; ta.ema(r, 20)."""
    r: List[Num] = [None]
    for i in range(1, len(closes)):
        r.append(math.log(closes[i] / closes[i - 1]) * 100.0)
    return ema(r, p.mom_ema_len)


def currency_indices(mom_by_pair: Dict[str, List[Num]]) -> Dict[str, List[Num]]:
    """P:258-265 symmetric indices = sum(sign * pair momentum) / 7."""
    n = len(next(iter(mom_by_pair.values())))
    out: Dict[str, List[Num]] = {}
    for ccy, terms in P.INDEX_TERMS.items():
        series: List[Num] = []
        for i in range(n):
            vals = [mom_by_pair[pair][i] for pair, _ in terms]
            if any(v is None for v in vals):
                series.append(None)
            else:
                series.append(sum(sign * mom_by_pair[pair][i] for pair, sign in terms) / 7.0)
        out[ccy] = series
    return out


def zscore(xs: List[Num], p: DataParams) -> List[Num]:
    """P:151-154 f_z: (x - sma) / stdev, 0.0 when stdev == 0."""
    out: List[Num] = []
    for i in range(len(xs)):
        m = sma_at(xs, i, p.len_z)
        s = stdev_at(xs, i, p.len_z)
        if m is None or s is None or xs[i] is None:
            out.append(None)
        elif s == 0:
            out.append(0.0)
        else:
            out.append((xs[i] - m) / s)
    return out


def state_series(z: List[Num], p: DataParams):
    """P:156-178 f_bands + f_state (v21 extreme machinery)."""
    n = len(z)
    up_o: List[Num] = [None] * n
    up_i: List[Num] = [None] * n
    lo_i: List[Num] = [None] * n
    lo_o: List[Num] = [None] * n
    for i in range(n):
        m = sma_at(z, i, p.z_band_len)
        s = stdev_at(z, i, p.z_band_len)
        if m is not None and s is not None:
            up_o[i] = m + p.k_outer * s
            up_i[i] = m + p.k_inner * s
            lo_i[i] = m - p.k_inner * s
            lo_o[i] = m - p.k_outer * s

    is_weak = [False] * n
    is_strong = [False] * n
    last_top = None   # last bar where z >= upper outer
    last_bot = None
    last_fire_w = None
    last_fire_s = None
    armed_top_prev = False
    armed_bot_prev = False
    for i in range(n):
        zi = z[i]
        if zi is not None and up_o[i] is not None and zi >= up_o[i]:
            last_top = i
        if zi is not None and lo_o[i] is not None and zi <= lo_o[i]:
            last_bot = i
        armed_top = last_top is not None and (i - last_top) <= p.arm_window
        armed_bot = last_bot is not None and (i - last_bot) <= p.arm_window
        trig_w = crossunder_point(zi, at(z, i, 1), up_i[i], at(up_i, i, 1))
        trig_s = crossover_point(zi, at(z, i, 1), lo_i[i], at(lo_i, i, 1))
        fire_w = armed_top_prev and trig_w   # P:171 armedTop[1] and trigW
        fire_s = armed_bot_prev and trig_s
        if fire_w:
            last_fire_w = i
        if fire_s:
            last_fire_s = i
        bs_w = (i - last_fire_w) if last_fire_w is not None else None
        bs_s = (i - last_fire_s) if last_fire_s is not None else None
        sl = (zi - at(z, i, p.slope_len)) if (zi is not None and at(z, i, p.slope_len) is not None) else None
        is_weak[i] = (bs_w is not None and bs_w <= p.hold_bars
                      and sl is not None and sl < -p.slope_min
                      and zi is not None and zi > 0)
        is_strong[i] = (bs_s is not None and bs_s <= p.hold_bars
                        and sl is not None and sl > p.slope_min
                        and zi is not None and zi < 0)
        armed_top_prev = armed_top
        armed_bot_prev = armed_bot
    return is_weak, is_strong


def score_series(z: List[Num], p: DataParams):
    """P:180-194 f_score -> (weak score, strong score) per bar."""
    n = len(z)
    sc_w: List[Num] = [None] * n
    sc_s: List[Num] = [None] * n
    for i in range(n):
        peak_high = highest_at(z, i, p.score_win)
        peak_low = lowest_at(z, i, p.score_win)
        if peak_high is None or peak_low is None:
            continue
        zi = z[i]
        sl = (zi - at(z, i, p.slope_len)) if (zi is not None and at(z, i, p.slope_len) is not None) else None
        vel = nz((zi - at(z, i, p.vel_len)) if (zi is not None and at(z, i, p.vel_len) is not None) else None)
        sl_rate = nz(sl) / p.slope_len
        vel_rate = vel / p.vel_len
        acc_down = max(0.0, sl_rate - vel_rate)
        acc_up = max(0.0, vel_rate - sl_rate)
        ext_w = max(0.0, peak_high)
        ext_s = max(0.0, -peak_low)
        slp_w = max(0.0, -nz(sl))
        slp_s = max(0.0, nz(sl))
        sc_w[i] = p.w_extreme * ext_w + p.w_slope * slp_w + p.w_accel * acc_down
        sc_s[i] = p.w_extreme * ext_s + p.w_slope * slp_s + p.w_accel * acc_up
    return sc_w, sc_s


def rank_series(z_by_ccy: Dict[str, List[Num]]):
    """P:209-214 f_rankz: count of currencies strictly weaker (na-compare = False)."""
    n = len(next(iter(z_by_ccy.values())))
    out = {ccy: [0] * n for ccy in P.CURRENCIES}
    for i in range(n):
        for ccy in P.CURRENCIES:
            mine = z_by_ccy[ccy][i]
            cnt = 0
            if mine is not None:
                for other in P.CURRENCIES:
                    ov = z_by_ccy[other][i]
                    if ov is not None and ov < mine:
                        cnt += 1
            out[ccy][i] = cnt
    return out


def build(times: List[str], closes_by_pair: Dict[str, List[float]],
          p: Optional[DataParams] = None) -> CurrencyData:
    p = p or DataParams()
    mom = {pair: momentum(closes_by_pair[pair], p) for pair in P.PAIRS}
    idx = currency_indices(mom)
    cd = CurrencyData(times=times)
    for ccy in P.CURRENCIES:
        z = zscore(idx[ccy], p)
        cd.z[ccy] = z
        cd.sl[ccy] = [
            (z[i] - at(z, i, p.slope_len)) if (z[i] is not None and at(z, i, p.slope_len) is not None) else None
            for i in range(len(z))]
        cd.v[ccy] = [
            (z[i] - at(z, i, p.vel_len)) if (z[i] is not None and at(z, i, p.vel_len) is not None) else None
            for i in range(len(z))]
        w, s = state_series(z, p)
        cd.is_weak[ccy] = w
        cd.is_strong[ccy] = s
        sc_w, sc_s = score_series(z, p)
        cd.sc_weak[ccy] = sc_w
        cd.sc_strong[ccy] = sc_s
    cd.rank = rank_series(cd.z)
    return cd


def pair_frames(cd: CurrencyData, pair: str) -> List[PairFrame]:
    """P:326-348: extract base/quote per-bar inputs for one pair."""
    base, quote = P.base_quote(pair)
    valid = base in P.CURRENCIES and quote in P.CURRENCIES and base != quote
    frames = []
    for i in range(len(cd.times)):
        frames.append(PairFrame(
            time=cd.times[i],
            valid=valid,
            z_base=cd.z[base][i] if valid else None,
            z_quote=cd.z[quote][i] if valid else None,
            sl_base=cd.sl[base][i] if valid else None,
            sl_quote=cd.sl[quote][i] if valid else None,
            v_base=cd.v[base][i] if valid else None,
            v_quote=cd.v[quote][i] if valid else None,
            rank_base=cd.rank[base][i] if valid else 0,
            rank_quote=cd.rank[quote][i] if valid else 0,
            strong_base=cd.is_strong[base][i] if valid else False,
            weak_base=cd.is_weak[base][i] if valid else False,
            strong_quote=cd.is_strong[quote][i] if valid else False,
            weak_quote=cd.is_weak[quote][i] if valid else False,
            sc_weak_base=cd.sc_weak[base][i] if valid else None,
            sc_strong_base=cd.sc_strong[base][i] if valid else None,
            sc_weak_quote=cd.sc_weak[quote][i] if valid else None,
            sc_strong_quote=cd.sc_strong[quote][i] if valid else None,
        ))
    return frames
