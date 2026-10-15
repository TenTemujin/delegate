#!/bin/bash
# Enable/disable agy-delegate add-ons in Claude Code (macOS/Linux). Windows: toggle.ps1.
# Usage: ./toggle.sh              interactive menu (press a number to flip, q to quit)
#        ./toggle.sh status | on <name> | off <name>      names: agy-delegate, caveman
# Edits enabledPlugins in settings.json (same switch as /plugin). Restart Claude Code to apply.
set -euo pipefail
command -v python3 >/dev/null || { echo "python3 required" >&2; exit 1; }
S="${CLAUDE_CONFIG_DIR:-$HOME/.claude}/settings.json"
py() { python3 - "$S" "$@" <<'PY'
import json, os, sys
p, cmd = sys.argv[1], sys.argv[2]
ids = {"agy-delegate": "agy-delegate@agy-delegate-marketplace", "caveman": "caveman@caveman"}
cfg = json.load(open(p)) if os.path.exists(p) and os.path.getsize(p) else {}
en = cfg.setdefault("enabledPlugins", {})
def state(n): return "ON " if en.get(ids[n]) else ("OFF" if ids[n] in en else "n/a")
if cmd in ("on", "off"):
    n = sys.argv[3]
    if n not in ids: sys.exit(f"unknown name: {n} (use {', '.join(ids)})")
    en[ids[n]] = cmd == "on"
    if os.path.exists(p): open(p + ".toggle-bak", "w").write(open(p).read())
    json.dump(cfg, open(p, "w"), indent=2)
for i, n in enumerate(ids, 1): print(f"{i}) [{state(n)}] {n}")
PY
}
names=(agy-delegate caveman)
case "${1:-}" in
  status) py status;;
  on|off) py "$1" "${2:?name required}";;
  "") while true; do
        echo; echo "agy-delegate add-ons  ($S)"; py status
        printf "number to toggle, q to quit: "; read -r k
        case "$k" in q|Q) break;; 1|2) n="${names[$((k-1))]}"
          cur=$(py status | sed -n "${k}p" | grep -c '\[ON ' || true)
          if [ "$cur" = 1 ]; then py off "$n" >/dev/null; else py on "$n" >/dev/null; fi;; esac
      done; echo "Restart Claude Code to apply.";;
  *) sed -n '2,5p' "$0"; exit 2;;
esac
