"""Run report (Markdown + JSON). Radar of attention only: no trade language."""

from __future__ import annotations

import json
from dataclasses import asdict
from typing import Dict, List

from .candles import AlignInfo
from .engine import BarResult
from .focus import FocusRow


def build_report(run_time_utc: str, align_info: AlignInfo,
                 last_by_pair: Dict[str, BarResult],
                 focus_rows: List[FocusRow]) -> dict:
    pairs_rows = []
    for pair in sorted(last_by_pair):
        r = last_by_pair[pair]
        pairs_rows.append({
            "pair": pair,
            "bias": r.panel_bias, "tipo": r.panel_tipo, "stato": r.panel_stato,
            "score": r.panel_score, "forte": r.panel_forte, "debole": r.panel_debole,
            "spread": round(r.panel_spread, 2) if r.panel_spread is not None else None,
            "note": r.panel_note,
            "age": r.display_age,
            "attention_event": r.attention_event,
            "raw_dir": r.raw_dir, "raw_type": r.raw_type,
            "hidden_reason": r.hidden_reason,
        })
    events = [row for row in pairs_rows if row["attention_event"]]
    hidden = [row for row in pairs_rows if row["hidden_reason"]]
    return {
        "run_time_utc": run_time_utc,
        "last_aligned_bar_utc": align_info.times[-1],
        "misaligned_pairs": align_info.misaligned_pairs,
        "latest_by_pair": align_info.latest_by_pair,
        "focus": [asdict(f) for f in focus_rows],
        "events_this_bar": events,
        "hidden_this_bar": hidden,
        "pairs": pairs_rows,
        "disclaimer": "Radar di attenzione: decisione sulle linee manuali.",
    }


def render_markdown(rep: dict) -> str:
    L = []
    L.append(f"# FX Bias Radar - scan {rep['run_time_utc']}")
    L.append("")
    L.append(f"Ultima barra H4 chiusa (UTC): {rep['last_aligned_bar_utc']}")
    if rep["misaligned_pairs"]:
        L.append(f"ATTENZIONE coppie non allineate: {', '.join(rep['misaligned_pairs'])}")
    L.append("")
    L.append("## Focus list")
    L.append("")
    if rep["focus"]:
        L.append("| # | COPPIA | BIAS | TIPO | STATO | SCORE | FORTE | DEBOLE | SPREAD | NOTE |")
        L.append("|---|--------|------|------|-------|-------|-------|--------|--------|------|")
        for f in rep["focus"]:
            L.append(f"| {f['rank']} | {f['pair']} | {f['bias']} | {f['tipo']} | {f['stato']} "
                     f"| {f['score']} | {f['forte']} | {f['debole']} | {f['spread']:.2f} | {f['note']} |")
    else:
        L.append("Nessuna coppia attiva.")
    L.append("")
    if rep["events_this_bar"]:
        L.append("## Eventi su questa barra")
        L.append("")
        for e in rep["events_this_bar"]:
            L.append(f"- {e['pair']} {e['bias']} {e['tipo']} {e['stato']} {e['score']} "
                     f"| {e['forte']} / {e['debole']} | spread {e['spread']} | {e['note']}")
        L.append("")
    if rep["hidden_this_bar"]:
        L.append("## Eventi soppressi (debug)")
        L.append("")
        for e in rep["hidden_this_bar"]:
            L.append(f"- {e['pair']} raw {e['raw_dir']} {e['raw_type']} -> {e['hidden_reason']}")
        L.append("")
    L.append("## Tutte le coppie")
    L.append("")
    L.append("| COPPIA | BIAS | TIPO | STATO | SCORE | FORTE | DEBOLE | SPREAD | NOTE | AGE |")
    L.append("|--------|------|------|-------|-------|-------|--------|--------|------|-----|")
    for r in rep["pairs"]:
        spread = f"{r['spread']:.2f}" if r["spread"] is not None else "-"
        age = r["age"] if r["age"] is not None else "-"
        L.append(f"| {r['pair']} | {r['bias']} | {r['tipo']} | {r['stato']} | {r['score']} "
                 f"| {r['forte']} | {r['debole']} | {spread} | {r['note']} | {age} |")
    L.append("")
    L.append(rep["disclaimer"])
    L.append("")
    return "\n".join(L)


def to_json(rep: dict) -> str:
    return json.dumps(rep, indent=2)
