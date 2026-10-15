#!/bin/bash
# Claude (controller) -> Antigravity CLI (helper). Read-only by default.
# Usage: agy-run.sh [-w] [-r] [-m model] [-t timeout] [-d dir] "prompt"
#   -r  prepend the academic research profile (references/research-profile.md)
#   -w  allow edits (accept-edits); default is plan (read-only)
set -euo pipefail
AGY="$(command -v agy || true)"
[ -x "$AGY" ] || AGY="$HOME/.local/bin/agy"
[ -x "$AGY" ] || { echo "agy not found. Run /agy-delegate:setup" >&2; exit 127; }
MODEL="${AGY_DELEGATE_MODEL:-gemini-3.8-flash-medium}"; MODE="plan"; TMO="5m"; DIR="$PWD"; RESEARCH=0
while getopts "wrm:t:d:" o; do
  case $o in w) MODE="accept-edits";; r) RESEARCH=1;; m) MODEL="$OPTARG";; t) TMO="$OPTARG";; d) DIR="$OPTARG";; *) exit 2;; esac
done
shift $((OPTIND-1))
[ $# -ge 1 ] || { echo "missing prompt" >&2; exit 2; }
cd "$DIR"
PREFIX=""
if [ "$RESEARCH" = 1 ]; then PREFIX="$(cat "$(dirname "$0")/../references/research-profile.md")"$'\n\n'; fi
PREFIX="${PREFIX}Constraint: read files with your file-view tool or simple grep/rg/wc/head/tail/cat/find/ls commands only (no python, awk, node, pipes or scripts; they are auto-denied in headless mode). "
# never --dangerously-skip-permissions; output capped to protect the controller's context
# usage log for the monitor widget (monitor.py); set AGY_DELEGATE_LOG=/dev/null to disable
LOG="${AGY_DELEGATE_LOG:-$HOME/.agy-delegate/usage.jsonl}"; mkdir -p "$(dirname "$LOG")" 2>/dev/null || true
ID="$$-$(date +%s)"; T0=$(date +%s)
printf '{"ev":"start","id":"%s","ts":%s,"model":"%s","mode":"%s","in_bytes":%s}\n' "$ID" "$T0" "$MODEL" "$MODE" "${#1}" >> "$LOG" 2>/dev/null || true
OUT="$("$AGY" -p "$PREFIX$1" --model "$MODEL" --mode "$MODE" --print-timeout "$TMO" </dev/null 2>&1 | head -c 20000 || true)"
ST=ok; case "$OUT" in "jetski: no output"*) ST=denied;; "") ST=empty;; esac
printf '{"ev":"end","id":"%s","ts":%s,"model":"%s","dur_s":%s,"out_bytes":%s,"status":"%s"}\n' "$ID" "$(date +%s)" "$MODEL" "$(( $(date +%s)-T0 ))" "${#OUT}" "$ST" >> "$LOG" 2>/dev/null || true
printf '%s\n' "$OUT"
