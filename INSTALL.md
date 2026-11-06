# Installing the PIPESIM AI Assistant on a new PC

About 30–60 minutes, most of it downloading. Everything runs locally: no account, no internet needed after setup,
no model data leaves the PC.

## What you need

| | Requirement | Notes |
|---|---|---|
| OS | Windows 10/11 | PIPESIM is Windows-only |
| PIPESIM | 2023.1 with a licence, **and the PIPESIM Python Toolkit** | tested on 2023.1; the toolkit is a separate installer from SLB |
| GPU | NVIDIA, 8 GB VRAM or more (e.g. RTX 3060 Ti) | works without a GPU, but much slower |
| Disk | about 8 GB free | 6 GB is the language model |

## Step 1 — Get the assistant's files
The code is in a **private** GitHub repository, so the owner must give you access first (or send you a ZIP).
- With access: open https://github.com/shoshaqaibolma/pipesim-helper, switch to the branch `claude/pipesim-agent`,
  then **Code → Download ZIP**, and unzip it, e.g. to `C:\pipesim-assistant`.
- Or with git: `git clone -b claude/pipesim-agent https://github.com/shoshaqaibolma/pipesim-helper.git`

Use a folder path without special characters. Spaces are fine.

## Step 2 — Get the local language model (two downloads)
1. **llama.cpp** (the program that runs the model): go to https://github.com/ggml-org/llama.cpp/releases, open
   the latest release, and download the Windows **CUDA** zip (file name like `llama-…-bin-win-cuda-…-x64.zip`;
   if the release also lists a `cudart-…` zip, download and unzip it into the same folder). Unzip, e.g. to
   `C:\llama.cpp`. The folder must contain `llama-server.exe`.
   No NVIDIA GPU: take the `…-bin-win-cpu-x64.zip` instead.
2. **The model**: on https://huggingface.co search for **Qwen3.5-9B GGUF** (Qwen's own or Unsloth's page),
   open *Files*, and download the file ending in **`Q4_K_M.gguf`** (about 6 GB), e.g. to `C:\models`.

## Step 3 — Run setup
Double-click **`setup.bat`** in the assistant's folder.
1. Notepad opens `config.bat`. Set the three paths and save:
   - `PIPESIM_PY` — the `python.exe` of the PIPESIM Python Toolkit (look in the folder you installed the toolkit
     to, e.g. `C:\Program Files\Schlumberger\PIPESIM Python Toolkit\python.exe`)
   - `LLAMA_DIR` — the folder with `llama-server.exe` from step 2
   - `MODEL_PATH` — the `.gguf` file from step 2
2. Close Notepad. Setup installs two small Python packages (`openai`, `matplotlib`) into PIPESIM's Python, then
   checks everything, including a real PIPESIM test run. Every line should say `OK`; for a `FAIL` it prints the fix.
   Run `setup.bat` again after fixing. (`WARN` for "model server not running" is normal.)

## Step 4 — Start
Double-click **`agent_ui.bat`**. It starts the model (first start takes up to a minute) and opens the assistant
in your browser at http://127.0.0.1:8765. Close the two black windows to stop it.

Try one of the example buttons, or type e.g.:
> Build one oil well W1: reservoir 230 bara, depth 2400 m, PI 10 sm3/d/bar. Black oil 32 API, GOR 90, 30 % water
> cut. A 3 km, 100 mm flat flowline goes to a separator at 15 bara. How does the oil rate change if the separator
> pressure goes from 10 to 30 bara?

The assistant asks for anything missing (reply "use defaults" to accept its suggestions), shows a plan, and runs
PIPESIM when you press **Approve & run**. Results, charts and a report are saved in `runs\<date-time>\`.

## Troubleshooting

| Problem | Fix |
|---|---|
| `setup.bat` says PIPESIM Python not found | `PIPESIM_PY` in `config.bat` must point to the toolkit's `python.exe` |
| "PIPESIM simulation" check fails | open PIPESIM once to check the licence; the toolkit version must match the PIPESIM version |
| Model window closes at once / out of memory | set `LLM_CTX=8192` in `config.bat`; close other GPU programs |
| No NVIDIA GPU | use the CPU llama.cpp build and set `LLM_GPU_LAYERS=0` (answers take minutes) |
| Browser says "could not reach the model" | wait for the model window to finish loading, or run `start_llm.bat` alone to see its error |
| Port 8080 or 8765 already in use | close the other program, or restart the PC |

## What is in the folder
- `agent_ui.bat` — browser chat (main entry); `agent.bat` — the same in a terminal window
- `setup.bat`, `config.example.bat` — setup; your settings live in `config.bat`
- `docs\VALIDATION.md` — comparison with the PIPESIM case studies and test results
- `README.md` — how it works (for developers)
