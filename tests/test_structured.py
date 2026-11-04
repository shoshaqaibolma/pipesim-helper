"""Schema-constrained extraction, unstated-number dropping and stage-based tool masking (fake LLM, fake sixgill)."""
import json, os, sys, types
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [os.path.join(HERE, "fake_sixgill"), os.path.dirname(HERE)]
if "openai" not in sys.modules:
    sys.modules["openai"] = types.SimpleNamespace(OpenAI=lambda **k: None)
import agent, structured
import project as prj

FIELD = open(os.path.join(HERE, "scripts", "field_project.txt"), encoding="utf-8").readline().strip()

# --- schemas: only real field names, enums for fluid type / IPR model / port, names required
ps = structured.project_schema()
w = ps["properties"]["wells"]["items"]
assert w["additionalProperties"] is False and w["required"] == ["name"]
assert "reservoir_pressure" in w["properties"] and "liquid_pi" not in w["properties"]
assert w["properties"]["ipr"]["properties"]["model"]["enum"] == list(prj.IPR_FIELDS)
assert "_delete" in structured.project_schema(for_tool=True)["properties"]["wells"]["items"]["properties"]
GL = {"fluids": [{"name": "BO", "type": "black_oil"}], "wells": [{"name": "W1", "gas_lift": {"depth": 2000}}],
      "sinks": [{"name": "SEP"}], "chokes": [{"name": "CK1"}], "flowlines": [{"name": "FL-W1"}]}
opts = structured.study_variables(GL)
assert "GasLiftInjection|W1:W1_GL|GasRate" in opts and "Choke|CK1|BeanSize" in opts and "Sink|SEP|Pressure" in opts
assert structured.study_schema(GL)["properties"]["variables"]["items"]["properties"]["variable"]["enum"] == opts
print("schemas: exact field names, enums, and study variables only from components that exist")

# --- numbers the user never wrote are dropped; ranges keep their steps; km and 0 are fine
said = structured._user_numbers("5 km trunkline, 152 mm, flat, separator from 10 to 30 bara")
out, dropped = structured.drop_unstated({"flowlines": [{"name": "T", "length": 5000, "id": 152, "elevation_change": 0,
                                                       "depth": 2500}], "values": [10, 15, 20, 25, 30]}, said)
assert out["flowlines"][0] == {"name": "T", "length": 5000, "id": 152, "elevation_change": 0}, out
assert out["values"] == [10, 15, 20, 25, 30] and dropped == ["flowlines.depth=2500"], (out, dropped)
assert structured.drop_unstated({"values": [10, 50]}, said)[0]["values"] == []
print("extraction guard: invented inputs dropped, ranges kept")


# --- pre-steps inside the agent: the network and the study come from two constrained calls
class FakeCompletions:
    def __init__(self):
        self.calls = []

    def create(self, **kw):
        self.calls.append(kw)
        schema = kw["response_format"]["json_schema"]["schema"]
        if "wells" in schema["properties"]:
            content = {"name": "Field", "fluids": [{"name": "BO", "type": "black_oil", "api": 35, "gor": 100, "water_cut": 20}],
                       "wells": [{"name": "W1", "fluid": "BO", "reservoir_pressure": 250, "depth": 2500,
                                  "ipr": {"model": "pi", "liquid_pi": 10}, "reservoir_temperature": 77},   # 77: invented
                                 {"name": "W2", "fluid": "BO", "reservoir_pressure": 230, "depth": 2400,
                                  "ipr": {"model": "pi", "liquid_pi": 15}}],
                       "junctions": [{"name": "J1"}], "sinks": [{"name": "SEP", "pressure": 15}],
                       "flowlines": [{"name": "FL-W1", "from": "W1", "to": "J1", "length": 1500, "id": 100, "elevation_change": 0},
                                     {"name": "FL-W2", "from": "W2", "to": "J1", "length": 900, "id": 100, "elevation_change": 0},
                                     {"name": "Trunk", "from": "J1", "to": "SEP", "length": 5000, "id": 152, "elevation_change": 10}]}
        else:
            assert "Sink|SEP|Pressure" in schema["properties"]["variables"]["items"]["properties"]["variable"]["enum"]
            content = {"type": "sweep", "variables": [{"variable": "Sink|SEP|Pressure", "start": 10, "stop": 30, "steps": 5}]}
        msg = types.SimpleNamespace(content=json.dumps(content))
        return types.SimpleNamespace(choices=[types.SimpleNamespace(message=msg)])


