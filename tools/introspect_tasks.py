"""
Record the simulation-task API (nodal analysis, P/T profile, optimizer, ...), connection ports, extra definitions,
and the parameter values of equipment (separators, pumps, compressors, gas lift, ESP) in case studies that use them.
Read-only: every model is opened from a TEMP COPY. Writes knowledge/tasks.json.
  "D:\\Program\\Pipesim toolkit\\python.exe" tools\\introspect_tasks.py "D:\\Program\\Pipesim2023.1\\Case Studies"
"""
import inspect, json, os, shutil, sys, tempfile, traceback
from sixgill.pipesim import Model
from sixgill import definitions as d

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EQUIPMENT = ["TwoPhaseSeparator", "ThreePhaseSeparator", "Pump", "Compressor", "GasLiftInjection", "ESP", "Choke",
             "HeatExchanger", "MultiplierAdder", "Injector", "CheckValve", "Packer", "SubsurfaceSafetyValve"]
WANTED = ["CSN_301_Small Network", "CSN_312_Gas_Lift_Optimization", "CSN_313_ESP_Optimization", "Nodal_example",
          "TF_M3B_Final_Oil_Well", "TF_M6_Pipeline_Network"]


def js(o, depth=0):
    if depth > 5:
        return str(o)
    if hasattr(o, "to_dict"):
        try:
            o = o.to_dict()
        except Exception:
            pass
    if isinstance(o, dict):
        return {str(k): js(v, depth + 1) for k, v in o.items()}
    if isinstance(o, (list, tuple, set)):
        return [js(v, depth + 1) for v in o]
    if o is None or isinstance(o, (int, float, str, bool)):
        return o
    return str(o)


def members(obj):
    out = {}
    for n in dir(obj):
        if n.startswith("_"):
            continue
        try:
            a = getattr(obj, n)
        except Exception as e:
            out[n] = {"error": str(e)}
            continue
        if callable(a):
            try:
                sig = str(inspect.signature(a))
            except Exception:
                sig = "?"
            out[n] = {"signature": sig, "doc": (inspect.getdoc(a) or "")[:2500]}
        elif inspect.isclass(a) or hasattr(a, "__dict__"):
            out[n] = {"members": {k: js(getattr(a, k)) for k in dir(a) if not k.startswith("_")
                                  and not callable(getattr(a, k, None))}}
        else:
            out[n] = js(a)
    return out


def main():
    root = sys.argv[1]
    files = {}
    for dp, _, fs in os.walk(root):
        for f in fs:
            if f.lower().endswith(".pips"):
                files[os.path.splitext(f)[0]] = os.path.join(dp, f)
    out = {"definitions": {}, "tasks": {}, "equipment_values": {}, "errors": []}
    for name in ("Connection", "Tasks", "SimulationOptions", "OutputVariables", "OptimizerVariables",
                 "SimulationState", "EspCurvesVariables"):
        if hasattr(d, name):
            out["definitions"][name] = members(getattr(d, name))
    for g in ("NodalAnalysisSimulation", "SystemAnalysisSimulation", "PTProfileSimulation", "NetworkOptimizerSimulation",
              "WellPerformanceCurvesSimulation", "GasLiftInjection", "ESP", "Pump", "Compressor", "TwoPhaseSeparator",
              "ThreePhaseSeparator", "RateConstraint", "OptimizerInitialConditions"):
        grp = getattr(d.Parameters, g, None)
        out["definitions"][f"Parameters.{g}"] = members(grp) if grp is not None else "missing"
    for want in WANTED:
        path = files.get(want)
        if not path:
            out["errors"].append(f"not found: {want}")
            continue
        tmp = tempfile.mkdtemp(prefix="pipesim_tasks_")
        copy = os.path.join(tmp, os.path.basename(path))
        shutil.copy2(path, copy)
        print("opening", want, flush=True)
        try:
            m = Model.open(copy, units=d.Units.METRIC)
            if not out["tasks"]:
                out["tasks"] = {t: members(getattr(m.tasks, t)) for t in dir(m.tasks) if not t.startswith("_")}
            vals = {}
            for t in EQUIPMENT:
                try:
                    names = m.find(**{t: d.ALL}) or []
                except Exception:
                    continue
                for n in names:
                    kw = {"Well": n.split(":", 1)[0], t: n.split(":", 1)[1]} if ":" in n else {t: n}
                    try:
                        vals[f"{t}|{n}"] = js(m.get_values(**kw))
                    except Exception as e:
                        vals[f"{t}|{n}"] = {"_error": str(e)}
            try:
                vals["_connections"] = js(m.connections())
            except Exception as e:
                vals["_connections"] = {"_error": str(e)}
            out["equipment_values"][want] = vals
            m.close()
        except Exception:
            out["errors"].append(f"{want}: {traceback.format_exc()[-800:]}")
        shutil.rmtree(tmp, ignore_errors=True)
    os.makedirs(os.path.join(ROOT, "knowledge"), exist_ok=True)
    json.dump(out, open(os.path.join(ROOT, "knowledge", "tasks.json"), "w"), indent=1)
    print("tasks recorded:", sorted(out["tasks"]))
    print("definitions recorded:", sorted(out["definitions"]))
    print("equipment values:", {k: len(v) for k, v in out["equipment_values"].items()})
    print("errors:", out["errors"])


if __name__ == "__main__":
    main()
