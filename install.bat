@echo off
REM PIPESIM Assistant setup: double-click this file. Safe to run again (repairs or updates the installation).
title PIPESIM Assistant setup
cd /d "%~dp0"
echo Looking for the PIPESIM Python Toolkit on this PC...
set "PY="
for /f "usebackq delims=" %%p in (`powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0tools\find_pipesim_python.ps1"`) do set "PY=%%p"
if not defined PY (
    echo.
    echo  The PIPESIM Python Toolkit was not found.
    echo  It is a separate installer from SLB that comes with the PIPESIM licence.
    echo  Install it, open PIPESIM once to check the licence, then run install.bat again.
    echo.
    pause
    exit /b 1
)
echo Found: %PY%
"%PY%" "%~dp0tools\install.py" %*
if errorlevel 1 exit /b 1
echo.
pause
