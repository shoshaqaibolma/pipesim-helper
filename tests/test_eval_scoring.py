"""The before/after evaluation reads study outputs correctly (fake sixgill; the numbers mean nothing)."""
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [os.path.join(HERE, "fake_sixgill"), os.path.dirname(HERE), HERE]
import executor
import real_eval as ev

FIELD = {"name": "F", "fluids": [{"name": "BO", "type": "black_oil", "api": 35, "gor": 100, "water_cut": 20, "gas_sg": 0.7}],
         "wells": [{"name": w, "fluid": "BO", "reservoir_pressure": p, "reservoir_temperature": 90, "depth": 2500,
                    "tubing_id": 76, "ipr": {"model": "pi", "liquid_pi": 10}, "gas_lift": {"depth": 2000, "rate": 0.05}}
                   for w, p in (("W1", 250), ("W2", 230))],
         "junctions": [{"name": "J1"}], "sinks": [{"name": "SEP", "pressure": 15}],
         "flowlines": [{"name": "FL-W1", "from": "W1", "to": "J1", "length": 1500, "id": 100, "elevation_change": 0},
                       {"name": "FL-W2", "from": "W2", "to": "J1", "length": 900, "id": 100, "elevation_change": 0},
                       {"name": "Trunk", "from": "J1", "to": "SEP", "length": 5000, "id": 152, "elevation_change": 10}]}


def run(analysis):
    r = executor.run({"model": {"source": "project"}, "analysis": analysis}, progress=lambda s: None, project=FIELD)
    return ev.load_run(r["output_dir"])


sw = run({"type": "sweep", "variables": [{"component_type": "Sink", "name": "SEP", "parameter": "Pressure",
                                          "values": [10, 20, 30]}]})
assert sw["summary"]["type"] == "sweep" and sw["summary"]["primary"] and sw["rows"], sw["summary"]
done, ok, note = ev.score("field_project", [sw])
assert done and ok, note
opt = run({"type": "optimize", "max_total": 0.15, "variables": [
    {"component_type": "GasLiftInjection", "name": f"{w}:{w}_GL", "parameter": "GasRate", "values": [0, 0.05, 0.1]}
    for w in ("W1", "W2")]})
done, ok, note = ev.score("gaslift_allocation", [sw, opt])
assert done and "W1" in note and "W2" in note, note
grid = run({"type": "grid", "variables": [
    {"component_type": "Flowline", "name": "Trunk", "parameter": "InnerDiameter", "values": [152, 203]},
    {"component_type": "Sink", "name": "SEP", "parameter": "Pressure", "values": [12, 8]}]})
done, ok, note = ev.score("debottleneck", [grid])
assert done and "None" not in note, note
tor = run({"type": "tornado", "variables": [
    {"component_type": "Completion", "name": "W1:W1_Comp", "parameter": "ReservoirPressure", "low": 200, "high": 250},
    {"component_type": "BlackOilFluid", "name": "BO", "parameter": "WaterCut", "low": 20, "high": 50}]})
done, ok, note = ev.score("uncertainty", [tor])
assert done and "ranking [" in note and "[]" not in note, note
assert ev.score("pipeline_sizing", [sw]) == (False, False, "no diameter sweep")
assert ev.settings("BO.WaterCut low=20") == {"WaterCut": 20.0, "BO.WaterCut": 20.0}
print("eval scoring: sweep / optimize / grid / tornado outputs parsed; missing study reported")
