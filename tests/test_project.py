"""Offline tests for the project description checker."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from project import check_project, apply_defaults, summary

# a vague two-well request: lots to ask, nothing invented
p = {"name": "Field A", "wells": [{"name": "W1"}, {"name": "W2"}], "sinks": [{"name": "Sep"}]}
c = check_project(p)
fields = {m["field"] for m in c["missing"]}
assert {"wells.W1.reservoir_pressure", "wells.W2.depth", "sinks.Sep.pressure"} <= fields, fields
assert "STOP calling tools" in c["next_step"]

# complete, valid network
full = {"name": "Field A", "fluids": [{"name": "BO", "type": "black_oil", "api": 35, "gor": 100, "water_cut": 10, "gas_sg": 0.7}],
        "wells": [{"name": w, "fluid": "BO", "reservoir_pressure": 250, "reservoir_temperature": 90,
                   "ipr": {"model": "pi", "liquid_pi": 8}, "depth": 2500, "tubing_id": 76} for w in ("W1", "W2")],
        "junctions": [{"name": "J1"}], "sinks": [{"name": "Sep", "pressure": 15}],
        "flowlines": [{"name": "FL1", "from": "W1", "to": "J1", "length": 1500, "id": 100, "elevation_change": 0},
                      {"name": "FL2", "from": "W2", "to": "J1", "length": 900, "id": 100, "elevation_change": 5},
                      {"name": "FL3", "from": "J1", "to": "Sep", "length": 4000, "id": 200, "elevation_change": 0}]}
c = check_project(full)
assert c["ready"], c

# topology errors
bad = dict(full, flowlines=full["flowlines"][:2])          # J1 goes nowhere
c = check_project(bad)
assert any("not connected to any sink" in e for e in c["errors"]) and any("no outgoing" in e for e in c["errors"]), c
bad = dict(full, flowlines=full["flowlines"] + [{"name": "X", "from": "Sep", "to": "W1", "length": 1, "id": 1, "elevation_change": 0}])
c = check_project(bad)
assert any("sink cannot be upstream" in e for e in c["errors"]) and any("cannot be downstream" in e for e in c["errors"])
bad = dict(full, wells=[dict(full["wells"][0], fluid="NOPE"), full["wells"][1]])
assert any("not defined in fluids" in e for e in check_project(bad)["errors"])
bad = dict(full, wells=[dict(full["wells"][0], ipr={"model": "vogel"}), full["wells"][1]])
assert any(m["field"] == "wells.W1.ipr.aof" for m in check_project(bad)["missing"])

# "use defaults" fills only fields that have a default; required ones stay missing
d = apply_defaults(p, {m["field"] for m in check_project(p)["missing"]})
left = {m["field"] for m in check_project(d)["missing"]}
assert "wells.W1.tubing_id" not in left and "wells.W1.reservoir_pressure" in left, left
print(summary(full))
print("\nALL OK")
