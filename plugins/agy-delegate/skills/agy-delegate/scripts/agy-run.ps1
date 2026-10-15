# Windows twin of agy-run.sh. Read-only by default.
# Usage: powershell -File agy-run.ps1 [-Write] [-Research] [-Kind extract|summarize|edit|reason] [-Bytes N] [-Model m] [-Timeout 5m] [-Dir d] "prompt"
# Exit codes: 0 ok, 1 agy error/denied/empty, 3 router says stay in Claude, 127 agy missing.
param([switch]$Write, [switch]$Research, [string]$Kind = "", [long]$Bytes = -1, [string]$Model = "", [string]$Timeout = "5m", [string]$Dir = $PWD.Path,
      [Parameter(Mandatory, Position = 0)][string]$Prompt)
$agy = (Get-Command agy -ErrorAction SilentlyContinue).Source
if (-not $agy) { $agy = Join-Path $env:LOCALAPPDATA "agy\bin\agy.exe" }
if (-not (Test-Path $agy)) { [Console]::Error.WriteLine("agy not found. Run install.ps1"); exit 127 }
Set-Location $Dir
$forced = [bool]$Model
if (-not $Model) { $Model = if ($env:AGY_DELEGATE_MODEL) { $env:AGY_DELEGATE_MODEL } else { "gemini-3.8-flash-medium" } }
if ($Kind -and -not $forced -and (Get-Command python -ErrorAction SilentlyContinue)) {
  $ra = @((Join-Path $PSScriptRoot "router.py"), "choose", "--kind", $Kind); if ($Bytes -ge 0) { $ra += @("--bytes", "$Bytes") }
  $r = (& python @ra 2>$null | Select-Object -First 1); if ($r) {
    $rm, $why = $r -split "`t", 2
    if ($rm -eq "claude") { [Console]::Error.WriteLine("agy-run: router says stay in Claude ($why); nothing delegated"); exit 3 }
    if ($rm) { $Model = $rm }
  }
}
$pre = if ($Research) { (Get-Content (Join-Path $PSScriptRoot '..\references\research-profile.md') -Raw) + "`n`n" } else { "" }
$mode = if ($Write) { "accept-edits" } else { "plan" }
$full = $pre + "Constraint: read files with your file-view tool or simple grep/rg/wc/head/tail/cat/ls commands only (no python, awk, node, pipes or scripts; they are auto-denied in headless mode). " + $Prompt
$log = if ($env:AGY_DELEGATE_LOG) { $env:AGY_DELEGATE_LOG } else { Join-Path $HOME ".agy-delegate\usage.jsonl" }
function Write-Log($o) { try { New-Item -ItemType Directory -Force -Path (Split-Path $log) | Out-Null; Add-Content -Path $log -Value ($o | ConvertTo-Json -Compress) } catch {} }
$id = "$PID-$([DateTimeOffset]::UtcNow.ToUnixTimeSeconds())"; $t0 = [DateTimeOffset]::UtcNow.ToUnixTimeSeconds()
Write-Log ([ordered]@{ ev = "start"; id = $id; ts = $t0; model = $Model; mode = $mode; in_bytes = $Prompt.Length })
$raw = (& $agy -p $full --model $Model --mode $mode --print-timeout $Timeout --output-format json 2>&1 | Out-String); $rc = $LASTEXITCODE
$st = "ok"; $text = $raw; $tin = 0; $tout = 0
try {
  $d = $raw | ConvertFrom-Json
  $text = [string]$d.response
  if ($d.usage) { $tin = [int]$d.usage.input_tokens; $tout = [int]$d.usage.output_tokens }
  if ($rc -ne 0 -or $d.status -ne "SUCCESS") { $st = "error"; if (-not $text) { $text = $raw } }
} catch { if ($rc -ne 0) { $st = "error" } }
if ($st -eq "ok" -and $text.StartsWith("jetski: no output")) { $st = "denied" }
elseif ($st -eq "ok" -and -not $text.Trim()) { $st = "empty" }
if ($text.Length -gt 20000) { $text = $text.Substring(0, 20000) }
$t1 = [DateTimeOffset]::UtcNow.ToUnixTimeSeconds()
Write-Log ([ordered]@{ ev = "end"; id = $id; ts = $t1; model = $Model; dur_s = ($t1 - $t0); out_bytes = $text.Length; status = $st; in_tokens = $tin; out_tokens = $tout; src_bytes = [Math]::Max(0, $Bytes); prompt_bytes = $Prompt.Length })
$text
if ($st -ne "ok") { exit 1 }
