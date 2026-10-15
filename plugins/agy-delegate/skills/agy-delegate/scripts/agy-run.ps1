# Windows twin of agy-run.sh. Read-only by default.
# Usage: powershell -File agy-run.ps1 [-Write] [-Model m] [-Timeout 5m] [-Dir d] "prompt"
param([switch]$Write, [switch]$Research, [string]$Model = $(if ($env:AGY_DELEGATE_MODEL) { $env:AGY_DELEGATE_MODEL } else { "gemini-3.8-flash-medium" }),
      [string]$Timeout = "5m", [string]$Dir = $PWD.Path, [Parameter(Mandatory, Position = 0)][string]$Prompt)
$agy = (Get-Command agy -ErrorAction SilentlyContinue).Source
if (-not $agy) { $agy = Join-Path $env:LOCALAPPDATA "agy\bin\agy.exe" }
if (-not (Test-Path $agy)) { [Console]::Error.WriteLine("agy not found. Run install.ps1"); exit 127 }
Set-Location $Dir
$pre = if ($Research) { (Get-Content (Join-Path $PSScriptRoot '..\references\research-profile.md') -Raw) + "`n`n" } else { "" }
$mode = if ($Write) { "accept-edits" } else { "plan" }
$out = (& $agy -p ($pre + "Constraint: read files with your file-view tool or simple grep/rg/wc/head/tail/cat/find/ls commands only (no python, awk, node, pipes or scripts; they are auto-denied in headless mode). " + $Prompt) --model $Model --mode $mode --print-timeout $Timeout 2>&1 | Out-String)
if ($out.Length -gt 20000) { $out = $out.Substring(0, 20000) }
$out
