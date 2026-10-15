# Enable/disable agy-delegate add-ons in Claude Code (Windows). Untested: no PowerShell on the dev machine.
# Usage: powershell -File toggle.ps1 [status | on <name> | off <name>]   names: agy-delegate, caveman
param([string]$Cmd = "", [string]$Name = "")
$ids = [ordered]@{ "agy-delegate" = "agy-delegate@agy-delegate-marketplace"; "caveman" = "caveman@caveman" }
$dir = if ($env:CLAUDE_CONFIG_DIR) { $env:CLAUDE_CONFIG_DIR } else { Join-Path $HOME ".claude" }
$p = Join-Path $dir "settings.json"
function Load { if ((Test-Path $p) -and (Get-Item $p).Length) { Get-Content $p -Raw | ConvertFrom-Json } else { [pscustomobject]@{} } }
function Show { $c = Load; $i = 1
  foreach ($n in $ids.Keys) { $v = if ($c.enabledPlugins) { $c.enabledPlugins.PSObject.Properties[$ids[$n]] } else { $null }
    $s = if (-not $v) { "n/a" } elseif ($v.Value) { "ON " } else { "OFF" }; "$i) [$s] $n"; $i++ } }
function Set-State($n, $on) {
  if (-not $ids.Contains($n)) { throw "unknown name: $n" }
  $c = Load; if (Test-Path $p) { Copy-Item $p "$p.toggle-bak" -Force }
  if (-not $c.PSObject.Properties["enabledPlugins"]) { $c | Add-Member -NotePropertyName enabledPlugins -NotePropertyValue ([pscustomobject]@{}) }
  $c.enabledPlugins | Add-Member -NotePropertyName $ids[$n] -NotePropertyValue $on -Force
  $c | ConvertTo-Json -Depth 20 | Set-Content $p -Encoding UTF8 }
switch ($Cmd) {
  "status" { Show }
  "on"  { Set-State $Name $true;  Show }
  "off" { Set-State $Name $false; Show }
  default { while ($true) { ""; Show; $k = Read-Host "number to toggle, q to quit"
      if ($k -eq "q") { break }
      $n = @($ids.Keys)[[int]$k - 1]; if ($n) { $cur = (Show)[[int]$k - 1] -match "\[ON "; Set-State $n (-not $cur) }
    }; "Restart Claude Code to apply." }
}
