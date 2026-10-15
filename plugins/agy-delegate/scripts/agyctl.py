#!/usr/bin/env python3
"""agy-delegate control: the single implementation behind install.sh, install.ps1, toggle.*, setup.sh and the
control panel (panel.py). Stdlib only, same code on macOS, Linux and Windows.

  agyctl.py install [--repo owner/name] [--with-caveman] [--skip-agy] [--keep-legacy]
  agyctl.py uninstall
  agyctl.py status [--json]
  agyctl.py toggle on|off agy-delegate|caveman
  agyctl.py perms                      # agy permission rules only (used by /agy-delegate:setup)

Reversibility: before changing any settings key, install records once (in ~/.agy-delegate/install-state.json)
whether it existed and its previous value; uninstall restores exactly that. Permission rules are recorded only
when this tool added them. Reinstalling keeps the first (original) record."""
import argparse, json, os, shutil, subprocess, sys, tempfile, urllib.error, urllib.request

MKT, PLUG = "agy-delegate-marketplace", "agy-delegate@agy-delegate-marketplace"
CAVEMAN_MKT, CAVEMAN_PLUG = "caveman", "caveman@caveman"
PLUGINS = {"agy-delegate": PLUG, "caveman": CAVEMAN_PLUG}
LEGACY_RULES = ("command(find)", "command(sed -n)")   # broad prefix rules from <=0.1 installs (find -delete/-exec, sed w)
ALLOW = ["ls", "cat", "head", "tail", "grep", "rg", "wc", "pwd", "git status", "git diff", "git log"]
DENY = ["rm", "sudo", "git push", "git commit", "git reset", "git checkout", "git clean", "curl", "wget"]
WIN_ALLOW = ["type", "dir", "findstr"]
WIN_DENY = ["del", "rmdir", "Remove-Item", "Invoke-WebRequest"]
AGY_INSTALLER = {"nt": "https://antigravity.google/cli/install.ps1", "posix": "https://antigravity.google/cli/install.sh"}
FROZEN = bool(getattr(sys, "frozen", False))   # packaged desktop app: REPO_ROOT is a temporary bundle folder
REPO_ROOT = getattr(sys, "_MEIPASS", None) if FROZEN else     os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))
STATE_VERSION = 2


class SettingsError(Exception):
    """A settings file exists but is not valid JSON: never overwrite it."""


def home():
    return os.environ.get("AGY_DELEGATE_HOME") or os.path.expanduser("~")

def paths():
    claude_dir = os.environ.get("CLAUDE_CONFIG_DIR") or os.path.join(home(), ".claude")
    return {"claude": os.path.join(claude_dir, "settings.json"),
            "agy": os.path.join(home(), ".gemini", "antigravity-cli", "settings.json"),
            "state": os.path.join(home(), ".agy-delegate", "install-state.json")}

def load_json(p):
    if not os.path.exists(p) or not os.path.getsize(p): return {}
    try:
        with open(p, encoding="utf-8-sig") as f: d = json.load(f)   # -sig: PowerShell 5.1 writes a BOM
    except ValueError as e: raise SettingsError(f"{p} is not valid JSON ({e}); fix it by hand, nothing was changed")
    if not isinstance(d, dict): raise SettingsError(f"{p} is not a JSON object; nothing was changed")
    return d

def save_json(p, obj, backup=True):
    os.makedirs(os.path.dirname(p), exist_ok=True)
    if backup and os.path.exists(p): shutil.copy2(p, p + ".agy-bak")
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(p), suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as f: json.dump(obj, f, indent=2); f.write("\n")
    os.replace(tmp, p)   # atomic: a crash never leaves a half-written settings file


# ---- state ---------------------------------------------------------------------------------------------------
def load_state():
    st = load_json(paths()["state"])
    if st.get("version") == STATE_VERSION: return st
    # v1 (<=0.1): {"agy_perms": {...}, "caveman": true}; plugin keys were overwritten without a record -> created by us
    claude = {"extraKnownMarketplaces": {}, "enabledPlugins": {}}
    if st:
        claude["extraKnownMarketplaces"][MKT] = {"existed": False}
        claude["enabledPlugins"][PLUG] = {"existed": False}
    if st.get("caveman"):
        claude["extraKnownMarketplaces"][CAVEMAN_MKT] = {"existed": False}
        claude["enabledPlugins"][CAVEMAN_PLUG] = {"existed": False}
    return {"version": STATE_VERSION, "claude": claude, "agy_perms": st.get("agy_perms", {})}

