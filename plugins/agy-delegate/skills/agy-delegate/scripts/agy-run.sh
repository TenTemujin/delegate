#!/bin/bash
# Claude (controller) -> Antigravity CLI (helper). Read-only by default.
# Usage: agy-run.sh [-w] [-m model] [-t timeout] [-d dir] "prompt"
#   -w  allow edits (accept-edits); default is plan (read-only)
set -euo pipefail
AGY="$(command -v agy || true)"
[ -x "$AGY" ] || AGY="$HOME/.local/bin/agy"
[ -x "$AGY" ] || { echo "agy not found. Run /agy-delegate:setup" >&2; exit 127; }
MODEL="${AGY_DELEGATE_MODEL:-gemini-3.8-flash-medium}"; MODE="plan"; TMO="5m"; DIR="$PWD"
while getopts "wm:t:d:" o; do
  case $o in w) MODE="accept-edits";; m) MODEL="$OPTARG";; t) TMO="$OPTARG";; d) DIR="$OPTARG";; *) exit 2;; esac
done
shift $((OPTIND-1))
[ $# -ge 1 ] || { echo "missing prompt" >&2; exit 2; }
cd "$DIR"
# never --dangerously-skip-permissions; output capped to protect the controller's context
"$AGY" -p "$1" --model "$MODEL" --mode "$MODE" --print-timeout "$TMO" </dev/null 2>&1 | head -c 20000
