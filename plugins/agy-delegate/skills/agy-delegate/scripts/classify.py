#!/usr/bin/env python3
"""Classify one agy --output-format json run for agy-run.sh.
Usage: classify.py STDOUT_FILE EXIT_CODE   (reads STDOUT_FILE.err for agy's stderr)
Prints "<status> <in_tokens> <out_tokens> <retry_after_s>" and writes the capped answer text to STDOUT_FILE.txt.
status: ok | error | denied | empty | quota."""
import json, sys
raw, rc = open(sys.argv[1], encoding="utf-8", errors="replace").read(), int(sys.argv[2])
try: err = open(sys.argv[1] + ".err", encoding="utf-8", errors="replace").read()
except OSError: err = ""
d = None
for cand in [raw] + [l for l in reversed(raw.splitlines()) if l.lstrip().startswith("{")]:   # JSON after stray text
    try: d = json.loads(cand); break
    except ValueError: pass
if not isinstance(d, dict): st, text, u = ("error" if rc else "ok"), (raw if raw.strip() else err), {}
else:
    text, u = d.get("response") or "", d.get("usage") or {}
    st = "error" if rc or d.get("status") != "SUCCESS" else "ok"
    blob = json.dumps(d) + err
    if st == "error" and ("RESOURCE_EXHAUSTED" in blob or '"error_code": 429' in blob):
        st = "quota"   # provider quota for this model: the router skips it until the reset
    if st in ("error", "quota") and not text: text = (json.dumps({k: d[k] for k in d if k != "usage"}) + " " + err.strip())[:2000]
    elif st == "ok" and not text.strip() and (d.get("denied_actions") or "auto-denied" in err):
        st, text = "denied", "jetski: no output (denied: " + ", ".join(a.get("action", "?") for a in d.get("denied_actions") or []) + ")"
if st == "ok" and (text.startswith("jetski: no output") or (not text.strip() and err.startswith("jetski: no output"))): st = "denied"
elif st == "ok" and not text.strip(): st = "empty"
import re
m = re.search(r"[Rr]esets in ((?:\d+[hms])+)", json.dumps(d) + err if isinstance(d, dict) else raw + err)
retry = sum(int(n) * {"h": 3600, "m": 60, "s": 1}[k] for n, k in re.findall(r"(\d+)([hms])", m.group(1))) if m else 0
open(sys.argv[1] + ".txt", "w", encoding="utf-8").write(text[:20000])
print(st, u.get("input_tokens") or 0, u.get("output_tokens") or 0, retry)
