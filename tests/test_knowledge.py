"""Recipes, engineering sanity checks and the invented-number guard (no PIPESIM, no llama-server needed)."""
import json, os, sys, types
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [os.path.join(HERE, "fake_sixgill"), os.path.dirname(HERE)]
if "openai" not in sys.modules:
    sys.modules["openai"] = types.SimpleNamespace(OpenAI=lambda **k: None)
import agent, numguard, recipes, study
import project as prj

DATA = os.path.join(HERE, "data")
SCRIPTS = os.path.join(HERE, "scripts")

# --- recipe selection for the evaluation scenarios
want = {"field_project": ["wells into a manifold and a trunkline"], "gaslift_nodal": ["nodal analysis", "gas lift"],
        "gaslift_allocation": ["wells into a manifold and a trunkline", "gas lift"],
        "uncertainty": ["one well to a separator", "uncertainty ranking"],
        "pipeline_sizing": ["pipeline from a fixed-rate source"]}
for name, names in want.items():
    first = open(os.path.join(SCRIPTS, name + ".txt"), encoding="utf-8").readline()
    got = sorted(r["name"] for r in recipes.select(first))
    assert got == sorted(names), (name, got)
assert recipes.select("Yes, approved. Run it.") == []
print("recipes: the right worked examples are picked for each scenario, none for short replies")

# recipes must not leak the scenario answers (their numbers/names differ from the test scenarios)
for r in recipes.RECIPES:
    for leak in ('"W1"', "0.15", "203,254,305", '"low":200,"high":250', '"SEP"'):
        assert leak not in r["text"], (r["name"], leak)
print("recipes: placeholders differ from the evaluation scenarios")

# --- sanity checks: unit mistakes warn, impossible values block
base = {"name": "x", "fluids": [{"name": "BO", "type": "black_oil", "api": 35, "gor": 100, "water_cut": 20, "gas_sg": 0.7}],
        "wells": [{"name": "W1", "fluid": "BO", "reservoir_pressure": 250, "reservoir_temperature": 90, "depth": 2500,
                   "tubing_id": 76, "ipr": {"model": "pi", "liquid_pi": 10}}],
        "sinks": [{"name": "S", "pressure": 15}],
        "flowlines": [{"name": "F", "from": "W1", "to": "S", "length": 2000, "id": 100, "elevation_change": 0}]}
c = prj.check_project(base)
assert c["ready"] and "warnings" not in c, c
bad = json.loads(json.dumps(base))
bad["wells"][0].update(reservoir_pressure=3600, tubing_id=3, depth=8200)   # psi, inch, ft
bad["fluids"][0]["gor"] = 560 * 10
c = prj.check_project(bad)
assert c["ready"] and len(c["warnings"]) == 4, c
assert any("psi" in w for w in c["warnings"]) and any("inches" in w for w in c["warnings"])
assert "warnings" in c["next_step"]
bad = json.loads(json.dumps(base))
bad["fluids"][0]["water_cut"] = 140
bad["flowlines"][0]["elevation_change"] = 2500
c = prj.check_project(bad)
assert not c["ready"] and len(c["errors"]) == 2, c
bad = json.loads(json.dumps(base)); bad["sinks"][0]["pressure"] = 260
assert any("no well can flow" in w for w in prj.check_project(bad)["warnings"])
spec = {"model": {"source": "project"}, "analysis": {"type": "sweep", "variables": [
    {"component_type": "GasLiftInjection", "name": "W1:W1_GL", "parameter": "GasRate", "values": [0, 50000]}]}}
c = study.check(spec, project=base)
assert any("mmsm3/d" in w for w in c.get("warnings", [])), c
spec["analysis"]["variables"] = [{"component_type": "Sink", "name": "S", "parameter": "Pressure", "values": [10, 300]}]
assert any("no well flows" in w for w in study.check(spec, project=base).get("warnings", []))
print("sanity: psi/inch/ft/scf mistakes warn, impossible water cut and elevation block, dead-well sweeps warn")

# --- number guard on the real job-16 reply (tornado): the invented 64 / 56 / 35 % are caught, real ones pass
led = numguard.Ledger()
led.add_user(open(os.path.join(SCRIPTS, "uncertainty.txt"), encoding="utf-8").read())
led.add_result("run_study", json.load(open(os.path.join(DATA, "job16_tornado.json"))))
reply = open(os.path.join(DATA, "job16_reply.txt"), encoding="utf-8").read()
assert led.unverified(reply) == ["64", "56", "35"], led.unverified(reply)
assert led.unverified("Base oil 417 sm3/d; W1 at 20% water cut gives 90.5 sm3/d more (21.7 %).") == []
assert led.unverified("Lift gas 0.05 mmsm3/d is 50,000 sm3/d.") == []        # unit scaling of a known number
assert led.unverified("Oil drops by 12.3 % at 50% water cut.") == ["12.3"]
assert led.unverified("Wells W1, FL-2 and run 20261104-141216-136, steps 1. 2. 3.") == []
print("number guard: job-16 invented values 64, 56 and 35 % flagged; real, rounded and derived values pass")

# guidance numbers are placeholders, not facts
led = numguard.Ledger()
led.add_user("Sweep the separator" + recipes.GUIDANCE + recipes.RECIPES[0]["text"])
assert led.unverified("Reservoir 180 bara") == ["180"]
print("number guard: recipe placeholders never count as real numbers")


# --- the guard inside the agent loop: one rewrite; what is still unverified is flagged under the reply
class Msg:
    def __init__(self, content=None, tool_calls=None):
        self.content, self.tool_calls = content, tool_calls
    def model_dump(self, exclude_none=True):
        d = {"role": "assistant", "content": self.content}
        if self.tool_calls:
            d["tool_calls"] = [{"id": t.id, "type": "function",
                                "function": {"name": t.function.name, "arguments": t.function.arguments}}
                               for t in self.tool_calls]
        return d


