"""
Find out how PIPESIM 2023.1 really changes network boundary conditions (sink/source pressure, well
reservoir pressure). Works on a TEMP COPY. Writes knowledge/probe_bc.json and prints a summary.

  "D:\\Program\\Pipesim toolkit\\python.exe" tools\\probe_bc.py "...\\CSN_301_Small Network.pips"
"""
import copy, inspect, json, os, shutil, sys, tempfile, traceback
from sixgill.pipesim import Model
from sixgill import definitions as d

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SV = [getattr(d.SystemVariables, n) for n in ("PRESSURE", "VOLUME_FLOWRATE_LIQUID_STOCKTANK",
                                              "VOLUME_FLOWRATE_GAS_STOCKTANK") if hasattr(d.SystemVariables, n)]


def js(o):
    if hasattr(o, "to_dict"):
        o = o.to_dict()
    if isinstance(o, dict):
        return {str(k): js(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [js(v) for v in o]
    return o if o is None or isinstance(o, (int, float, str, bool)) else str(o)


def snapshot(m):
    r = m.tasks.networksimulation.run(system_variables=SV, profile_variables=[])
    node = js(getattr(r, "node", {}) or {})
    keep = {}
    for var, comps in node.items():
        if isinstance(comps, dict):
            keep[var] = {c: v for c, v in comps.items() if ":" not in c}
    return {"state": str(getattr(r, "state", "")), "node": keep}


def main():
    src = sys.argv[1]
    tmp = tempfile.mkdtemp(prefix="pipesim_probe_")
    path = os.path.join(tmp, "m.pips")
    shutil.copy2(src, path)
    out = {"tests": {}}
    m = Model.open(path, units=d.Units.METRIC)
    nt = m.tasks.networksimulation

    def rec(name, fn):
        try:
            out["tests"][name] = {"ok": True, "result": js(fn())}
        except Exception as e:
            out["tests"][name] = {"ok": False, "error": f"{type(e).__name__}: {e}",
                                  "trace": traceback.format_exc()[-800:]}
        print(name, "->", "ok" if out["tests"][name]["ok"] else out["tests"][name]["error"], flush=True)

    out["networksimulation_api"] = {}
    for n in dir(nt):
        if n.startswith("_"):
            continue
        a = getattr(nt, n)
        try:
            sig = str(inspect.signature(a)) if callable(a) else "attr"
        except Exception:
            sig = "?"
        out["networksimulation_api"][n] = {"sig": sig, "doc": (inspect.getdoc(a) or "")[:1500] if callable(a) else ""}
    out["parameters_boundary"] = {g: {k: str(getattr(getattr(d.Parameters, g), k)) for k in dir(getattr(d.Parameters, g))
                                      if not k.startswith("_")}
                                  for g in dir(d.Parameters) if "bound" in g.lower() or "network" in g.lower()}
    sinks = [n for n in m.find(Sink=d.ALL) if ":" not in n]
    out["sinks"] = sinks
    target = sinks[-1]
    rec("get_conditions()", lambda: nt.get_conditions())
    rec("baseline", lambda: snapshot(m))
    rec("sink_get_value", lambda: m.get_value(Sink=target, parameter="Pressure"))

    # A: change the component parameter
    def a():
        old = m.get_value(Sink=target, parameter="Pressure")
        m.set_value(Sink=target, parameter="Pressure", value=old * 2 + 10)
        res = snapshot(m)
        m.set_value(Sink=target, parameter="Pressure", value=old)
        return {"set_to": old * 2 + 10, "result": res}
    rec("A_set_value_sink_pressure", a)

    # B: change the task's boundary conditions
    def b():
        conds = nt.get_conditions()
        c2 = copy.deepcopy(js(conds))
        tried = []
        entry = c2.get(target) if isinstance(c2, dict) else None
        if not isinstance(entry, dict):
            return {"conditions_shape": str(type(conds)), "sample": str(conds)[:1500]}
        pkey = next((k for k in entry if "pressure" in k.lower()), None)
        entry[pkey] = (entry[pkey] or 0) * 2 + 10
        for label, call in [("set_conditions(boundaries=...)", lambda: nt.set_conditions(boundaries=c2)),
                            ("set_conditions(c)", lambda: nt.set_conditions(c2)),
                            ("set_conditions(**{target: entry})", lambda: nt.set_conditions(**{target: entry})),
                            ("set_condition(target, entry)", lambda: nt.set_condition(target, entry))]:
            try:
                call()
                return {"method": label, "key": pkey, "set_to": entry[pkey], "after": js(nt.get_conditions()).get(target),
                        "result": snapshot(m), "failed_before": tried}
            except Exception as e:
                tried.append(f"{label}: {type(e).__name__}: {e}")
        return {"all_failed": tried}
    rec("B_set_conditions_sink_pressure", b)

    # C: sanity - does anything change the rates? reservoir pressure of the first completion
    def c():
        comps = m.find(Completion=d.ALL)
        name = comps[0]
        old = m.get_value(Completion=name, parameter="ReservoirPressure")
        m.set_value(Completion=name, parameter="ReservoirPressure", value=old * 1.3)
        res = snapshot(m)
        m.set_value(Completion=name, parameter="ReservoirPressure", value=old)
        return {"completion": name, "old": old, "new": old * 1.3, "result": res}
    rec("C_reservoir_pressure", c)
    m.close()
    shutil.rmtree(tmp, ignore_errors=True)
    os.makedirs(os.path.join(ROOT, "knowledge"), exist_ok=True)
    json.dump(out, open(os.path.join(ROOT, "knowledge", "probe_bc.json"), "w"), indent=1)
    print(json.dumps({k: (v if not isinstance(v, dict) or "result" not in v else
                          {"ok": v["ok"], "result": str(v["result"])[:600]}) for k, v in out["tests"].items()}, indent=1))


if __name__ == "__main__":
    main()
