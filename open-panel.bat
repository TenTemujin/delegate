@echo off
rem Windows launcher: starts the control panel (hidden) if needed and opens the browser.
rem Usage: open-panel.bat      env: AGY_PANEL_PORT (default 8765)
if "%AGY_PANEL_PORT%"=="" set AGY_PANEL_PORT=8765
powershell -NoProfile -ExecutionPolicy Bypass -Command ". '%~dp0find-python.ps1'; $py = Find-Python; if (-not $py) { Write-Error 'Python 3.8+ not found'; exit 1 }; $u='http://127.0.0.1:%AGY_PANEL_PORT%'; try { (Invoke-WebRequest -UseBasicParsing \"$u/api/ping\" -TimeoutSec 1) | Out-Null } catch { $a = @($py | Select-Object -Skip 1) + @(\"`\"%~dp0panel.py`\"\", '--port', '%AGY_PANEL_PORT%', '--no-open'); Start-Process -WindowStyle Hidden $py[0] -ArgumentList $a; for ($i=0; $i -lt 25; $i++) { Start-Sleep -Milliseconds 200; try { (Invoke-WebRequest -UseBasicParsing \"$u/api/ping\" -TimeoutSec 1) | Out-Null; break } catch {} } }; Start-Process $u"