def scripted(replies):
    seen = []
    def fake(client, msgs):
        seen.append([dict(m) for m in msgs])
        return replies.pop(0)
    return fake, seen


for rewrite, expect_flag in (("Oil rate is 417.2 sm3/d.", False), ("Oil rate is about 470 sm3/d.", True)):
    msgs = agent.new_conversation()
    agent.LEDGER.add_result("run_study", json.load(open(os.path.join(DATA, "job16_tornado.json"))))
    fake, seen = scripted([Msg("Oil rate is 417.2 sm3/d, about 64 sm3/d above plan."), Msg(rewrite)])
    agent.chat = fake
    events = []
    agent.run_turn(None, msgs, "What is the oil rate?", events.append)
    final = [e for e in events if e["type"] == "assistant"][-1]["text"]
    assert "rewrite" in seen[1][-1]["content"].lower() and "64" in seen[1][-1]["content"]
    assert final.startswith(rewrite) and ("Number check" in final) == expect_flag, final
    assert msgs[-1] == {"role": "assistant", "content": final} and msgs[-2]["role"] == "user"
    assert any(e["type"] == "tool" and e["name"] == "(number check)" for e in events)
print("agent: invented number -> one rewrite; still invented -> flagged under the reply; history stays clean")

# recipes are added once per conversation, and the switches turn both features off
msgs = agent.new_conversation()
fake, seen = scripted([Msg("ok"), Msg("ok")])
agent.chat = fake
agent.run_turn(None, msgs, "Build two oil wells into a manifold", lambda e: None)
agent.run_turn(None, msgs, "Add a trunkline to the manifold", lambda e: None)
users = [m["content"] for m in msgs if m["role"] == "user"]
assert recipes.GUIDANCE in users[0] and recipes.GUIDANCE not in users[1], users
agent.KNOWLEDGE = agent.NUMBER_GUARD = False
msgs = agent.new_conversation()
fake, seen = scripted([Msg("About 64 sm3/d.")])
agent.chat = fake
events = []
agent.run_turn(None, msgs, "Build two oil wells into a manifold", events.append)
assert recipes.GUIDANCE not in msgs[1]["content"] and events[-1]["text"] == "About 64 sm3/d."
agent.KNOWLEDGE = agent.NUMBER_GUARD = True
print("agent: recipes once per conversation; PIPESIM_AGENT_KNOWLEDGE / PIPESIM_NUMBER_GUARD switches work")

# --- names copied from a recipe example (job 20: fluid "OilA") are replaced unless the user wrote them
msgs = agent.new_conversation()
agent.STATE["user_text"] = "Build one oil well W1 ... Black oil: 32 API ... separator SEP"
r = agent.update_project({"name": "x", "fluids": [{"name": "OilA", "type": "black_oil", "api": 32}],
                          "wells": [{"name": "W1", "fluid": "OilA"}]})
assert agent.PROJECT["fluids"][0]["name"] == "BO" and agent.PROJECT["wells"][0]["fluid"] == "BO", agent.PROJECT
assert any("OilA -> BO" in x for x in r["renamed"]), r
agent.STATE["user_text"] = "the fluid is called OilA"
agent.PROJECT = {}
agent.update_project({"fluids": [{"name": "OilA", "type": "black_oil"}]})
assert agent.PROJECT["fluids"][0]["name"] == "OilA"
# job 21: flowlines named after the user's wells (FL-A for well A) must stay, and names must never collide
agent.STATE["user_text"] = "two oil wells, A and B, each with a 2 km line into manifold M"
agent.PROJECT = {}
agent.update_project({"fluids": [{"name": "OilA", "type": "black_oil"}, {"name": "Gas1", "type": "gas"}],
                      "wells": [{"name": "A"}, {"name": "B"}],
                      "flowlines": [{"name": "FL-A", "from": "A", "to": "M"}, {"name": "FL-B", "from": "B", "to": "M"}]})
assert [f["name"] for f in agent.PROJECT["flowlines"]] == ["FL-A", "FL-B"], agent.PROJECT
assert [f["name"] for f in agent.PROJECT["fluids"]] == ["BO", "Gas"], agent.PROJECT["fluids"]
print("names: copied example FLUID names are replaced (BO/Gas) unless the user used them; other names untouched")

# --- approvals are answered from the workflow state
msgs = agent.new_conversation()
assert "nothing to approve" in agent.approval_note("Approved.")
agent.SPEC, agent.PROJECT = {"model": {"source": "x"}}, {}
agent.STATE["plan_ok_for"] = agent._plan_key()
assert "Call run_study now" in agent.approval_note("Yes, approved. Run it.")
agent.STATE["ran_plan"] = agent._plan_key()
assert "Do NOT propose" in agent.approval_note("Approved. Run the study and explain the result.")
assert agent.approval_note("Use the suggested defaults for everything else.") is None
assert agent.approval_note("Yes, but set the separator to 10 bara") is None        # a change, not an approval
assert agent.approval_note("Yes, but sweep the water cut from 10 to 70 % in 4 steps and the GOR as well please, thanks") is None
fake, seen = scripted([Msg("The study is done.")])
agent.chat = fake
agent.run_turn(None, msgs, "Approved.", lambda e: None)
assert "Do NOT propose" in seen[0][-1]["content"] and agent.LEDGER.unverified("") == []
print("approvals: run the waiting plan / say it already ran / nothing to approve; longer requests untouched")
print("ALL KNOWLEDGE TESTS PASSED")
