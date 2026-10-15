#!/bin/bash
# Integration tests for agy-run.sh + router.py using a fake `agy` (no network). Run: bash test_wrapper.sh
cd "$(dirname "$0")"; W="$PWD/agy-run.sh"; T="$(mktemp -d)"; trap 'rm -rf "$T"' EXIT
mkdir "$T/bin"; export PATH="$T/bin:$PATH" AGY_DELEGATE_LOG="$T/log.jsonl" AGY_DELEGATE_HOME="$T" FAKE_MODE=ok
cat > "$T/bin/agy" <<'FAKE'
#!/bin/bash
echo "$@" > "$FAKE_ARGS"
case "$FAKE_MODE" in
  ok)      echo '{"status":"SUCCESS","response":"hello","usage":{"input_tokens":11,"output_tokens":3}}';;
  rc1)     echo '{"status":"ERROR","response":"","error":"auth"}'; exit 1;;
  errzero) echo '{"status":"ERROR","response":"quota exceeded"}';;
  empty)   echo '{"status":"SUCCESS","response":"  "}';;
  denied)  echo '{"status":"SUCCESS","response":"jetski: no output (denied)"}';;
  text)    echo 'plain text answer';;
  textfail) echo 'error: invalid model'; exit 1;;
  deniedjson) echo 'jetski: no output produced — a tool required the "command" permission ... auto-denied.' >&2
              echo '{"status":"SUCCESS","response":"","usage":{"input_tokens":6535,"output_tokens":250},"denied_actions":[{"action":"command"}]}';;
  quota) echo '{"status":"ERROR","response":"","error":"RESOURCE_EXHAUSTED (code 429): Individual quota reached. Resets in 4h46m17s.","error_code":429}'; exit 1;;
  noisyok) echo 'warning: update available' >&2; echo '{"status":"SUCCESS","response":"hello","usage":{"input_tokens":5,"output_tokens":1}}';;
esac
FAKE
chmod +x "$T/bin/agy"; export FAKE_ARGS="$T/args"
PYT=python3; python3 -c "" 2>/dev/null || PYT=python
pass=0; fail=0
chk() { if [ "$2" = "$3" ]; then pass=$((pass+1)); else fail=$((fail+1)); echo "FAIL $1: got [$2] want [$3]"; sed 's/^/    stderr: /' "$T/err" 2>/dev/null | head -5; fi; }
last() { "$PYT" -c "import json,sys;print(json.loads(open(sys.argv[1]).read().splitlines()[-1])[sys.argv[2]])" "$AGY_DELEGATE_LOG" "$1"; }
run() { FAKE_MODE=$1 bash "$W" "${@:2}" >"$T/out" 2>"$T/err"; echo $?; }

chk "ok exit"       "$(run ok "p")" 0;            chk "ok text" "$(cat $T/out)" hello
chk "ok status"     "$(last status)" ok;          chk "ok tokens" "$(last in_tokens)/$(last out_tokens)" 11/3
chk "rc!=0 exit"    "$(run rc1 "p")" 1;           chk "rc!=0 status" "$(last status)" error
chk "ERROR rc0"     "$(run errzero "p")" 1;       chk "ERROR rc0 status" "$(last status)" error
chk "ERROR rc0 text" "$(cat $T/out)" "quota exceeded"
chk "empty"         "$(run empty "p")" 1;         chk "empty status" "$(last status)" empty
chk "denied"        "$(run denied "p")" 1;        chk "denied status" "$(last status)" denied
chk "plain text ok" "$(run text "p")" 0;          chk "plain status" "$(last status)" ok
chk "plain fail"    "$(run textfail "p")" 1;      chk "plain fail status" "$(last status)" error
chk "denied json"   "$(run deniedjson "p")" 1;   chk "denied json status" "$(last status)" denied
chk "denied json tok" "$(last in_tokens)" 6535
chk "stderr noise ok" "$(run noisyok "p")" 0;    chk "noise text" "$(cat $T/out)" hello
chk "quota exit"    "$(run quota "p")" 1;        chk "quota status" "$(last status)" quota
chk "quota retry"   "$(last retry_after_s)" 17177
# router integration
: > "$AGY_DELEGATE_LOG"
rm -f "$T/args"
chk "small stays"   "$(run ok -a extract -b 100 "p")" 3
chk "agy not called" "$([ -e "$T/args" ] && echo called || echo no)" no
chk "no log on skip" "$(wc -l < "$AGY_DELEGATE_LOG" | tr -d ' ')" 0
chk "big delegates" "$(run ok -a extract -b 50000 "p")" 0
chk "extract->argon-medium" "$(grep -o 'gemini-[a-z0-9.]*-[a-z]*-[a-z]*' "$T/args" | head -1)" gemini-4-argon-medium
chk "-m wins"       "$(run ok -a extract -b 100 -m gemini-x "p")" 0
chk "forced model"  "$(grep -o 'gemini-x' "$T/args" | head -1)" gemini-x
chk "no size = no gate" "$(run ok -a summarize "p")" 0
chk "summarize argon-med" "$(grep -o 'gemini-[a-z0-9.]*-[a-z]*-[a-z]*' "$T/args" | head -1)" gemini-4-argon-medium
# adaptive escalation from REAL failures recorded by the wrapper
: > "$AGY_DELEGATE_LOG"
for i in 1 2 3; do run errzero -a extract -b 50000 "p" >/dev/null; done
run ok -a extract -b 50000 "p" >/dev/null
chk "escalated"     "$(grep -o 'gemini-[a-z0-9.]*-[a-z]*-[a-z]*' "$T/args" | head -1)" gemini-3.8-flash-medium
# arg safety: prompt with quotes/newlines passes through intact
run ok 'a "quoted" $HOME
line2' >/dev/null; chk "prompt intact" "$(grep -c 'line2' "$T/args")" 1
echo "wrapper tests: $pass passed, $fail failed"; [ "$fail" = 0 ]
