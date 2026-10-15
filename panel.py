#!/usr/bin/env python3
"""agy-delegate control panel: install, toggle, update and monitor from the browser. Stdlib only, localhost only.
Run: python3 panel.py [--port 8765] [--no-open]

Every request must carry a Host of 127.0.0.1/localhost on this port (blocks DNS-rebinding pages); every state-changing
request must also carry the per-process token embedded in the page (blocks cross-site requests). Actions run one at a
time in a background job whose log the page polls."""
import json, os, secrets, sys, threading, time, urllib.request, uuid, webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [HERE, os.path.join(HERE, "plugins", "agy-delegate", "scripts"),
                os.path.join(HERE, "plugins", "agy-delegate", "skills", "agy-delegate", "scripts")]
import agyctl, monitor, router   # noqa: E402

TOKEN = secrets.token_urlsafe(24)


class Jobs:
    """At most one mutating action at a time; each keeps its log for the page to poll."""
    def __init__(self): self.lock, self.items, self.current = threading.Lock(), {}, None

    def start(self, name, fn):
        with self.lock:
            if self.current and self.items[self.current]["state"] == "running": return None
            jid = uuid.uuid4().hex[:12]
            job = self.items[jid] = {"id": jid, "name": name, "state": "running", "log": [], "started": time.time()}
            self.current = jid
        def log(line): job["log"].append(str(line))
        def run():
            try: ok = fn(log); job["state"] = "failed" if ok is False else "done"
            except Exception as e: log(f"error: {e}"); job["state"] = "failed"
            job["ended"] = time.time()
        threading.Thread(target=run, daemon=True).start()
        return jid

JOBS = Jobs()


def act_install(p):
    return lambda log: agyctl.install(repo=str(p.get("repo", "")).strip(), with_caveman=bool(p.get("with_caveman")),
                                      skip_agy=bool(p.get("skip_agy")), keep_legacy=bool(p.get("keep_legacy")), log=log)

def act_perms(_):
    def f(log):
        st = agyctl.load_state(); agyctl.merge_agy_perms(st, log=log); agyctl.save_json(agyctl.paths()["state"], st, backup=False)
    return f

def act_check(_):
    def f(log):
        u = agyctl.check_update(force=True)
        log(f"installed {u['current']}, latest {u.get('latest') or 'none published'}" + (f" ({u['error']})" if u.get("error") else ""))
        return not u.get("error")
    return f

def act_refresh_models(log):
    c = router.catalog(refresh=True)
    log(f"refresh failed: {c['error']}" if c["error"] else f"{len(c['models'])} models listed by agy")
    return not c["error"]

ACTIONS = {   # name -> (builder, runs in background job)
    "install": act_install,
    "uninstall": lambda p: (lambda log: agyctl.uninstall(log=log)),
    "install_agy": lambda p: (lambda log: agyctl.install_agy(log=log)),
    "perms": act_perms,
    "update": lambda p: (lambda log: agyctl.apply_update(log=log)),
    "check_update": act_check,
    "refresh_models": lambda p: act_refresh_models,
}


def status():
    s = agyctl.status()
    s["version"] = agyctl.local_version()
    s["update"] = agyctl.check_update()          # cached for 24 h
    s["config"] = agyctl.config()
    return s

def router_view():
    st = router.stats()
    allow = router.config().get("allow_claude_in_agy", True); avail = router.offered()
    return {"choices": {k: dict(zip(("model", "why"), router.choose(k, 100000, st, avail, allow)),
                                ladder=router.ladder(k, avail, allow), about=router.KINDS[k]) for k in router.LADDERS},
            "models": st, "catalog": router.catalog(), "allow_claude": allow, "ladder": router.LADDER, "min_bytes": router.MIN_BYTES,
            "fail_rate": router.FAIL_RATE, "min_calls": router.MIN_CALLS}


