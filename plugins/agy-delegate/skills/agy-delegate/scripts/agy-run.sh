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
if [ -n "$KIND" ] && [ -z "${MODEL_FORCED:-}" ] && command -v python3 >/dev/null; then
  RB=(); [ -n "$NBYTES" ] && RB=(--bytes "$NBYTES")
  R="$(python3 "$(dirname "$0")/router.py" choose --kind "$KIND" ${RB[@]+"${RB[@]}"} 2>/dev/null || true)"
  RM="${R%%$'\t'*}"
  if [ "$RM" = "claude" ]; then echo "agy-run: router says stay in Claude (${R#*$'\t'}); nothing delegated" >&2; exit 3; fi
  [ -n "$RM" ] && MODEL="$RM"
fi
PREFIX=""
if [ "$RESEARCH" = 1 ]; then PREFIX="$(cat "$(dirname "$0")/../references/research-profile.md")"$'\n\n'; fi
PREFIX="${PREFIX}Constraint: read files with your file-view tool or simple grep/rg/wc/head/tail/cat/ls commands only (no python, awk, node, pipes or scripts; they are auto-denied in headless mode). "
# never --dangerously-skip-permissions; output capped to protect the controller's context
# usage log for the monitor widget (monitor.py); set AGY_DELEGATE_LOG=/dev/null to disable
LOG="${AGY_DELEGATE_LOG:-$HOME/.agy-delegate/usage.jsonl}"; mkdir -p "$(dirname "$LOG")" 2>/dev/null || true
ID="$$-$(date +%s)"; T0=$(date +%s)
printf '{"ev":"start","id":"%s","ts":%s,"model":"%s","mode":"%s","in_bytes":%s}\n' "$ID" "$T0" "$MODEL" "$MODE" "${#1}" >> "$LOG" 2>/dev/null || true
# JSON output gives an explicit status and token usage; exit code is captured separately (no pipe masking it)
TMP="$(mktemp)"; trap 'rm -f "$TMP"' EXIT
RC=0; "$AGY" -p "$PREFIX$1" --model "$MODEL" --mode "$MODE" --print-timeout "$TMO" --output-format json </dev/null >"$TMP" 2>&1 || RC=$?
# classify: prints "<status> <in_tokens> <out_tokens>" and writes the (capped) answer text to $TMP.txt
META="$(python3 - "$TMP" "$RC" <<'PY' 2>/dev/null || true
import json, sys
raw, rc = open(sys.argv[1], errors="replace").read(), int(sys.argv[2])
try: d = json.loads(raw)
except ValueError: d = None
if not isinstance(d, dict): st, text, u = ("error" if rc else "ok"), raw, {}
else:
    text, u = d.get("response") or "", d.get("usage") or {}
    st = "error" if rc or d.get("status") != "SUCCESS" else "ok"
    if st == "error" and not text: text = json.dumps({k: d[k] for k in d if k != "usage"})[:2000]
if st == "ok" and text.startswith("jetski: no output"): st = "denied"
elif st == "ok" and not text.strip(): st = "empty"
open(sys.argv[1] + ".txt", "w").write(text[:20000])
print(st, u.get("input_tokens") or 0, u.get("output_tokens") or 0)
PY
)"
if [ -n "$META" ]; then read -r ST TIN TOUT <<<"$META"; OUT="$(cat "$TMP.txt")"
else  # python3 missing/failed: raw text, exit code decides status
  OUT="$(head -c 20000 "$TMP")"; TIN=0; TOUT=0; ST=ok; [ "$RC" -ne 0 ] && ST=error; [ -z "$OUT" ] && ST=empty
fi
rm -f "$TMP.txt"
printf '{"ev":"end","id":"%s","ts":%s,"model":"%s","dur_s":%s,"out_bytes":%s,"status":"%s","in_tokens":%s,"out_tokens":%s,"src_bytes":%s,"prompt_bytes":%s}\n' "$ID" "$(date +%s)" "$MODEL" "$(( $(date +%s)-T0 ))" "${#OUT}" "$ST" "$TIN" "$TOUT" "${NBYTES:-0}" "${#1}" >> "$LOG" 2>/dev/null || true
printf '%s\n' "$OUT"
[ "$ST" = ok ] || exit 1
