"""
Real-PIPESIM test of a CSN_301-style facility built from a description: well -> flowline -> choke -> manifold ->
two-phase separator; gas -> compressor -> gas sales; liquid -> pump -> oil facility. Then a compressor-power sweep.
Charts are copied to runner\\artifacts\\ so they come back with the results.
  "D:\\Program\\Pipesim toolkit\\python.exe" tests\\real_facility_test.py
"""
import json, os, shutil, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import executor, study, netbuilder, project as prj
import sixgill_adapter as sa
from sixgill import definitions as d

FAC = {"name": "Facility test",
       "fluids": [{"name": "BF", "type": "black_oil", "api": 32, "gor": 1500, "water_cut": 20, "gas_sg": 0.65}],
       "wells": [{"name": "W1", "fluid": "BF", "reservoir_pressure": 200, "reservoir_temperature": 55,
                  "ipr": {"model": "pi", "liquid_pi": 5}, "depth": 1500, "tubing_id": 100}],
       "chokes": [{"name": "CK", "bean_size": 50.8}], "junctions": [{"name": "MAN"}],
       "separators": [{"name": "SEP1", "efficiency": 99.9}],
       "compressors": [{"name": "C1", "efficiency": 70, "power": 1000}],
       "pumps": [{"name": "P1", "efficiency": 70, "power": 350}],
       "sinks": [{"name": "GasSales", "pressure": 41.4}, {"name": "OilFacility", "pressure": 20.7}],
       "flowlines": [{"name": "FL-1", "from": "W1", "to": "CK", "length": 61, "id": 154, "elevation_change": 3},
                     {"name": "FL-2", "from": "CK", "to": "MAN", "length": 61, "id": 154, "elevation_change": 3},
                     {"name": "FL-4", "from": "MAN", "to": "SEP1", "length": 30, "id": 154, "elevation_change": 0},
                     {"name": "GL-1", "from": "SEP1", "port": "gas", "to": "C1", "length": 7, "id": 154, "elevation_change": 3},
                     {"name": "GL-2", "from": "C1", "to": "GasSales", "length": 6096, "id": 154, "elevation_change": 0},
                     {"name": "LL-1", "from": "SEP1", "port": "liquid", "to": "P1", "length": 61, "id": 154, "elevation_change": 3},
                     {"name": "LL-2", "from": "P1", "to": "OilFacility", "length": 3109, "id": 154, "elevation_change": 0}]}


def keep_charts(r, prefix):
    dst = os.path.join(ROOT, "runner", "artifacts")
    os.makedirs(dst, exist_ok=True)
    for c in r.get("charts") or []:
        shutil.copy2(c, os.path.join(dst, f"{prefix}_{os.path.basename(c)}"))


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
    print("check:", json.dumps(prj.check_project(FAC))[:300])
    import tempfile
    m, rep = netbuilder.build(FAC, os.path.join(tempfile.mkdtemp(prefix="pipesim_fac_"), "facility.pips"))
    print("build:", json.dumps({k: rep[k] for k in ("connections", "boundary_conditions", "validation")}))
    print("connections:", json.dumps(m.connections())[:900])
    sv = [d.SystemVariables.PRESSURE, d.SystemVariables.VOLUME_FLOWRATE_LIQUID_STOCKTANK,
          d.SystemVariables.VOLUME_FLOWRATE_GAS_STOCKTANK]
    r = m.tasks.networksimulation.run(system_variables=sv, profile_variables=[])
    node = {str(k): {c: v for c, v in comps.items() if ":" not in str(c)} for k, comps in (r.node or {}).items()}
    print("network:", str(getattr(r, "state", "")), json.dumps(node)[:1500])
    print("summary:", json.dumps(getattr(r, "summary", None), default=str)[:800])
    m.close()
    spec = {"objective": "Compressor power vs production", "units": "METRIC", "model": {"source": "project"},
            "analysis": {"type": "sweep", "variables": [{"component_type": "Compressor", "name": "C1",
                                                          "parameter": "Power", "values": [600, 1000, 1400]}]}}
    c = study.check(spec, project=FAC)
    print("study check:", c["ready"], c["errors"][:3])
    if c["ready"]:
        res = executor.run(spec, progress=lambda s: None, project=FAC)
        print("\n".join(res["table"]))
        print("warnings:", res["warnings"])
        keep_charts(res, "facility")
