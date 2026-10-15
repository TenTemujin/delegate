#!/bin/bash
# Installs agy (if missing) and merges safe permission rules into ~/.gemini/antigravity-cli/settings.json.
# Existing settings are preserved; a .bak copy is made. Does NOT log you in (run `agy` once if needed).
set -euo pipefail
if ! command -v agy >/dev/null 2>&1 && [ ! -x "$HOME/.local/bin/agy" ]; then
  echo "Installing Antigravity CLI (official installer, SHA512-verified by the installer)..."
  curl -fsSL https://antigravity.google/cli/install.sh -o /tmp/agy_install.sh
  echo "Installer saved at /tmp/agy_install.sh — review it if you wish. Running..."
  bash /tmp/agy_install.sh
fi
S="$HOME/.gemini/antigravity-cli/settings.json"; mkdir -p "$(dirname "$S")"
[ -f "$S" ] && cp "$S" "$S.bak"
python3 - "$S" <<'PY'
import json, os, sys
p = sys.argv[1]
cfg = json.load(open(p)) if os.path.exists(p) and os.path.getsize(p) else {}
perm = cfg.setdefault("permissions", {})
allow = ["command(ls)","command(cat)","command(head)","command(tail)","command(grep)","command(rg)",
         "command(find)","command(wc)","command(sed -n)","command(pwd)","command(git status)",
         "command(git diff)","command(git log)"]
deny = ["command(rm)","command(sudo)","command(git push)","command(git commit)","command(git reset)",
        "command(git checkout)","command(git clean)","command(curl)","command(wget)"]
for k, v in (("allow", allow), ("deny", deny)):
    perm[k] = sorted(set(perm.get(k, [])) | set(v))
json.dump(cfg, open(p, "w"), indent=2)
print("Permissions merged into", p)
PY
echo "Done. Check: $(command -v agy || echo $HOME/.local/bin/agy) --version"
echo "If not logged in, run 'agy' once (opens browser sign-in)."
