#!/usr/bin/env python3
"""agyctl install/uninstall/toggle/update checks in a throwaway home (no network, agy not installed). Run: python3 test_agyctl.py"""
import json, os, shutil, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import agyctl as A

A.install_agy = lambda log=print: True    # never download anything in tests
quiet = lambda *a: None
passed = 0

def case(fn):
    global passed
    d = tempfile.mkdtemp()
    os.environ["AGY_DELEGATE_HOME"] = d; os.environ["CLAUDE_CONFIG_DIR"] = os.path.join(d, ".claude")
    try: fn(A.paths()); passed += 1
    finally: shutil.rmtree(d)
    return fn

def put(p, obj, bom=False):
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8-sig" if bom else "utf-8") as f: json.dump(obj, f)

def get(p): return A.load_json(p)

@case
def fresh_install_then_uninstall_leaves_nothing(P):
    A.install(log=quiet)
    c = get(P["claude"])
    assert c["enabledPlugins"][A.PLUG] is True and c["extraKnownMarketplaces"][A.MKT]["source"]["source"] == "directory"
    assert "command(rg)" in get(P["agy"])["permissions"]["allow"]
    A.uninstall(log=quiet)
    assert get(P["claude"]) == {"extraKnownMarketplaces": {}, "enabledPlugins": {}}
    assert get(P["agy"])["permissions"] == {"allow": [], "deny": []} and not os.path.exists(P["state"])

@case
def preexisting_entries_and_disabled_plugin_are_restored(P):
    before = {"theme": "dark", "enabledPlugins": {A.PLUG: False, "x@y": True},
              "extraKnownMarketplaces": {A.MKT: {"source": {"source": "github", "repo": "fork/delegate"}}}}
    put(P["claude"], before)
    put(P["agy"], {"permissions": {"allow": ["command(ls)", "command(make)"]}, "model": "m"})
    A.install(repo="TenTemujin/delegate", log=quiet)
    assert get(P["claude"])["enabledPlugins"][A.PLUG] is True
    A.uninstall(log=quiet)
    assert get(P["claude"]) == before
    a = get(P["agy"])
    assert a["permissions"]["allow"] == ["command(ls)", "command(make)"] and a["model"] == "m"   # user's own rules kept

@case
def reinstall_keeps_original_record(P):
    before = {"enabledPlugins": {A.PLUG: False}}
    put(P["claude"], before)
    A.install(log=quiet); A.install(with_caveman=True, log=quiet); A.toggle("agy-delegate", False, log=quiet); A.install(log=quiet)
    A.uninstall(log=quiet)
    assert get(P["claude"]) == {"enabledPlugins": {A.PLUG: False}, "extraKnownMarketplaces": {}}

@case
def caveman_partial_presence_only_reverts_what_was_added(P):
    mine = {"source": {"source": "github", "repo": "me/caveman-fork"}}
    put(P["claude"], {"extraKnownMarketplaces": {"caveman": mine}})
    A.install(with_caveman=True, log=quiet)
    c = get(P["claude"])
    assert c["extraKnownMarketplaces"]["caveman"] == mine and c["enabledPlugins"][A.CAVEMAN_PLUG] is True
    A.uninstall(log=quiet)
    c = get(P["claude"])
    assert c["extraKnownMarketplaces"] == {"caveman": mine} and A.CAVEMAN_PLUG not in c["enabledPlugins"]

@case
def legacy_rules_removed_unless_kept(P):
    put(P["agy"], {"permissions": {"allow": ["command(find)", "command(sed -n)", "command(ls)"]}})
    A.install(keep_legacy=True, log=quiet)
    assert "command(find)" in get(P["agy"])["permissions"]["allow"]
    assert A.status()["perms"]["legacy"] == ["command(find)", "command(sed -n)"]
    A.install(log=quiet)
    allow = get(P["agy"])["permissions"]["allow"]
    assert "command(find)" not in allow and "command(sed -n)" not in allow and A.status()["perms"] == {"missing": [], "legacy": []}

@case
def v1_state_with_bom_is_migrated(P):
    put(P["state"], {"agy_perms": {"allow": ["command(rg)"], "deny": []}, "caveman": True}, bom=True)
    put(P["claude"], {"enabledPlugins": {A.PLUG: True, A.CAVEMAN_PLUG: True, "keep@me": True},
                      "extraKnownMarketplaces": {A.MKT: {}, "caveman": {}}}, bom=True)
    put(P["agy"], {"permissions": {"allow": ["command(rg)", "command(ls)"]}}, bom=True)
    A.uninstall(log=quiet)
    assert get(P["claude"]) == {"enabledPlugins": {"keep@me": True}, "extraKnownMarketplaces": {}}
    assert get(P["agy"])["permissions"]["allow"] == ["command(ls)"]

