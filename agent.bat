@echo off
REM One-click start: launches the local model server (if it is not running yet), waits for it, then the agent.
cd /d "%~dp0"
if exist config.bat (call config.bat) else (call config.example.bat)
powershell -NoProfile -Command "try { Invoke-WebRequest -UseBasicParsing http://127.0.0.1:8080/health -TimeoutSec 2 | Out-Null; exit 0 } catch { exit 1 }"
if errorlevel 1 (
    echo Starting the local model server in its own window...
    start "llama-server (close this window to stop the model)" /min cmd /c start_llm.bat
    powershell -NoProfile -Command "for ($i = 0; $i -lt 120; $i++) { try { Invoke-WebRequest -UseBasicParsing http://127.0.0.1:8080/health -TimeoutSec 2 | Out-Null; exit 0 } catch { Start-Sleep 1 } }; exit 1"
    if errorlevel 1 (
        echo The model server did not start. Run start_llm.bat on its own to see the error.
        pause
        exit /b 1
    )
)
"%PIPESIM_PY%" agent.py
pause
