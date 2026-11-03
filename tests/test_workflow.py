"""Plumbing test using the fake sixgill: python tests/test_workflow.py  (no PIPESIM or LLM needed)."""
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [os.path.join(HERE, "fake_sixgill"), os.path.dirname(HERE)]
import study, executor, agent

# 1. a vague request -> the checker must list what to ask
agent.update_spec({"objective": "Effect of water cut on oil rate",
                   "model": {"source": "new", "template": "single_well", "params": {"reservoir_pressure": 260}},
                   "analysis": {"type": "sweep"}})
c = agent.check_spec()
assert not c["ready"] and any(m["field"] == "model.params.water_cut" for m in c["missing"])
assert any(m["field"] == "analysis.variables" for m in c["missing"])
assert "error" in agent.propose_plan() and "error" in agent.run_study()
print(f"asks user about {len(c['missing'])} items, e.g. {c['missing'][0]}")

# 2. the user answers "use defaults" + gives a sweep range
defaults = {f.split(".")[-1]: m["suggested_default"] for m in c["missing"]
            if (f := m["field"]).startswith("model.params.")}
agent.update_spec({"model": {"params": defaults},
                   "analysis": {"variables": [{"alias": "water_cut", "start": 0, "stop": 80, "steps": 5}]}})
assert agent.check_spec()["ready"], agent.check_spec()
print(agent.propose_plan()["plan"])

# 3. execute each analysis type
for a in [{"type": "sweep", "variables": [{"alias": "water_cut", "start": 0, "stop": 80, "steps": 5}]},
          {"type": "grid", "variables": [{"alias": "water_cut", "values": [0, 30, 60]},
                                         {"alias": "separator_pressure", "values": [10, 20]}]},
          {"type": "tornado", "variables": [{"alias": "water_cut", "low": 10, "high": 50},
                                            {"alias": "reservoir_pressure", "low": 220, "high": 300},
                                            {"alias": "separator_pressure", "low": 8, "high": 30}]},
          {"type": "pt_profile", "producer": "Well"},
          {"type": "single_run"}]:
    spec = study.merge(agent.SPEC, {"analysis": a})
    spec["analysis"] = a
    assert study.check(spec)["ready"], study.check(spec)
    r = executor.run(spec, progress=lambda s: None)
    assert not r["failed_cases"] and os.path.exists(r["report"]), r
    print(f"{a['type']:<11} rows={r['n_rows']:<3} charts={len(r['charts'])}  {r['table'][1][:90]}")

# 4. the existing-model path rejects component names that are not in the model
spec = {"objective": "x", "model": {"source": "existing", "path": __file__},
        "analysis": {"type": "sweep", "variables": [{"component_type": "Sink", "name": "Nope", "parameter": "Pressure",
                                                      "values": [1, 2]}]}}
e = study.check(spec, {"Sink": ["Sink-1"]})["errors"]
assert e and "Sink-1" in e[0]; print("bad name caught:", e[0])
print("\nALL OK")
