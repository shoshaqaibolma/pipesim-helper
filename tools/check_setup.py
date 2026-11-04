"""
Checks a new installation step by step and says how to fix what is missing. Run with PIPESIM's Python:

  "<PIPESIM toolkit>\\python.exe" tools\\check_setup.py      (setup.bat does this for you)

Checks: Python packages, the PIPESIM Python Toolkit (sixgill), a real PIPESIM simulation (licence and engine),
llama-server and the model file from config.bat, the GPU, and whether the model server answers.
"""
import os, re, shutil, subprocess, sys, tempfile, urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
results = []


def report(name, ok, detail="", fix=""):
    results.append(ok)
    print(f"[{'OK' if ok else 'FAIL' if ok is False else 'WARN'}] {name}" + (f": {detail}" if detail else ""))
    if not ok and fix:
        print(f"       fix: {fix}")


def config():
    path = os.path.join(ROOT, "config.bat")
    if not os.path.exists(path):
        path = os.path.join(ROOT, "config.example.bat")
    vals = {}
    for line in open(path, encoding="utf-8", errors="replace"):
        m = re.match(r"\s*set\s+(\w+)=(.*)$", line, re.I)
        if m:
            vals[m.group(1).upper()] = m.group(2).strip().strip('"')
    return path, vals


print(f"Python {sys.version.split()[0]} at {sys.executable}\n")

# 1. packages
for mod, pip_name in (("openai", "openai"), ("matplotlib", "matplotlib")):
    try:
        __import__(mod)
        report(f"package {pip_name}", True)
    except Exception as e:
        report(f"package {pip_name}", False, str(e), f'"{sys.executable}" -m pip install -r requirements.txt')

# 2. PIPESIM Python Toolkit
try:
    import sixgill
    report("PIPESIM Python Toolkit (sixgill)", True, getattr(sixgill, "__version__", "") or os.path.dirname(sixgill.__file__))
    have_sixgill = True
except Exception as e:
    have_sixgill = False
    report("PIPESIM Python Toolkit (sixgill)", False, str(e),
           "set PIPESIM_PY in config.bat to the python.exe that comes with the PIPESIM Python Toolkit")

# 3. a real simulation: builds a 1-well model in a temp folder and runs it (needs the PIPESIM licence)
if have_sixgill:
    try:
        import netbuilder
        project = {"name": "Setup check", "fluids": [{"name": "BO", "type": "black_oil", "api": 35, "gor": 100,
                                                      "water_cut": 20, "gas_sg": 0.7}],
                   "wells": [{"name": "W1", "fluid": "BO", "reservoir_pressure": 250, "reservoir_temperature": 90,
                              "depth": 2500, "tubing_id": 76, "ipr": {"model": "pi", "liquid_pi": 10}}],
                   "sinks": [{"name": "SEP", "pressure": 15}],
                   "flowlines": [{"name": "FL-W1", "from": "W1", "to": "SEP", "length": 2000, "id": 100,
                                  "elevation_change": 0}]}
        tmp = tempfile.mkdtemp(prefix="pipesim_check_")
        model, rep = netbuilder.build(project, os.path.join(tmp, "check.pips"))
        try:
            res = model.tasks.networksimulation.run()
            q = res.node["VolumeFlowrateLiquidStockTank"]["SEP"]
            report("PIPESIM simulation (licence + engine)", isinstance(q, (int, float)) and q > 0,
                   f"test well flows {q:.0f} sm3/d" if isinstance(q, (int, float)) else str(q))
        finally:
            model.close()
            shutil.rmtree(tmp, ignore_errors=True)
    except Exception as e:
        report("PIPESIM simulation (licence + engine)", False, f"{type(e).__name__}: {str(e)[:300]}",
               "open PIPESIM once to check the licence; the toolkit version must match the PIPESIM install")

# 4. model server files
cfg_path, cfg = config()
print(f"\nSettings from {os.path.basename(cfg_path)}")
llama = os.path.join(cfg.get("LLAMA_DIR", ""), "llama-server.exe")
report("llama-server.exe", os.path.exists(llama), llama,
       "download a llama.cpp release (CUDA build for NVIDIA) and set LLAMA_DIR in config.bat")
model = cfg.get("MODEL_PATH", "")
if os.path.exists(model):
    report("model file", True, f"{model} ({os.path.getsize(model) / 1e9:.1f} GB)")
else:
    report("model file", False, model, "download the Qwen 3.5 9B Q4_K_M .gguf and set MODEL_PATH in config.bat")

# 5. GPU
try:
    out = subprocess.run(["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader"],
                         capture_output=True, text=True, timeout=10).stdout.strip()
    report("NVIDIA GPU", bool(out), out or "none found")
except Exception:
    report("NVIDIA GPU", None, "nvidia-smi not found. Without a GPU set LLM_GPU_LAYERS=0 in config.bat "
                               "(works, but answers take much longer)")

# 6. model server running?
try:
    ok = urllib.request.urlopen("http://127.0.0.1:8080/health", timeout=3).status == 200
    report("model server", ok, "answering on http://127.0.0.1:8080")
except Exception:
    report("model server", None, "not running now (normal: agent_ui.bat starts it)")

print()
if all(r is not False for r in results):
    print("All set. Double-click agent_ui.bat to open the assistant in your browser.")
else:
    print("Some checks failed: fix the items marked FAIL (see 'fix:'), then run setup.bat again.")
