#!/usr/bin/env python3
"""Monitor checks (no server). Run: python3 test_monitor.py"""
import os, sys, tempfile, json, time
d = tempfile.mkdtemp(); log = os.path.join(d, "u.jsonl")
os.environ.update(AGY_DELEGATE_LOG=log, CLAUDE_CONFIG_DIR=d, AGY_MONITOR_LIMIT_24H="1000", AGY_MONITOR_LIMIT_7D="abc")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__))); import monitor as M
sv = M.saved_tokens
assert sv({"status": "ok", "src_bytes": 98000, "prompt_bytes": 300, "out_bytes": 200}) == 24375
assert sv({"status": "ok", "in_tokens": 37000, "prompt_bytes": 300, "out_bytes": 200}) is None    # no -b: not estimated
assert sv({"status": "ok", "src_bytes": 0, "in_tokens": 37000}) is None
assert sv({"status": "error", "src_bytes": 98000}) == 0 and sv({"status": "denied", "src_bytes": 98000}) == 0
assert sv({"status": "ok", "src_bytes": 100, "prompt_bytes": 300, "out_bytes": 900}) == 0           # never negative
assert M.limits() == {"5h": 0, "24h": 1000, "7d": 0}                                                # bad value -> 0
now = time.time()
rows = [{"ev": "end", "id": "a", "ts": now - 60, "model": "m", "dur_s": 5, "out_bytes": 200, "status": "ok", "in_tokens": 20000, "out_tokens": 50, "src_bytes": 40000, "prompt_bytes": 400},
        {"ev": "end", "id": "b", "ts": now - 6 * 3600, "model": "m", "dur_s": 5, "out_bytes": 0, "status": "error", "src_bytes": 40000, "prompt_bytes": 400},
        {"ev": "end", "id": "d", "ts": now - 120, "model": "m", "dur_s": 5, "out_bytes": 100, "status": "ok", "in_tokens": 30000, "src_bytes": 0, "prompt_bytes": 50},
        {"ev": "start", "id": "c", "ts": now - 5, "model": "m"}]
open(log, "w").write("\n".join(json.dumps(r) for r in rows) + '\n{"ev":"end"}\n[1]\nnot json\n')   # malformed tail is skipped
models, running, saved, unest = M.agy_stats(now)
assert models["m"]["calls"] == 3 and models["m"]["failed"] == 1 and len(running) == 1
assert saved == {"5h": 9850, "24h": 9850, "7d": 9850}, saved
assert unest == {"5h": 1, "24h": 1, "7d": 1}, unest
rc = M.recent_calls()
assert [r["status"] for r in rc] == ["ok", "error", "ok"] and rc[0]["saved"] is None and rc[2]["saved"] == 9850
assert M.snapshot()["saved_unestimated"]["24h"] == 1
print("monitor tests: passed")
