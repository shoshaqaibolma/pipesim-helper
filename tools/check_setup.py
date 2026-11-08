"""
Checks an installation step by step and says how to fix what is missing. Run with PIPESIM's Python:

  "<PIPESIM toolkit>\\python.exe" tools\\check_setup.py      (install.bat does this for you)

Checks: Python packages, the PIPESIM Python Toolkit (sixgill), a real PIPESIM simulation (licence and engine),
the model server program and the model file from settings.toml, and the GPU. Exit code 1 if something failed.
"""
import os, shutil, subprocess, sys, tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import settings

QUIET = "--quiet" in sys.argv
results = []


def report(name, ok, detail="", fix=""):
    results.append(ok)
    print(f"      [{'OK' if ok else 'FAIL' if ok is False else 'WARN'}] {name}" + (f": {detail}" if detail else ""))
    if not ok and fix:
        print(f"             fix: {fix}")


if not QUIET:
    print(f"Python {sys.version.split()[0]} at {sys.executable}\n")

# 1. packages
for mod in ("openai", "matplotlib"):
    try:
        __import__(mod)
        report(f"package {mod}", True)
    except Exception as e:
        report(f"package {mod}", False, str(e), "run install.bat again")

# 2. PIPESIM Python Toolkit
try:
    import sixgill
    report("PIPESIM Python Toolkit (sixgill)", True, getattr(sixgill, "__version__", "") or os.path.dirname(sixgill.__file__))
    have_sixgill = True
except Exception as e:
    have_sixgill = False
    report("PIPESIM Python Toolkit (sixgill)", False, str(e),
           "run install.bat; it finds the PIPESIM Python Toolkit or lets you pick its python.exe")

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

# 4. model server program and model file
cfg = settings.load()
llama = cfg["paths"]["llama_server"]
report("model server program", bool(llama) and os.path.isfile(llama), llama or "not set",
       "run install.bat to download it, or set it in the app under Settings")
model = cfg["paths"]["model"]
if model and os.path.isfile(model):
    report("language model file", True, f"{model} ({os.path.getsize(model) / 1e9:.1f} GB)")
else:
    report("language model file", False, model or "not set",
           "run install.bat to download it, or set it in the app under Settings")

# 5. GPU
try:
    out = subprocess.run(["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader"],
                         capture_output=True, text=True, timeout=10).stdout.strip()
    report("NVIDIA GPU", bool(out) or None, out or "none found: the model runs on the processor (slower)")
except Exception:
    report("NVIDIA GPU", None, "none found: the model runs on the processor (works, but answers take longer)")

ok = all(r is not False for r in results)
if not QUIET:
    print()
    print("All set. Open 'PIPESIM Assistant' from the desktop shortcut." if ok else
          "Some checks failed: fix the items marked FAIL (see 'fix:'), then run install.bat again.")
sys.exit(0 if ok else 1)
