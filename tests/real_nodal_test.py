"""
Real-PIPESIM test of the nodal analysis study type on a built test well (with and without gas lift).
Prints the operating point and whether the inflow/outflow curves could be read (and their raw attribute names).
  "D:\\Program\\Pipesim toolkit\\python.exe" tests\\real_nodal_test.py
"""
import json, os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import executor, study

BASE = {"name": "Nodal test", "fluids": [{"name": "BO", "type": "black_oil", "api": 35, "gor": 100, "water_cut": 20,
                                          "gas_sg": 0.7}],
        "wells": [{"name": "W1", "fluid": "BO", "reservoir_pressure": 250, "reservoir_temperature": 90,
                   "ipr": {"model": "pi", "liquid_pi": 10}, "depth": 2500, "tubing_id": 76}],
        "sinks": [{"name": "SEP", "pressure": 15}],
        "flowlines": [{"name": "FL", "from": "W1", "to": "SEP", "length": 2000, "id": 100, "elevation_change": 0}]}
GL = dict(BASE, wells=[dict(BASE["wells"][0], gas_lift={"depth": 2000, "rate": 0.05})])

if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
    for label, proj in (("natural flow", BASE), ("gas lift 0.05 mmsm3/d", GL)):
        spec = {"objective": f"Nodal analysis, {label}", "units": "METRIC", "model": {"source": "project"},
                "analysis": {"type": "nodal", "producer": "W1", "outlet_pressure": 20}}
        print(f"\n== {label}: check", study.check(spec, project=proj)["ready"])
        r = executor.run(spec, progress=lambda s: None, project=proj)
        print("operating point:", json.dumps(r["summary"]["operating_point"]))
        print("charts:", [os.path.basename(c) for c in r["charts"]], "| warnings:", r["warnings"])
        raw = json.load(open(os.path.join(r["output_dir"], "nodal_raw.json")))
        for k, v in raw.items():
            print(f"raw {k}:", json.dumps(v)[:700])
