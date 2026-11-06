"""
Read-only probe for the next features: what nodal analysis returns, separator port constants, and the units of
pump/compressor power. Builds one test well in %TEMP% and uses temp copies of two case studies.
Writes knowledge/probe_nodal.json.
  "D:\\Program\\Pipesim toolkit\\python.exe" tools\\probe_nodal.py "D:\\Program\\Pipesim2023.1\\Case Studies"
"""
import json, os, shutil, sys, tempfile, traceback
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from sixgill import definitions as d
import netbuilder, sixgill_adapter as sa

out = {}


def js(o, depth=0, maxlist=12):
    if depth > 6:
        return str(o)[:200]
    if hasattr(o, "to_dict"):
        try:
            o = o.to_dict()
        except Exception:
            pass
    if isinstance(o, dict):
        return {str(k): js(v, depth + 1) for k, v in list(o.items())[:60]}
    if isinstance(o, (list, tuple)):
        return [js(v, depth + 1) for v in o[:maxlist]] + ([f"... {len(o)} items"] if len(o) > maxlist else [])
    if o is None or isinstance(o, (int, float, str, bool)):
        return o
    return str(o)[:300]


def shape(r):
    """Describe a result object: its public attributes and the structure of each."""
    s = {"type": type(r).__name__}
    for a in dir(r):
        if a.startswith("_"):
            continue
        try:
            v = getattr(r, a)
        except Exception as e:
            s[a] = f"<error {e}>"
            continue
        if callable(v):
            continue
        s[a] = js(v)
    return s


def rec(name, fn):
    try:
        out[name] = {"ok": True, "result": fn()}
        print(f"{name}: OK {json.dumps(out[name]['result'], default=str)[:600]}", flush=True)
    except Exception as e:
        out[name] = {"ok": False, "error": f"{type(e).__name__}: {e}", "trace": traceback.format_exc(limit=3)[-900:]}
        print(f"{name}: FAILED {type(e).__name__}: {str(e)[:400]}", flush=True)


def find(root, stem):
    for dp, _, fs in os.walk(root):
        for f in fs:
            if os.path.splitext(f)[0].replace(" ", "_").lower() == stem.lower() and f.lower().endswith(".pips"):
                return os.path.join(dp, f)


def main():
    root = sys.argv[1]
    sep = getattr(d.Connection, "Separator", None)
    rec("Connection.Separator values", lambda: {k: js(getattr(sep, k)) for k in dir(sep) if not k.startswith("_")})
    tmp = tempfile.mkdtemp(prefix="pipesim_nodal_")
    # 1. units of equipment parameters on CSN_301
    p = find(root, "CSN_301_Small_Network")
    if p:
        c = os.path.join(tmp, "csn301.pips"); shutil.copy2(p, c)
        m = sa.open_model(c)
        rec("units: pump power", lambda: m.describe(context="Pmp", parameter="Power").units)
        rec("units: compressor power", lambda: m.describe(context="Compressor", parameter="Power").units)
        rec("units: compressor pressure differential", lambda: m.describe(context="Compressor", parameter="PressureDifferential").units)
        rec("units: separator efficiency", lambda: m.describe(context="Separator", parameter="Efficiency").units)
        m.close()
    # 2. nodal analysis on a well we build
    well = {"name": "Nodal test", "fluids": [{"name": "BO", "type": "black_oil", "api": 35, "gor": 100, "water_cut": 20,
                                              "gas_sg": 0.7}],
            "wells": [{"name": "W1", "fluid": "BO", "reservoir_pressure": 250, "reservoir_temperature": 90,
                       "ipr": {"model": "pi", "liquid_pi": 10}, "depth": 2500, "tubing_id": 76,
                       "gas_lift": {"depth": 2000, "rate": 0.05}}],
            "sinks": [{"name": "SEP", "pressure": 15}],
            "flowlines": [{"name": "FL", "from": "W1", "to": "SEP", "length": 2000, "id": 100, "elevation_change": 0}]}
    try:
        m, rep = netbuilder.build(well, os.path.join(tmp, "nodal_well.pips"))
        out["build"] = js(rep)
        na = m.tasks.nodalanalysis
        rec("built well: nodalanalysis.get_conditions(W1)", lambda: js(na.get_conditions("W1")))
        rec("built well: nodalanalysis.run(W1, OutletPressure=20)", lambda: shape(
            na.run("W1", parameters={d.Parameters.NodalAnalysisSimulation.OUTLETPRESSURE: 20})))
        m.close()
    except Exception:
        out["build_error"] = traceback.format_exc()[-1200:]
        print(out["build_error"])
    # 3. nodal analysis as set up in the Nodal_example case study
    p = find(root, "Nodal_example")
    if p:
        c = os.path.join(tmp, "nodal_example.pips"); shutil.copy2(p, c)
        m = sa.open_model(c)
        wells = [w for w in m.find(Well=d.ALL) if ":" not in w]
        out["nodal_example_wells"] = wells
        na = m.tasks.nodalanalysis
        rec("Nodal_example: get_conditions(first well)", lambda: js(na.get_conditions(wells[0])))
        rec("Nodal_example: run(first well) with its own settings", lambda: shape(na.run(wells[0])))
        m.close()
    shutil.rmtree(tmp, ignore_errors=True)
    os.makedirs(os.path.join(ROOT, "knowledge"), exist_ok=True)
    json.dump(out, open(os.path.join(ROOT, "knowledge", "probe_nodal.json"), "w"), indent=1, default=str)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
    main()
