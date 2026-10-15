#!/usr/bin/env python3
"""Local usage widget: Claude Code tokens per model (from session transcripts) + agy helper calls
(from ~/.agy-delegate/usage.jsonl), with a live "operating" indicator.
Run: python3 monitor.py [--port 8765]   then open http://127.0.0.1:8765  (stdlib only, localhost only)."""
import calendar, glob, json, os, sys, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

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

AGY_BASE_TOKENS = 12700  # agy's fixed system/tool overhead per call (measured: a 1-word prompt reports ~12.7k input tokens)

def saved_tokens(e):
    """Estimated Claude-side tokens avoided by one successful delegation: what Claude would have read
    (src_bytes/4, or agy input tokens beyond its fixed overhead when the caller gave no -b) minus what
    it actually received (prompt + answer, bytes/4). Heuristic, never negative."""
    if e.get("status") != "ok": return 0
    src = e.get("src_bytes", 0) / 4 or max(0, e.get("in_tokens", 0) - AGY_BASE_TOKENS)
    return max(0, int(src - (e.get("prompt_bytes", 0) + e.get("out_bytes", 0)) / 4))

def agy_stats(now):
    open_calls, models = {}, {}
    saved = {"5h": 0, "24h": 0, "7d": 0}
    spans = {"5h": 5 * 3600, "24h": 24 * 3600, "7d": 7 * 24 * 3600}
    try:
        for line in open(AGYLOG):
            try: e = json.loads(line)
            except ValueError: continue
            if e["ev"] == "start": open_calls[e["id"]] = e
            else:
                open_calls.pop(e["id"], None)
                sv = saved_tokens(e)
                for k, span in spans.items():
                    if now - e["ts"] <= span: saved[k] += sv
                if now - e["ts"] <= WINDOW:
                    r = models.setdefault(e["model"], {"calls": 0, "ok": 0, "denied": 0, "failed": 0, "out_bytes": 0, "dur_s": 0, "in_tokens": 0, "out_tokens": 0})
                    r["calls"] += 1; r["ok"] += e["status"] == "ok"; r["denied"] += e["status"] == "denied"
                    r["failed"] += e["status"] not in ("ok", "denied")   # error / empty
                    r["out_bytes"] += e["out_bytes"]; r["dur_s"] += e["dur_s"]
                    r["in_tokens"] += e.get("in_tokens", 0); r["out_tokens"] += e.get("out_tokens", 0)
    except OSError: pass
    running = [c for c in open_calls.values() if now - c["ts"] < 900]  # ignore stale starts (>15 min)
    return models, running, saved

def limits():
    """Optional quotas in new tokens (in+out+cache write) per window: AGY_MONITOR_LIMIT_5H / _24H (daily) / _7D (weekly)."""
    def env(k):
        try: return max(0, int(os.environ.get(k, 0)))
        except ValueError: return 0
    return {"5h": env("AGY_MONITOR_LIMIT_5H"), "24h": env("AGY_MONITOR_LIMIT_24H"), "7d": env("AGY_MONITOR_LIMIT_7D")}

def snapshot():
    now = time.time()
    claude, last, win = claude_stats(now); agy, running, saved = agy_stats(now)
    return {"now": now, "claude": claude, "windows": win,
            "limits": limits(),
            "claude_active": now - last < 60, "claude_last_s": now - last if last else None,
            "agy": agy, "saved": saved, "agy_running": [{"model": c["model"], "age_s": now - c["ts"]} for c in running]}

PAGE = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "monitor.html")).read() if os.path.exists(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "monitor.html")) else "monitor.html missing"

class H(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path.startswith("/api/stats"): body, ct = json.dumps(snapshot()).encode(), "application/json"
        else: body, ct = PAGE.encode(), "text/html; charset=utf-8"
        self.send_response(200); self.send_header("Content-Type", ct); self.send_header("Cache-Control", "no-store")
        self.end_headers(); self.wfile.write(body)
    def log_message(self, *a): pass

if __name__ == "__main__":
    port = int(sys.argv[sys.argv.index("--port") + 1]) if "--port" in sys.argv else 8765
    if "--once" in sys.argv: print(json.dumps(snapshot(), indent=2)); sys.exit()
    print(f"agy-delegate monitor: http://127.0.0.1:{port}  (Ctrl-C to stop)")
    ThreadingHTTPServer(("127.0.0.1", port), H).serve_forever()
