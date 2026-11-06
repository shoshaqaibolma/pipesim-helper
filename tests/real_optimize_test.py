"""
Real-PIPESIM test of the 'optimize' study: share 0.15 mmsm3/d of lift gas between two gas-lifted wells to
maximize field oil (all feasible splits of 0/0.05/0.1/0.15 per well). Models in %TEMP% / runs\\.
  "D:\\Program\\Pipesim toolkit\\python.exe" tests\\real_optimize_test.py
"""
import json, os, shutil, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import executor, study

FIELD = {"name": "Gas lift allocation test",
         "fluids": [{"name": "BO", "type": "black_oil", "api": 30, "gor": 80, "water_cut": 40, "gas_sg": 0.7}],
         "wells": [{"name": "W1", "fluid": "BO", "reservoir_pressure": 220, "reservoir_temperature": 90, "depth": 2500,
                    "tubing_id": 76, "ipr": {"model": "pi", "liquid_pi": 8}, "gas_lift": {"depth": 2200, "rate": 0.05}},
                   {"name": "W2", "fluid": "BO", "reservoir_pressure": 200, "reservoir_temperature": 90, "depth": 2400,
                    "tubing_id": 76, "ipr": {"model": "pi", "liquid_pi": 12}, "gas_lift": {"depth": 2100, "rate": 0.05}}],
         "junctions": [{"name": "J1"}], "sinks": [{"name": "SEP", "pressure": 15}],
         "flowlines": [{"name": "FL-W1", "from": "W1", "to": "J1", "length": 1000, "id": 100, "elevation_change": 0},
                       {"name": "FL-W2", "from": "W2", "to": "J1", "length": 1000, "id": 100, "elevation_change": 0},
                       {"name": "Trunk", "from": "J1", "to": "SEP", "length": 4000, "id": 152, "elevation_change": 0}]}
spec = {"objective": "Split 0.15 mmsm3/d of lift gas between W1 and W2 for maximum oil", "units": "METRIC",
        "model": {"source": "project"},
        "analysis": {"type": "optimize", "max_total": 0.15, "variables": [
            {"component_type": "GasLiftInjection", "name": f"{w}:{w}_GL", "parameter": "GasRate",
             "values": [0, 0.05, 0.1, 0.15]} for w in ("W1", "W2")]}}

if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
    c = study.check(spec, project=FIELD)
    print("check:", c["ready"], c["errors"], "cases:", c["n_cases"])
    r = executor.run(spec, progress=lambda s: None, project=FIELD)
    print("\n".join(r["table"]))
    print("optimum:", json.dumps(r["summary"].get("optimum"), indent=1))
    print("warnings:", r["warnings"], "| failed:", r["failed_cases"])
