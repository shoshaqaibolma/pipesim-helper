@echo off
REM Starts llama.cpp's OpenAI-compatible server with Qwen 3.5 9B (sized for an 8 GB GPU such as an RTX 3060 Ti).
REM 1. Download a recent llama.cpp CUDA build: https://github.com/ggml-org/llama.cpp/releases
REM 2. Download the Qwen 3.5 9B Q4_K_M GGUF (about 6 GB) from Unsloth's or Qwen's Hugging Face page.
REM 3. Set MODEL_PATH below.
REM Alternative if tool calls come out malformed: Gemma 4 E4B (about 5 GB). Swap MODEL_PATH only.
set MODEL_PATH=C:\models\Qwen3.5-9B-Q4_K_M.gguf
llama-server.exe -m "%MODEL_PATH%" --jinja -c 16384 -ngl 99 -fa on --host 127.0.0.1 --port 8080 --temp 0
REM --jinja   : required for tool calling (uses the model's own chat template)
REM -c 16384  : context size; drop to 8192 if you get out-of-memory errors
REM -ngl 99   : keep the whole model on the GPU (it fits in 8 GB at Q4)
REM -fa on    : flash attention, which saves VRAM (older builds use plain -fa)
