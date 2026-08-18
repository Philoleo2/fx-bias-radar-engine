"""Hourly PAIR_PREWAKE_V1 production step.

Runs in its own GitHub Actions workflow (.github/workflows/prewake.yml) at
HH:10, five minutes after the FX Bias Pre-Rottura job. PREWAKE does not read
any FX Bias state — the frozen `fx_bias_same` feature is computed from price
inside the frozen engine — so the two jobs are fully isolated (SS48).

Order of operations:
    OANDA H1 fetch -> verify complete common grid -> advance frozen state
    -> persist run + events -> notifications -> UI snapshot

Nothing here fits a model. Scoring uses the immutable artifact only.
"""
from __future__ import annotations

import argparse
import os
import sys
import time
import traceback

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np

from prewake import config, market, notify, store
from prewake.engine import evaluate
from prewake.model import load_model
from prewake.state import PrewakeState

DEFAULT_WINDOW = 400          # >= 241 required bars, with headroom for gaps


def _run_record(**kwargs) -> dict:
    base = {
        "run_id": None, "model_version": None, "model_fingerprint": None,
        "bar_time_utc": None, "started_at": None, "completed_at": None,
        "status": None, "input_data_fingerprint": None, "pair_count": 0,
        "event_count": 0, "error_code": None, "error_detail": None,
        "feature_build_ms": None, "model_eval_ms": None, "total_prewake_ms": None,
        "created_at": store.now_utc(),
    }
    base.update(kwargs)
    return base


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--oanda", action="store_true", help="fetch live candles from OANDA")
    parser.add_argument("--count", type=int, default=DEFAULT_WINDOW)
    parser.add_argument("--base", default=store.BASE_DIR)
    parser.add_argument("--email-dry-run", action="store_true")
    args = parser.parse_args()

    config.assert_no_model_overrides()
    started = store.now_utc()
    t0 = time.perf_counter()

    if not config.engine_enabled():
        print("PREWAKE_ENGINE_ENABLED is off; nothing to do.")
        store.append_jsonl(store.RUNS, [_run_record(
            started_at=started, completed_at=store.now_utc(), status="DISABLED")], args.base)
        return 0

    model = load_model()
    state = PrewakeState.load(model, args.base)
    print(f"model {model.model_version} fingerprint {model.research_fingerprint[:12]}… "
          f"artifact {model.artifact_hash[:19]}…")

    if not state.is_seeded:
        detail = ("state not seeded: run scripts/prewake_seed.py once before enabling the engine, "
                  "otherwise NEW_WAKE/REAWAKENING labels and the recursive EWMA would not match "
                  "the frozen research")
        print("ERROR:", detail)
        store.append_jsonl(store.RUNS, [_run_record(
            model_version=model.model_version, model_fingerprint=model.research_fingerprint,
            started_at=started, completed_at=store.now_utc(), status="NOT_SEEDED",
            error_code="NOT_SEEDED", error_detail=detail)], args.base)
        return 1

    # ---------------------------------------------------------------- input
    try:
        if args.oanda:
            from fx_bias_radar.oanda_fetch import env_credentials
            token, env = env_credentials()
            grid = market.fetch_grid(token, env=env, count=args.count)
        else:
            raise SystemExit("run with --oanda (offline replay lives in scripts/prewake_seed.py)")
    except market.IncompleteInput as exc:
        print("SKIPPED:", exc)
        store.append_jsonl(store.RUNS, [_run_record(
            model_version=model.model_version, model_fingerprint=model.research_fingerprint,
            started_at=started, completed_at=store.now_utc(), status="SKIPPED_INCOMPLETE_INPUT",
            error_code="SKIPPED_INCOMPLETE_INPUT", error_detail=str(exc))], args.base)
        return 0

    newest = grid.times[-1]
    if state.last_bar_time_utc and newest <= state.last_bar_time_utc:
        print(f"no new complete H1 (newest {newest}, already processed {state.last_bar_time_utc})")
        store.append_jsonl(store.RUNS, [_run_record(
            model_version=model.model_version, model_fingerprint=model.research_fingerprint,
            bar_time_utc=newest, started_at=started, completed_at=store.now_utc(),
            status="NO_NEW_BAR", input_data_fingerprint=grid.fingerprint(),
            pair_count=len(grid.close[0]))], args.base)
        return 0

    try:
        emit_from = next((i for i, t in enumerate(grid.times) if t > state.last_bar_time_utc), len(grid.times))
        if emit_from >= len(grid.times):
            print("nothing new to emit")
            return 0
        if emit_from < model.minimum_bars:
            detail = (f"warm-up gap: newest unprocessed bar sits at index {emit_from} of a "
                      f"{len(grid.times)}-bar window, below the {model.minimum_bars} required; "
                      "re-seed to close the gap")
            print("SKIPPED:", detail)
            store.append_jsonl(store.RUNS, [_run_record(
                model_version=model.model_version, model_fingerprint=model.research_fingerprint,
                bar_time_utc=newest, started_at=started, completed_at=store.now_utc(),
                status="SKIPPED_INCOMPLETE_INPUT", error_code="WARMUP_GAP", error_detail=detail,
                input_data_fingerprint=grid.fingerprint())], args.base)
            return 0

        t_feat = time.perf_counter()
        result = evaluate(grid.times, grid.close, grid.high, grid.low,
                          lifecycle_state=state.lifecycle,
                          ewma_state=state.ewma_state, ewma_ready=state.ewma_ready,
                          emit_from=emit_from, model=model)
        eval_ms = (time.perf_counter() - t_feat) * 1000.0

        if result.skipped_reason:
            print("SKIPPED:", result.skipped_reason)
            store.append_jsonl(store.RUNS, [_run_record(
                model_version=model.model_version, model_fingerprint=model.research_fingerprint,
                bar_time_utc=newest, started_at=started, completed_at=store.now_utc(),
                status="SKIPPED_INCOMPLETE_INPUT", error_code="SKIPPED_INCOMPLETE_INPUT",
                error_detail=result.skipped_reason)], args.base)
            return 0

        # ------------------------------------------------------- persistence
        prospective_start = state.prospective_start_at
        records = []
        for event in result.events:
            eid = store.event_id(model.model_version, event["pair"], event["bar_time_utc"],
                                 event["type"], event["direction"])
            bar_close = event["bar_time_utc"]
            is_prospective = bool(prospective_start and bar_close >= prospective_start)
            records.append({
                "event_id": eid,
                "model_version": model.model_version,
                "model_fingerprint": model.research_fingerprint,
                "artifact_hash": model.artifact_hash,
                "pair": event["pair"],
                "direction": "LONG" if event["direction"] > 0 else "SHORT",
                "direction_sign": event["direction"],
                "event_type": event["type"],
                "bar_time_utc": event["bar_time_utc"],
                "generated_at_utc": store.now_utc(),
                "score": event["score"],
                "threshold": model.threshold,
                "state_before": "ARMED",
                "state_after": "ACTIVE",
                "fx_bias_same": event["fx_bias_same"],
                "same_bar_raw_breakout": event["same_bar_raw_breakout"],
                "is_backfill": not is_prospective,
                "is_prospective": is_prospective,
                "features": event["features"],
                "direction_source_value": event["direction_source_value"],
                "ewma4_gap": event["ewma4_gap"],
                "ols_lopo_gap": event["ols_lopo_gap"],
                "gap_robust_z": event["gap_robust_z"],
            })
        stored = store.append_events(records, args.base)
        print(f"bar {newest}: {len(result.events)} event(s), {len(stored)} new after idempotency")

        state.lifecycle = result.lifecycle_state
        state.ewma_state = result.features.ewma_state
        state.ewma_ready = result.features.ewma_ready
        state.last_bar_time_utc = newest
        state.save(args.base)

        total_ms = (time.perf_counter() - t0) * 1000.0
        store.append_jsonl(store.RUNS, [_run_record(
            run_id=f"{model.model_version}:{newest}",
            model_version=model.model_version, model_fingerprint=model.research_fingerprint,
            bar_time_utc=newest, started_at=started, completed_at=store.now_utc(), status="OK",
            input_data_fingerprint=grid.fingerprint(), pair_count=len(grid.close[0]),
            event_count=len(stored), model_eval_ms=round(eval_ms, 2),
            total_prewake_ms=round(total_ms, 2))], args.base)

        # ------------------------------------------------------ notifications
        _notify(model, args, stored)
        _snapshot(model, state, args.base, newest, total_ms)
        return 0

    except Exception as exc:                                       # noqa: BLE001
        # SS48: a PREWAKE failure must never affect FX Bias. This job is separate,
        # and it still records a structured failure instead of crashing silently.
        print("PREWAKE run failed:", type(exc).__name__)
        traceback.print_exc()
        store.append_jsonl(store.RUNS, [_run_record(
            model_version=model.model_version, model_fingerprint=model.research_fingerprint,
            bar_time_utc=newest, started_at=started, completed_at=store.now_utc(), status="ERROR",
            error_code=type(exc).__name__, error_detail=str(exc)[:500])], args.base)
        return 1


