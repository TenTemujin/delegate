@echo off
rem Windows launcher (untested): starts the monitor if needed and opens the browser.
set PORT=8765
where python >nul 2>nul && (set PY=python) || (set PY=py)
powershell -NoProfile -Command "try{(Invoke-WebRequest -UseBasicParsing http://127.0.0.1:%PORT%/api/stats -TimeoutSec 1)|Out-Null}catch{Start-Process -WindowStyle Hidden %PY% '\"%~dp0monitor.py\" --port %PORT%'; Start-Sleep 2}"
start "" http://127.0.0.1:%PORT%