fc = FakeCompletions()
client = types.SimpleNamespace(chat=types.SimpleNamespace(completions=fc))
seen = []


def fake_chat(c, msgs):
    seen.append([dict(m) for m in msgs])
    return types.SimpleNamespace(content="1. W1/W2 reservoir temperature? 2. Tubing ID? (defaults 90 degC, 76 mm)",
                                 tool_calls=None, model_dump=lambda exclude_none=True: {
                                     "role": "assistant", "content": "questions"})


agent.chat = fake_chat
msgs = agent.new_conversation()
events = []
agent.run_turn(client, msgs, FIELD, events.append)
names = [e["name"] for e in events if e["type"] == "tool"]
assert names[:4] == ["(extraction)", "update_project", "check_project", "update_spec"] or \
    names[:4] == ["update_project", "check_project", "update_spec", "check_spec"], names
assert "reservoir_temperature" not in agent.PROJECT["wells"][0], agent.PROJECT["wells"][0]     # invented 77 dropped
assert agent.SPEC["analysis"]["variables"][0] == {"component_type": "Sink", "name": "SEP", "parameter": "Pressure",
                                                  "start": 10, "stop": 30, "steps": 5}, agent.SPEC
roles = [m["role"] for m in seen[0]]
assert roles[:2] == ["system", "user"] and roles.count("tool") == 4, roles       # injected as normal tool calls
assert len(fc.calls) == 2 and all(c["response_format"]["type"] == "json_schema" for c in fc.calls)
check = json.loads([m for m in seen[0] if m["role"] == "tool"][1]["content"])
assert any("reservoir_temperature" in m["field"] for m in check["missing"]), check   # ...and asked instead
print("pre-steps: project + study extracted by two constrained calls, invented 77 degC dropped and asked instead")

# a short approval or a defaults answer does not trigger extraction
n = len(fc.calls)
agent.run_turn(client, msgs, "Use the suggested defaults for everything else.", lambda e: None)
agent.run_turn(client, msgs, "Yes, approved. Run it.", lambda e: None)
assert len(fc.calls) == n
# a broken extraction falls back to the normal loop
agent.run_turn(None, agent.new_conversation(), FIELD, events.append)
assert any(e.get("name") == "(extraction skipped)" for e in events)
print("pre-steps: not used for approvals/short answers; failures fall back to the normal loop")

# --- tool masking by stage
msgs = agent.new_conversation()
agent.PROJECT = json.loads(json.dumps(fc.calls and {
    "name": "F", "fluids": [{"name": "BO", "type": "black_oil", "api": 35, "gor": 100, "water_cut": 20, "gas_sg": 0.7}],
    "wells": [{"name": "W1", "fluid": "BO", "reservoir_pressure": 250, "reservoir_temperature": 90, "depth": 2500,
               "tubing_id": 76, "ipr": {"model": "pi", "liquid_pi": 10}}],
    "sinks": [{"name": "SEP", "pressure": 15}],
    "flowlines": [{"name": "FL", "from": "W1", "to": "SEP", "length": 2000, "id": 100, "elevation_change": 0}]}))
offered = lambda: {t["function"]["name"] for t in agent.offered_tools()}
assert "run_study" not in offered() and "propose_plan" not in offered() and "use_defaults" not in offered()
assert "build_project" in offered()
agent.update_spec({"model": {"source": "project"}, "analysis": {"type": "sweep", "variables": [
    {"component_type": "Sink", "name": "SEP", "parameter": "Pressure", "values": [10, 20]}]}})
assert "propose_plan" in offered() and "run_study" not in offered()
agent.propose_plan()
assert "run_study" not in offered() and "propose_plan" not in offered()       # same turn: the user must answer
agent.STATE["turn"] += 1
assert "run_study" in offered()
agent.STATE["ran_plan"] = agent._plan_key()
assert "run_study" not in offered()                                            # already ran
agent.STRUCTURED = False
assert len(agent.offered_tools()) == len(agent.TOOLS)
agent.STRUCTURED = True
print("masking: run_study only after the user has answered a plan; propose_plan only when the spec is ready")
print("ALL STRUCTURED TESTS PASSED")