class Handler(BaseHTTPRequestHandler):
    server_version = "agy-delegate-panel"

    def _host_ok(self):
        port = self.server.server_address[1]
        return self.headers.get("Host", "") in (f"127.0.0.1:{port}", f"localhost:{port}")

    def _send(self, code, body, ct="application/json"):
        if not isinstance(body, bytes): body = json.dumps(body).encode()
        self.send_response(code); self.send_header("Content-Type", ct); self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff"); self.send_header("Referrer-Policy", "no-referrer")
        if ct.startswith("text/html"):
            self.send_header("Content-Security-Policy", "default-src 'self'; style-src 'self' 'unsafe-inline'; "
                             "script-src 'self' 'unsafe-inline'; img-src 'self' data:; frame-ancestors 'none'")
        self.end_headers(); self.wfile.write(body)

    def do_GET(self):
        if not self._host_ok(): return self._send(403, {"error": "bad host"})
        path = self.path.split("?")[0]
        try:
            if path == "/": return self._send(200, page(), "text/html; charset=utf-8")
            if path in ("/assets/icon-256.png", "/favicon.ico"):
                with open(os.path.join(HERE, "assets", "icon-256.png"), "rb") as f: return self._send(200, f.read(), "image/png")
            if path == "/api/ping": return self._send(200, {"app": "agy-delegate-panel"})
            if path == "/api/stats": return self._send(200, dict(monitor.snapshot(), calls=monitor.recent_calls()))
            if path == "/api/status": return self._send(200, status())
            if path == "/api/router": return self._send(200, router_view())
            if path.startswith("/api/job/"):
                j = JOBS.items.get(path.rsplit("/", 1)[1])
                return self._send(200, j) if j else self._send(404, {"error": "no such job"})
        except agyctl.SettingsError as e: return self._send(409, {"error": str(e)})
        self._send(404, {"error": "not found"})

    def do_POST(self):
        try: n = max(0, int(self.headers.get("Content-Length", 0)))
        except ValueError: n = 0
        if n > 65536: return self._send(413, {"error": "body too large"})
        body = self.rfile.read(n)   # always drain the body first: answering early makes some clients see a reset
        if not self._host_ok(): return self._send(403, {"error": "bad host"})
        if not secrets.compare_digest(self.headers.get("X-Agy-Token", ""), TOKEN): return self._send(403, {"error": "bad token"})
        try:
            p = json.loads(body or b"{}")
            if not isinstance(p, dict): raise ValueError
        except ValueError: return self._send(400, {"error": "bad json"})
        a = p.get("action")
        try:
            if a == "toggle":   # instant actions
                agyctl.toggle(p.get("name", ""), bool(p.get("on")), log=lambda *_: None); return self._send(200, {"ok": True})
            if a == "config":
                lim = p.get("limits")
                kw = {}
                for k in ("auto_update", "allow_claude_in_agy"):
                    if isinstance(p.get(k), bool): kw[k] = p[k]
                if isinstance(lim, dict): kw["limits"] = {k: max(0, int(lim.get(k) or 0)) for k in ("5h", "24h", "7d")}
                return self._send(200, agyctl.set_config(**kw))
        except (ValueError, TypeError, agyctl.SettingsError) as e: return self._send(400, {"error": str(e)})
        if a not in ACTIONS: return self._send(400, {"error": f"unknown action: {a}"})
        jid = JOBS.start(a, ACTIONS[a](p))
        return self._send(202, {"job": jid}) if jid else self._send(409, {"error": "another action is running"})

    def log_message(self, *a): pass


def page():
    with open(os.path.join(HERE, "panel.html"), encoding="utf-8") as f:
        return f.read().replace("__AGY_TOKEN__", TOKEN).encode()

def running(port):
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/ping", timeout=1) as r:
            return json.load(r).get("app") == "agy-delegate-panel"
    except (OSError, ValueError): return False

def maybe_auto_update():
    if not agyctl.config().get("auto_update"): return
    u = agyctl.check_update()
    if agyctl.FROZEN and os.name != "nt": return   # macOS cannot self-replace: never re-download on every start
    if u.get("available"): JOBS.start("auto-update", lambda log: agyctl.apply_update(log=log))

def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    port = int(argv[argv.index("--port") + 1]) if "--port" in argv else int(os.environ.get("AGY_PANEL_PORT", 8765))
    url = f"http://127.0.0.1:{port}"
    if running(port):
        print(f"already running: {url}")
    else:
        srv = ThreadingHTTPServer(("127.0.0.1", port), Handler)
        threading.Thread(target=maybe_auto_update, daemon=True).start()
        print(f"agy-delegate panel: {url}  (Ctrl-C to stop)")
        if "--no-open" not in argv: threading.Timer(0.4, webbrowser.open, (url,)).start()
        try: srv.serve_forever()
        except KeyboardInterrupt: pass
        return
    if "--no-open" not in argv: webbrowser.open(url)

if __name__ == "__main__":
    main()
