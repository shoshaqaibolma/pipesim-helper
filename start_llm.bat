@echo off
REM Starts llama.cpp's OpenAI-compatible server with the model set in config.bat.
cd /d "%~dp0"
set "CFG=%~dp0config.bat"
if not exist "%CFG%" set "CFG=%~dp0config.example.bat"
call "%CFG%"
if not exist "%LLAMA_DIR%\llama-server.exe" (
    echo llama-server.exe not found in "%LLAMA_DIR%". Fix LLAMA_DIR in config.bat.
    pause
    exit /b 1
)
if not exist "%MODEL_PATH%" (
    echo Model file not found: "%MODEL_PATH%". Fix MODEL_PATH in config.bat.
    pause
    exit /b 1
)
"%LLAMA_DIR%\llama-server.exe" -m "%MODEL_PATH%" --jinja -c %LLM_CTX% -ngl %LLM_GPU_LAYERS% -fa on --reasoning-budget 0 --host 127.0.0.1 --port 8080 --temp 0
REM --jinja   : required for tool calling (uses the model's own chat template)
REM -c        : context size (LLM_CTX in config.bat)
REM -ngl      : layers on the GPU (LLM_GPU_LAYERS in config.bat)
REM -fa on    : flash attention, which saves VRAM (older builds use plain -fa)
REM --reasoning-budget 0 : thinking off; Qwen 3.5 otherwise thinks until the context is full
