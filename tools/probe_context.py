"""
Check, on a TEMP COPY of an existing model, how PIPESIM 2023.1 addresses items inside a well and whether
the adapter's boundary handling works there. Writes knowledge/probe_context.json and prints a summary.
  "D:\\Program\\Pipesim toolkit\\python.exe" tools\\probe_context.py "...\\CSN_301_Small Network.pips"
"""
import io, json, os, shutil, sys, tempfile, traceback
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True)
from sixgill import definitions as d
import sixgill_adapter as sa

out = {}


def rec(name, fn):
    try:
        r = fn()
        out[name] = {"ok": True, "result": r}
        print(f"{name}: OK {json.dumps(r, default=str)[:400]}")
        return r
    except Exception as e:
        out[name] = {"ok": False, "error": f"{type(e).__name__}: {e}", "trace": traceback.format_exc(limit=2)[-500:]}
        print(f"{name}: FAILED {type(e).__name__}: {str(e)[:300]}")


def main():
    tmp = tempfile.mkdtemp(prefix="pipesim_ctx_")
    path = os.path.join(tmp, "m.pips")
    shutil.copy2(sys.argv[1], path)
    m = sa.open_model(path, "METRIC")
    comp = m.find(Completion=d.ALL)[0]
    well, item = comp.split(":", 1)
    sinks = [s for s in m.find(Sink=d.ALL) if ":" not in s]
    out["completion"], out["sinks"] = comp, sinks
    sv = [d.SystemVariables.PRESSURE, d.SystemVariables.VOLUME_FLOWRATE_LIQUID_STOCKTANK]

    def rate():
        r = m.tasks.networksimulation.run(system_variables=sv, profile_variables=[])
        return sa.result(r.node, d.SystemVariables.VOLUME_FLOWRATE_LIQUID_STOCKTANK, well)[0]

    rec("keyword form ReservoirPressure", lambda: m.get_value(Well=well, Completion=item, parameter="ReservoirPressure"))
    rec("context form ReservoirPressure", lambda: m.get_value(context=comp, component="Completion", parameter="ReservoirPressure"))
    rec("keyword form LiquidPI (IPR param via completion)", lambda: m.get_value(Well=well, Completion=item, parameter="LiquidPI"))
    rec("keyword form IPRModel", lambda: m.get_value(Well=well, Completion=item, parameter="IPRModel"))
    rec("completion: all values", lambda: m.get_values(Well=well, Completion=item))
    rec("tubing: all values", lambda: m.get_values(Well=well, Tubing=m.find(Tubing=d.ALL)[0].split(":", 1)[1]))
    rec("adapter get_value", lambda: sa.get_value(m, "Completion", comp, "ReservoirPressure"))
    base = rec("well liquid rate, base", rate)
    old = sa.get_param(m, "Completion", comp, "ReservoirPressure")
    rec("adapter set_param ReservoirPressure x1.2", lambda: (sa.set_param(m, "Completion", comp, "ReservoirPressure", old * 1.2),
                                                             sa.get_boundaries(m)[comp]["Pressure"])[1])
    hi = rec("well liquid rate, reservoir pressure x1.2", rate)
    out["verdict_reservoir_pressure"] = "CHANGED" if base is not None and hi is not None and abs(hi - base) > 1e-6 else "UNCHANGED"
    sa.set_param(m, "Completion", comp, "ReservoirPressure", old)
    rec("set_value only (no boundary) then reset_conditions syncs?", lambda: (
        m.set_value(Well=well, Completion=item, parameter="ReservoirPressure", value=old * 0.9),
        sa.get_boundaries(m)[comp]["Pressure"], sa.sync_boundaries(m), sa.get_boundaries(m)[comp]["Pressure"])[1:])
    rec("adapter sink pressure round trip", lambda: (sa.set_param(m, "Sink", sinks[-1], "Pressure", 33.0),
                                                     sa.get_param(m, "Sink", sinks[-1], "Pressure"))[1])
    rec("validate()", lambda: sa.validate(m)[:20])
    m.close()
    shutil.rmtree(tmp, ignore_errors=True)
    os.makedirs(os.path.join(ROOT, "knowledge"), exist_ok=True)
    json.dump(out, open(os.path.join(ROOT, "knowledge", "probe_context.json"), "w"), indent=1, default=str)
    print("verdict, reservoir pressure through the adapter:", out["verdict_reservoir_pressure"])


if __name__ == "__main__":
    main()