def _remember(state, section, container, key):
    """Record the pre-install value of container[key] once; later installs keep the original record."""
    rec = state["claude"].setdefault(section, {})
    if key not in rec:
        rec[key] = {"existed": key in container, "prev": container.get(key)} if key in container else {"existed": False}


# ---- agy -----------------------------------------------------------------------------------------------------
def find_agy():
    cands = [shutil.which("agy"), os.path.join(home(), ".local", "bin", "agy")]
    if os.name == "nt": cands.append(os.path.join(os.environ.get("LOCALAPPDATA", ""), "agy", "bin", "agy.exe"))
    return next((c for c in cands if c and os.path.isfile(c)), None)

def agy_version(exe):
    try:
        r = subprocess.run([exe, "--version"], capture_output=True, text=True, timeout=15)
        return (r.stdout or r.stderr).strip().splitlines()[0] if r.returncode == 0 and (r.stdout or r.stderr).strip() else None
    except (OSError, subprocess.SubprocessError): return None

def install_agy(log=print):
    """Download and run Google's official agy installer (it verifies its own download)."""
    if find_agy(): log("agy already installed: " + find_agy()); return True
    url = AGY_INSTALLER["nt" if os.name == "nt" else "posix"]
    log("Installing Antigravity CLI from " + url)
    fd, script = tempfile.mkstemp(suffix=".ps1" if os.name == "nt" else ".sh"); os.close(fd)
    try:
        urllib.request.urlretrieve(url, script)
        cmd = (["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", script] if os.name == "nt" else ["bash", script])
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        for line in (r.stdout + r.stderr).splitlines(): log(line)
        return r.returncode == 0
    finally:
        os.path.exists(script) and os.remove(script)

def wanted_rules():
    a, d = ALLOW + (WIN_ALLOW if os.name == "nt" else []), DENY + (WIN_DENY if os.name == "nt" else [])
    return {"allow": {f"command({c})" for c in a}, "deny": {f"command({c})" for c in d}}

def merge_agy_perms(state, keep_legacy=False, log=print):
    p = paths()["agy"]; cfg = load_json(p); perm = cfg.setdefault("permissions", {})
    rec = state.setdefault("agy_perms", {})
    for k, rules in wanted_rules().items():
        cur = list(perm.get(k, []))
        added = rules - set(cur)
        perm[k] = sorted(set(cur) | rules)
        rec[k] = sorted(set(rec.get(k, [])) | added)
    legacy = [x for x in perm.get("allow", []) if x in LEGACY_RULES]
    if legacy and keep_legacy: log(f"WARNING: broad legacy rules kept (--keep-legacy): {legacy}")
    elif legacy:
        perm["allow"] = [x for x in perm["allow"] if x not in LEGACY_RULES]
        log(f"removed broad legacy rules (they allow find -delete/-exec, sed w): {legacy}")
    save_json(p, cfg); log("agy permissions merged: " + p)


