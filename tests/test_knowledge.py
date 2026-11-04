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
print("ALL KNOWLEDGE TESTS PASSED")
