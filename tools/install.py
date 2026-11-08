"""
Installs the PIPESIM Assistant on this PC. install.bat finds PIPESIM's Python and runs this file with it.

1. installs two Python packages into PIPESIM's Python (openai, matplotlib)
2. downloads the model server (llama.cpp, about 0.7 GB with GPU support) and the language model (5.7 GB),
   unless they are already on the PC; everything goes into the llm\\ folder next to this project
3. writes settings.toml, checks PIPESIM with a real test simulation, and makes a desktop shortcut

Safe to run again: finished downloads are kept, an interrupted download resumes.
  --yes   answer yes to every question (unattended install)
"""
import hashlib, os, shutil, subprocess, sys, time, urllib.request, zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import settings

LLM_DIR = os.path.join(ROOT, "llm")
LLAMA_BUILD = "b12081"      # the llama.cpp build this project is tested with
RELEASE = f"https://github.com/ggml-org/llama.cpp/releases/download/{LLAMA_BUILD}/"
LLAMA_ZIPS = {"gpu": [f"llama-{LLAMA_BUILD}-bin-win-cuda-12.4-x64.zip", "cudart-llama-bin-win-cuda-12.4-x64.zip"],
              "cpu": [f"llama-{LLAMA_BUILD}-bin-win-cpu-x64.zip"]}
MODEL = {"file": "Qwen3.5-9B-Q4_K_M.gguf", "size": 5680522464,
         "url": "https://huggingface.co/unsloth/Qwen3.5-9B-GGUF/resolve/main/Qwen3.5-9B-Q4_K_M.gguf",
         "sha256": "03b74727a860a56338e042c4420bb3f04b2fec5734175f4cb9fa853daf52b7e8"}
YES = "--yes" in sys.argv
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def say(text=""):
    print(text, flush=True)


def step(n, text):
    say(f"\n[{n}/6] {text}")


def ask(question, default=True):
    if YES:
        return True
    hint = "[Y/n]" if default else "[y/N]"
    try:
        a = input(f"      {question} {hint} ").strip().lower()
    except EOFError:
        return default
    return default if not a else a.startswith("y")


def fail(text):
    say(f"\n  PROBLEM: {text}")
    say("  Fix it and run install.bat again (finished downloads are kept).")
    input("\nPress Enter to close.") if not YES else None
    sys.exit(1)


def download(url, dest, size=None):
    """Download with a progress line; resumes a partial download (dest + '.part')."""
    part = dest + ".part"
    have = os.path.getsize(part) if os.path.exists(part) else 0
    req = urllib.request.Request(url, headers={"User-Agent": "pipesim-assistant-installer",
                                               **({"Range": f"bytes={have}-"} if have else {})})
    for attempt in range(5):
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                if have and r.status != 206:        # server ignored the resume request: start over
                    have = 0
                total = (int(r.headers.get("Content-Length") or 0) + have) or size or 0
                mode, t0, done = ("ab" if have else "wb"), time.time(), have
                with open(part, mode) as f:
                    while True:
                        chunk = r.read(1 << 20)
                        if not chunk:
                            break
                        f.write(chunk)
                        done += len(chunk)
                        speed = (done - have) / max(time.time() - t0, 0.1) / 1e6
                        pct = f"{done / total * 100:5.1f} %" if total else ""
                        print(f"\r      {os.path.basename(dest)}: {pct}  {done / 1e9:.2f} GB  ({speed:.1f} MB/s)   ",
                              end="", flush=True)
            print()
            os.replace(part, dest)
            return
        except Exception as e:
            print()
            if attempt == 4:
                fail(f"download of {url} failed: {e}. Check the internet connection.")
            say(f"      connection problem ({e}); retrying in 10 s...")
            time.sleep(10)
            have = os.path.getsize(part) if os.path.exists(part) else 0
            req = urllib.request.Request(url, headers={"User-Agent": "pipesim-assistant-installer",
                                                       **({"Range": f"bytes={have}-"} if have else {})})


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 24), b""):
            h.update(chunk)
    return h.hexdigest()


def gpu():
    """(name, memory in GB) of the NVIDIA GPU, or None."""
    try:
        out = subprocess.run(["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"],
                             capture_output=True, text=True, timeout=15, creationflags=NO_WINDOW).stdout.strip()
        name, mem = out.splitlines()[0].rsplit(",", 1)
        return name.strip(), float(mem) / 1024
    except Exception:
        return None


def powershell(script):
    return subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
                          capture_output=True, text=True, creationflags=NO_WINDOW)


def shortcut(folder_ps, name, target, args, icon):
    ps = (f"$d = [Environment]::GetFolderPath('{folder_ps}'); $s = (New-Object -ComObject WScript.Shell)"
          f".CreateShortcut((Join-Path $d '{name}.lnk')); $s.TargetPath = '{target}'; $s.Arguments = '{args}'; "
          f"$s.WorkingDirectory = '{ROOT}'; $s.IconLocation = '{icon}'; "
          "$s.Description = 'PIPESIM Assistant: plain-language PIPESIM studies with a local AI model'; $s.Save(); "
          f"Join-Path $d '{name}.lnk'")
    r = powershell(ps)
    return r.stdout.strip() if r.returncode == 0 else None


