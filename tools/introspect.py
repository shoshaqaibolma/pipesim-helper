"""
Record the real sixgill API and the structure of PIPESIM case-study models, so the builder can use
exact 2023.1 names instead of guesses. Read-only: every model is opened from a TEMP COPY.

  "D:\\Program\\Pipesim toolkit\\python.exe" tools\\introspect.py "D:\\Program\\Pipesim2023.1\\Case Studies" [max_models]

Writes knowledge/api.json and knowledge/models/<name>.json (plus knowledge/summary.txt).
"""
import inspect, json, os, shutil, sys, tempfile, time, traceback

from sixgill.pipesim import Model
from sixgill import definitions as d

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "knowledge")


def js(o, depth=0):
    if depth > 6:
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
    if isinstance(o, float):
        return o if o == o else None
    if o is None or isinstance(o, (int, str, bool)):
        return o
    return str(o)


def consts(cls):
    return {k: js(getattr(cls, k)) for k in dir(cls) if not k.startswith("_") and not callable(getattr(cls, k))}


def groups(ns):
    out = {}
    for g in dir(ns):
        if g.startswith("_"):
            continue
        obj = getattr(ns, g)
        out[g] = consts(obj) if inspect.isclass(obj) else js(obj)
    return out


def api():
    a = {"model_methods": {}}
    for n, f in inspect.getmembers(Model):
        if n.startswith("_") or not callable(f):
            continue
        try:
            sig = str(inspect.signature(f))
        except Exception:
            sig = "?"
        a["model_methods"][n] = {"signature": sig, "doc": (inspect.getdoc(f) or "")[:3000]}
    for name in ("ModelComponents", "SystemVariables", "ProfileVariables", "Units"):
        a[name] = consts(getattr(d, name)) if hasattr(d, name) else "missing"
    a["Parameters"] = groups(d.Parameters)
    a["Constants"] = groups(d.Constants)
    a["definitions_names"] = [n for n in dir(d) if not n.startswith("_")]
    m = None
    return a


def try_call(log, label, fn):
    try:
        r = fn()
        log[label] = {"ok": True, "result": js(r)}
        return r
    except Exception as e:
        log[label] = {"ok": False, "error": f"{type(e).__name__}: {e}"}
        return None


def dump_model(path, comp_types):
    tmp = tempfile.mkdtemp(prefix="pipesim_introspect_")
    copy = os.path.join(tmp, os.path.basename(path))
    shutil.copy2(path, copy)
    info = {"file": path, "components": {}, "values": {}, "probe": {}}
    t0 = time.time()
    m = Model.open(copy, units=d.Units.METRIC)
    try:
        info["about"] = js(try_call(info["probe"], "about", m.about))
        for t in comp_types:
            try:
                names = m.find(**{t: d.ALL})
            except Exception:
                continue
            if names:
                info["components"][t] = js(list(names))
        # all parameter values per component (try the no-parameters form first, then per-group constants)
        for t, names in info["components"].items():
            for n in names:
                key = f"{t}:{n}" if not n.startswith(t) else n
                v = None
                try:
                    v = m.get_values(**{t: n})
                except Exception:
                    pass
                if not v:
                    grp = getattr(d.Parameters, t, None)
                    params = list(consts(grp).values()) if grp else []
                    try:
                        v = m.get_values(**{t: n}, parameters=params) if params else None
                    except Exception as e:
                        v = {"_error": str(e)}
                info["values"][f"{t}|{n}"] = js(v)
        # connections / topology: probe the candidates the API offers
        for meth in ("connections", "get_connections", "find_connections", "topology"):
            if hasattr(m, meth):
                attr = getattr(m, meth)
                try_call(info["probe"], meth, attr if callable(attr) else (lambda: attr))
        # boundary conditions and a baseline network run
        nt = m.tasks.networksimulation
        for meth in ("get_conditions", "get_boundary_conditions"):
            if hasattr(nt, meth):
                try_call(info["probe"], f"networksimulation.{meth}", getattr(nt, meth))
        svars = [getattr(d.SystemVariables, n) for n in (
            "PRESSURE", "TEMPERATURE", "VOLUME_FLOWRATE_LIQUID_STOCKTANK", "VOLUME_FLOWRATE_OIL_STOCKTANK",
            "VOLUME_FLOWRATE_GAS_STOCKTANK", "VOLUME_FLOWRATE_WATER_STOCKTANK", "MASS_FLOWRATE")
            if hasattr(d.SystemVariables, n)]
        r = try_call(info["probe"], "networksimulation.run", lambda: nt.run(system_variables=svars, profile_variables=[]))
        if r is not None:
            info["baseline"] = {k: js(getattr(r, k, None)) for k in ("state", "summary", "messages", "system", "node")}
            info["probe"].pop("networksimulation.run", None)
    except Exception:
        info["fatal"] = traceback.format_exc()[-2000:]
    finally:
        try:
            m.close()
        except Exception:
            pass
        shutil.rmtree(tmp, ignore_errors=True)
    info["seconds"] = round(time.time() - t0, 1)
    return info


def main():
    folder = sys.argv[1]
    limit = int(sys.argv[2]) if len(sys.argv) > 2 else 999
    os.makedirs(os.path.join(OUT, "models"), exist_ok=True)
    a = api()
    json.dump(a, open(os.path.join(OUT, "api.json"), "w"), indent=1)
    comp_types = sorted(set(list(a["ModelComponents"].values()) if isinstance(a["ModelComponents"], dict) else []) |
                        {"Well", "Source", "Sink", "Junction", "Flowline", "Riser", "Choke", "Completion", "Tubing",
                         "Casing", "TwoPhaseSeparator", "ThreePhaseSeparator", "BlackOilFluid", "CompositionalFluid",
                         "Pump", "Compressor", "ESP", "GasLiftInjection", "HeatExchanger", "Packer", "SubsurfaceSafetyValve"})
    files = []
    for dp, _, fs in os.walk(folder):
        files += [os.path.join(dp, f) for f in fs if f.lower().endswith(".pips")]
    files = sorted(files)[:limit]
    lines = [f"sixgill Model methods: {sorted(a['model_methods'])}", f"{len(files)} models"]
    for f in files:
        print("dumping", f, flush=True)
        info = dump_model(f, comp_types)
        name = os.path.splitext(os.path.basename(f))[0].replace(" ", "_")
        json.dump(info, open(os.path.join(OUT, "models", name + ".json"), "w"), indent=1)
        state = (info.get("baseline") or {}).get("state")
        lines.append(f"{name}: {sum(len(v) for v in info['components'].values())} components "
                     f"{ {k: len(v) for k, v in info['components'].items()} } run={state} "
                     f"{'FATAL' if 'fatal' in info else ''} {info['seconds']}s")
        print(lines[-1], flush=True)
    open(os.path.join(OUT, "summary.txt"), "w").write("\n".join(lines))
    print("\n".join(lines))


if __name__ == "__main__":
    main()