@case
def install_without_state_file_uninstall_removes_own_keys(P):
    put(P["claude"], {"enabledPlugins": {A.PLUG: True}, "extraKnownMarketplaces": {A.MKT: {}}})
    A.uninstall(log=quiet)
    assert get(P["claude"]) == {"enabledPlugins": {}, "extraKnownMarketplaces": {}}

@case
def invalid_json_is_never_overwritten(P):
    os.makedirs(os.path.dirname(P["claude"])); open(P["claude"], "w").write("{broken")
    for op in (lambda: A.install(log=quiet), lambda: A.uninstall(log=quiet), lambda: A.toggle("caveman", True, log=quiet)):
        try: op(); raise AssertionError("expected SettingsError")
        except A.SettingsError: pass
    assert open(P["claude"]).read() == "{broken" and not os.path.exists(P["agy"])
    assert A.status()["errors"]

@case
def toggle_and_status(P):
    A.install(log=quiet); A.toggle("agy-delegate", False, log=quiet)
    assert A.status()["plugins"] == {"agy-delegate": "off", "caveman": "absent"}
    assert os.path.exists(P["claude"] + ".agy-bak")
    try: A.toggle("nope", True, log=quiet); raise AssertionError
    except ValueError: pass

@case
def update_check(P):
    cur = A.local_version()
    major = int(cur.split(".")[0])
    assert A.check_update(force=True, fetch=lambda: {"latest": f"{major + 1}.0.0", "url": "u"})["available"]
    assert A.check_update(fetch=lambda: 1 / 0)["latest"] == f"{major + 1}.0.0"            # cached: fetch not called
    assert not A.check_update(force=True, fetch=lambda: {"latest": cur})["available"]
    r = A.check_update(force=True, fetch=lambda: (_ for _ in ()).throw(OSError("offline")))
    assert r["error"] and not r["available"]
    assert not A.check_update(force=True, fetch=lambda: {"latest": None})["available"]    # no release yet
    assert A._vt("v0.10.0") > A._vt("0.9.9")
    assert A.set_config(auto_update=True)["auto_update"] and A.config()["auto_update"]

@case
def packaged_app_update_verifies_checksum(P):
    import hashlib
    name = A.APP_ASSET.get("nt" if os.name == "nt" else sys.platform) or "agy-delegate-windows-x64.exe"
    A.APP_ASSET.setdefault(sys.platform, name)
    d = os.path.dirname(P["state"]); os.makedirs(d, exist_ok=True)
    exe = os.path.join(d, "agy-delegate.exe"); open(exe, "wb").write(b"old")
    blobs = {"u/bin": b"new-binary"}
    good = hashlib.sha256(blobs["u/bin"]).hexdigest()
    real = (A.FROZEN, A._fetch_latest, A._download, sys.executable, A.check_update)
    try:
        A.FROZEN, sys.executable = True, exe
        A.check_update = lambda force=False, fetch=None: {"latest": "9.0.0", "url": "u"}
        A._fetch_latest = lambda: {"latest": "9.0.0", "assets": {name: "u/bin", "SHA256SUMS": "u/sums"}}
        def dl(url, dst): open(dst, "wb").write(blobs[url])
        A._download = dl
        blobs["u/sums"] = ("0" * 64 + "  " + name + "\n").encode()
        assert A.apply_update(log=quiet) is False and open(exe, "rb").read() == b"old"     # bad checksum: untouched
        blobs["u/sums"] = (good + "  " + name + "\n").encode()
        if os.name == "nt":
            assert A.apply_update(log=quiet) is True and open(exe, "rb").read() == b"new-binary" and os.path.exists(exe + ".old")
        A._fetch_latest = lambda: {"latest": "9.0.0", "assets": {name: "u/bin"}}                # no SHA256SUMS: refused
        assert A.apply_update(log=quiet) is False
    finally:
        A.FROZEN, A._fetch_latest, A._download, sys.executable, A.check_update = real

@case
def packaged_app_registers_github_marketplace(P):
    real = A.FROZEN
    try:
        A.FROZEN = True; A.install(skip_agy=True, log=quiet)
        assert get(P["claude"])["extraKnownMarketplaces"][A.MKT]["source"] == {"source": "github", "repo": A.GITHUB_REPO}
    finally: A.FROZEN = real

print(f"agyctl tests: {passed} passed")