# ---- operations ----------------------------------------------------------------------------------------------
def install(repo="", with_caveman=False, skip_agy=False, keep_legacy=False, log=print):
    P, state = paths(), load_state()
    cfg = load_json(P["claude"])   # parse both files before writing either
    if not skip_agy:
        if not install_agy(log): log("WARNING: agy install failed; plugin is still registered, run 'agy' manually")
        merge_agy_perms(state, keep_legacy, log)
    mk, en = cfg.setdefault("extraKnownMarketplaces", {}), cfg.setdefault("enabledPlugins", {})
    _remember(state, "extraKnownMarketplaces", mk, MKT); _remember(state, "enabledPlugins", en, PLUG)
    if not repo and FROZEN: repo = GITHUB_REPO   # the bundle folder is temporary: register the published repo
    mk[MKT] = {"source": {"source": "github", "repo": repo} if repo else {"source": "directory", "path": REPO_ROOT}}
    en[PLUG] = True
    if with_caveman:   # third-party add-on: add only the entries that are missing; never touch the user's own
        for sec, cont, key, val in (("extraKnownMarketplaces", mk, CAVEMAN_MKT, {"source": {"source": "github", "repo": "JuliusBrussee/caveman"}}),
                                    ("enabledPlugins", en, CAVEMAN_PLUG, True)):
            if key not in cont: _remember(state, sec, cont, key); cont[key] = val
            else: log(f"caveman: {sec}.{key} already present, left as is")
    save_json(P["claude"], cfg); save_json(P["state"], state, backup=False)
    log("Claude Code settings updated: " + P["claude"])
    log("Done. Restart Claude Code, then check /plugin. If agy is not signed in, run 'agy' once in a terminal.")

def uninstall(log=print):
    P, state = paths(), load_state()
    cfg = load_json(P["claude"])
    claude = state["claude"]
    # installs that predate the state file: remove our own two keys (same as the old installers did)
    claude.setdefault("extraKnownMarketplaces", {}).setdefault(MKT, {"existed": False})
    claude.setdefault("enabledPlugins", {}).setdefault(PLUG, {"existed": False})
    if os.path.exists(P["claude"]):
        for sec, recs in claude.items():
            cont = cfg.setdefault(sec, {})
            for key, r in recs.items():
                if r.get("existed"): cont[key] = r.get("prev"); log(f"restored {sec}.{key}")
                elif cont.pop(key, None) is not None: log(f"removed {sec}.{key}")
        save_json(P["claude"], cfg)
    if state.get("agy_perms") and os.path.exists(P["agy"]):
        a = load_json(P["agy"]); perm = a.get("permissions", {})
        for k, mine in state["agy_perms"].items():
            if k in perm: perm[k] = [x for x in perm[k] if x not in set(mine)]
        save_json(P["agy"], a); log("agy permissions added by the installer reverted")
    if os.path.exists(P["state"]): os.remove(P["state"])
    log("(RTK hook, if enabled, must be removed with: rtk init -g --uninstall)")
    log("Removed. Restart Claude Code.")

def toggle(name, on, log=print):
    if name not in PLUGINS: raise ValueError(f"unknown name: {name} (use {', '.join(PLUGINS)})")
    p = paths()["claude"]; cfg = load_json(p)
    cfg.setdefault("enabledPlugins", {})[PLUGINS[name]] = bool(on)
    save_json(p, cfg); log(f"{name}: {'ON' if on else 'OFF'} (restart Claude Code to apply)")

def status():
    P = paths()
    out = {"paths": P, "repo_root": REPO_ROOT, "errors": []}
    try: cfg = load_json(P["claude"])
    except SettingsError as e: cfg = {}; out["errors"].append(str(e))
    en, mk = cfg.get("enabledPlugins", {}), cfg.get("extraKnownMarketplaces", {})
    out["plugins"] = {n: ("on" if en.get(i) else "off" if i in en else "absent") for n, i in PLUGINS.items()}
    out["marketplace"] = mk.get(MKT, {}).get("source") if isinstance(mk.get(MKT), dict) else None
    exe = find_agy(); out["agy"] = {"path": exe, "version": agy_version(exe) if exe else None}
    try: perm = load_json(P["agy"]).get("permissions", {})
    except SettingsError as e: perm = {}; out["errors"].append(str(e))
    w = wanted_rules()
    out["perms"] = {"missing": sorted((w["allow"] - set(perm.get("allow", []))) | (w["deny"] - set(perm.get("deny", [])))),
                    "legacy": [x for x in perm.get("allow", []) if x in LEGACY_RULES]}
    out["installed"] = os.path.exists(P["state"]) or out["plugins"]["agy-delegate"] != "absent"
    return out


# ---- updates -------------------------------------------------------------------------------------------------
GITHUB_REPO = "TenTemujin/delegate"
CHECK_EVERY = 24 * 3600

