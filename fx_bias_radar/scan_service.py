"""Shared scan service for CLI, dashboard API, and future Telegram alerts.

This module is display/infrastructure only. It does not change the engine,
thresholds, scoring, protective memory, or anti-flip behavior.
"""

from __future__ import annotations

import glob
import json
import os
from datetime import datetime, timezone
from typing import Dict, List, Optional

from . import candles as C
from . import currency_index as CI
from . import engine as E
from . import pairs as P
from . import report as R
from .candles import Candle
from .focus import build_focus

ENGINE_LABEL = "M1 Python port - FX Bias Radar v1.1/v1.3 current logic"
DEFAULT_COUNT = 500


def build_scan_report(
    candles_by_pair: Dict[str, List[Candle]],
    *,
    run_time_utc: Optional[str] = None,
    focus_max_rows: int = 5,
    focus_cluster_cap: int = 2,
    include_incomplete: bool = False,
) -> dict:
    """Run the validated engine on an already loaded candle universe."""
    missing = [pair for pair in P.PAIRS if pair not in candles_by_pair]
    if missing:
        raise ValueError(f"coppie mancanti: {missing}")

    times, closes, align_info = C.align(
        candles_by_pair,
        include_incomplete=include_incomplete,
    )
    cd = CI.build(times, closes)

    last_by_pair = {}
    for pair in P.PAIRS:
        frames = CI.pair_frames(cd, pair)
        results = E.run_pair(pair, frames)
        last_by_pair[pair] = results[-1]

    focus_rows = build_focus(
        last_by_pair,
        max_rows=focus_max_rows,
        cluster_cap=focus_cluster_cap,
    )
    stamp = run_time_utc or datetime.now(timezone.utc).isoformat(timespec="seconds")
    return R.build_report(stamp, align_info, last_by_pair, focus_rows)


def run_scan_from_fixtures(
    fixtures_dir: str,
    *,
    run_time_utc: Optional[str] = None,
    include_incomplete: bool = False,
) -> dict:
    """Run a scan from fixture JSON files."""
    return build_scan_report(
        C.load_fixture_dir(fixtures_dir),
        run_time_utc=run_time_utc,
        include_incomplete=include_incomplete,
    )


def run_scan_from_oanda(
    *,
    token: Optional[str] = None,
    env: Optional[str] = None,
    count: int = DEFAULT_COUNT,
    include_incomplete: bool = False,
) -> dict:
    """Fetch live OANDA H4 candles and run the shared scan."""
    from .oanda_fetch import env_credentials, fetch_all_pairs

    if token is None:
        token, resolved_env = env_credentials()
        env = env or resolved_env
    candles_by_pair = fetch_all_pairs(
        token,
        env=env or "practice",
        count=count,
        include_incomplete=include_incomplete,
    )
    return build_scan_report(
        candles_by_pair,
        include_incomplete=include_incomplete,
    )


def latest_report_path(report_dir: str = "reports/actions") -> Optional[str]:
    """Return the newest committed JSON scan report, if one exists.

    Review Sonnet (M2C): relative dirs are also resolved against the repo
    root, so the Actions fallback works when the serverless cwd is not the
    repo root (e.g. Vercel). Display/infra only: engine untouched.
    """
    search_dirs = [report_dir]
    if not os.path.isabs(report_dir):
        repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        search_dirs.append(os.path.join(repo_root, report_dir))
    for directory in search_dirs:
        files = glob.glob(os.path.join(directory, "scan_*.json"))
        if files:
            return max(files, key=os.path.getmtime)
    return None


def load_report_json(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_latest_actions_report(report_dir: str = "reports/actions") -> Optional[dict]:
    path = latest_report_path(report_dir)
    if not path:
        return None
    return load_report_json(path)


def dashboard_payload(
    report: dict,
    *,
    source: str,
    warnings: Optional[List[str]] = None,
    cache_hit: bool = False,
    requested_mode: str = "closed",
) -> dict:
    """Build the public dashboard JSON payload.

    The payload intentionally contains no credentials, account ids, or raw
    request URLs. Markdown is included so the browser can download the same
    report format used by GitHub Actions.
    """
    warnings_out = list(warnings or [])
    if report.get("misaligned_pairs"):
        warnings_out.append(
            "Alcune coppie non sono allineate sull'ultima H4 chiusa."
        )
    is_live = source.strip().lower().startswith("oanda ")
    bar_status = report.get("bar_status", "closed")
    return {
        "ok": True,
        "data_status": "live" if is_live else "fallback",
        "is_live": is_live,
        "requested_mode": requested_mode,
        "bar_status": bar_status,
        "generated_at_utc": report["run_time_utc"],
        "analyzed_h4_utc": report["analyzed_bar_utc"],
        "analyzed_h4_close_utc": report["analyzed_bar_close_utc"],
        "last_closed_h4_utc": report.get(
            "last_complete_bar_close_utc",
            report.get(
                "last_closed_bar_utc",
                report["last_aligned_bar_utc"],
            ),
        ),
        "last_closed_h4_open_utc": report.get(
            "last_complete_bar_utc",
            report["last_aligned_bar_utc"],
        ),
        "source": source,
        "engine": ENGINE_LABEL,
        "cache": {"hit": bool(cache_hit)},
        "warnings": warnings_out,
        "misaligned_pairs": report.get("misaligned_pairs", []),
        "focus": report.get("focus", []),
        "events_this_bar": report.get("events_this_bar", []),
        "hidden_this_bar": report.get("hidden_this_bar", []),
        "pairs": report.get("pairs", []),
        "disclaimer": report.get(
            "disclaimer",
            "Radar di attenzione: decisione sulle linee manuali.",
        ),
        "markdown": R.render_markdown(report),
    }
