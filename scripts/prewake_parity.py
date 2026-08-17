"""Historical parity: production prewake package vs frozen research ledger.

Run offline against the frozen Phase 1/2 dataset. Not part of the hourly job.

  python scripts/prewake_parity.py --mid <mid.pkl.gz> --ba <ba.pkl.gz> \
      --golden <pair_prewake_events.csv> --holdout-start 40084
"""
from __future__ import annotations

import argparse
import csv
import gzip
import os
import pickle
import sys
from collections import Counter

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fx_bias_radar import pairs as P
from prewake.engine import evaluate
from prewake.lifecycle import LifecycleState, batch_lifecycle_events
from prewake.model import load_model
from prewake.primitives import parse_utc


def load_grid(mid_path, ba_path):
    with gzip.open(mid_path, "rb") as h:
        mid = pickle.load(h)["h1"]
    with gzip.open(ba_path, "rb") as h:
        ba = pickle.load(h)["pairs"]
    iso = lambda v: parse_utc(v).isoformat(timespec="seconds")
    common_mid = set.intersection(*[{iso(r.time) for r in mid[p]} for p in P.PAIRS])
    common_ba = set.intersection(*[{iso(r[0]) for r in ba[p]} for p in P.PAIRS])
    times = sorted(common_mid & common_ba)
    n, k = len(times), len(P.PAIRS)
    o, h_, l_, c = (np.empty((n, k)) for _ in range(4))
    for j, pair in enumerate(P.PAIRS):
        m = {iso(r.time): r for r in mid[pair] if r.complete}
        for i, t in enumerate(times):
            row = m[t]
            o[i, j], h_[i, j], l_[i, j], c[i, j] = row.o, row.h, row.l, row.c
    return times, c, h_, l_


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mid", required=True)
    ap.add_argument("--ba", required=True)
    ap.add_argument("--golden", required=True)
    ap.add_argument("--holdout-start", type=int, default=40084)
    args = ap.parse_args()

    model = load_model()
    print(f"model {model.model_version} artifact {model.artifact_hash}")
    print(f"fingerprint {model.research_fingerprint}")

    times, close, high, low = load_grid(args.mid, args.ba)
    n = len(times)
    print(f"grid {n} H1 x {len(P.PAIRS)} pairs, {times[0]} -> {times[-1]}")

    emit_from = args.holdout_start
    emit_to = n - 24                     # frozen holdout end: allowed_range(n, dev_end, n-24)
    result = evaluate(times, close, high, low, lifecycle_state=LifecycleState.fresh(), emit_from=emit_from)
    events = [e for e in result.events if e["t"] < emit_to]
    print(f"production events (incremental lifecycle): {len(events)}")

    allowed = np.zeros(n, dtype=bool)
    allowed[emit_from:emit_to] = True
    batch = batch_lifecycle_events(result.score, result.features.direction, model.threshold,
                                   allowed, result.features.breakout)
    print(f"frozen batch lifecycle events           : {len(batch)}")
    bk = {(e["t"], e["pair_index"], e["direction"], e["type"]) for e in batch}
    pk = {(e["t"], e["pair_index"], e["direction"], e["type"]) for e in events}
    print(f"  incremental vs batch: only_batch={len(bk - pk)} only_incremental={len(pk - bk)}")

    golden = [r for r in csv.DictReader(open(args.golden, encoding="utf-8"))
              if r["sample"] == "PREVIOUSLY_SEEN_FINAL_HOLDOUT"]
    print(f"golden research events                  : {len(golden)}")

    prod = {(times[e["t"]], e["pair"], e["direction"], e["type"]): e for e in events}
    gold = {(r["bar_open_utc"], r["pair"], int(r["direction_sign"]), r["event_type"]): r for r in golden}
    only_prod = sorted(set(prod) - set(gold))
    only_gold = sorted(set(gold) - set(prod))
    common = sorted(set(prod) & set(gold))
    print(f"  matched={len(common)} only_production={len(only_prod)} only_research={len(only_gold)}")
    for k in only_prod[:10]:
        print("    ONLY PRODUCTION", k)
    for k in only_gold[:10]:
        print("    ONLY RESEARCH  ", k)

    names = ["dir_ret1", "dir_ret4", "dir_ret12", "dir_ret24",
             "abs_pair_z", "compression_ratio", "pair_vol120", "fx_bias_same"]
    sdiff, fdiff = [], {c: 0.0 for c in names}
    for k in common:
        e, r = prod[k], gold[k]
        sdiff.append(abs(e["score"] - float(r["signal_value"])))
        for c in names:
            fdiff[c] = max(fdiff[c], abs(e["features"][c] - float(r[c])))
    sdiff = np.array(sdiff) if sdiff else np.array([0.0])
    print(f"  score parity : max|diff|={sdiff.max():.3e}  within 1e-12: {(sdiff <= 1e-12).sum()}/{len(sdiff)}")
    print("  feature parity (max abs diff):")
    for c in names:
        print(f"    {c:<18} {fdiff[c]:.3e}")

    hits = sum(1 for r in golden if str(r["primary_hit_plus1_plus12"]).strip().lower() in ("1", "true", "yes"))
    same_bar_prod = sum(1 for e in events if e["same_bar_raw_breakout"])
    print(f"  event types  : {Counter(e['type'] for e in events)}")
    print(f"  GOLDEN §54   : alerts={len(events)} (expect 1104), breakout+1..+12={hits} (expect 702)")
    print(f"  GOLDEN §56   : same_bar_raw_breakout={same_bar_prod} (expect 4)")

    ei = P.PAIRS.index("EURNZD")
    win = [i for i, t in enumerate(times) if "2026-08-10" <= t[:10] <= "2026-08-14"]
    mx = max(result.score[i, ei] for i in win if np.isfinite(result.score[i, ei]))
    print(f"  GOLDEN §55   : EURNZD case max={mx:.6f} threshold={model.threshold:.6f} -> "
          f"{'NO ALERT' if mx < model.threshold else 'ALERT (FAILURE)'}")

    ok = (not only_prod and not only_gold and len(events) == len(golden) == 1104
          and hits == 702 and same_bar_prod == 4 and mx < model.threshold
          and float(sdiff.max()) <= 1e-12 and not (bk - pk) and not (pk - bk))
    print("\nPARITY RESULT:", "ZERO DIFFERENCES" if ok else "DIFFERENCES PRESENT")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
