#!/bin/bash
# agy-delegate installer for macOS / Linux (Windows: install.ps1).
# 1) installs agy if missing  2) merges safe permissions into agy settings
# 3) registers this repo as a Claude Code marketplace and enables the plugin.
# Usage: ./install.sh [--repo owner/name] [--skip-agy] [--with-caveman] [--with-rtk] [--uninstall]
# Optional third-party add-ons (off by default, NOT validated by this project): caveman (terse output plugin), rtk (CLI output compressor).
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MKT="agy-delegate-marketplace"; PLUG="agy-delegate@$MKT"
REPO=""; SKIP_AGY=0; UNINSTALL=0; WITH_CAVEMAN=0; WITH_RTK=0
while [ $# -gt 0 ]; do
  case "$1" in
    --repo) REPO="${2:?--repo needs owner/name}"; shift;;
    --skip-agy) SKIP_AGY=1;;
    --with-caveman) WITH_CAVEMAN=1;;
    --with-rtk) WITH_RTK=1;;
    --uninstall) UNINSTALL=1;;
    -h|--help) sed -n '2,6p' "$0"; exit 0;;
    *) echo "unknown option: $1" >&2; exit 2;;
  esac; shift
done
command -v python3 >/dev/null || { echo "python3 is required (used to merge JSON settings)." >&2; exit 1; }

CLAUDE_SETTINGS="${CLAUDE_CONFIG_DIR:-$HOME/.claude}/settings.json"
AGY_SETTINGS="$HOME/.gemini/antigravity-cli/settings.json"
STATE="$HOME/.agy-delegate/install-state.json"   # records exactly what this installer added, so uninstall reverts only that

merge_claude() { # $1 = install|uninstall
  mkdir -p "$(dirname "$CLAUDE_SETTINGS")"
  [ -f "$CLAUDE_SETTINGS" ] && cp "$CLAUDE_SETTINGS" "$CLAUDE_SETTINGS.agy-bak"
  python3 - "$CLAUDE_SETTINGS" "$1" "$MKT" "$PLUG" "$ROOT" "$REPO" "$WITH_CAVEMAN" "$STATE" <<'PY'
import json, os, sys
p, action, mkt, plug, root, repo, cav, state_p = sys.argv[1:9]
state = json.load(open(state_p)) if os.path.exists(state_p) else {}
cfg = json.load(open(p)) if os.path.exists(p) and os.path.getsize(p) else {}
mk, en = cfg.setdefault("extraKnownMarketplaces", {}), cfg.setdefault("enabledPlugins", {})
if action == "install":
    mk[mkt] = {"source": {"source": "github", "repo": repo} if repo else {"source": "directory", "path": root}}
    en[plug] = True
    if cav == "1":
        if "caveman" not in mk and "caveman@caveman" not in en: state["caveman"] = True   # ours only if absent before
        mk.setdefault("caveman", {"source": {"source": "github", "repo": "JuliusBrussee/caveman"}})
        en.setdefault("caveman@caveman", True)
else:
    mk.pop(mkt, None); en.pop(plug, None)
    if state.pop("caveman", False):
        mk.pop("caveman", None); en.pop("caveman@caveman", None)
    else:
        print("caveman left untouched (not installed by this installer)")
os.makedirs(os.path.dirname(state_p), exist_ok=True)
json.dump(state, open(state_p, "w"), indent=2)
json.dump(cfg, open(p, "w"), indent=2)
print(f"{action}: {p}")
PY
}

if [ "$UNINSTALL" = 1 ]; then
  merge_claude uninstall
  python3 - "$AGY_SETTINGS" "$STATE" <<'PY'
import json, os, sys
p, sp = sys.argv[1:3]
st = json.load(open(sp)) if os.path.exists(sp) else {}
if os.path.exists(p) and st.get("agy_perms"):
    cfg = json.load(open(p)); perm = cfg.get("permissions", {})
    for k in ("allow", "deny"):
        if k in perm: perm[k] = [x for x in perm[k] if x not in set(st["agy_perms"].get(k, []))]
    json.dump(cfg, open(p, "w"), indent=2); print("agy permissions added by installer reverted")
os.path.exists(sp) and os.remove(sp)
PY
 echo "(RTK hook, if enabled, must be removed with: rtk init -g --uninstall)"; echo "Removed. Restart Claude Code."; exit 0; fi

if [ "$SKIP_AGY" = 0 ]; then
  if ! command -v agy >/dev/null 2>&1 && [ ! -x "$HOME/.local/bin/agy" ]; then
    echo "Installing Antigravity CLI (official installer)..."
    T="$(mktemp)"; curl -fsSL https://antigravity.google/cli/install.sh -o "$T"; bash "$T"; rm -f "$T"
  fi
  mkdir -p "$(dirname "$AGY_SETTINGS")"
  [ -f "$AGY_SETTINGS" ] && cp "$AGY_SETTINGS" "$AGY_SETTINGS.bak"
  python3 - "$AGY_SETTINGS" <<'PY'
import json, os, sys
p = sys.argv[1]
cfg = json.load(open(p)) if os.path.exists(p) and os.path.getsize(p) else {}
perm = cfg.setdefault("permissions", {})
sp = os.path.expanduser("~/.agy-delegate/install-state.json")
state = json.load(open(sp)) if os.path.exists(sp) else {}
allow = ["ls","cat","head","tail","grep","rg","wc","pwd","git status","git diff","git log"]
deny = ["rm","sudo","git push","git commit","git reset","git checkout","git clean","curl","wget"]
for k, v in (("allow", allow), ("deny", deny)):
    new = {f"command({c})" for c in v}
    added = new - set(perm.get(k, []))
    perm[k] = sorted(set(perm.get(k, [])) | new)
    rec = state.setdefault("agy_perms", {}).setdefault(k, [])
    state["agy_perms"][k] = sorted(set(rec) | added)
json.dump(cfg, open(p, "w"), indent=2)
os.makedirs(os.path.dirname(sp), exist_ok=True); json.dump(state, open(sp, "w"), indent=2)
legacy = [x for x in perm.get("allow", []) if x in ("command(find)", "command(sed -n)")]
if legacy: print("WARNING: remove broad rules from an older install (they allow find -delete/-exec, sed w):", legacy)
print("agy permissions merged:", p)
PY
fi

merge_claude install
if [ "$WITH_RTK" = 1 ]; then
  if command -v rtk >/dev/null 2>&1; then :
  elif command -v brew >/dev/null 2>&1; then brew install rtk
  else echo "rtk not found: install it from https://github.com/rtk-ai/rtk (brew/winget/curl), then re-run with --with-rtk." >&2; fi
  command -v rtk >/dev/null 2>&1 && rtk init -g   # adds a PreToolUse hook to Claude Code (see rtk docs to uninstall)
fi
echo
echo "Done. Restart Claude Code, then check: /plugin  (agy-delegate should be enabled)."
echo "If agy is not signed in, run 'agy' once in a terminal."
