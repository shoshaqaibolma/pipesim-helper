"""
Real-PIPESIM smoke test of the network builder (run on the PC with PIPESIM's Python):
  "D:\\Program\\Pipesim toolkit\\python.exe" tests\\real_build_test.py
Builds a small 2-well field (choke, junction, trunkline, separator) in a temp folder, runs the network
simulation, reads key values back, and re-runs with a different separator pressure through the adapter.
Prints each step, so the first failure shows exactly which sixgill name or call this PIPESIM version rejects.
"""
import io, json, os, sys, tempfile, traceback
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

FIELD = {"name": "Smoke test field", "ambient_temperature": 15,
         "fluids": [{"name": "BO", "type": "black_oil", "api": 35, "gor": 100, "water_cut": 20, "gas_sg": 0.7}],
         "wells": [{"name": w, "fluid": "BO", "reservoir_pressure": p, "reservoir_temperature": 90,
                    "ipr": {"model": "pi", "liquid_pi": pi}, "depth": 2500, "tubing_id": 76}
                   for w, p, pi in (("W1", 250, 10), ("W2", 230, 15))],
         "chokes": [{"name": "CK1", "from": "W1", "bean_size": 40}],
         "junctions": [{"name": "J1"}], "sinks": [{"name": "Sep", "pressure": 15}],
         "flowlines": [{"name": "FL1", "from": "CK1", "to": "J1", "length": 1500, "id": 100, "elevation_change": 0},
                       {"name": "FL2", "from": "W2", "to": "J1", "length": 900, "id": 100, "elevation_change": 5},
                       {"name": "FL3", "from": "J1", "to": "Sep", "length": 4000, "id": 152, "elevation_change": 10}]}


def step(label, fn):
    print(f"\n== {label}")
    try:
        r = fn()
        print("   OK", (json.dumps(r, default=str)[:1500] if r is not None else ""))
        return r
    except Exception as e:
        print(f"   FAILED {type(e).__name__}: {e}")
        print("   " + traceback.format_exc(limit=3).replace("\n", "\n   ")[-1500:])
        return None


def main():
    import netbuilder, sixgill_adapter as sa
    from sixgill import definitions as d
    path = os.path.join(tempfile.mkdtemp(prefix="pipesim_buildtest_"), "smoke.pips")
    built = step("build the 2-well field", lambda: netbuilder.build(FIELD, path))
    if not built:
        return
    m, report = built
    print("   build report:", json.dumps(report, default=str))
    sv = [getattr(d.SystemVariables, n) for n in ("PRESSURE", "VOLUME_FLOWRATE_LIQUID_STOCKTANK",
                                                  "VOLUME_FLOWRATE_OIL_STOCKTANK") if hasattr(d.SystemVariables, n)]

    def run():
        r = m.tasks.networksimulation.run(system_variables=sv, profile_variables=[])
        node = getattr(r, "node", {}) or {}
        keep = {str(var): {c: v for c, v in comps.items() if ":" not in str(c)} for var, comps in node.items()
                if isinstance(comps, dict)}
        return {"state": str(getattr(r, "state", "")), "messages": str(getattr(r, "messages", ""))[:800], "node": keep}
    step("components the model reports", lambda: {t: m.find(**{t: d.ALL}) for t in
                                                 ("Well", "Junction", "Sink", "Flowline", "Choke", "Completion", "Tubing")})
    step("read back key values", lambda: {
        "W1 reservoir pressure": sa.get_param(m, "Completion", "W1:W1_Comp", sa.P("Completion", "RESERVOIRPRESSURE")),
        "W1 liquid PI (expect 10)": sa.get_value(m, "Completion", "W1:W1_Comp", sa.P("IPRPIModel", "LIQUIDPI")),
        "W1 IPR model": sa.get_value(m, "Completion", "W1:W1_Comp", sa.P("Completion", "IPRMODEL")),
        "W1 fluid": sa.get_value(m, "Completion", "W1:W1_Comp", sa.P("Completion", "ASSOCIATEDBLACKOILFLUID")),
        "W1 tubing length": sa.get_value(m, "Tubing", "W1:Tubing", sa.P("Tubing", "LENGTH")),
        "FL3 inner diameter": m.get_value(Flowline="FL3", parameter=sa.P("Flowline", "INNERDIAMETER")),
        "Sep pressure (boundary)": sa.get_param(m, "Sink", "Sep", sa.P("Sink", "PRESSURE"))})
    step("network boundary conditions", lambda: sa.get_boundaries(m))
    base = step("network simulation at Sep = 15 bara", run)
    step("set Sep = 30 bara through the adapter",
         lambda: (sa.set_param(m, "Sink", "Sep", sa.P("Sink", "PRESSURE"), 30.0),
                  sa.get_param(m, "Sink", "Sep", sa.P("Sink", "PRESSURE")))[1])
    hi = step("network simulation at Sep = 30 bara", run)
    if base and hi:
        print("\n== verdict: results", "CHANGED" if base["node"] != hi["node"] else "DID NOT CHANGE",
              "when the separator pressure changed")
    m.close()
    print(f"\n(model left at {path}; open it in PIPESIM to inspect)")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
    main()
