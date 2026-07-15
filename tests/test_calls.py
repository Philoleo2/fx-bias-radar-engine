"""Test registro chiamate + classifica."""
from __future__ import annotations
import os, sys
from datetime import datetime, timezone, timedelta
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from fx_bias_radar import calls as CALLS


def test_append_idempotent(tmp_path):
    p = os.path.join(str(tmp_path), "calls.csv")
    n1 = CALLS.append_calls(p, "2026-06-23T13:00:00+00:00",
                            [{"pair": "AUDNZD", "dir": "LONG"}], "2026-06-23T13:05:00+00:00")
    n2 = CALLS.append_calls(p, "2026-06-23T13:00:00+00:00",
                            [{"pair": "AUDNZD", "dir": "LONG"}], "2026-06-23T13:05:00+00:00")
    assert n1 == 1 and n2 == 0            # stessa barra -> non riscrive


def test_classifica_nuove_vs_rank(tmp_path):
    p = os.path.join(str(tmp_path), "calls.csv")
    now = datetime(2026, 6, 23, tzinfo=timezone.utc)
    def bar(days_ago, hour=12):
        return (now - timedelta(days=days_ago)).replace(hour=hour).isoformat()
    # EURUSD chiamata 3 volte, AUDNZD 1 volta (nuova), GBPJPY 1 volta MA fuori finestra (25gg)
    CALLS.append_calls(p, bar(5), [{"pair": "EURUSD", "dir": "SHORT"}])
    CALLS.append_calls(p, bar(3), [{"pair": "EURUSD", "dir": "SHORT"}])
    CALLS.append_calls(p, bar(1), [{"pair": "EURUSD", "dir": "SHORT"}, {"pair": "AUDNZD", "dir": "LONG"}])
    CALLS.append_calls(p, bar(25), [{"pair": "GBPJPY", "dir": "LONG"}])
    c = CALLS.build_classifica(p, now=now + timedelta(hours=1), window_days=20)
    rank = {e["pair"]: e["count"] for e in c["classifica"]}
    nuove = {e["pair"] for e in c["nuove"]}
    assert rank == {"EURUSD": 3}          # >=2 -> classifica
    assert nuove == {"AUDNZD"}            # 1 chiamata -> nuova; GBPJPY escluso (fuori 20gg)
