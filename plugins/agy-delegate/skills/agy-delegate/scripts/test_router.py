#!/usr/bin/env python3
"""Router checks (no network, no agy). Run: python3 test_router.py"""
import json, os, sys, tempfile
d = tempfile.mkdtemp()
os.environ.update(AGY_DELEGATE_LOG=os.path.join(d, "u.jsonl"), AGY_DELEGATE_HOME=d)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import router as R
n = 0
def ok(cond, msg):
    global n; assert cond, msg; n += 1

ALL = {m for lad in R.LADDERS.values() for m in lad}
ok(R.choose("extract", 98000, {}, ALL, True)[0] == R.A_MED, "extract starts on argon-medium (benchmarked 12/12; flash-low miscounts)")
ok(R.choose("quick", 98000, {}, ALL, True)[0] == R.A_LOW, "quick starts on argon-low")
ok(R.choose("reason", 98000, {}, ALL, True)[0] == R.A_HIGH, "reason starts on argon-high")
ok(R.choose("extract", 2000, {}, ALL, True)[0] == "claude", "too small to delegate")
bad = {R.A_MED: {"calls": 4, "fails": 2, "ok_s": 20.0}}
ok(R.choose("extract", 98000, bad, ALL, True)[0] == R.F_MED, "climbs past an unreliable rung")
few = {R.A_MED: {"calls": 2, "fails": 2, "ok_s": 0.0}}
ok(R.choose("extract", 98000, few, ALL, True)[0] == R.A_MED, "too little data: stays")
dead = {m: {"calls": 9, "fails": 9, "ok_s": 0} for m in ALL}
ok(R.choose("reason", 98000, dead, ALL, True)[0] == R.LADDERS["reason"][-1], "top rung stays even when failing")
both = {R.A_HIGH: {"calls": 5, "fails": 5, "ok_s": 0}, R.F_HIGH: {"calls": 5, "fails": 5, "ok_s": 0}}
ok(R.choose("reason", 98000, both, ALL, True)[0] == R.LADDERS["reason"][2], "reason climbs to the next model family")
ok(all(not R.is_claude(R.choose(k, 98000, dead, ALL, False)[0]) for k in R.LADDERS), "Claude-in-agy off: never picked")
ok(R.choose("extract", 98000, {}, {R.F_HIGH}, True)[0] == R.F_HIGH, "skips models agy does not offer")
ok(R.choose("extract", 98000, {}, {"something-else"}, True)[0] == "claude", "catalog known, nothing eligible: stay in Claude")
ok(R.ladder("extract", {"something-else"}) == [], "ladder empty when nothing eligible")
ok(R.choose("extract", 98000, {}, None, True)[0] == R.A_MED, "catalog unknown: assume first rung offered")

import time
q = {R.A_MED: {"calls": 0, "fails": 0, "ok_s": 0, "quota_until": time.time() + 600}}
m, why = R.choose("extract", 98000, q, ALL, True)
ok(m == R.F_MED and "quota" in why, "model out of quota is skipped until reset")
allq = {m: {"calls": 0, "fails": 0, "ok_s": 0, "quota_until": time.time() + 600} for m in R.LADDERS["extract"]}
m, why = R.choose("extract", 98000, allq, ALL, True)
ok(m == "claude" and "quota" in why, "all rungs out of quota: stay in Claude")
q[R.A_MED]["quota_until"] = time.time() - 1
ok(R.choose("extract", 98000, q, ALL, True)[0] == R.A_MED, "back after the reset")
with open(R.LOG, "w") as f:
    f.write(json.dumps({"ev": "end", "id": "1", "ts": time.time(), "model": R.F_MED, "status": "quota", "retry_after_s": 300}) + "\n")
st = R.stats()
ok(st[R.F_MED]["calls"] == 0 and st[R.F_MED]["quota_until"] > time.time() + 200, "quota logged as a parking, not a failure")
open(R.LOG, "w").close()
os.makedirs(os.path.join(d, ".agy-delegate"), exist_ok=True)
with open(os.path.join(d, ".agy-delegate", "config.json"), "w") as f: json.dump({"allow_claude_in_agy": False}, f)
ok(not R.is_claude(R.choose("reason", 98000, dead, ALL)[0]), "config switch read when not passed")

fake = lambda: [{"id": R.F_HIGH, "name": "Flash High"}, {"id": "claude-opus-5-5-high", "name": "Opus"},
                {"id": "gemini-9-pro", "name": "New"}]
cat = {m["id"]: m for m in R.catalog(refresh=True, fetch=fake)["models"]}
ok(cat[R.F_HIGH]["role"] == "router" and cat[R.F_HIGH]["available"], "offered ladder model")
ok(cat["gemini-9-pro"]["role"] == "manual", "unknown model is manual")
ok(cat["claude-opus-5-5-high"]["role"] == "off", "Claude model off by config")
ok(not cat[R.F_LOW]["available"], "ladder model agy does not offer is flagged")
ok(R.offered() == {R.F_HIGH, "claude-opus-5-5-high", "gemini-9-pro"}, "offered() reads the cache")
ok(R.catalog(fetch=lambda: 1 / 0)["error"] is None, "cached: fetch not called")
bad = R.catalog(refresh=True, fetch=lambda: (_ for _ in ()).throw(OSError("agy not installed")))
ok(bad["error"] == "agy not installed" and "gemini-9-pro" in {m["id"] for m in bad["models"]}, "stale cache still shown")
# empty catalog (agy answered with no models) is not the same as unknown catalog
cache = os.path.join(d, "models.json")
R.catalog(refresh=True, fetch=lambda: [])
ok(R.offered() == set(), "empty catalog: offered() is an empty set, not None")
ok(R.choose("extract", 98000, {}, None, True)[0] == "claude", "empty catalog: nothing eligible, stay in Claude")
json.dump({"ts": time.time() - R.EMPTY_TTL - 5, "models": []}, open(cache, "w"))
ok(R.offered(fetch=lambda: [{"id": R.A_MED, "name": "x"}]) == {R.A_MED}, "empty cache is rechecked after EMPTY_TTL")
print(f"router tests: {n} passed")
