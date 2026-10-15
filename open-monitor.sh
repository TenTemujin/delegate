#!/bin/bash
# One-shot launcher: starts the usage monitor if it is not running, then opens it in the browser.
# Usage: ./open-monitor.sh [--no-open] [--stop]      env: AGY_MONITOR_PORT (default 8765)
set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"; PORT="${AGY_MONITOR_PORT:-8765}"; URL="http://127.0.0.1:$PORT"
PIDF="${TMPDIR:-/tmp}/agy-monitor-$PORT.pid"
up() { curl -fs --max-time 1 "$URL/api/stats" >/dev/null 2>&1; }
if [ "${1:-}" = "--stop" ]; then [ -f "$PIDF" ] && kill "$(cat "$PIDF")" 2>/dev/null && rm -f "$PIDF" && echo stopped || echo "not running"; exit 0; fi
PY="$(command -v python3 || command -v python || true)"; [ -n "$PY" ] || { echo "python3 not found" >&2; exit 1; }
if ! up; then
  nohup "$PY" "$DIR/monitor.py" --port "$PORT" >/dev/null 2>&1 & echo $! > "$PIDF"
  for _ in $(seq 20); do up && break; sleep 0.2; done
  up || { echo "monitor failed to start" >&2; exit 1; }
fi
echo "$URL"
[ "${1:-}" = "--no-open" ] && exit 0
if command -v open >/dev/null; then open "$URL"; elif command -v xdg-open >/dev/null; then xdg-open "$URL" >/dev/null 2>&1; fi
