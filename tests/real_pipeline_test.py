"""
Real-PIPESIM test of pipelines (rate-specified sources) and gas fluids/wells, plus the units PIPESIM uses for the
parameters whose units were not yet confirmed. Everything is built in a temp folder.
  "D:\\Program\\Pipesim toolkit\\python.exe" tests\\real_pipeline_test.py
"""
import json, os, sys, tempfile, traceback
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import netbuilder, sixgill_adapter as sa
from sixgill import definitions as d

GAS = {"name": "DryGas", "type": "gas", "gas_sg": 0.65, "ogr": 0, "wgr": 0, "api": 50}
CASES = {
    "gas export pipeline (2 mmsm3/d fixed, inlet pressure calculated)": {
        "name": "Gas export", "fluids": [GAS],
        "sources": [{"name": "Plant", "fluid": "DryGas", "temperature": 40, "gas_rate": 2.0}],
        "sinks": [{"name": "Terminal", "pressure": 50}],
        "flowlines": [{"name": "Export", "from": "Plant", "to": "Terminal", "length": 20000, "id": 254,
                       "elevation_change": 0}]},
    "oil pipeline (2000 sm3/d fixed)": {
        "name": "Oil line", "fluids": [{"name": "Crude", "type": "black_oil", "api": 32, "gor": 50, "water_cut": 5,
                                        "gas_sg": 0.7}],
        "sources": [{"name": "Field", "fluid": "Crude", "temperature": 60, "liquid_rate": 2000}],
        "sinks": [{"name": "Refinery", "pressure": 10}],
        "flowlines": [{"name": "Trunk", "from": "Field", "to": "Refinery", "length": 15000, "id": 203,
                       "elevation_change": 30}]},
    "gas well, back-pressure IPR": {
        "name": "Gas well", "fluids": [GAS],
        "wells": [{"name": "GW1", "fluid": "DryGas", "reservoir_pressure": 200, "reservoir_temperature": 95,
                   "ipr": {"model": "backpressure", "c": 1.0, "n": 0.8}, "depth": 2800, "tubing_id": 76}],
        "sinks": [{"name": "Plant", "pressure": 60}],
        "flowlines": [{"name": "FL", "from": "GW1", "to": "Plant", "length": 3000, "id": 152, "elevation_change": 0}]},
}
SV = [getattr(d.SystemVariables, n) for n in ("PRESSURE", "TEMPERATURE", "VOLUME_FLOWRATE_LIQUID_STOCKTANK",
                                              "VOLUME_FLOWRATE_GAS_STOCKTANK") if hasattr(d.SystemVariables, n)]


def units(m, **kw):
    try:
        return m.describe(**kw).units
    except Exception as e:
        return f"describe failed: {type(e).__name__}: {e}"


def run(m):
    r = m.tasks.networksimulation.run(system_variables=SV, profile_variables=[])
    node = getattr(r, "node", {}) or {}
    return {"state": str(getattr(r, "state", "")),
            "node": {str(v): {c: x for c, x in comps.items() if ":" not in str(c)} for v, comps in node.items()
                     if isinstance(comps, dict)}}


def main():
    tmp = tempfile.mkdtemp(prefix="pipesim_pipetest_")
    for label, proj in CASES.items():
        print(f"\n== {label}")
        try:
            m, rep = netbuilder.build(proj, os.path.join(tmp, proj["name"].replace(" ", "_") + ".pips"))
            print("   build:", json.dumps({k: rep[k] for k in ("boundary_conditions", "validation")}))
            if "wells" in proj:
                comp = "GW1:GW1_Comp"
                u = units(m, Well="GW1", Completion="GW1_Comp", parameter=sa.P("IPRBackPressure", "CONSTANTC"))
                print("   units of back-pressure C:", u, "| n:",
                      units(m, Well="GW1", Completion="GW1_Comp", parameter=sa.P("IPRBackPressure", "SLOPEN")))
                # q = C (Pr^2 - Pwf^2)^n with Pr 200, Pwf ~100 bara -> about 2 mmsm3/d
                c = 0.0005 if "mm" in str(u).lower() else 500.0 if "sm3" in str(u).lower() else None
                if c is None:
                    print("   unknown C units; not running"); m.close(); continue
                sa.set_value(m, "Completion", comp, sa.P("IPRBackPressure", "CONSTANTC"), c)
                print("   C set to", c, "->", sa.get_value(m, "Completion", comp, sa.P("IPRBackPressure", "CONSTANTC")))
            f = proj["fluids"][0]["name"]
            print("   units: OGR", units(m, context=f, parameter="OGR"), "| WGR", units(m, context=f, parameter="WGR"),
                  "| GOR", units(m, context=f, parameter="GOR"))
            if "sources" in proj:
                s = proj["sources"][0]["name"]
                print("   units: source gas rate", units(m, context=s, parameter="GasFlowRate"),
                      "| liquid rate", units(m, context=s, parameter="LiquidFlowRate"))
            print("   result:", json.dumps(run(m))[:1500])
            m.close()
        except Exception as e:
            print(f"   FAILED {type(e).__name__}: {e}\n   " + traceback.format_exc(limit=3)[-1200:])
    print(f"\n(models left in {tmp})")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
    main()
