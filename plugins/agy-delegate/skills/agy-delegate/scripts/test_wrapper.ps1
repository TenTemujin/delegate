# Integration tests for agy-run.ps1 + router.py using a fake `agy` (no network). Windows twin of test_wrapper.sh.
# Run: powershell -NoProfile -ExecutionPolicy Bypass -File test_wrapper.ps1
$ErrorActionPreference = "Stop"
$W = Join-Path $PSScriptRoot "agy-run.ps1"
$T = Join-Path ([IO.Path]::GetTempPath()) ("agyt-" + [guid]::NewGuid()); New-Item -ItemType Directory -Path "$T\bin" | Out-Null
$env:PATH = "$T\bin;$env:PATH"; $env:AGY_DELEGATE_LOG = "$T\log.jsonl"; $env:AGY_DELEGATE_HOME = $T; $env:FAKE_ARGS = "$T\args"
@'
$args -join " " | Set-Content $env:FAKE_ARGS
switch ($env:FAKE_MODE) {
  "ok"       { '{"status":"SUCCESS","response":"hello","usage":{"input_tokens":11,"output_tokens":3}}' }
  "rc1"      { '{"status":"ERROR","response":"","error":"auth"}'; exit 1 }
  "errzero"  { '{"status":"ERROR","response":"quota exceeded"}' }
  "empty"    { '{"status":"SUCCESS","response":"  "}' }
  "denied"   { '{"status":"SUCCESS","response":"jetski: no output (denied)"}' }
  "text"     { 'plain text answer' }
  "textfail" { 'error: invalid model'; exit 1 }
  "deniedjson" { [Console]::Error.WriteLine('jetski: no output produced - a tool required the "command" permission ... auto-denied.')
                 '{"status":"SUCCESS","response":"","usage":{"input_tokens":6535,"output_tokens":250},"denied_actions":[{"action":"command"}]}' }
  "quota"    { '{"status":"ERROR","response":"","error":"RESOURCE_EXHAUSTED (code 429): Individual quota reached. Resets in 4h46m17s.","error_code":429}'; exit 1 }
  "noisyok"  { [Console]::Error.WriteLine('warning: update available'); '{"status":"SUCCESS","response":"hello","usage":{"input_tokens":5,"output_tokens":1}}' }
}
exit 0
'@ | Set-Content "$T\bin\agy.ps1"
$script:pass = 0; $script:fail = 0
function Chk($name, $got, $want) { if ("$got" -eq "$want") { $script:pass++ } else { $script:fail++; Write-Host "FAIL ${name}: got [$got] want [$want]" } }
function Last($k) { ((Get-Content $env:AGY_DELEGATE_LOG)[-1] | ConvertFrom-Json).$k }
function Run($mode) {
  $env:FAKE_MODE = $mode; $ErrorActionPreference = "Continue"   # stderr of a child must not abort the test
  $p = Start-Process powershell -ArgumentList (@("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", "`"$W`"") + ($args | ForEach-Object { "`"$($_ -replace '"', '\"')`"" })) `
       -NoNewWindow -Wait -PassThru -RedirectStandardOutput "$T\out" -RedirectStandardError "$T\err"
  $out = Get-Content "$T\out"; $global:LASTEXITCODE = $p.ExitCode
  $script:out = ($out -join "`n").Trim(); return $LASTEXITCODE
}
function Used { (Select-String -Path $env:FAKE_ARGS -Pattern 'gemini-[\w.-]+' | Select-Object -First 1).Matches[0].Value }
try {
  Chk "agy is the fake" (Get-Command agy).Source "$T\bin\agy.ps1"
  Chk "ok exit" (Run ok "p") 0;            Chk "ok text" $out "hello"
  Chk "ok status" (Last status) ok;       Chk "ok tokens" "$(Last in_tokens)/$(Last out_tokens)" "11/3"
  Chk "rc!=0 exit" (Run rc1 "p") 1;        Chk "rc!=0 status" (Last status) error
  Chk "ERROR rc0" (Run errzero "p") 1;     Chk "ERROR rc0 status" (Last status) error
  Chk "ERROR rc0 text" $out "quota exceeded"
  Chk "empty" (Run empty "p") 1;           Chk "empty status" (Last status) empty
  Chk "denied" (Run denied "p") 1;         Chk "denied status" (Last status) denied
  Chk "plain text ok" (Run text "p") 0;    Chk "plain status" (Last status) ok
  Chk "plain fail" (Run textfail "p") 1;   Chk "plain fail status" (Last status) error
  Chk "denied json" (Run deniedjson "p") 1;  Chk "denied json status" (Last status) denied
  Chk "denied json tok" (Last in_tokens) 6535
  Chk "stderr noise ok" (Run noisyok "p") 0; Chk "noise text" $out "hello"
  Chk "quota exit" (Run quota "p") 1;       Chk "quota status" (Last status) quota
  Chk "quota retry" (Last retry_after_s) 17177
  # router integration
  Set-Content $env:AGY_DELEGATE_LOG ""; Remove-Item $env:FAKE_ARGS -ErrorAction SilentlyContinue
  Chk "small stays" (Run ok -Kind extract -Bytes 100 "p") 3
  Chk "agy not called" (Test-Path $env:FAKE_ARGS) False
  Chk "big delegates" (Run ok -Kind extract -Bytes 50000 "p") 0
  Chk "extract->medium" (Used) "gemini-3.8-flash-medium"
  Chk "src_bytes logged" (Last src_bytes) 50000
  Chk "-Model wins" (Run ok -Kind extract -Bytes 100 -Model gemini-x "p") 0
  Chk "forced model" (Used) "gemini-x"
  # adaptive escalation from real failures recorded by the wrapper
  Set-Content $env:AGY_DELEGATE_LOG ""
  1..3 | ForEach-Object { Run errzero -Kind extract -Bytes 50000 "p" | Out-Null }
  Run ok -Kind extract -Bytes 50000 "p" | Out-Null
  Chk "escalated" (Used) "gemini-3.8-flash-high"
  Run ok "a `"quoted`" `$HOME line2" | Out-Null
  Chk "prompt intact" ([bool](Select-String -Path $env:FAKE_ARGS -SimpleMatch 'a "quoted" $HOME line2')) True
} finally { Remove-Item -Recurse -Force $T }
Write-Host "wrapper tests (ps1): $pass passed, $fail failed"
if ($fail) { exit 1 }
