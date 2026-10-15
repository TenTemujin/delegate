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
    agg, last = {}, 0.0
    for f in glob.glob(os.path.join(CLAUDE, "**", "*.jsonl"), recursive=True):
        try: st = os.stat(f)
        except OSError: continue
        last = max(last, st.st_mtime)
        if now - st.st_mtime > WINDOW: continue
        c = _cache.get(f)
        if not c or c[0] != st.st_mtime or c[1] != st.st_size:
            per = {}
            try:
                for line in open(f, errors="ignore"):
                    if '"usage"' not in line: continue
                    try: e = json.loads(line)
                    except ValueError: continue
                    m = e.get("message")
                    if not isinstance(m, dict) or not m.get("usage") or not m.get("model"): continue
                    ts = e.get("timestamp", "")
                    try: t = calendar.timegm(time.strptime(ts[:19], "%Y-%m-%dT%H:%M:%S"))
                    except ValueError: t = st.st_mtime
                    if now - t > WINDOW: continue
                    u = m["usage"]; r = per.setdefault(m["model"], [0, 0, 0, 0, 0])
                    r[0] += u.get("input_tokens", 0); r[1] += u.get("output_tokens", 0)
                    r[2] += u.get("cache_read_input_tokens", 0); r[3] += u.get("cache_creation_input_tokens", 0); r[4] += 1
            except OSError: pass
            c = _cache[f] = (st.st_mtime, st.st_size, per)
        for k, v in c[2].items():
            a = agg.setdefault(k, [0, 0, 0, 0, 0]); a[:] = [x + y for x, y in zip(a, v)]
    return agg, last

def agy_stats(now):
    open_calls, models = {}, {}
    try:
        for line in open(AGYLOG):
            try: e = json.loads(line)
            except ValueError: continue
            if e["ev"] == "start": open_calls[e["id"]] = e
            else:
                open_calls.pop(e["id"], None)
                if now - e["ts"] <= WINDOW:
                    r = models.setdefault(e["model"], {"calls": 0, "ok": 0, "denied": 0, "out_bytes": 0, "dur_s": 0})
                    r["calls"] += 1; r["ok"] += e["status"] == "ok"; r["denied"] += e["status"] == "denied"
                    r["out_bytes"] += e["out_bytes"]; r["dur_s"] += e["dur_s"]
    except OSError: pass
    running = [c for c in open_calls.values() if now - c["ts"] < 900]  # ignore stale starts (>15 min)
    return models, running

def snapshot():
    now = time.time()
    claude, last = claude_stats(now); agy, running = agy_stats(now)
    return {"now": now, "claude": claude, "claude_active": now - last < 60, "claude_last_s": now - last if last else None,
            "agy": agy, "agy_running": [{"model": c["model"], "age_s": now - c["ts"]} for c in running]}

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
