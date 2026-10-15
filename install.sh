#!/bin/bash
# agy-delegate installer for macOS / Linux (Windows: install.ps1). Logic lives in plugins/agy-delegate/scripts/agyctl.py.
# 1) installs agy if missing  2) merges safe permissions into agy settings (removes broad legacy rules)
# 3) registers this repo as a Claude Code marketplace and enables the plugin. Uninstall restores prior values.
# Usage: ./install.sh [--repo owner/name] [--skip-agy] [--with-caveman] [--with-rtk] [--keep-legacy] [--uninstall]
# Optional third-party add-ons (off by default, NOT validated by this project): caveman (terse output plugin), rtk (CLI output compressor).
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PY=""; for c in python3 python; do "$c" -c 'import sys; sys.exit(sys.version_info < (3, 8))' >/dev/null 2>&1 && { PY="$c"; break; }; done
[ -n "$PY" ] || { echo "Python 3.8+ is required (python3 or python)." >&2; exit 1; }
CTL=("$PY" "$ROOT/plugins/agy-delegate/scripts/agyctl.py")
ARGS=(); UNINSTALL=0; WITH_RTK=0
while [ $# -gt 0 ]; do
  case "$1" in
    --repo) ARGS+=(--repo "${2:?--repo needs owner/name}"); shift;;
    --skip-agy|--with-caveman|--keep-legacy) ARGS+=("$1");;
    --with-rtk) WITH_RTK=1;;
    --uninstall) UNINSTALL=1;;
    -h|--help) sed -n '2,6p' "$0"; exit 0;;
    *) echo "unknown option: $1" >&2; exit 2;;
  esac; shift
done
if [ "$UNINSTALL" = 1 ]; then exec "${CTL[@]}" uninstall; fi
"${CTL[@]}" install ${ARGS[@]+"${ARGS[@]}"}
if [ "$WITH_RTK" = 1 ]; then
  if command -v rtk >/dev/null 2>&1; then :
  elif command -v brew >/dev/null 2>&1; then brew install rtk
  else echo "rtk not found: install it from https://github.com/rtk-ai/rtk (brew/winget/curl), then re-run with --with-rtk." >&2; fi
  command -v rtk >/dev/null 2>&1 && rtk init -g   # adds a PreToolUse hook to Claude Code (see rtk docs to uninstall)
fi
echo "Control panel: ./open-panel.sh"
