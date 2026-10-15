#!/usr/bin/env python3
"""Router checks (no network, no agy). Run: python3 test_router.py"""
import os, sys; sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import router as R
ok = lambda m, n: {m: {"calls": n, "fails": 0, "ok_s": 10.0 * n}}
assert R.choose("extract", 98000, {})[0] == "gemini-3.8-flash-medium"   # low is not a default start (benchmark)
assert R.choose("summarize", 98000, {})[0] == "gemini-3.8-flash-medium"
assert R.choose("reason", 98000, {})[0] == "gemini-3.8-flash-high"
assert R.choose("extract", 2000, {})[0] == "claude"                       # too small to delegate
bad = {"gemini-3.8-flash-medium": {"calls": 4, "fails": 2, "ok_s": 20.0}}  # 50% failures
assert R.choose("extract", 98000, bad)[0] == "gemini-3.8-flash-high"       # escalates
few = {"gemini-3.8-flash-medium": {"calls": 2, "fails": 2, "ok_s": 0.0}}   # too little data
assert R.choose("extract", 98000, few)[0] == "gemini-3.8-flash-medium"
assert R.choose("reason", 98000, {"gemini-3.8-flash-high": {"calls": 9, "fails": 9, "ok_s": 0}})[0] == "gemini-3.8-flash-high"  # top rung stays
print("router tests: 5/5 passed")
