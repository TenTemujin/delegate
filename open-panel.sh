#!/bin/bash
# One-shot launcher: starts the control panel if it is not running, then opens it in the browser.
# Usage: ./open-panel.sh [--no-open] [--stop]      env: AGY_PANEL_PORT (default 8765)
set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"; PORT="${AGY_PANEL_PORT:-8765}"; URL="http://127.0.0.1:$PORT"
PIDF="${TMPDIR:-/tmp}/agy-panel-$PORT.pid"
up() { curl -fs --max-time 1 "$URL/api/ping" 2>/dev/null | grep -q agy-delegate-panel; }
if [ "${1:-}" = "--stop" ]; then [ -f "$PIDF" ] && kill "$(cat "$PIDF")" 2>/dev/null && rm -f "$PIDF" && echo stopped || echo "not running"; exit 0; fi
PY=""; for c in python3 python; do "$c" -c 'import sys; sys.exit(sys.version_info < (3, 8))' >/dev/null 2>&1 && { PY="$c"; break; }; done
[ -n "$PY" ] || { echo "Python 3.8+ not found" >&2; exit 1; }
if ! up; then
  nohup "$PY" "$DIR/panel.py" --port "$PORT" --no-open >/dev/null 2>&1 & echo $! > "$PIDF"
  for _ in $(seq 25); do up && break; sleep 0.2; done
  up || { echo "panel failed to start" >&2; exit 1; }
fi
echo "$URL"
[ "${1:-}" = "--no-open" ] && exit 0
if command -v open >/dev/null; then open "$URL"; elif command -v xdg-open >/dev/null; then xdg-open "$URL" >/dev/null 2>&1; fi
