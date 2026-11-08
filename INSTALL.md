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

## What is in the folder

- `install.bat`: setup and repair. `start.bat` and `terminal.bat` are created by setup: the app, or the same in a
  text window.
- `settings.toml`: your settings (created by setup). `llm\`: the model server and the language model.
- `runs\`: results of your studies. `projects\`: PIPESIM models the assistant built.
- `docs\VALIDATION.md`: comparison with the PIPESIM case studies. `README.md`: how it works (for developers).
