# Round-trip of install.ps1 / toggle.ps1 / -Uninstall in a throwaway home. No network: -SkipAgy.
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$T = Join-Path ([IO.Path]::GetTempPath()) ("agyi-" + [guid]::NewGuid()); New-Item -ItemType Directory -Path "$T\.claude" | Out-Null
$env:AGY_DELEGATE_HOME = $T; $env:CLAUDE_CONFIG_DIR = "$T\.claude"
$s = "$T\.claude\settings.json"
'{"theme":"dark","enabledPlugins":{"x@y":true}}' | Set-Content $s -Encoding ASCII
try {
  & powershell -NoProfile -ExecutionPolicy Bypass -File "$Root\install.ps1" -SkipAgy -WithCaveman | Out-Null
  if (-not (Get-Content $s -Raw | ConvertFrom-Json).enabledPlugins.'agy-delegate@agy-delegate-marketplace') { throw "FAIL install" }
  & powershell -NoProfile -ExecutionPolicy Bypass -File "$Root\toggle.ps1" off caveman | Out-Null
  if ((Get-Content $s -Raw | ConvertFrom-Json).enabledPlugins.'caveman@caveman' -ne $false) { throw "FAIL toggle" }
  & powershell -NoProfile -ExecutionPolicy Bypass -File "$Root\install.ps1" -Uninstall | Out-Null
  $c = Get-Content $s -Raw | ConvertFrom-Json
  $names = @($c.enabledPlugins.PSObject.Properties.Name)
  if ($c.theme -ne "dark" -or $names.Count -ne 1 -or $names[0] -ne "x@y" -or @($c.extraKnownMarketplaces.PSObject.Properties).Count) { throw "FAIL uninstall did not restore settings: $(Get-Content $s -Raw)" }
  Write-Host "installer round-trip (ps1): passed"
} finally { Remove-Item -Recurse -Force $T }
