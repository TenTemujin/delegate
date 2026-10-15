#!/usr/bin/env python3
"""Model router for agy-delegate. Picks 'claude' (do it yourself) or an agy model per task kind/size,
adapting to the usage log (~/.agy-delegate/usage.jsonl).
  router.py choose --kind extract|summarize|edit|reason [--bytes N]   -> prints: <model>\t<reason>
Policy is heuristic (27-call benchmark, see docs/BENCHMARK.md); adaptation only escalates/de-escalates on logged outcomes."""
import argparse, json, os, sys, time

LOG = os.environ.get("AGY_DELEGATE_LOG", os.path.expanduser("~/.agy-delegate/usage.jsonl"))
LADDER = ["gemini-3.8-flash-low", "gemini-3.8-flash-medium", "gemini-3.8-flash-high"]
BASE = {"extract": 1, "summarize": 1, "edit": 1, "reason": 2}   # starting rung per task kind (flash-low got 6/9 on counting tasks, see docs/BENCHMARK.md)
MIN_BYTES = 6000      # below ~5-6 KB the skill overhead exceeds the saving: keep it in Claude
MIN_CALLS, FAIL_RATE, WINDOW = 3, 0.30, 7 * 24 * 3600

def stats(now=None):
    """Per-model {calls, fails, ok_s} from the log (fails = denied|empty), last 7 days."""
    now, out = now or time.time(), {}
    try:
        for line in open(LOG):
            try: e = json.loads(line)
            except ValueError: continue
            if e.get("ev") != "end" or now - e.get("ts", 0) > WINDOW: continue
            r = out.setdefault(e["model"], {"calls": 0, "fails": 0, "ok_s": 0.0})
            r["calls"] += 1
            if e.get("status") == "ok": r["ok_s"] += e.get("dur_s", 0)
            else: r["fails"] += 1
    except OSError: pass
    return out

def choose(kind, nbytes=None, st=None):
    if nbytes is not None and nbytes < MIN_BYTES:
        return "claude", f"{nbytes} B < {MIN_BYTES} B: delegation overhead exceeds saving"
    st = stats() if st is None else st
    rung, why = BASE.get(kind, 1), f"kind={kind}"
    while rung < len(LADDER) - 1:                      # escalate away from unreliable rungs
        r = st.get(LADDER[rung])
        if r and r["calls"] >= MIN_CALLS and r["fails"] / r["calls"] > FAIL_RATE:
            why += f"; {LADDER[rung]} failed {r['fails']}/{r['calls']} -> escalated"; rung += 1
        else: break
    return LADDER[rung], why

if __name__ == "__main__":
    ap = argparse.ArgumentParser(); sp = ap.add_subparsers(dest="cmd", required=True)
    c = sp.add_parser("choose"); c.add_argument("--kind", default="summarize", choices=sorted(BASE))
    c.add_argument("--bytes", type=int)
    a = ap.parse_args()
    m, why = choose(a.kind, a.bytes); print(f"{m}\t{why}")
