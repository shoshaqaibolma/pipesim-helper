"""Offline tests for the project description checker."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from project import check_project, apply_defaults, summary, merge_project, known_components

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

# chokes sit right after their upstream node; flowlines cannot connect to flowlines; one outlet per well
ck = dict(full, chokes=[{"name": "CK1", "from": "W1", "bean_size": 32}],
          flowlines=[dict(full["flowlines"][0], **{"from": "CK1"})] + full["flowlines"][1:])
assert check_project(ck)["ready"], check_project(ck)
bad = dict(ck, flowlines=ck["flowlines"] + [{"name": "X", "from": "FL3", "to": "Sep", "length": 1, "id": 1, "elevation_change": 0}])
assert any("is a flowline" in e for e in check_project(bad)["errors"])
bad = dict(full, flowlines=full["flowlines"] + [{"name": "FL4", "from": "W1", "to": "Sep", "length": 1, "id": 1, "elevation_change": 0}])
assert any("can feed only one" in e for e in check_project(bad)["errors"]), check_project(bad)
bad = dict(ck, flowlines=full["flowlines"][1:])               # CK1 leads nowhere
assert any("Choke CK1 has no outgoing" in e for e in check_project(bad)["errors"])

# merge by name: change one well, add one, delete one; nested ipr merges
m = merge_project(full, {"wells": [{"name": "W1", "depth": 3000, "ipr": {"liquid_pi": 12}}, {"name": "W3"}]})
w = {x["name"]: x for x in m["wells"]}
assert w["W1"]["depth"] == 3000 and w["W1"]["ipr"] == {"model": "pi", "liquid_pi": 12} and w["W2"]["depth"] == 2500
assert [x["name"] for x in m["wells"]] == ["W1", "W2", "W3"]
m = merge_project(m, {"wells": [{"name": "W3", "_delete": True}]})
assert [x["name"] for x in m["wells"]] == ["W1", "W2"]
assert known_components(full)["Completion"] == ["W1:W1_Comp", "W2:W2_Comp"]

# fluids ask type-specific fields; sources need exactly one of pressure / liquid_rate / gas_rate
g = check_project({"name": "x", "fluids": [{"name": "G", "type": "gas"}], "sources": [{"name": "S", "fluid": "G"}]})
f = {m["field"] for m in g["missing"]}
assert {"fluids.G.gas_sg", "fluids.G.ogr", "fluids.G.wgr", "sources.S.pressure"} <= f and "fluids.G.gor" not in f, f
g = check_project({"name": "x", "fluids": [{"name": "G", "type": "gas", "gas_sg": .6, "ogr": 0, "wgr": 0, "api": 50}],
                   "sources": [{"name": "S", "fluid": "G", "temperature": 30, "pressure": 60, "gas_rate": 1}],
                   "sinks": [{"name": "K", "pressure": 40}],
                   "flowlines": [{"name": "L", "from": "S", "to": "K", "length": 1000, "id": 200, "elevation_change": 0}]})
assert any("give only one" in e for e in g["errors"]), g
assert any("type must be one of" in e for e in check_project({"fluids": [{"name": "Z", "type": "steam"}]})["errors"])

# flowlines must have a real length and diameter (the 9B model once joined two nodes with a 0 m flowline)
z = dict(full, flowlines=[dict(full["flowlines"][2], length=0)] + full["flowlines"][:2])
assert any("length must be greater than 0" in e for e in check_project(z)["errors"])

# a sink takes one inlet (job 16 build failed: "The inlet port of destination SEP has been occupied")
two = dict(full, flowlines=full["flowlines"] + [{"name": "FL9", "from": "W2", "to": "Sep", "length": 10, "id": 50, "elevation_change": 0}])
two["flowlines"] = [f for f in two["flowlines"] if f["name"] != "FL2"]
assert any("has 2 inlets; PIPESIM allows one" in e for e in check_project(two)["errors"]), check_project(two)

# None is missing, not a value; built-in component names cannot be fluid names (job 16: 'Water' was ambiguous)
nn = dict(full, sinks=[{"name": "Sep", "pressure": None}], fluids=[dict(full["fluids"][0], name="Water")],
          wells=[dict(w, fluid="Water") for w in full["wells"]])
c = check_project(nn)
assert any(m["field"] == "sinks.Sep.pressure" for m in c["missing"]) and any("clashes" in e for e in c["errors"]), c

# "use defaults" fills only fields that have a default; required ones stay missing
d = apply_defaults(p, {m["field"] for m in check_project(p)["missing"]})
left = {m["field"] for m in check_project(d)["missing"]}
assert "wells.W1.tubing_id" not in left and "wells.W1.reservoir_pressure" in left, left
print(summary(full))
print("\nALL OK")
