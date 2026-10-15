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
$StatePath = Join-Path $HOME ".agy-delegate\install-state.json"   # what this installer added; uninstall reverts only that
function Read-State { if (Test-Path $StatePath) { return Get-Content $StatePath -Raw | ConvertFrom-Json } else { return [pscustomobject]@{} } }

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
  $st = Read-State
  if (Test-Path $ClaudeSettings) {
    Copy-Item $ClaudeSettings "$ClaudeSettings.agy-bak" -Force
    $c = Read-Json $ClaudeSettings
    $pairs = @(@("extraKnownMarketplaces", $Mkt), @("enabledPlugins", $Plug))
    if ($st.PSObject.Properties["caveman"] -and $st.caveman) { $pairs += @(@("extraKnownMarketplaces", "caveman"), @("enabledPlugins", "caveman@caveman")) }
    else { Write-Host "caveman left untouched (not installed by this installer)" }
    foreach ($pair in $pairs) {
      $o = Get-Obj $c $pair[0]; if ($o.PSObject.Properties[$pair[1]]) { $o.PSObject.Properties.Remove($pair[1]) }
    }
    Save-Json $c $ClaudeSettings
  }
  if ((Test-Path $AgySettings) -and $st.PSObject.Properties["agy_perms"]) {
    $a = Read-Json $AgySettings; $perm = Get-Obj $a "permissions"
    foreach ($k in "allow", "deny") {
      if ($perm.PSObject.Properties[$k] -and $st.agy_perms.PSObject.Properties[$k]) {
        $drop = @($st.agy_perms.$k); Set-Prop $perm $k @($perm.$k | Where-Object { $drop -notcontains $_ })
      }
    }
    Save-Json $a $AgySettings; Write-Host "agy permissions added by installer reverted"
  }
  if (Test-Path $StatePath) { Remove-Item $StatePath -Force }
  Write-Host "(RTK hook, if enabled, must be removed with: rtk init -g --uninstall)"
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
  $state = Read-State; if (-not $state.PSObject.Properties["agy_perms"]) { Set-Prop $state "agy_perms" ([pscustomobject]@{}) }
  $allow = "ls","cat","head","tail","grep","rg","wc","pwd","type","dir","findstr","git status","git diff","git log"
  $deny = "rm","del","rmdir","Remove-Item","sudo","git push","git commit","git reset","git checkout","git clean","curl","wget","Invoke-WebRequest"
  foreach ($k in @(@("allow", $allow), @("deny", $deny))) {
    $cur = @(); if ($perm.PSObject.Properties[$k[0]]) { $cur = @($perm.($k[0])) }
    $mine = @($k[1] | ForEach-Object { "command($_)" })
    $added = @($mine | Where-Object { $cur -notcontains $_ })
    Set-Prop $perm $k[0] @($cur + $mine | Sort-Object -Unique)
    $prev = @(); if ($state.agy_perms.PSObject.Properties[$k[0]]) { $prev = @($state.agy_perms.($k[0])) }
    Set-Prop $state.agy_perms $k[0] @($prev + $added | Sort-Object -Unique)
  }
  Save-Json $state $StatePath
  $legacy = @(@($perm.allow) | Where-Object { $_ -in "command(find)", "command(sed -n)" })
  if ($legacy) { Write-Host "WARNING: remove broad rules from an older install (they allow find -delete/-exec, sed w): $legacy" }
  Save-Json $s $AgySettings
  Write-Host "agy permissions merged: $AgySettings"
}

if (Test-Path $ClaudeSettings) { Copy-Item $ClaudeSettings "$ClaudeSettings.agy-bak" -Force }
$c = Read-Json $ClaudeSettings
$src = if ($Repo) { [pscustomobject]@{ source = "github"; repo = $Repo } } else { [pscustomobject]@{ source = "directory"; path = $Root } }
Set-Prop (Get-Obj $c "extraKnownMarketplaces") $Mkt ([pscustomobject]@{ source = $src })
Set-Prop (Get-Obj $c "enabledPlugins") $Plug $true
if ($WithCaveman) {
  $cm = Get-Obj $c "extraKnownMarketplaces"; $ce = Get-Obj $c "enabledPlugins"
  if (-not $cm.PSObject.Properties["caveman"] -and -not $ce.PSObject.Properties["caveman@caveman"]) {
    $st2 = Read-State; Set-Prop $st2 "caveman" $true; Save-Json $st2 $StatePath
  }
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
