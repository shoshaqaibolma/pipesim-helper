"""Replays the tool calls Qwen 3.5 9B actually made in job 05 (real run, 2026-11-04) against the fixed code."""
import builtins, os, sys, types
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [os.path.join(HERE, "fake_sixgill"), os.path.dirname(HERE)]
if "openai" not in sys.modules:
    sys.modules["openai"] = types.SimpleNamespace(OpenAI=lambda **k: None)
import agent, project as prj
builtins.input = lambda prompt="": "y"

# 1. the model's first call: a fluid without a name, synonyms, a fraction water cut, extra keys.
#    Before the fix this stored the unnamed fluid and every later call failed with KeyError: 'name'.
r = agent.update_project({"name": "Small Oil Field",
                          "fluids": [{"oil_api": 35, "water_cut": 0.2, "gas_oil_ratio": 100}],
                          "wells": [{"name": "W1", "type": "oil", "reservoir_pressure": 250, "depth": 2500,
                                     "productivity_index": 10, "flowline_from": "J1"},
                                    {"name": "W2", "type": "oil", "reservoir_pressure": 230, "depth": 2400,
                                     "productivity_index": 15}]})
assert any("has no \"name\"" in e for e in r["rejected"]) and any("flowline_from" in e for e in r["rejected"]), r
assert any("productivity_index -> ipr" in n for n in r["normalized"]) and any("ignored 'type'" in n for n in r["normalized"])
w1 = next(w for w in agent.PROJECT["wells"] if w["name"] == "W1")
assert w1 == {"name": "W1", "reservoir_pressure": 250, "depth": 2500, "ipr": {"model": "pi", "liquid_pi": 10}}, w1
assert not agent.PROJECT.get("fluids"), "the unnamed fluid must not be stored"

# 2. the next call works (no lingering KeyError); synonyms map; the fraction becomes a percentage
r = agent.update_project({"fluids": [{"name": "field_fluid", "oil_api": 35, "water_cut": 0.2, "gas_oil_ratio": 100}],
                          "wells": [{"name": "W1", "fluid": "field_fluid"}, {"name": "W2", "fluid": "field_fluid"}],
                          "junctions": [{"name": "J1"}], "sinks": [{"name": "SEP", "type": "separator", "pressure": 15}],
                          "flowlines": [{"name": "FL1", "from_node": "W1", "to_node": "J1", "length_km": 1.5, "diameter": 100},
                                        {"name": "FL2", "from": "W2", "to": "J1", "length": 900, "id": 100},
                                        {"name": "Trunk", "from": "J1", "to": "SEP", "length": 5000, "id": 152,
                                         "elevation": 10}]})
assert "rejected" not in r, r
f = agent.PROJECT["fluids"][0]
assert f == {"name": "field_fluid", "api": 35, "water_cut": 20.0, "gor": 100}, f
fl1 = next(x for x in agent.PROJECT["flowlines"] if x["name"] == "FL1")
assert fl1 == {"name": "FL1", "from": "W1", "to": "J1", "length": 1500.0, "id": 100}, fl1

# 3. "use the suggested defaults": one call fills them all; nothing without a default is invented
r = agent.use_defaults(["all"])
assert r["errors"] == [] and r["still_missing"] == [], r
assert agent.check_project()["ready"]
assert next(x for x in agent.PROJECT["fluids"])["gas_sg"] == 0.7
print("job-05 replay: unnamed item rejected without corrupting the project; synonyms, km, % and PI normalised;")
print("               use_defaults(['all']) completed the project; check_project ready")

# 4. a value with no default is never filled in
p, _, _ = prj.apply_patch({}, {"name": "x", "wells": [{"name": "W9"}], "sinks": [{"name": "S"}]})
p = prj.apply_defaults(p, "all")
left = {m["field"] for m in prj.check_project(p)["missing"]}
assert {"wells.W9.reservoir_pressure", "wells.W9.depth", "sinks.S.pressure"} <= left, left

# 5. summary never raises, whatever got in
assert "unnamed" in prj.summary({"fluids": [{"api": 30}]})
print("\nALL OK")
