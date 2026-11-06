"""Agent project workflow through its tool functions (fake sixgill, no LLM): describe -> ask -> build -> study."""
import builtins, os, sys, tempfile, types
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [os.path.join(HERE, "fake_sixgill"), os.path.dirname(HERE)]
if "openai" not in sys.modules:
    sys.modules["openai"] = types.SimpleNamespace(OpenAI=lambda **k: None)
import agent
builtins.input = lambda prompt="": "y"   # terminal approvals

# 1. a vague request: the checker lists what to ask, per component
agent.update_project({"name": "Field A", "wells": [{"name": "W1"}, {"name": "W2"}], "sinks": [{"name": "Sep"}]})
c = agent.check_project()
fields = {m["field"] for m in c["missing"]}
assert {"wells.W1.reservoir_pressure", "wells.W2.depth", "sinks.Sep.pressure", "project.flowlines"} <= fields, fields
assert "STOP calling tools" in c["next_step"]

# 2. the user's answers arrive in pieces; lists merge by name
agent.update_project({"fluids": [{"name": "BO", "type": "black_oil", "api": 33, "gor": 90, "water_cut": 25, "gas_sg": 0.72}],
                      "wells": [{"name": "W1", "fluid": "BO", "reservoir_pressure": 255, "reservoir_temperature": 88,
                                 "ipr": {"model": "pi", "liquid_pi": 9}, "depth": 2400, "tubing_id": 76}],
                      "sinks": [{"name": "Sep", "pressure": 12}]})
agent.update_project({"wells": [{"name": "W2", "fluid": "BO", "reservoir_pressure": 245, "reservoir_temperature": 86,
                                 "ipr": {"model": "pi", "liquid_pi": 11}, "depth": 2300, "tubing_id": 76}],
                      "junctions": [{"name": "J1"}],
                      "flowlines": [{"name": f"FL-{w}", "from": w, "to": "J1", "length": 1200, "id": 100,
                                     "elevation_change": 0} for w in ("W1", "W2")]
                                   + [{"name": "Trunk", "from": "J1", "to": "Sep", "length": 6000, "id": 200,
                                       "elevation_change": 15}]})
c = agent.check_project()
assert c["ready"] and "build_project" in c["next_step"], c

# 3. build a PIPESIM file; never overwrite
out = os.path.join(tempfile.mkdtemp(), "field_a")
r = agent.build_project(out)
assert r["file"].endswith("field_a.pips") and os.path.exists(r["file"]) and os.path.exists(out + ".project.json"), r
assert "already exists" in agent.build_project(out)["error"]

# 4. a study on the project; a project change after planning forces a new plan
agent.update_spec({"objective": "Trunkline size vs field rate", "model": {"source": "project"},
                   "analysis": {"type": "sweep", "variables": [{"component_type": "Sink", "name": "Sep",
                                                                "parameter": "Pressure", "values": [8, 12, 16]}]}})
c = agent.check_spec()
assert c["ready"], c
plan = agent.propose_plan()["plan"]
assert "Trunk: J1 -> Sep, 6000 m" in plan, plan
agent.update_project({"wells": [{"name": "W2", "reservoir_pressure": 250}]})
assert "changed" in agent.run_study()["error"]
agent.propose_plan()
assert "not seen the plan" in agent.run_study()["error"]      # same turn as the plan: must wait for the user
agent.STATE["turn"] += 1                                       # the user answers
r = agent.run_study()
assert r["n_rows"] == 4 and not r["failed_cases"] and not r["warnings"], r
print("project workflow: asked 4+ items -> merged answers -> built .pips -> stale plan refused -> 4-run study OK")
print("\nALL OK")
