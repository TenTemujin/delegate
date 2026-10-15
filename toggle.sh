#!/bin/bash
# Enable/disable agy-delegate add-ons in Claude Code (macOS/Linux). Windows: toggle.ps1. The control panel does the same.
# Usage: ./toggle.sh              interactive menu (press a number to flip, q to quit)
#        ./toggle.sh status | on <name> | off <name>      names: agy-delegate, caveman
# Edits enabledPlugins in settings.json (same switch as /plugin). Restart Claude Code to apply.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PY=""; for c in python3 python; do "$c" -c 'import sys; sys.exit(sys.version_info < (3, 8))' >/dev/null 2>&1 && { PY="$c"; break; }; done
[ -n "$PY" ] || { echo "Python 3.8+ required" >&2; exit 1; }
ctl() { "$PY" "$ROOT/plugins/agy-delegate/scripts/agyctl.py" "$@"; }
names=(agy-delegate caveman)
case "${1:-}" in
  status) ctl status;;
  on|off) ctl toggle "$1" "${2:?name required}" && ctl status;;
  "") while true; do
        echo; ctl status | head -2 | nl -w1 -s') '
        printf "number to toggle, q to quit: "; read -r k
        case "$k" in q|Q) break;; 1|2) n="${names[$((k-1))]}"
          if ctl status | sed -n "${k}p" | grep -q '\[ON'; then ctl toggle off "$n"; else ctl toggle on "$n"; fi;; esac
      done;;
  *) sed -n '2,5p' "$0"; exit 2;;
esac
