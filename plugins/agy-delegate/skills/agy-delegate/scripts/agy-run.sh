#!/bin/bash
# Claude (controller) -> Antigravity CLI (helper). Read-only by default.
# Usage: agy-run.sh [-w] [-r] [-m model] [-t timeout] [-d dir] "prompt"
#   -a KIND  auto-pick model via router.py (extract|summarize|edit|reason); -m overrides
#   -b N     input size in bytes (files the helper will read); with -a, below the router
#            threshold nothing is delegated: exit 3 "stay in Claude"
#   -r  prepend the academic research profile (references/research-profile.md)
#   -w  allow edits (accept-edits); default is plan (read-only)
set -euo pipefail
AGY="$(command -v agy || true)"
[ -x "$AGY" ] || AGY="$HOME/.local/bin/agy"
[ -x "$AGY" ] || { echo "agy not found. Run /agy-delegate:setup" >&2; exit 127; }
MODEL="${AGY_DELEGATE_MODEL:-gemini-3.8-flash-medium}"; MODE="plan"; TMO="5m"; DIR="$PWD"; RESEARCH=0; KIND=""; NBYTES=""
while getopts "wra:b:m:t:d:" o; do
  case $o in w) MODE="accept-edits";; r) RESEARCH=1;; a) KIND="$OPTARG";; b) NBYTES="$OPTARG";; m) MODEL="$OPTARG"; MODEL_FORCED=1;; t) TMO="$OPTARG";; d) DIR="$OPTARG";; *) exit 2;; esac
done
shift $((OPTIND-1))
[ $# -ge 1 ] || { echo "missing prompt" >&2; exit 2; }
cd "$DIR"
# a Python that actually runs (on Windows `python3` can be the Microsoft Store stub)
PY=""; for c in python3 python; do "$c" -c '' >/dev/null 2>&1 && { PY="$c"; break; }; done
if [ -n "$KIND" ] && [ -z "${MODEL_FORCED:-}" ] && [ -n "$PY" ]; then
  RB=(); [ -n "$NBYTES" ] && RB=(--bytes "$NBYTES")
  R="$("$PY" "$(dirname "$0")/router.py" choose --kind "$KIND" ${RB[@]+"${RB[@]}"} 2>/dev/null || true)"
  RM="${R%%$'\t'*}"
  if [ "$RM" = "claude" ]; then echo "agy-run: router says stay in Claude (${R#*$'\t'}); nothing delegated" >&2; exit 3; fi
  [ -n "$RM" ] && MODEL="$RM"
fi
PREFIX=""
if [ "$RESEARCH" = 1 ]; then PREFIX="$(cat "$(dirname "$0")/../references/research-profile.md")"$'\n\n'; fi
PREFIX="${PREFIX}Constraint: do not use run_command (shell commands are auto-denied in headless mode: agy allow-rules match only an exact command string). Use only your built-in tools: view_file, grep_search, find_by_name, list_dir (and replace_file_content / write_to_file when editing is allowed). "
# never --dangerously-skip-permissions; output capped to protect the controller's context
# usage log for the monitor widget (monitor.py); set AGY_DELEGATE_LOG=/dev/null to disable
LOG="${AGY_DELEGATE_LOG:-$HOME/.agy-delegate/usage.jsonl}"; mkdir -p "$(dirname "$LOG")" 2>/dev/null || true
ID="$$-$(date +%s)"; T0=$(date +%s)
printf '{"ev":"start","id":"%s","ts":%s,"model":"%s","mode":"%s","in_bytes":%s}\n' "$ID" "$T0" "$MODEL" "$MODE" "${#1}" >> "$LOG" 2>/dev/null || true
# JSON output gives an explicit status and token usage; exit code is captured separately (no pipe masking it)
TMP="$(mktemp)"; trap 'rm -f "$TMP" "$TMP.err" "$TMP.txt"' EXIT
# stderr kept apart: agy prints notices there (e.g. "jetski: no output ... auto-denied") that would corrupt the JSON
RC=0; "$AGY" -p "$PREFIX$1" --model "$MODEL" --mode "$MODE" --print-timeout "$TMO" --output-format json </dev/null >"$TMP" 2>"$TMP.err" || RC=$?
# classify: prints "<status> <in_tokens> <out_tokens>" and writes the (capped) answer text to $TMP.txt
META="$([ -n "$PY" ] && "$PY" "$(dirname "$0")/classify.py" "$TMP" "$RC" 2>/dev/null || true)"
RETRY=0
if [ -n "$META" ]; then read -r ST TIN TOUT RETRY <<<"$META"; OUT="$(cat "$TMP.txt")"
else  # python3 missing/failed: raw text, exit code decides status
  OUT="$(head -c 20000 "$TMP")"; TIN=0; TOUT=0; ST=ok; [ "$RC" -ne 0 ] && ST=error; [ -z "$OUT" ] && ST=empty
fi
rm -f "$TMP.txt" "$TMP.err"
printf '{"ev":"end","id":"%s","ts":%s,"model":"%s","dur_s":%s,"out_bytes":%s,"status":"%s","in_tokens":%s,"out_tokens":%s,"src_bytes":%s,"prompt_bytes":%s,"retry_after_s":%s}\n' "$ID" "$(date +%s)" "$MODEL" "$(( $(date +%s)-T0 ))" "${#OUT}" "$ST" "$TIN" "$TOUT" "${NBYTES:-0}" "${#1}" "${RETRY:-0}" >> "$LOG" 2>/dev/null || true
printf '%s\n' "$OUT"
[ "$ST" = ok ] || exit 1
