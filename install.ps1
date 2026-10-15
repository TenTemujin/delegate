# agy-delegate installer for Windows (macOS/Linux: install.sh). Logic lives in plugins\agy-delegate\scripts\agyctl.py.
# 1) installs agy if missing  2) merges safe permissions into agy settings (removes broad legacy rules)
# 3) registers this repo as a Claude Code marketplace and enables the plugin. Uninstall restores prior values.
# Usage: powershell -ExecutionPolicy Bypass -File install.ps1 [-Repo owner/name] [-SkipAgy] [-WithCaveman] [-WithRtk] [-KeepLegacy] [-Uninstall]
# Add-ons are optional third-party, not validated by this project.
param([string]$Repo = "", [switch]$SkipAgy, [switch]$Uninstall, [switch]$WithCaveman, [switch]$WithRtk, [switch]$KeepLegacy)
$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "find-python.ps1")
$py = Find-Python
if (-not $py) { Write-Error "Python 3.8+ is required (https://www.python.org/downloads/ or: winget install Python.Python.3.12)"; exit 1 }
$ctl = Join-Path $PSScriptRoot "plugins\agy-delegate\scripts\agyctl.py"
if ($Uninstall) { & $py[0] @($py | Select-Object -Skip 1) $ctl uninstall; exit $LASTEXITCODE }
$a = @("install"); if ($Repo) { $a += @("--repo", $Repo) }
if ($SkipAgy) { $a += "--skip-agy" }; if ($WithCaveman) { $a += "--with-caveman" }; if ($KeepLegacy) { $a += "--keep-legacy" }
& $py[0] @($py | Select-Object -Skip 1) $ctl @a; if ($LASTEXITCODE) { exit $LASTEXITCODE }
if ($WithRtk) {
  if (-not (Get-Command rtk -ErrorAction SilentlyContinue) -and (Get-Command winget -ErrorAction SilentlyContinue)) { winget install rtk-ai.rtk }
  if (Get-Command rtk -ErrorAction SilentlyContinue) { rtk init -g } else { Write-Warning "rtk not found: see https://github.com/rtk-ai/rtk, then re-run with -WithRtk." }
}
Write-Host "Control panel: open-panel.bat"
