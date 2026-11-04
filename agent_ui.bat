@echo off
REM One-click start of the browser chat: launches the local model server (if not running), then the web window.
cd /d "%~dp0"
set PIPESIM_PY=D:\Program\Pipesim toolkit\python.exe
powershell -NoProfile -Command "try { Invoke-WebRequest -UseBasicParsing http://127.0.0.1:8080/health -TimeoutSec 2 | Out-Null; exit 0 } catch { exit 1 }"
if errorlevel 1 (
    echo Starting the local model server in its own window...
    start "llama-server (close this window to stop the model)" /min cmd /c start_llm.bat
)
echo Opening the PIPESIM assistant in your browser (http://127.0.0.1:8765). Close this window to stop it.
"%PIPESIM_PY%" webui.py
pause
