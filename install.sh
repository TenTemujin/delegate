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

merge_claude() { # $1 = install|uninstall
  mkdir -p "$(dirname "$CLAUDE_SETTINGS")"
  [ -f "$CLAUDE_SETTINGS" ] && cp "$CLAUDE_SETTINGS" "$CLAUDE_SETTINGS.agy-bak"
  python3 - "$CLAUDE_SETTINGS" "$1" "$MKT" "$PLUG" "$ROOT" "$REPO" "$WITH_CAVEMAN" <<'PY'
import json, os, sys
p, action, mkt, plug, root, repo, cav = sys.argv[1:8]
cfg = json.load(open(p)) if os.path.exists(p) and os.path.getsize(p) else {}
mk, en = cfg.setdefault("extraKnownMarketplaces", {}), cfg.setdefault("enabledPlugins", {})
if action == "install":
    mk[mkt] = {"source": {"source": "github", "repo": repo} if repo else {"source": "directory", "path": root}}
    en[plug] = True
    if cav == "1":
        mk["caveman"] = {"source": {"source": "github", "repo": "JuliusBrussee/caveman"}}
        en["caveman@caveman"] = True
else:
    mk.pop(mkt, None); en.pop(plug, None)
    mk.pop("caveman", None); en.pop("caveman@caveman", None)
json.dump(cfg, open(p, "w"), indent=2)
print(f"{action}: {p}")
PY
}

if [ "$UNINSTALL" = 1 ]; then merge_claude uninstall; echo "Removed. Restart Claude Code."; exit 0; fi

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
allow = ["ls","cat","head","tail","grep","rg","find","wc","sed -n","pwd","git status","git diff","git log"]
deny = ["rm","sudo","git push","git commit","git reset","git checkout","git clean","curl","wget"]
for k, v in (("allow", allow), ("deny", deny)):
    perm[k] = sorted(set(perm.get(k, [])) | {f"command({c})" for c in v})
json.dump(cfg, open(p, "w"), indent=2)
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