def local_version():
    try:
        with open(os.path.join(REPO_ROOT, "plugins", "agy-delegate", ".claude-plugin", "plugin.json"), encoding="utf-8") as f:
            return json.load(f)["version"]
    except (OSError, ValueError, KeyError): return "0.0.0"

def _vt(v):
    return tuple(int(x) if x.isdigit() else 0 for x in v.lstrip("v").split("-")[0].split("."))

def config():
    """User options in ~/.agy-delegate/config.json: {"auto_update": bool}."""
    try: return load_json(os.path.join(home(), ".agy-delegate", "config.json"))
    except SettingsError: return {}

def set_config(**kw):
    p = os.path.join(home(), ".agy-delegate", "config.json"); c = config(); c.update(kw); save_json(p, c, backup=False); return c

def check_update(force=False, fetch=None):
    """Latest GitHub release vs local plugin.json; cached for 24 h in ~/.agy-delegate/update-check.json."""
    import time
    cache = os.path.join(home(), ".agy-delegate", "update-check.json")
    try: c = load_json(cache)
    except SettingsError: c = {}
    if force or time.time() - c.get("checked", 0) > CHECK_EVERY or not c.get("latest"):
        fetch = fetch or _fetch_latest
        try: c = {"checked": time.time(), **fetch()}
        except Exception as e:   # offline, rate-limited: report, do not cache the failure
            return {"current": local_version(), "latest": None, "available": False, "error": str(e)}
        save_json(cache, c, backup=False)
    cur = local_version()
    return {"current": cur, "latest": c.get("latest"), "url": c.get("url"), "notes": c.get("notes", ""),
            "available": bool(c.get("latest")) and _vt(c["latest"]) > _vt(cur), "checked": c.get("checked")}

def _fetch_latest():
    req = urllib.request.Request(f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest",
                                 headers={"Accept": "application/vnd.github+json", "User-Agent": "agy-delegate-updater"})
    try:
        with urllib.request.urlopen(req, timeout=8) as r: d = json.load(r)
    except urllib.error.HTTPError as e:
        if e.code == 404: return {"latest": None, "url": None, "notes": "no release published yet"}
        raise
    return {"latest": d["tag_name"].lstrip("v"), "url": d.get("html_url"), "notes": (d.get("body") or "")[:4000],
            "assets": {a["name"]: a["browser_download_url"] for a in d.get("assets", [])}}

def _git(*a):
    return subprocess.run(["git", "-C", REPO_ROOT, *a], capture_output=True, text=True, timeout=120)

APP_ASSET = {"nt": "agy-delegate-windows-x64.exe", "darwin": "agy-delegate-macos.zip"}

def _download(url, dst):
    req = urllib.request.Request(url, headers={"User-Agent": "agy-delegate-updater"})
    with urllib.request.urlopen(req, timeout=60) as r, open(dst, "wb") as f: shutil.copyfileobj(r, f)

def _update_app(log):
    """Packaged app: download the release binary, verify it against the release's SHA256SUMS, swap it in."""
    import hashlib
    u = check_update(force=True); assets = {}
    try: assets = _fetch_latest().get("assets", {})
    except Exception as e: log(f"cannot read the release: {e}"); return False
    name = APP_ASSET.get("nt" if os.name == "nt" else sys.platform)
    if not name or name not in assets or "SHA256SUMS" not in assets:
        log(f"no {name or 'binary'} for this platform in release {u.get('latest')}: {u.get('url')}"); return False
    tmpd = tempfile.mkdtemp(); sums, new = os.path.join(tmpd, "SHA256SUMS"), os.path.join(tmpd, name)
    log(f"downloading {name} {u.get('latest')}..."); _download(assets["SHA256SUMS"], sums); _download(assets[name], new)
    want = next((l.split()[0] for l in open(sums, encoding="utf-8") if l.strip().endswith(name)), None)
    got = hashlib.sha256(open(new, "rb").read()).hexdigest()
    if want != got: log(f"checksum mismatch for {name} (want {want}, got {got}): not installed"); return False
    log("checksum verified (SHA256SUMS)")
    if os.name == "nt":
        exe = sys.executable; old = exe + ".old"
        if os.path.exists(old): os.remove(old)
        os.replace(exe, old); shutil.move(new, exe)   # a running exe can be renamed, not overwritten
        log("installed: restart agy-delegate to use the new version"); return True
    dl = os.path.join(home(), "Downloads", name); shutil.move(new, dl)
    log(f"saved to {dl}: unzip it and replace the app in Applications"); subprocess.run(["open", "-R", dl]); return True