def main():
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    say("=" * 70)
    say(" PIPESIM Assistant setup")
    say(" Everything stays on this PC. The first install downloads about 6.5 GB.")
    say("=" * 70)
    s = settings.load()
    s["paths"]["pipesim_python"] = sys.executable

    step(1, "Python packages")
    r = subprocess.run([sys.executable, "-m", "pip", "install", "-q", "--disable-pip-version-check",
                        "-r", os.path.join(ROOT, "requirements.txt")], capture_output=True, text=True)
    if r.returncode:
        say(r.stdout[-2000:] + r.stderr[-2000:])
        fail("could not install the Python packages (openai, matplotlib). Is the internet connection blocked "
             "by a proxy? Ask IT, or run install.bat as the user who installed PIPESIM.")
    say("      OK")

    step(2, "Graphics card")
    g = gpu()
    if g:
        say(f"      {g[0]}, {g[1]:.0f} GB: the model runs on the GPU")
        s["model"]["gpu_layers"] = 99
        if g[1] < 7.5:
            s["model"]["context"] = 8192
            say("      less than 8 GB of graphics memory: using a smaller context (8192) so the model fits")
    else:
        say("      no NVIDIA graphics card found: the model runs on the processor (works, but answers are slow)")
        s["model"]["gpu_layers"] = 0

    step(3, "Model server (llama.cpp)")
    exe = s["paths"]["llama_server"]
    if exe and os.path.isfile(exe):
        say(f"      already installed: {exe}")
    else:
        kind = "gpu" if g else "cpu"
        target = os.path.join(LLM_DIR, f"llama.cpp-{LLAMA_BUILD}-{kind}")
        os.makedirs(os.path.join(LLM_DIR, "downloads"), exist_ok=True)
        for z in LLAMA_ZIPS[kind]:
            zp = os.path.join(LLM_DIR, "downloads", z)
            if not os.path.exists(zp):
                download(RELEASE + z, zp)
            with zipfile.ZipFile(zp) as zf:
                zf.extractall(target)
        found = [os.path.join(dp, "llama-server.exe") for dp, _, fs in os.walk(target) if "llama-server.exe" in fs]
        if not found:
            fail(f"llama-server.exe was not in the download ({target}).")
        s["paths"]["llama_server"] = found[0]
        shutil.rmtree(os.path.join(LLM_DIR, "downloads"), ignore_errors=True)
        say(f"      installed: {found[0]}")

    step(4, "Language model (Qwen 3.5 9B, 5.7 GB)")
    path = s["paths"]["model"]
    if path and os.path.isfile(path):
        say(f"      already on this PC: {path}")
    else:
        dest = os.path.join(LLM_DIR, "models", MODEL["file"])
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        if not os.path.exists(dest):
            free = shutil.disk_usage(os.path.dirname(dest)).free
            part = os.path.getsize(dest + ".part") if os.path.exists(dest + ".part") else 0
            if free < MODEL["size"] - part + 5e8:
                fail(f"not enough disk space on {os.path.splitdrive(dest)[0]} for the model: "
                     f"{(MODEL['size'] - part) / 1e9:.1f} GB needed, {free / 1e9:.1f} GB free.")
            if not ask(f"Download the language model now ({(MODEL['size'] - part) / 1e9:.1f} GB from Hugging Face)?"):
                fail("the language model is needed. Run install.bat again when you are ready to download it.")
            download(MODEL["url"], dest, MODEL["size"])
            say("      checking the download...")
            if sha256(dest) != MODEL["sha256"]:
                os.remove(dest)
                fail("the downloaded model file is damaged and was deleted. Run install.bat again to download it again.")
        s["paths"]["model"] = dest
        say(f"      OK: {dest}")
    settings.save(s)

    step(5, "Checking PIPESIM (a real test simulation; needs the PIPESIM licence)")
    r = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "check_setup.py"), "--quiet"])
    if r.returncode:
        fail("the check above found a problem.")

    step(6, "Shortcuts")
    pyw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
    pyw = pyw if os.path.exists(pyw) else sys.executable
    launch = os.path.join(ROOT, "launch.py")
    icon = os.path.join(ROOT, "assets", "app.ico")
    made = [p for p in (shortcut("Desktop", "PIPESIM Assistant", pyw, f'"{launch}"', icon),
                        shortcut("Programs", "PIPESIM Assistant", pyw, f'"{launch}"', icon)) if p]
    with open(os.path.join(ROOT, "start.bat"), "w", newline="\r\n") as f:   # for people who prefer the folder
        f.write(f'@echo off\nstart "" "{pyw}" "{launch}"\n')
    with open(os.path.join(ROOT, "terminal.bat"), "w", newline="\r\n") as f:
        f.write(f'@echo off\ncd /d "%~dp0"\n"{sys.executable}" "{launch}" --terminal\npause\n')
    for p in made:
        say(f"      {p}")
    say("      start.bat in this folder does the same")

    say("\n" + "=" * 70)
    say(" Done. Open 'PIPESIM Assistant' from the desktop or the Start menu.")
    say(" Settings (paths, GPU, ...) are in the app under Settings, or in settings.toml.")
    say("=" * 70)
    if ask("Start the assistant now?"):
        subprocess.Popen([pyw, launch], cwd=ROOT, creationflags=getattr(subprocess, "DETACHED_PROCESS", 0))


if __name__ == "__main__":
    main()
