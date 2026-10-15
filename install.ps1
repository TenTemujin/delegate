# agy-delegate installer for Windows (macOS/Linux: install.sh).
# 1) installs agy if missing  2) merges safe permissions into agy settings
# 3) registers this repo as a Claude Code marketplace and enables the plugin.
# Usage: powershell -ExecutionPolicy Bypass -File install.ps1 [-Repo owner/name] [-SkipAgy] [-WithCaveman] [-WithRtk] [-Uninstall]  (add-ons are optional third-party, not validated by this project)
param([string]$Repo = "", [switch]$SkipAgy, [switch]$Uninstall, [switch]$WithCaveman, [switch]$WithRtk)
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Mkt = "agy-delegate-marketplace"; $Plug = "agy-delegate@$Mkt"
$ClaudeDir = if ($env:CLAUDE_CONFIG_DIR) { $env:CLAUDE_CONFIG_DIR } else { Join-Path $HOME ".claude" }
$ClaudeSettings = Join-Path $ClaudeDir "settings.json"
$AgySettings = Join-Path $HOME ".gemini\antigravity-cli\settings.json"

function Read-Json($p) {
  if ((Test-Path $p) -and (Get-Item $p).Length -gt 0) { return Get-Content $p -Raw | ConvertFrom-Json }
  return [pscustomobject]@{}
}
function Set-Prop($o, $n, $v) {
  if ($o.PSObject.Properties[$n]) { $o.$n = $v } else { $o | Add-Member -NotePropertyName $n -NotePropertyValue $v }
}
function Get-Obj($o, $n) {
  if (-not $o.PSObject.Properties[$n]) { $o | Add-Member -NotePropertyName $n -NotePropertyValue ([pscustomobject]@{}) }
  return $o.$n
}
function Save-Json($o, $p) {
  New-Item -ItemType Directory -Force -Path (Split-Path $p) | Out-Null
  $o | ConvertTo-Json -Depth 20 | Set-Content -Path $p -Encoding UTF8
}

if ($Uninstall) {
  if (Test-Path $ClaudeSettings) {
    Copy-Item $ClaudeSettings "$ClaudeSettings.agy-bak" -Force
    $c = Read-Json $ClaudeSettings
    foreach ($pair in @(@("extraKnownMarketplaces", $Mkt), @("enabledPlugins", $Plug), @("extraKnownMarketplaces", "caveman"), @("enabledPlugins", "caveman@caveman"))) {
      $o = Get-Obj $c $pair[0]; if ($o.PSObject.Properties[$pair[1]]) { $o.PSObject.Properties.Remove($pair[1]) }
    }
    Save-Json $c $ClaudeSettings
  }
  Write-Host "Removed. Restart Claude Code."; exit 0
}

if (-not $SkipAgy) {
  $agyExe = Join-Path $env:LOCALAPPDATA "agy\bin\agy.exe"
  if (-not (Get-Command agy -ErrorAction SilentlyContinue) -and -not (Test-Path $agyExe)) {
    Write-Host "Installing Antigravity CLI (official installer)..."
    $t = Join-Path $env:TEMP "agy_install.ps1"
    Invoke-WebRequest -UseBasicParsing https://antigravity.google/cli/install.ps1 -OutFile $t
    & powershell -NoProfile -ExecutionPolicy Bypass -File $t
    Remove-Item $t -Force -ErrorAction SilentlyContinue
  }
  if (Test-Path $AgySettings) { Copy-Item $AgySettings "$AgySettings.bak" -Force }
  $s = Read-Json $AgySettings
  $perm = Get-Obj $s "permissions"
  $allow = "ls","cat","head","tail","grep","rg","find","wc","pwd","type","dir","findstr","git status","git diff","git log"
  $deny = "rm","del","rmdir","Remove-Item","sudo","git push","git commit","git reset","git checkout","git clean","curl","wget","Invoke-WebRequest"
  foreach ($k in @(@("allow", $allow), @("deny", $deny))) {
    $cur = @(); if ($perm.PSObject.Properties[$k[0]]) { $cur = @($perm.($k[0])) }
    $new = @($cur + ($k[1] | ForEach-Object { "command($_)" }) | Sort-Object -Unique)
    Set-Prop $perm $k[0] $new
  }
  Save-Json $s $AgySettings
  Write-Host "agy permissions merged: $AgySettings"
}

if (Test-Path $ClaudeSettings) { Copy-Item $ClaudeSettings "$ClaudeSettings.agy-bak" -Force }
$c = Read-Json $ClaudeSettings
$src = if ($Repo) { [pscustomobject]@{ source = "github"; repo = $Repo } } else { [pscustomobject]@{ source = "directory"; path = $Root } }
Set-Prop (Get-Obj $c "extraKnownMarketplaces") $Mkt ([pscustomobject]@{ source = $src })
Set-Prop (Get-Obj $c "enabledPlugins") $Plug $true
if ($WithCaveman) {
  Set-Prop (Get-Obj $c "extraKnownMarketplaces") "caveman" ([pscustomobject]@{ source = [pscustomobject]@{ source = "github"; repo = "JuliusBrussee/caveman" } })
  Set-Prop (Get-Obj $c "enabledPlugins") "caveman@caveman" $true
}
Save-Json $c $ClaudeSettings
if ($WithRtk) {
  if (-not (Get-Command rtk -ErrorAction SilentlyContinue) -and (Get-Command winget -ErrorAction SilentlyContinue)) { winget install rtk-ai.rtk }
  if (Get-Command rtk -ErrorAction SilentlyContinue) { rtk init -g } else { Write-Warning "rtk not found: see https://github.com/rtk-ai/rtk, then re-run with -WithRtk." }
}
Write-Host "`nDone. Restart Claude Code, then check: /plugin (agy-delegate should be enabled)."
Write-Host "If agy is not signed in, run 'agy' once in a terminal."
