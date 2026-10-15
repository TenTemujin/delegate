# Dot-sourced helper: returns @(exe, args...) for a working Python 3.8+, skipping the Microsoft Store alias stub.
function Find-Python {
  foreach ($c in @(@("py", "-3"), @("python"), @("python3"))) {
    if (-not (Get-Command $c[0] -ErrorAction SilentlyContinue)) { continue }
    $extra = @($c | Select-Object -Skip 1)
    try { & $c[0] @extra -c "import sys; sys.exit(sys.version_info < (3, 8))" 2>$null | Out-Null; if ($LASTEXITCODE -eq 0) { return $c } } catch {}
  }
  return $null
}
