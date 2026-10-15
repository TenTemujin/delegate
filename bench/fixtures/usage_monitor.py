#!/usr/bin/env python3
"""Local usage widget: Claude Code tokens per model (from session transcripts) + agy helper calls
(from ~/.agy-delegate/usage.jsonl), with a live "operating" indicator.
Data layer of the control panel (panel.py). `python3 monitor.py --once` prints a JSON snapshot."""
import calendar, glob, json, os, sys, time

CLAUDE = os.path.join(os.environ.get("CLAUDE_CONFIG_DIR", os.path.expanduser("~/.claude")), "projects")
AGYLOG = os.environ.get("AGY_DELEGATE_LOG", os.path.expanduser("~/.agy-delegate/usage.jsonl"))
WINDOW = 24 * 3600
_cache = {}  # path -> (mtime, size, {model: [in, out, cache_r, cache_w, msgs]})

def claude_stats(now):
    """Per-model totals for 24 h plus rolling 5 h / 7 d windows (local estimate from transcripts)."""
    agg, last = {}, 0.0
    win = {k: [0, 0, 0, 0, 0] for k in ("5h", "24h", "7d")}  # in, out, cache_read, cache_write, msgs
    spans = {"5h": 5 * 3600, "24h": 24 * 3600, "7d": 7 * 24 * 3600}
    for f in glob.glob(os.path.join(CLAUDE, "**", "*.jsonl"), recursive=True):
        try: st = os.stat(f)
        except OSError: continue
        last = max(last, st.st_mtime)
        if now - st.st_mtime > spans["7d"]: continue
        c = _cache.get(f)
        if not c or c[0] != st.st_mtime or c[1] != st.st_size:
            msgs = []
            try:
                for line in open(f, errors="ignore"):
                    if '"usage"' not in line: continue
                    try: e = json.loads(line)
                    except ValueError: continue
                    m = e.get("message")
                    if not isinstance(m, dict) or not m.get("usage") or not m.get("model"): continue
                    try: t = calendar.timegm(time.strptime(e.get("timestamp", "")[:19], "%Y-%m-%dT%H:%M:%S"))
                    except ValueError: t = st.st_mtime
                    u = m["usage"]
                    msgs.append((t, m["model"], u.get("input_tokens", 0), u.get("output_tokens", 0),
                                 u.get("cache_read_input_tokens", 0), u.get("cache_creation_input_tokens", 0)))
            except OSError: pass
            c = _cache[f] = (st.st_mtime, st.st_size, msgs)
        for t, model, i, o, cr, cw in c[2]:
            age = now - t
            for k, span in spans.items():
                if age <= span:
                    w = win[k]; w[0] += i; w[1] += o; w[2] += cr; w[3] += cw; w[4] += 1
            if age <= spans["24h"]:
                r = agg.setdefault(model, [0, 0, 0, 0, 0])
                r[0] += i; r[1] += o; r[2] += cr; r[3] += cw; r[4] += 1
    return agg, last, win

def saved_tokens(e):
    """Estimated Claude-side tokens avoided by one successful delegation: what Claude would have read
    (src_bytes/4, known only when the caller passed -b) minus what it actually received (prompt + answer, bytes/4).
    Returns None when the source size is unknown: agy's own input tokens include its tool context and internal
    steps, so they are not a proxy for what Claude would have read. Heuristic, never negative."""
    if e.get("status") != "ok": return 0
    if not e.get("src_bytes"): return None
    return max(0, int((e["src_bytes"] - e.get("prompt_bytes", 0) - e.get("out_bytes", 0)) / 4))

def read_log():
    """Valid rows of the usage log; malformed lines (partial writes, other encodings) are skipped."""
    try:
        with open(AGYLOG, encoding="utf-8-sig", errors="replace") as f:
            for line in f:
                try: e = json.loads(line)
                except ValueError: continue
                if isinstance(e, dict) and e.get("ev") in ("start", "end") and "id" in e and isinstance(e.get("ts"), (int, float)): yield e
    except OSError: return

def agy_stats(now):
    open_calls, models = {}, {}
    saved = {"5h": 0, "24h": 0, "7d": 0}; unestimated = {"5h": 0, "24h": 0, "7d": 0}
    spans = {"5h": 5 * 3600, "24h": 24 * 3600, "7d": 7 * 24 * 3600}
    for e in read_log():
        if e["ev"] == "start": open_calls[e["id"]] = e; continue
        open_calls.pop(e["id"], None)
        sv = saved_tokens(e)
        for k, span in spans.items():
            if now - e["ts"] <= span:
                if sv is None: unestimated[k] += 1
                else: saved[k] += sv
        if now - e["ts"] <= WINDOW:
            st = e.get("status", "error")
            r = models.setdefault(e.get("model", "?"), {"calls": 0, "ok": 0, "denied": 0, "failed": 0, "out_bytes": 0, "dur_s": 0, "in_tokens": 0, "out_tokens": 0})
            r["calls"] += 1; r["ok"] += st == "ok"; r["denied"] += st == "denied"
            r["failed"] += st not in ("ok", "denied")   # error / empty
            r["out_bytes"] += e.get("out_bytes", 0); r["dur_s"] += e.get("dur_s", 0)
            r["in_tokens"] += e.get("in_tokens", 0); r["out_tokens"] += e.get("out_tokens", 0)
    running = [c for c in open_calls.values() if now - c["ts"] < 900]  # ignore stale starts (>15 min)
    return models, running, saved, unestimated

def recent_calls(n=40):
    """Last n finished calls, newest first, with the per-call saving estimate (None = not estimated)."""
    ends = [e for e in read_log() if e["ev"] == "end"][-n:]
    keys = ("ts", "model", "status", "dur_s", "in_tokens", "out_tokens", "src_bytes", "out_bytes")
    return [dict({k: e.get(k) for k in keys}, saved=saved_tokens(e)) for e in reversed(ends)]

def limits():
    """Optional quotas in new tokens (in+out+cache write) per window. Env AGY_MONITOR_LIMIT_5H / _24H / _7D wins over
    "limits" in ~/.agy-delegate/config.json (set from the control panel)."""
    try:
        with open(os.path.join(os.environ.get("AGY_DELEGATE_HOME") or os.path.expanduser("~"), ".agy-delegate", "config.json"), encoding="utf-8-sig") as f:
            cfg = json.load(f).get("limits") or {}
    except (OSError, ValueError, AttributeError): cfg = {}
    def get(k, env):
        for v in (os.environ.get(env), cfg.get(k) if isinstance(cfg, dict) else None):
            try:
                if v not in (None, ""): return max(0, int(v))
            except (TypeError, ValueError): return 0
        return 0
    return {"5h": get("5h", "AGY_MONITOR_LIMIT_5H"), "24h": get("24h", "AGY_MONITOR_LIMIT_24H"), "7d": get("7d", "AGY_MONITOR_LIMIT_7D")}

def snapshot():
    now = time.time()
    claude, last, win = claude_stats(now); agy, running, saved, unest = agy_stats(now)
    return {"now": now, "claude": claude, "windows": win,
            "limits": limits(),
            "claude_active": now - last < 60, "claude_last_s": now - last if last else None,
            "agy": agy, "saved": saved, "saved_unestimated": unest, "agy_running": [{"model": c["model"], "age_s": now - c["ts"]} for c in running]}

if __name__ == "__main__":
    if "--once" in sys.argv: print(json.dumps(snapshot(), indent=2)); sys.exit()
    import panel; panel.main(sys.argv[1:] + ["--no-open"])   # the monitor now lives in the control panel
