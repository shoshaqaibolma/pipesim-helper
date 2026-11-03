# PIPESIM Local Agent

A local AI assistant that operates SLB PIPESIM: it opens models, reads and changes parameters, runs
network and P/T profile simulations, and explains the results. Everything runs on your own PC.
No model data leaves the machine.

```
 you (terminal)
      │
  agent.py ──HTTP──► llama-server (Saluki 27B GGUF, GPU)       ← local LLM, OpenAI-compatible API
      │
  pipesim_tools.py ──► sixgill (PIPESIM Python Toolkit) ──► PIPESIM engine / .pips model
      │
  mcp_server.py (optional) ──► same tools for Claude Desktop / LM Studio / other MCP clients
```

## 1. Prerequisites (Windows PC with PIPESIM)
- PIPESIM 2017.1 or later with a core license. The Python Toolkit is included with that license.
- An NVIDIA GPU with about 12 GB of VRAM or more. The Saluki file is about 7.9 GB, plus room for the context cache.
- The Python environment that has `sixgill`. The PIPESIM installer ships the toolkit. Either use its bundled
  Python, or `pip install` the sixgill wheel from the PIPESIM install folder into your own venv.

## 2. Install
```bat
cd pipesim-agent
python -m pip install -r requirements.txt
python selftest.py "C:\path\to\some_model.pips"
```
The self-test needs no LLM. If it fails, the cause is a sixgill API difference in your PIPESIM version.
Adjust `pipesim_tools.py` using PIPESIM's Python Toolkit help, which has the exact signatures.

## 3. Start the local model
1. Download a CUDA build of llama.cpp: https://github.com/ggml-org/llama.cpp/releases
2. Download the Saluki 27B GGUF from Underdog's Hugging Face page.
3. Set `MODEL_PATH` in `start_llm.bat` and run it. `--jinja` is required for tool calling.

## 4. Run
```bat
python agent.py
```
Describe the study in plain language. The agent works through it with you:

| Step | What happens | Who decides |
|---|---|---|
| Understand | Your request becomes a structured study spec (`study.py`) | LLM |
| Ask | A checker lists every required input you didn't give, with suggested defaults | **Code** (cannot be skipped) |
| Plan | A readable plan: model, cases, outputs, number of runs | You approve in chat |
| Run | `executor.py` runs every case. The LLM does not drive individual runs | You confirm `y` in the terminal |
| Analyze | CSV, charts and `report.md` in `runs/<timestamp>/`. The LLM explains the trends | LLM |

Analysis types: `single_run`, `sweep` (1 variable), `grid` (2-3 variables, full factorial),
`tornado` (low/high per variable, ranked), `pt_profile`.
Models: an **existing .pips** (always run on a copy), or **built from a description** (template `single_well`).

Example:
> *"New single-well oil model, reservoir at 260 bar. How does water cut from 0 to 80% affect oil rate?"*
> → the agent asks for the 13 missing inputs (temperature, PI, depths, IDs, fluid...) with defaults
> → you reply "use defaults, but tubing ID 62 mm" → plan → approve → 6 runs → chart and explanation.

Terminal commands: `spec` shows the current spec, `reset` starts a new study.

## Tests (no PIPESIM or LLM needed)
`python tests/test_workflow.py` runs the whole workflow against a fake `sixgill` with a toy formula.
It only checks the plumbing. The numbers it produces mean nothing.

## Adding templates and analyses
- New model template: add a field table, aliases and a build function in `builder.py`.
- New analysis: add it to `study.ANALYSES` and to `check()`, then add a branch in `executor.run()`.

## Tuning for a small local model
- Temperature is 0 and thinking is off for tool calls. Low-bit quantizations reason less well, so the
  tools are coarse-grained and return compact, downsampled JSON.
- If the model guesses parameter names, add the exact names your models use (from the Python Toolkit
  `Parameters` reference) to the system prompt in `agent.py`.
- Swapping models only needs a new GGUF. Any llama.cpp model with tool calling works,
  for example a non-quantized Qwen if you have more VRAM.

## Using it from Claude or other MCP clients
Run `python mcp_server.py` (needs Python 3.10 or later and `pip install mcp`) and register it as a stdio MCP server.