def apply_update(log=print):
    """Fast-forward the local clone (never discards local changes), then refresh the Claude Code marketplace.
    The packaged app updates its own binary instead."""
    if FROZEN: return _update_app(log)
    ok = True
    if shutil.which("git") and os.path.isdir(os.path.join(REPO_ROOT, ".git")):
        if _git("status", "--porcelain").stdout.strip():
            log("local clone has uncommitted changes: not updating it (commit or stash first)"); ok = False
        else:
            r = _git("pull", "--ff-only")
            log((r.stdout + r.stderr).strip() or "git pull done"); ok = r.returncode == 0
    else: log(f"{REPO_ROOT} is not a git clone: download the latest release from https://github.com/{GITHUB_REPO}/releases")
    claude = shutil.which("claude")
    if claude:
        r = subprocess.run([claude, "plugin", "marketplace", "update", MKT], capture_output=True, text=True, timeout=180)
        log((r.stdout + r.stderr).strip() or "marketplace updated")
        if r.returncode: log("marketplace refresh failed: run '/plugin marketplace update " + MKT + "' inside Claude Code"); ok = False
    else: log("run '/plugin marketplace update " + MKT + "' inside Claude Code to load the new version")
    log("Restart Claude Code to apply." if ok else "Update incomplete, see above.")
    return ok


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sp = ap.add_subparsers(dest="cmd", required=True)
    i = sp.add_parser("install"); i.add_argument("--repo", default=""); i.add_argument("--with-caveman", action="store_true")
    i.add_argument("--skip-agy", action="store_true"); i.add_argument("--keep-legacy", action="store_true")
    sp.add_parser("uninstall"); sp.add_parser("perms")
    u = sp.add_parser("update"); u.add_argument("--check", action="store_true", help="only report, change nothing")
    u.add_argument("--auto", choices=["on", "off"], help="let the control panel apply updates on start")
    s = sp.add_parser("status"); s.add_argument("--json", action="store_true")
    t = sp.add_parser("toggle"); t.add_argument("state", choices=["on", "off"]); t.add_argument("name", choices=sorted(PLUGINS))
    a = ap.parse_args(argv)
    try:
        if a.cmd == "install": install(a.repo, a.with_caveman, a.skip_agy, a.keep_legacy)
        elif a.cmd == "uninstall": uninstall()
        elif a.cmd == "perms":
            st = load_state(); merge_agy_perms(st); save_json(paths()["state"], st, backup=False)
        elif a.cmd == "toggle": toggle(a.name, a.state == "on")
        elif a.cmd == "update":
            if a.auto: set_config(auto_update=a.auto == "on"); print("auto-update:", a.auto); return 0
            u = check_update(force=True)
            if u.get("error"): print("update check failed:", u["error"], file=sys.stderr); return 1
            print(f"installed {u['current']}, latest {u['latest'] or 'none published'}")
            if not u["available"]: print("up to date"); return 0
            if a.check: print("update available:", u["url"]); return 0
            return 0 if apply_update() else 1
        else:
            s = status()
            if a.json: print(json.dumps(s, indent=2))
            else:
                for n, v in s["plugins"].items(): print(f"[{v.upper():6}] {n}")
                print("agy:", s["agy"]["path"] or "not found", s["agy"]["version"] or "")
                if s["perms"]["missing"]: print("agy rules missing:", ", ".join(s["perms"]["missing"]))
                if s["perms"]["legacy"]: print("WARNING broad legacy rules:", ", ".join(s["perms"]["legacy"]))
                for e in s["errors"]: print("ERROR:", e)
    except (SettingsError, ValueError) as e:
        print("error:", e, file=sys.stderr); return 1
    return 0

if __name__ == "__main__":
    sys.exit(main())
