"""FX Bias Radar engine: 1:1 port of FX_Bias_Radar_Production_v1_1.pine.

Covers Pine lines 350-670 (directional frames, RESUME/ROT triggers,
arbitration, anti-flip / regime lock / post-death TTL / protective peak /
strong-opposite bypass, accepted vs attention events, series memory,
display state, display-only label dedup) plus the panel fields (699-713).

Pine line references are noted as P:<line>. All thresholds default to the
validated v1.1 input values and MUST NOT be changed (FR025/FR029).

Intentionally NOT ported (dead code in v1.1, left from diagnostics):
P:489 acceptedAge, P:493 dominantPeakActive, P:496 dominantExtended,
P:519 postDeathDeadDirNum, P:520 acceptedSpreadPeak - none of them feeds
events, display, or panel in v1.1.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from .currency_index import PairFrame
from .pine_series import Num, nz


@dataclass
class EngineParams:
    # P:85-98 RESUME trigger (proposal v1 + FR002)
    spread_min: float = 1.00          # spreadMin
    look_high: int = 12               # lookHigh
    look_low: int = 6                 # lookLow
    pullback_min: float = 0.30        # pullbackMin
    comp_max: float = 0.15            # compMax
    reexpand_min: float = 0.25        # reexpandMin
    slope5_min_both: float = 0.10     # slope5MinBoth
    vel2_min_both: float = 0.05       # vel2MinBoth
    resume_score_min: float = 55.0    # resumeScoreMin
    extension_max: float = 1.20       # extensionMax
    new_bars: int = 2                 # newBars
    remove_floor: float = 0.70        # removeFloor
    z_side_soft: float = 0.50         # zSideSoft
    # P:111-112 ROT
    min_abs_z: float = 0.7            # minAbsZ
    min_side_score: float = 1.0       # minSideScore
    # P:114-121 Display
    hist_bars: int = 400              # histBars
    min_marker_gap: int = 4           # minMarkerGap
    marker_label_score_min: float = 65.0  # markerLabelScoreMin
    bias_memory_bars: int = 36        # biasMemoryBars
    # P:123-127 Production label dedup (display only)
    dedup_same_direction: bool = True
    dedup_bars: int = 20
    dedup_spread_mult: float = 1.15
    dedup_score_step: float = 10.0
    # P:129-136 Anti-flip filter
    enable_anti_flip: bool = True
    reset_bars: int = 4                       # resetBars
    neutral_floor: float = 0.35               # neutralFloor
    post_extended_death_ttl_bars: int = 36    # postExtendedDeathTtlBars
    dead_takeover_mult: float = 1.10          # deadTakeoverMult
    protective_peak_cap_bars: int = 120       # protectivePeakCapBars
    strong_opposite_floor: float = 3.0        # strongOppositeFloor


@dataclass
class BarResult:
    time: str
    bar_index: int
    # spreads
    spread_long: Num = None
    spread_short: Num = None
    # raw event (after LONG/SHORT arbitration, P:422-436)
    raw_dir: str = ""
    raw_type: str = ""
    raw_score: Num = None
    # event stream (P:497-521)
    candidate_event: bool = False
    accepted_event: bool = False
    attention_event: bool = False
    anti_flip_block: bool = False
    post_death_hidden: bool = False
    opposite_resume_extended: bool = False
    strong_opposite: bool = False
    strong_live_opposite: bool = False
    strong_post_death_opposite: bool = False
    takeover_ok: bool = False
    post_death_takeover_ok: bool = False
    effective_dead_peak: float = 0.0
    post_death_takeover_level: float = 0.0
    hidden_reason: str = ""
    # regime debug
    regime_dir: str = ""
    regime_peak_spread: Num = None
    regime_weak_bars: int = 0
    regime_touched_extended: bool = False
    regime_dead: bool = True
    # markers / labels (P:590-670)
    marker_fired: bool = False
    marker_state: str = ""
    label_shown: bool = False
    # display memory = panel truth (P:604-616)
    display_active: bool = False
    display_dir: str = ""
    display_type: str = ""
    display_score: Num = None
    display_state: str = ""
    display_age: Optional[int] = None
    # panel fields (P:699-713)
    panel_bias: str = "-"
    panel_tipo: str = "-"
    panel_stato: str = "NESSUNO"
    panel_score: int = 0
    panel_forte: str = ""
    panel_debole: str = ""
    panel_spread: Num = None
    panel_note: str = "-"


def f_clamp(x: float, lo: float, hi: float) -> float:  # P:141
    return min(hi, max(lo, x))


def resume_score(spread: float, rank_gap: float, lead_slope5: float,
                 lag_slope5: float, lead_vel2: float, lag_vel2: float) -> float:
    """P:216-221 f_resume_score (1.00/1.50 hardcoded in Pine)."""
    spread_score = f_clamp((spread - 1.00) / 1.50, 0, 1)
    rank_score = f_clamp(rank_gap / 4.0, 0, 1)
    slope_score = f_clamp((lead_slope5 + lag_slope5) / 0.80, 0, 1)
    vel_score = f_clamp((lead_vel2 + lag_vel2) / 0.50, 0, 1)
    return 100 * (0.30 * spread_score + 0.20 * rank_score
                  + 0.30 * slope_score + 0.20 * vel_score)


def _win_extreme(hist: List[Num], i: int, length: int, fn) -> Num:
    """Pine ta.highest/lowest(series[1], length): window i-1 .. i-length."""
    if i < length:
        return None
    w = hist[i - length: i]
    if any(v is None for v in w):
        return None
    return fn(w)


class _Side:
    """Directional frame for one side (LONG or SHORT), P:353-405."""

    def __init__(self):
        self.spread: Num = None
        self.rank_gap: Num = None
        self.lead_slope: Num = None
        self.lag_slope: Num = None
        self.lead_vel: Num = None
        self.lag_vel: Num = None
        self.pullback: Num = None
        self.extension: Num = None
        self.trend = False
        self.pullback_ok = False
        self.compression_ok = False
        self.pause = False
        self.expansion = False
        self.sides = False
        self.resume_score: float = 0.0
        self.score_ok = False
        self.resume = False
        self.rot_score: float = 0.0
        self.rot = False


def run_pair(pair: str, frames: List[PairFrame],
             params: Optional[EngineParams] = None) -> List[BarResult]:
    p = params or EngineParams()
    base = pair[:3]
    quote = pair[3:]
    n = len(frames)
    last_bar_index = n - 1

    hist_l: List[Num] = []
    hist_s: List[Num] = []

    # P:438-452 persistent vars
    accepted_dir = ""
    accepted_bar: Optional[int] = None
    accepted_score: Num = None
    regime_dir = ""
    regime_peak_spread: Num = None
    regime_weak_bars = 0
    regime_touched_extended = False
    dead_long_peak: Num = None
    dead_long_bar: Optional[int] = None
    dead_short_peak: Num = None
    dead_short_bar: Optional[int] = None
    prot_long_peak: Num = None
    prot_long_bar: Optional[int] = None
    prot_short_peak: Num = None
    prot_short_bar: Optional[int] = None
    # P:590 display memory
    last_marker_bar: Optional[int] = None
    # P:651-654 dedup memory (display only)
    last_shown_dir = ""
    last_shown_spread: Num = None
    last_shown_score: Num = None
    last_shown_bar: Optional[int] = None
    # P:557-571 series memory trackers (bar + score of last attention events)
    ev = {("LONG", "RESUME"): (None, None), ("LONG", "ROT"): (None, None),
          ("SHORT", "RESUME"): (None, None), ("SHORT", "ROT"): (None, None)}

    results: List[BarResult] = []

    for i, f in enumerate(frames):
        valid = (f.valid and f.z_base is not None and f.z_quote is not None)
        s_l: Num = (f.z_base - f.z_quote) if valid else None   # P:353
        s_s: Num = (f.z_quote - f.z_base) if valid else None   # P:354
        hist_l.append(s_l)
        hist_s.append(s_s)

        def side_frame(is_long: bool) -> _Side:
            sd = _Side()
            hist = hist_l if is_long else hist_s
            sd.spread = s_l if is_long else s_s
            if valid:
                sd.rank_gap = (f.rank_base - f.rank_quote) if is_long else (f.rank_quote - f.rank_base)  # P:356-357
                sd.lead_slope = f.sl_base if is_long else f.sl_quote          # P:359-367
                sd.lag_slope = (-f.sl_quote if f.sl_quote is not None else None) if is_long else (-f.sl_base if f.sl_base is not None else None)
                sd.lead_vel = f.v_base if is_long else f.v_quote
                sd.lag_vel = (-f.v_quote if f.v_quote is not None else None) if is_long else (-f.v_base if f.v_base is not None else None)
            # P:369-377 recent windows on spread[1]
            recent_high = _win_extreme(hist, i, p.look_high, max)
            recent_low = _win_extreme(hist, i, p.look_low, min)
            sd.pullback = (recent_high - recent_low) if (recent_high is not None and recent_low is not None) else None
            sd.extension = (sd.spread - recent_low) if (sd.spread is not None and recent_low is not None) else None
            z_lead = f.z_base if is_long else f.z_quote
            z_lag = f.z_quote if is_long else f.z_base
            # P:383-384 trend gate
            sd.trend = (sd.spread is not None and sd.spread >= p.spread_min
                        and (nz(sd.rank_gap) >= 2
                             or abs(nz(z_lead)) >= p.z_side_soft
                             or abs(nz(z_lag)) >= p.z_side_soft))
            # P:386-393 pause = pullback OR compression
            sd.pullback_ok = sd.pullback is not None and sd.pullback >= p.pullback_min
            s1, s2, s3, s4 = (hist[i - 1] if i >= 1 else None,
                              hist[i - 2] if i >= 2 else None,
                              hist[i - 3] if i >= 3 else None,
                              hist[i - 4] if i >= 4 else None)
            comp_a = s2 is not None and s4 is not None and abs(s2 - s4) <= p.comp_max
            comp_b = s1 is not None and s3 is not None and abs(s1 - s3) <= p.comp_max
            sd.compression_ok = (s4 is not None) and (comp_a or comp_b)
            sd.pause = sd.pullback_ok or sd.compression_ok
            # P:395-396 re-expansion
            exp_a = (sd.spread is not None and s2 is not None
                     and sd.spread - s2 >= p.reexpand_min)
            exp_b = sd.extension is not None and sd.extension >= p.reexpand_min
            exp_c = sd.spread is not None and s1 is not None and sd.spread > s1
            sd.expansion = (exp_a or exp_b) and exp_c
            # P:398-399 both sides participate
            sd.sides = (nz(sd.lead_slope) >= p.slope5_min_both
                        and nz(sd.lag_slope) >= p.slope5_min_both
                        and nz(sd.lead_vel) >= p.vel2_min_both
                        and nz(sd.lag_vel) >= p.vel2_min_both)
            # P:401-408 dedicated RESUME score + trigger
            sd.resume_score = resume_score(nz(sd.spread), nz(sd.rank_gap),
                                           nz(sd.lead_slope), nz(sd.lag_slope),
                                           nz(sd.lead_vel), nz(sd.lag_vel))
            sd.score_ok = sd.resume_score >= p.resume_score_min
            sd.resume = (valid and sd.trend and sd.pause and sd.expansion
                         and sd.sides and sd.score_ok)
            # P:413-417 ROT (v21 extreme machinery)
            if is_long:
                sd.rot_score = min(nz(f.sc_strong_base), nz(f.sc_weak_quote))
                rot_flags = f.strong_base and f.weak_quote
            else:
                sd.rot_score = min(nz(f.sc_strong_quote), nz(f.sc_weak_base))
                rot_flags = f.strong_quote and f.weak_base
            sd.rot = (valid and rot_flags
                      and abs(nz(f.z_base)) >= p.min_abs_z
                      and abs(nz(f.z_quote)) >= p.min_abs_z
                      and sd.rot_score >= p.min_side_score)
            return sd

        L = side_frame(True)
        S = side_frame(False)

        # P:422-436 raw arbitration: ROT > RESUME, then score
        raw_long_type = "ROT" if L.rot else ("RESUME" if L.resume else "")
        raw_short_type = "ROT" if S.rot else ("RESUME" if S.resume else "")
        raw_long_score = L.rot_score if L.rot else L.resume_score
        raw_short_score = S.rot_score if S.rot else S.resume_score
        raw_long_event = raw_long_type != ""
        raw_short_event = raw_short_type != ""
        prio = {"ROT": 2, "RESUME": 1, "": 0}
        raw_use_long = raw_long_event and (
            not raw_short_event
            or prio[raw_long_type] > prio[raw_short_type]
            or (prio[raw_long_type] == prio[raw_short_type]
                and raw_long_score >= raw_short_score))
        raw_use_short = raw_short_event and not raw_use_long
        raw_dir = "LONG" if raw_use_long else ("SHORT" if raw_use_short else "")
        raw_type = raw_long_type if raw_use_long else (raw_short_type if raw_use_short else "")
        raw_score: Num = raw_long_score if raw_use_long else (raw_short_score if raw_use_short else None)
        raw_extension: Num = L.extension if raw_use_long else (S.extension if raw_use_short else None)

        # P:454-457 live regime measures
        regime_spread_live = s_l if regime_dir == "LONG" else (s_s if regime_dir == "SHORT" else None)
        regime_extension_live = L.extension if regime_dir == "LONG" else (S.extension if regime_dir == "SHORT" else None)
        current_regime_extended = regime_dir != "" and nz(regime_extension_live) > p.extension_max

        # P:459-463 regime alive update (confirmedBar always true: closed bars)
        if regime_dir != "":
            regime_touched_extended = regime_touched_extended or current_regime_extended
            regime_death_floor = p.neutral_floor if regime_touched_extended else p.remove_floor
            regime_peak_spread = (regime_spread_live if regime_peak_spread is None
                                  else max(regime_peak_spread, nz(regime_spread_live)))
            regime_weak_bars = regime_weak_bars + 1 if nz(regime_spread_live) < regime_death_floor else 0

        # P:465-466
        regime_dead = regime_dir == "" or regime_weak_bars >= p.reset_bars
        regime_died_this_bar = regime_dir != "" and regime_dead

        # P:468-486 save dead + protective peaks on ESTESO death
        if regime_died_this_bar and regime_touched_extended:
            dl_age = (i - dead_long_bar) if dead_long_bar is not None else 100000
            ds_age = (i - dead_short_bar) if dead_short_bar is not None else 100000
            pl_age = (i - prot_long_bar) if prot_long_bar is not None else 100000
            ps_age = (i - prot_short_bar) if prot_short_bar is not None else 100000
            if regime_dir == "LONG":
                keep_hw = p.post_extended_death_ttl_bars > 0 and dl_age <= p.post_extended_death_ttl_bars
                dead_long_peak = max(nz(dead_long_peak), nz(regime_peak_spread)) if keep_hw else regime_peak_spread
                dead_long_bar = i
                keep_prot = p.protective_peak_cap_bars == 0 or pl_age <= p.protective_peak_cap_bars
                prot_long_peak = max(nz(prot_long_peak), nz(regime_peak_spread)) if keep_prot else regime_peak_spread
                prot_long_bar = i
            elif regime_dir == "SHORT":
                keep_hw = p.post_extended_death_ttl_bars > 0 and ds_age <= p.post_extended_death_ttl_bars
                dead_short_peak = max(nz(dead_short_peak), nz(regime_peak_spread)) if keep_hw else regime_peak_spread
                dead_short_bar = i
                keep_prot = p.protective_peak_cap_bars == 0 or ps_age <= p.protective_peak_cap_bars
                prot_short_peak = max(nz(prot_short_peak), nz(regime_peak_spread)) if keep_prot else regime_peak_spread
                prot_short_bar = i

        # P:488-521 suppression / event stream
        opposite_spread_live = s_l if raw_dir == "LONG" else (s_s if raw_dir == "SHORT" else None)
        raw_opposite = raw_dir != "" and regime_dir != "" and raw_dir != regime_dir
        raw_is_rot = raw_type == "ROT"
        raw_is_resume = raw_type == "RESUME"
        takeover_ok = regime_dir == "" or nz(opposite_spread_live) >= nz(regime_peak_spread)
        strong_live_opposite = (p.enable_anti_flip and raw_opposite and raw_is_resume
                                and nz(opposite_spread_live) >= p.strong_opposite_floor)
        anti_flip_block = (p.enable_anti_flip and raw_opposite and raw_is_resume
                           and not regime_dead and not takeover_ok
                           and not strong_live_opposite)
        candidate_event = raw_dir != "" and not anti_flip_block

        dead_ref_dir = "SHORT" if raw_dir == "LONG" else ("LONG" if raw_dir == "SHORT" else "")
        dead_ref_bar = dead_short_bar if raw_dir == "LONG" else (dead_long_bar if raw_dir == "SHORT" else None)
        dead_ref_peak = dead_short_peak if raw_dir == "LONG" else (dead_long_peak if raw_dir == "SHORT" else None)
        prot_ref_bar = prot_short_bar if raw_dir == "LONG" else (prot_long_bar if raw_dir == "SHORT" else None)
        prot_ref_peak = prot_short_peak if raw_dir == "LONG" else (prot_long_peak if raw_dir == "SHORT" else None)
        prot_ref_age = (i - prot_ref_bar) if prot_ref_bar is not None else 100000
        prot_ref_active = prot_ref_peak is not None and (
            p.protective_peak_cap_bars == 0 or prot_ref_age <= p.protective_peak_cap_bars)
        effective_dead_peak = max(nz(dead_ref_peak), nz(prot_ref_peak) if prot_ref_active else 0.0)
        effective_dead_peak_valid = dead_ref_peak is not None or prot_ref_active
        post_death_age = (i - dead_ref_bar) if dead_ref_bar is not None else 100000
        post_extended_death_opposite = (raw_is_resume and dead_ref_dir != ""
                                        and dead_ref_bar is not None
                                        and post_death_age <= p.post_extended_death_ttl_bars)
        strong_post_death_opposite = (p.enable_anti_flip and post_extended_death_opposite
                                      and nz(opposite_spread_live) >= p.strong_opposite_floor)
        strong_opposite = strong_live_opposite or strong_post_death_opposite
        post_death_takeover_level = effective_dead_peak * p.dead_takeover_mult
        post_death_takeover_ok = (effective_dead_peak_valid
                                  and nz(opposite_spread_live) >= post_death_takeover_level)
        post_death_cooldown = (p.enable_anti_flip and p.post_extended_death_ttl_bars > 0
                               and candidate_event and post_extended_death_opposite)
        post_death_hidden = (post_death_cooldown and not post_death_takeover_ok
                             and not strong_opposite)
        accepted_event = candidate_event and not post_death_hidden
        opposite_resume_extended = (accepted_event and raw_opposite and raw_is_resume
                                    and nz(raw_extension) > p.extension_max
                                    and not strong_opposite)
        attention_event = accepted_event and not opposite_resume_extended

        # P:523-545 regime promotion / clear
        if accepted_event:
            if raw_is_rot or post_death_takeover_ok:
                if raw_dir == "LONG":
                    prot_short_peak = None
                    prot_short_bar = None
                elif raw_dir == "SHORT":
                    prot_long_peak = None
                    prot_long_bar = None
            accepted_dir = raw_dir
            accepted_bar = i
            accepted_score = raw_score
            accepted_event_spread = s_l if raw_dir == "LONG" else (s_s if raw_dir == "SHORT" else None)
            accepted_event_extended = nz(raw_extension) > p.extension_max
            same_regime = raw_dir == regime_dir and regime_peak_spread is not None
            regime_peak_spread = (max(regime_peak_spread, nz(accepted_event_spread))
                                  if same_regime else accepted_event_spread)
            regime_touched_extended = ((regime_touched_extended or accepted_event_extended)
                                       if same_regime else accepted_event_extended)
            regime_dir = raw_dir
            regime_weak_bars = 0
        elif regime_dead and regime_dir != "":
            regime_dir = ""
            regime_peak_spread = None
            regime_weak_bars = 0
            regime_touched_extended = False

        # P:549-552 typed attention events
        resume_long_f = attention_event and raw_use_long and raw_type == "RESUME"
        rot_long_f = attention_event and raw_use_long and raw_type == "ROT"
        resume_short_f = attention_event and raw_use_short and raw_type == "RESUME"
        rot_short_f = attention_event and raw_use_short and raw_type == "ROT"

        # P:557-574 series memory: barssince/valuewhen include the current bar
        if resume_long_f:
            ev[("LONG", "RESUME")] = (i, L.resume_score)
        if rot_long_f:
            ev[("LONG", "ROT")] = (i, L.rot_score)
        if resume_short_f:
            ev[("SHORT", "RESUME")] = (i, S.resume_score)
        if rot_short_f:
            ev[("SHORT", "ROT")] = (i, S.rot_score)

        def age_of(key):
            b, _ = ev[key]
            return (i - b) if b is not None else 100000  # nz(barssince, 100000)

        age_res_l = age_of(("LONG", "RESUME"))
        age_rot_l = age_of(("LONG", "ROT"))
        age_res_s = age_of(("SHORT", "RESUME"))
        age_rot_s = age_of(("SHORT", "ROT"))
        series_long_age = min(age_res_l, age_rot_l)
        series_short_age = min(age_res_s, age_rot_s)
        series_long_type = "RESUME" if age_res_l <= age_rot_l else "ROT"
        series_short_type = "RESUME" if age_res_s <= age_rot_s else "ROT"
        series_long_score = ev[("LONG", "RESUME")][1] if age_res_l <= age_rot_l else ev[("LONG", "ROT")][1]
        series_short_score = ev[("SHORT", "RESUME")][1] if age_res_s <= age_rot_s else ev[("SHORT", "ROT")][1]
        # P:576-585
        series_long_ok = series_long_age <= p.bias_memory_bars and s_l is not None and s_l >= p.remove_floor
        series_short_ok = series_short_age <= p.bias_memory_bars and s_s is not None and s_s >= p.remove_floor
        series_use_long = series_long_ok and (not series_short_ok or series_long_age <= series_short_age)
        series_use_short = series_short_ok and not series_use_long
        series_memory_active = series_use_long or series_use_short
        series_memory_dir = "LONG" if series_use_long else ("SHORT" if series_use_short else "")
        series_memory_type = series_long_type if series_use_long else (series_short_type if series_use_short else "")
        series_memory_score = series_long_score if series_use_long else (series_short_score if series_use_short else None)
        series_memory_age = series_long_age if series_use_long else (series_short_age if series_use_short else None)

        # P:590-601 marker stream
        marker_gap_ok = last_marker_bar is None or (i - last_marker_bar >= p.min_marker_gap)
        marker_fired = attention_event and marker_gap_ok
        marker_dir = raw_dir
        marker_type = raw_type
        marker_score = raw_score
        marker_extension = raw_extension
        marker_spread = s_l if marker_dir == "LONG" else (s_s if marker_dir == "SHORT" else None)
        marker_state = "ESTESO" if (marker_extension is not None and marker_extension > p.extension_max) else "NUOVO"
        if marker_fired:
            last_marker_bar = i

        # P:604-616 display invite + state (panel truth)
        memory_spread = s_l if series_memory_dir == "LONG" else (s_s if series_memory_dir == "SHORT" else None)
        memory_is_new = series_memory_active and nz(float(series_memory_age) if series_memory_age is not None else None) <= p.new_bars
        memory_is_rot = series_memory_active and series_memory_type == "ROT"
        memory_has_strength = series_memory_active and nz(memory_spread) >= p.spread_min
        display_invite = series_memory_active and (memory_has_strength or memory_is_new or memory_is_rot)
        display_active = display_invite
        display_dir = series_memory_dir if display_invite else ""
        display_type = series_memory_type if display_invite else ""
        display_score = series_memory_score if display_invite else None
        display_extension = L.extension if display_dir == "LONG" else (S.extension if display_dir == "SHORT" else None)
        display_bars_since = series_memory_age if display_invite else None
        if display_active:
            if display_extension is not None and display_extension > p.extension_max:
                display_state = "ESTESO"
            elif nz(float(display_bars_since) if display_bars_since is not None else None) <= p.new_bars:
                display_state = "NUOVO"
            else:
                display_state = "ATTIVO"
        else:
            display_state = ""

        # P:621-643 diag direction for panel NOTE/FORTE/DEBOLE/SPREAD
        dominant_long = nz(s_l) >= nz(s_s)
        diag_long = (display_dir == "LONG") if display_active else dominant_long
        diag = L if diag_long else S
        lead_name = base if diag_long else quote
        lag_name = quote if diag_long else base

        # P:648-670 label visibility (display only; engine state untouched)
        recent_enough = (last_bar_index - i) <= p.hist_bars
        marker_strong = marker_type == "ROT" or nz(marker_score) >= p.marker_label_score_min
        same_dir_as_last = last_shown_dir != "" and marker_dir == last_shown_dir
        dedup_upgrade = (last_shown_bar is None
                         or nz(marker_spread) >= nz(last_shown_spread) * p.dedup_spread_mult
                         or nz(marker_score) >= nz(last_shown_score) + p.dedup_score_step
                         or (i - last_shown_bar) >= p.dedup_bars)
        dedup_show = ((not p.dedup_same_direction) or (not same_dir_as_last)
                      or marker_type == "ROT" or dedup_upgrade)
        label_shown = marker_fired and recent_enough and marker_strong and dedup_show
        if label_shown:
            last_shown_dir = marker_dir
            last_shown_spread = marker_spread
            last_shown_score = marker_score
            last_shown_bar = i

        # P:694-713 panel
        note_str = "pullback" if diag.pullback_ok else ("compression" if diag.compression_ok else "-")
        score_val = display_score if display_active else diag.resume_score
        hidden_reason = ""
        if anti_flip_block:
            hidden_reason = "anti-flip"
        elif post_death_hidden:
            hidden_reason = "post-death-hidden"
        elif opposite_resume_extended:
            hidden_reason = "opposite-esteso-display"

        results.append(BarResult(
            time=f.time, bar_index=i,
            spread_long=s_l, spread_short=s_s,
            raw_dir=raw_dir, raw_type=raw_type, raw_score=raw_score,
            candidate_event=candidate_event, accepted_event=accepted_event,
            attention_event=attention_event,
            anti_flip_block=anti_flip_block, post_death_hidden=post_death_hidden,
            opposite_resume_extended=opposite_resume_extended,
            strong_opposite=strong_opposite,
            strong_live_opposite=strong_live_opposite,
            strong_post_death_opposite=strong_post_death_opposite,
            takeover_ok=takeover_ok, post_death_takeover_ok=post_death_takeover_ok,
            effective_dead_peak=effective_dead_peak,
            post_death_takeover_level=post_death_takeover_level,
            hidden_reason=hidden_reason,
            regime_dir=regime_dir, regime_peak_spread=regime_peak_spread,
            regime_weak_bars=regime_weak_bars,
            regime_touched_extended=regime_touched_extended,
            regime_dead=(regime_dir == "" or regime_weak_bars >= p.reset_bars),
            marker_fired=marker_fired, marker_state=marker_state,
            label_shown=label_shown,
            display_active=display_active, display_dir=display_dir,
            display_type=display_type, display_score=display_score,
            display_state=display_state, display_age=display_bars_since,
            panel_bias=display_dir if display_active else "-",
            panel_tipo=display_type if display_active else "-",
            panel_stato=display_state if display_active else "NESSUNO",
            panel_score=int(round(nz(score_val))),
            panel_forte=lead_name + " +", panel_debole=lag_name + " -",
            panel_spread=diag.spread, panel_note=note_str,
        ))

    return results
