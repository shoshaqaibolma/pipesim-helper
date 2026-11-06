@echo off
REM ---------------------------------------------------------------------------------------------
REM  Settings for this PC. setup.bat copies this file to config.bat; edit config.bat, not this one.
REM  Every .bat in this folder reads config.bat.
REM ---------------------------------------------------------------------------------------------

REM 1. The Python that comes with the PIPESIM Python Toolkit (it has the "sixgill" package).
REM    Typical places: "C:\Program Files\Schlumberger\PIPESIM Python Toolkit\python.exe"
REM    or the folder you chose when installing the toolkit.
set PIPESIM_PY=D:\Program\Pipesim toolkit\python.exe

REM 2. Folder that contains llama-server.exe (unzipped llama.cpp release, CUDA build for NVIDIA GPUs).
set LLAMA_DIR=D:\llama.cpp\b12081

REM 3. The language model file (.gguf). Recommended: Qwen 3.5 9B, Q4_K_M (about 6 GB).
set MODEL_PATH=D:\models\Qwen3.5-9B-Q4_K_M.gguf

REM 4. Optional tuning.
REM    LLM_CTX: context size in tokens. 16384 fits an 8 GB GPU; use 8192 if you get out-of-memory errors.
REM    LLM_GPU_LAYERS: 99 = whole model on the GPU. 0 = CPU only (works without a GPU, but 5-20x slower).
set LLM_CTX=16384
set LLM_GPU_LAYERS=99
