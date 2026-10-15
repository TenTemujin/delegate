# Enable/disable agy-delegate add-ons in Claude Code (Windows). The control panel does the same.
# Usage: powershell -File toggle.ps1 [status | on <name> | off <name>]   names: agy-delegate, caveman
param([string]$Cmd = "", [string]$Name = "")
. (Join-Path $PSScriptRoot "find-python.ps1")
$py = Find-Python; if (-not $py) { Write-Error "Python 3.8+ required"; exit 1 }
$ctl = Join-Path $PSScriptRoot "plugins\agy-delegate\scripts\agyctl.py"
function Ctl { & $py[0] @($py | Select-Object -Skip 1) $ctl @args }
$names = @("agy-delegate", "caveman")
switch ($Cmd) {
  "status" { Ctl status }
  { $_ -in "on", "off" } { Ctl toggle $Cmd $Name; Ctl status }
  default { while ($true) { ""; $s = @(Ctl status); for ($i = 0; $i -lt 2; $i++) { "$($i + 1)) $($s[$i])" }
      $k = Read-Host "number to toggle, q to quit"; if ($k -eq "q") { break }
      $n = $names[[int]$k - 1]; if ($n) { if ($s[[int]$k - 1] -match "\[ON") { Ctl toggle off $n } else { Ctl toggle on $n } } } }
}
