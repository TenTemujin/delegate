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
$full = $pre + "Constraint: do not use run_command (shell commands are auto-denied in headless mode: agy allow-rules match only an exact command string). Use only your built-in tools: view_file, grep_search, find_by_name, list_dir (and replace_file_content / write_to_file when editing is allowed). " + $Prompt
$log = if ($env:AGY_DELEGATE_LOG) { $env:AGY_DELEGATE_LOG } else { Join-Path $HOME ".agy-delegate\usage.jsonl" }
function Write-Log($o) { try { New-Item -ItemType Directory -Force -Path (Split-Path $log) | Out-Null; Add-Content -Path $log -Value ($o | ConvertTo-Json -Compress) } catch {} }
$id = "$PID-$([DateTimeOffset]::UtcNow.ToUnixTimeSeconds())"; $t0 = [DateTimeOffset]::UtcNow.ToUnixTimeSeconds()
Write-Log ([ordered]@{ ev = "start"; id = $id; ts = $t0; model = $Model; mode = $mode; in_bytes = $Prompt.Length })
# stdout and stderr apart: agy prints notices (e.g. "jetski: no output ... auto-denied") on stderr, which would
# otherwise corrupt the JSON on stdout and turn a denied call into "ok"
$errf = [IO.Path]::GetTempFileName()
$raw = (& $agy -p $full --model $Model --mode $mode --print-timeout $Timeout --output-format json 2>$errf | Out-String); $rc = $LASTEXITCODE
$stderr = (Get-Content $errf -Raw -ErrorAction SilentlyContinue); Remove-Item $errf -ErrorAction SilentlyContinue
$st = "ok"; $text = $raw; $tin = 0; $tout = 0; $d = $null
try { $d = $raw | ConvertFrom-Json } catch {
  $j = @($raw -split "`r?`n" | Where-Object { $_.TrimStart().StartsWith("{") })   # JSON line after any stray text
  if ($j) { try { $d = $j[-1] | ConvertFrom-Json } catch {} }
}
if ($d -and $d.PSObject.Properties["status"]) {
  $text = [string]$d.response
  if ($d.usage) { $tin = [int]$d.usage.input_tokens; $tout = [int]$d.usage.output_tokens }
  if ($rc -ne 0 -or $d.status -ne "SUCCESS") {
    $st = "error"; if (-not $text) { $text = (($raw + $stderr).Trim()) }
    if ("$raw$stderr" -match 'RESOURCE_EXHAUSTED|"error_code":\s*429') { $st = "quota" }   # router skips it until reset
  }
  elseif (-not $text.Trim() -and ($d.denied_actions -or "$stderr".Contains("auto-denied"))) { $st = "denied"; $text = "jetski: no output (denied: $(@($d.denied_actions | ForEach-Object { $_.action }) -join ', '))" }
} else {
  if (-not $raw.Trim()) { $text = "$stderr" }
  if ($rc -ne 0) { $st = "error" }
}
if ($st -eq "ok" -and ($text.StartsWith("jetski: no output") -or ("$stderr".StartsWith("jetski: no output") -and -not $text.Trim()))) { $st = "denied" }
elseif ($st -eq "ok" -and -not $text.Trim()) { $st = "empty" }
if ($text.Length -gt 20000) { $text = $text.Substring(0, 20000) }
$retry = 0
if ("$raw$stderr" -match '[Rr]esets in ((?:\d+[hms])+)') {
  foreach ($m in [regex]::Matches($Matches[1], '(\d+)([hms])')) { $retry += [int]$m.Groups[1].Value * @{ h = 3600; m = 60; s = 1 }[$m.Groups[2].Value] }
}
$t1 = [DateTimeOffset]::UtcNow.ToUnixTimeSeconds()
Write-Log ([ordered]@{ ev = "end"; id = $id; ts = $t1; model = $Model; dur_s = ($t1 - $t0); out_bytes = $text.Length; status = $st; in_tokens = $tin; out_tokens = $tout; src_bytes = [Math]::Max(0, $Bytes); prompt_bytes = $Prompt.Length; retry_after_s = $retry })
$text
if ($st -ne "ok") { exit 1 }
