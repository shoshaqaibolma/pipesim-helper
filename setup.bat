@echo off
REM One-time setup on a new PC: creates config.bat, installs the two Python packages into PIPESIM's Python,
REM and checks everything (PIPESIM licence, model files, GPU). Safe to run again.
cd /d "%~dp0"
if not exist config.bat (
    copy /y config.example.bat config.bat >nul
    echo.
    echo  config.bat was created. Notepad opens it now: set the three paths, save, close Notepad.
    echo.
    notepad config.bat
)
call "%~dp0config.bat"
if not exist "%PIPESIM_PY%" (
    echo.
    echo  PIPESIM Python not found: "%PIPESIM_PY%"
    echo  Set PIPESIM_PY in config.bat to the python.exe of the PIPESIM Python Toolkit, then run setup.bat again.
    pause
    exit /b 1
)
echo.
echo == Installing Python packages into "%PIPESIM_PY%"
"%PIPESIM_PY%" -m pip install -r requirements.txt
echo.
echo == Checking the setup
"%PIPESIM_PY%" tools\check_setup.py
pause
