#!/usr/bin/env python3
"""Control panel checks against a real server on an ephemeral port, in a throwaway home (no network). Run: python3 test_panel.py"""
import http.client, json, os, shutil, sys, tempfile, threading, time
d = tempfile.mkdtemp()
os.environ.update(AGY_DELEGATE_HOME=d, CLAUDE_CONFIG_DIR=os.path.join(d, ".claude"), AGY_DELEGATE_LOG=os.path.join(d, "u.jsonl"))
for k in ("AGY_MONITOR_LIMIT_5H", "AGY_MONITOR_LIMIT_24H", "AGY_MONITOR_LIMIT_7D"): os.environ.pop(k, None)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import panel as P
from http.server import ThreadingHTTPServer
P.agyctl.install_agy = lambda log=print: True                                         # never download in tests
P.agyctl.check_update = lambda force=False, fetch=None: {"current": "x", "latest": None, "available": False}
P.router.catalog = lambda refresh=False: {"models": [{"id": m, "name": m, "role": "ladder", "note": "", "available": True} for m in P.router.LADDER], "fetched": 1, "error": None}
P.router.offered = lambda fetch=None: None
srv = ThreadingHTTPServer(("127.0.0.1", 0), P.Handler); port = srv.server_address[1]
threading.Thread(target=srv.serve_forever, daemon=True).start()

def req(method, path, body=None, host=None, token=None, raw=None):
    c = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    h = {"Host": host or f"127.0.0.1:{port}", "Content-Type": "application/json"}
    if token: h["X-Agy-Token"] = token
    c.request(method, path, raw if raw is not None else (json.dumps(body) if body is not None else None), h)
    r = c.getresponse(); data = r.read(); c.close()
    try: data = json.loads(data)
    except ValueError: data = data.decode()
    return r.status, data

def wait(jid):
    for _ in range(100):
        s, j = req("GET", f"/api/job/{jid}")
        if j["state"] != "running": return j
        time.sleep(0.05)
    raise AssertionError("job did not finish")

checks = 0
def ok(cond, msg):
    global checks
    assert cond, msg; checks += 1

try:
    s, page = req("GET", "/")
    ok(s == 200 and P.TOKEN in page and "__AGY_TOKEN__" not in page, "page served with token")
    ok(req("GET", "/", host="evil.example:80")[0] == 403, "DNS-rebinding host rejected")
    ok(req("GET", "/api/stats", host=f"localhost:{port}")[0] == 200, "localhost host accepted")
    ok(req("POST", "/api/action", {"action": "perms"})[0] == 403, "POST without token rejected")
    ok(req("POST", "/api/action", {"action": "perms"}, token="wrong")[0] == 403, "POST with wrong token rejected")
    ok(req("POST", "/api/action", {"action": "perms"}, token=P.TOKEN, host="evil.example")[0] == 403, "token + bad host rejected")
    ok(req("POST", "/api/action", raw="{nope", token=P.TOKEN)[0] == 400, "bad json rejected")
    ok(req("POST", "/api/action", {"action": "rm -rf"}, token=P.TOKEN)[0] == 400, "unknown action rejected")
    c = http.client.HTTPConnection("127.0.0.1", port, timeout=10); c.request("GET", "/assets/icon-256.png", headers={"Host": f"127.0.0.1:{port}"})
    r = c.getresponse(); body = r.read(); c.close()
    ok(r.status == 200 and r.getheader("Content-Type") == "image/png" and body[1:4] == b"PNG", "logo served")
    ok(req("GET", "/assets/../panel.py")[0] == 404 and req("GET", "/assets/logo.svg")[0] == 404, "only whitelisted assets")
    ok(req("GET", "/api/job/nope")[0] == 404 and req("GET", "/nope")[0] == 404, "404s")

    s, st = req("GET", "/api/status")
    ok(s == 200 and st["plugins"] == {"agy-delegate": "absent", "caveman": "absent"} and not st["installed"], "fresh status")

    s, r = req("POST", "/api/action", {"action": "install", "with_caveman": True}, token=P.TOKEN)
    ok(s == 202, "install accepted"); j = wait(r["job"])
    ok(j["state"] == "done" and any("Claude Code settings updated" in l for l in j["log"]), "install job done with log")
    s, st = req("GET", "/api/status")
    ok(st["installed"] and st["plugins"] == {"agy-delegate": "on", "caveman": "on"} and st["perms"]["missing"] == [], "installed status")

    ok(req("POST", "/api/action", {"action": "toggle", "name": "caveman", "on": False}, token=P.TOKEN)[0] == 200, "toggle")
    ok(req("GET", "/api/status")[1]["plugins"]["caveman"] == "off", "toggle applied")
    ok(req("POST", "/api/action", {"action": "toggle", "name": "x", "on": True}, token=P.TOKEN)[0] == 400, "toggle unknown name")

    s, c = req("POST", "/api/action", {"action": "config", "auto_update": True, "limits": {"5h": "1000", "24h": "", "7d": -5}}, token=P.TOKEN)
    ok(s == 200 and c["auto_update"] and c["limits"] == {"5h": 1000, "24h": 0, "7d": 0}, "config saved and sanitized")
    ok(req("GET", "/api/stats")[1]["limits"]["5h"] == 1000, "monitor reads limits from config")
    ok(req("POST", "/api/action", {"action": "config", "limits": {"5h": "abc"}}, token=P.TOKEN)[0] == 400, "bad limit rejected")

    s, r = req("GET", "/api/router")
    ok(s == 200 and set(r["choices"]) == set(P.router.LADDERS) and r["choices"]["reason"]["model"].endswith("high")
       and r["choices"]["extract"]["ladder"][0] == r["choices"]["extract"]["model"] and len(r["catalog"]["models"]) == len(P.router.LADDER), "router view with ladders")
    s, c = req("POST", "/api/action", {"action": "config", "allow_claude_in_agy": False}, token=P.TOKEN)
    lads = req("GET", "/api/router")[1]["choices"]
    ok(s == 200 and not any(m.startswith("claude-") for c in lads.values() for m in c["ladder"]), "Claude-in-agy switch applied")

    # one action at a time
    gate = threading.Event()
    P.ACTIONS["slow"] = lambda p: (lambda log: gate.wait(5))
    s1, r1 = req("POST", "/api/action", {"action": "slow"}, token=P.TOKEN)
    s2, _ = req("POST", "/api/action", {"action": "perms"}, token=P.TOKEN)
    gate.set(); wait(r1["job"])
    ok(s1 == 202 and s2 == 409, "second action refused while one runs")

    s, r = req("POST", "/api/action", {"action": "uninstall"}, token=P.TOKEN); j = wait(r["job"])
    s, st = req("GET", "/api/status")
    ok(j["state"] == "done" and st["plugins"] == {"agy-delegate": "absent", "caveman": "absent"} and not st["installed"], "uninstall via panel")

    # a broken settings file is reported, never overwritten
    open(os.path.join(d, ".claude", "settings.json"), "w").write("{broken")
    s, st = req("GET", "/api/status"); ok(st["errors"], "broken settings reported")
    ok(req("POST", "/api/action", {"action": "toggle", "name": "caveman", "on": True}, token=P.TOKEN)[0] == 400, "toggle refuses broken file")
    ok(open(os.path.join(d, ".claude", "settings.json")).read() == "{broken", "broken file untouched")
finally:
    srv.shutdown(); shutil.rmtree(d, ignore_errors=True)
print(f"panel tests: {checks} passed")
