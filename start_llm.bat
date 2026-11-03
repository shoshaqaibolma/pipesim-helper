@echo off
REM Starts llama.cpp's OpenAI-compatible server with the Saluki GGUF.
REM Download llama.cpp (CUDA build) from https://github.com/ggml-org/llama.cpp/releases
REM and the Saluki 27B GGUF from Underdog's Hugging Face page; set MODEL_PATH below.
set MODEL_PATH=C:\models\saluki-27b.gguf
llama-server.exe -m "%MODEL_PATH%" --jinja -c 32768 -ngl 99 --host 127.0.0.1 --port 8080 --temp 0
REM --jinja  : required for tool calling (uses the model's own chat template)
REM -c 32768 : context size; lower to 16384 if you run out of VRAM
REM -ngl 99  : offload all layers to the GPU
