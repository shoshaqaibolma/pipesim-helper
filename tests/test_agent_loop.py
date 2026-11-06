"""Agent-loop and checker tests with a scripted fake LLM (no PIPESIM, no llama-server needed).
Reproduces the failures seen in the first real test on Qwen 3.5 9B."""
import io, json, os, sys, types, contextlib
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [os.path.join(HERE, "fake_sixgill"), os.path.dirname(HERE)]
if "openai" not in sys.modules:  # the loop never calls the real client here
    sys.modules["openai"] = types.SimpleNamespace(OpenAI=lambda **k: None)
import study, agent

# --- checker: the exact mistakes the 9B model made
c = study.check({"objective": "x", "model": {"source": r"C:\cases\CSN_301.pips"}})
assert any("must be exactly" in e and "model.path" in e for e in c["errors"]), c
c = study.check({"objective": "x", "model": {"source": "new", "template": "single_well"},
                 "analysis": {"type": "sweep", "variables": [{"alias": "water_cut", "low": 0, "high": 50}]}})
assert any("only for tornado" in e for e in c["errors"]), c
c = study.check({"objective": "x", "results": {"oil": 5}, "analysis": {"type": "sweep", "result": 1}})
assert any("'results'" in e for e in c["errors"]) and any("analysis.result" in e for e in c["errors"]), c
assert "ONE update_spec" in c["next_step"]
c = study.check({"objective": "x"})
assert not c["errors"] and "STOP calling tools" in c["next_step"]
print("checker: path-in-source, low/high on sweep, stray keys -> precise errors + next_step")


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


def call(name, args, i=[0]):
    i[0] += 1
    return types.SimpleNamespace(id=f"c{i[0]}", function=types.SimpleNamespace(name=name, arguments=json.dumps(args)))


def run(script_lines, fake_chat):
    p = os.path.join(HERE, "_script.txt")
    open(p, "w").write("\n".join(script_lines))
    agent.chat = fake_chat
    agent.SPEC = {}; agent.STATE.update(plan_ok_for=None, components=None)
    sys.argv = ["agent.py", "--script", p]
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        agent.main()
    os.remove(p)
    return out.getvalue()


# --- loop guard: a model that keeps editing the spec forever is stopped and told to ask the user
seen = []
def looping(client, msgs):
    seen.append(msgs[-1])
    if msgs[-1].get("role") == "tool" and "Too many edits" in msgs[-1]["content"]:
        return Msg("1. Which model file? 2. Which analysis?")
    return Msg(tool_calls=[call("update_spec", {"patch": {"model": {"source": "C:/x.pips"}}})])
out = run(["sweep sink pressure on my model"], looping)
assert "Which model file?" in out, out
assert sum(1 for m in seen if m.get("role") == "tool") == agent.MAX_SPEC_CALLS + 1
print(f"loop guard: stopped after {agent.MAX_SPEC_CALLS} spec edits, model then asked the user")

# --- server down: clear message, no traceback, conversation not corrupted
class APIConnectionError(Exception): pass
def down(client, msgs): raise APIConnectionError("Connection refused")
out = run(["hello"], down)
assert "could not reach the model" in out and "llama-server" in out and "Traceback" not in out, out
print("server down: clear message instead of a stack trace")

# --- empty reply (runaway thinking symptom) is reported, not printed as a blank line
out = run(["hello"], lambda c, m: Msg(""))
assert "empty reply" in out
print("empty reply: explained to the user")
# --- an invalid tool-call JSON from llama-server is retried, not reported as a dead server
calls = {"n": 0}
def flaky(client, msgs):
    calls["n"] += 1
    if calls["n"] == 1:
        raise Exception("Error code: 500 - Failed to parse tool call arguments as JSON")
    return Msg("recovered")
out = run(["hello"], flaky)
assert "recovered" in out and "could not reach" not in out, out
print("invalid tool-call JSON: retried with a smaller call")

# --- long sessions: old tool results are shortened, the latest turn is kept intact
msgs = [{"role": "system", "content": "s"}, {"role": "user", "content": "u1"},
        {"role": "tool", "tool_call_id": "a", "content": "x" * 30000}, {"role": "user", "content": "u2"},
        {"role": "tool", "tool_call_id": "b", "content": "y" * 20000}]
c = agent.compact(msgs)
assert len(c[2]["content"]) < 400 and c[4]["content"] == "y" * 20000 and c[1] == msgs[1]
assert agent.compact(msgs[:2]) == msgs[:2]
print("compaction: old tool results shortened, latest kept")
print("\nALL OK")

# --- one turn with many tool calls is shortened too (job 21 overflowed the 16k context inside one turn)
big = "x" * 5000
ms = [{"role": "system", "content": "s"}, {"role": "user", "content": "u"}]
for i in range(12):
    ms += [{"role": "assistant", "content": None, "tool_calls": [{"id": f"t{i}"}]},
           {"role": "tool", "tool_call_id": f"t{i}", "content": big}]
out = agent.compact(ms, limit=20000)
assert sum(len(str(m.get("content") or "")) for m in out) < 30000 and out[-1]["content"] == big
print("compaction: older results inside a long turn are shortened, the latest stay")
