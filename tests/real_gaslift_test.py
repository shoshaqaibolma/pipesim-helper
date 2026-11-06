"""
Real-PIPESIM test of gas lift: builds one gas-lifted oil well and sweeps the injection rate through executor.run
(a gas lift performance curve, as in the gas lift optimization case studies). Built in %TEMP% / runs\\.
  "D:\\Program\\Pipesim toolkit\\python.exe" tests\\real_gaslift_test.py
"""
import json, os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import executor, study

WELL = {"name": "Gas lift test", "fluids": [{"name": "BO", "type": "black_oil", "api": 30, "gor": 60, "water_cut": 50,
                                             "gas_sg": 0.7}],
        "wells": [{"name": "W1", "fluid": "BO", "reservoir_pressure": 200, "reservoir_temperature": 90,
                   "ipr": {"model": "pi", "liquid_pi": 8}, "depth": 2500, "tubing_id": 76,
                   "gas_lift": {"depth": 2200, "rate": 0.05}}],
        "sinks": [{"name": "SEP", "pressure": 15}],
        "flowlines": [{"name": "FL", "from": "W1", "to": "SEP", "length": 2000, "id": 100, "elevation_change": 0}]}
spec = {"objective": "Gas lift performance curve", "units": "METRIC", "model": {"source": "project"},
        "analysis": {"type": "sweep", "variables": [{"component_type": "GasLiftInjection", "name": "W1:W1_GL",
                                                      "parameter": "GasRate", "values": [0.0, 0.02, 0.05, 0.1, 0.2]}]}}

if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
    c = study.check(spec, project=WELL)
    print("check:", json.dumps(c)[:400])
    if c["ready"]:
        r = executor.run(spec, progress=print, project=WELL)
        print("\n".join(r["table"]))
        print("warnings:", r["warnings"], "| failed:", r["failed_cases"])
        print("summary W1 liquid rate:", json.dumps(r["summary"].get("W1 liquid rate"))[:600])