def _notify(model, args, stored):
    """Send prospective alerts once; retry anything still pending."""
    if not config.email_enabled():
        if stored:
            print(f"PREWAKE_EMAIL_ENABLED is off; {len(stored)} event(s) stored without email.")
        return
    joined = store.events_with_status(args.base)
    pending = [e for e in joined
               if e.get("is_prospective") and e.get("email_status") in ("PENDING", "RETRY")]
    if not pending:
        return
    logs = []
    for event in pending:
        event = dict(event)
        event["threshold"] = event.get("threshold", model.threshold)
        logs.append(notify.deliver(event, model.model_version, dry_run=args.email_dry_run))
    store.append_jsonl(store.EMAIL_LOG, logs, args.base)
    sent = sum(1 for r in logs if r["status"] == "SENT")
    print(f"email: {sent} sent, {len(logs) - sent} pending retry")


def _snapshot(model, state, base, newest, total_ms):
    """Derived UI/health snapshots. Regenerated, never a source of truth."""
    joined = store.events_with_status(base)
    joined.sort(key=lambda r: (r["bar_time_utc"], r["pair"]), reverse=True)
    today = newest[:10]
    store.write_json(store.LATEST, {
        "model_name": model.model_name, "model_version": model.model_version,
        "model_fingerprint": model.research_fingerprint, "artifact_hash": model.artifact_hash,
        "threshold": model.threshold, "tuning": "FROZEN", "status": "ACTIVE",
        "prospective_start_at": state.prospective_start_at,
        "last_complete_h1_utc": newest,
        "generated_at_utc": store.now_utc(),
        "events": joined[:200],
        "disclaimer": "Radar di attenzione: decisione sulle linee manuali.",
    }, base)
    runs = store.read_jsonl(store.RUNS, base)
    ok_runs = [r for r in runs if r["status"] == "OK"]
    store.write_json(store.HEALTH, {
        "model_version": model.model_version,
        "model_fingerprint": model.research_fingerprint,
        "last_prewake_run": runs[-1]["completed_at"] if runs else None,
        "last_complete_h1_seen": newest,
        "last_successful_evaluation": ok_runs[-1]["completed_at"] if ok_runs else None,
        "event_count_today": sum(1 for e in joined if e["bar_time_utc"][:10] == today),
        "event_count_total": len(joined),
        "email_queue_status": {
            "pending": sum(1 for e in joined if e.get("email_status") in ("PENDING", "RETRY")),
            "sent": sum(1 for e in joined if e.get("email_status") == "SENT"),
        },
        "total_prewake_ms": round(total_ms, 2),
        "engine_enabled": config.engine_enabled(),
        "email_enabled": config.email_enabled(),
        "generated_at_utc": store.now_utc(),
    }, base)


if __name__ == "__main__":
    sys.exit(main())
