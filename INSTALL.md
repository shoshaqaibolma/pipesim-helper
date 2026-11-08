# Installing the PIPESIM Assistant

Three steps, about 30 minutes (mostly waiting for one 5.7 GB download). Everything runs on your PC. No account is
needed, nothing is sent anywhere, and after setup it works without internet.

## What you need

| | Requirement |
|---|---|
| PIPESIM | 2017.1 or later with a licence, **and the PIPESIM Python Toolkit** (a separate SLB installer that comes with the licence). Tested on 2023.1. |
| Computer | Windows 10 or 11, about 8 GB of free disk space |
| Graphics card | NVIDIA with 8 GB or more recommended (e.g. RTX 3060 Ti). Without one it still works, but answers take minutes. |

## 1. Download

On https://github.com/shoshaqaibolma/pipesim-helper click **Code → Download ZIP** and unzip it to a folder of your
choice, for example `C:\PIPESIM Assistant`.

## 2. Install

Double-click **`install.bat`** in that folder. It:

- finds the PIPESIM Python Toolkit by itself (if it cannot, a window asks you to pick its `python.exe`),
- downloads the model server and the language model into the `llm` folder (it asks before the 5.7 GB download;
  an interrupted download continues where it stopped),
- runs a real PIPESIM test simulation to check the licence,
- puts a **PIPESIM Assistant** icon on the desktop and in the Start menu.

If something is missing it says what to do. Fix it and run `install.bat` again: finished downloads are kept.

## 3. Start

Double-click **PIPESIM Assistant** on the desktop. The app opens in its own window. The first start takes up to a
minute while the language model loads (the dot at the top right turns green). Closing the window stops everything.

Try one of the example buttons, or type, for example:
> Build one oil well W1: reservoir 230 bara, depth 2400 m, PI 10 sm3/d/bar. Black oil 32 API, GOR 90, 30 % water
> cut. A 3 km, 100 mm flat flowline goes to a separator at 15 bara. How does the oil rate change if the separator
> pressure goes from 10 to 30 bara?

The assistant asks for anything missing (reply "use defaults" to accept its suggestions), shows a plan, and runs
PIPESIM only after you press **Approve & run**. Results, charts and a report are saved in `runs\<date-time>\`.

## Settings

Click **Settings** in the app to change file locations, the graphics card use and the app options. They are stored in
`settings.toml` in the app folder, which you can also open in Notepad.

## If something goes wrong

| Problem | What to do |
|---|---|
| `install.bat` says the PIPESIM Python Toolkit was not found | Install the toolkit from SLB, open PIPESIM once, run `install.bat` again |
| The PIPESIM check fails | Open PIPESIM once to check the licence. The toolkit version must match the PIPESIM version. |
| "The language model did not start" with an out-of-memory note | Close other programs that use the graphics card, or set the context size to 8192 in Settings |
| The download stops (proxy or firewall) | Run `install.bat` again; it continues. Some company networks block huggingface.co, so ask IT, or copy the model file from a colleague and select it in Settings. |
| Anything else | Details are in the `logs` folder. Running `terminal.bat` shows the same assistant in a text window, with any error messages. |

To uninstall, delete the app folder and the two shortcuts.

## Manual installation (without install.bat)

The standard Python way, for people who prefer to set things up themselves or whose IT blocks scripts. Use the
Python of the PIPESIM Python Toolkit (it has `sixgill`), shown below as `<PIPESIM python>`.

1. Get the code: `git clone https://github.com/shoshaqaibolma/pipesim-helper.git` (or the ZIP).
2. Install the packages: `"<PIPESIM python>" -m pip install -r requirements.txt`
3. Check PIPESIM without the language model: `"<PIPESIM python>" selftest.py "C:\path\to\some_model.pips"`
4. Get the language model yourself:
   - llama.cpp from https://github.com/ggml-org/llama.cpp/releases (the Windows CUDA zip, plus the `cudart` zip
     in the same folder; the CPU zip without an NVIDIA GPU). Tested with build `b12081`.
   - `Qwen3.5-9B-Q4_K_M.gguf` (about 6 GB) from https://huggingface.co/unsloth/Qwen3.5-9B-GGUF
5. Copy `settings.example.toml` to `settings.toml` and set the three paths.
6. Check everything: `"<PIPESIM python>" tools\check_setup.py`
7. Start:

| Command | What it does |
|---|---|
| `"<PIPESIM python>" launch.py` | Model server and app window (what the desktop icon does) |
| `"<PIPESIM python>" launch.py --terminal` | Model server and chat in the console |
| `"<PIPESIM python>" launch.py --model-only` | Only the model server, in the foreground |
| `"<PIPESIM python>" webui.py` / `agent.py` | App or console chat, with a model server you started yourself |

You can also run llama-server yourself with any settings. The app uses whatever answers on the model port (8080 by
default). The command `launch.py` uses is in `settings.py` (`llama_command`). `--jinja` is required for tool calling.

## What is in the folder

- `install.bat`: setup and repair. `start.bat` and `terminal.bat` are created by setup: the app, or the same in a
  text window.
- `settings.toml`: your settings (created by setup). `llm\`: the model server and the language model.
- `runs\`: results of your studies. `projects\`: PIPESIM models the assistant built.
- `docs\VALIDATION.md`: comparison with the PIPESIM case studies. `README.md`: how it works (for developers).
