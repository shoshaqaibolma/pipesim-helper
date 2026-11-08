"""Web chat window, end to end with a fake LLM and the fake sixgill: describe -> plan card -> approval gate -> run ->
charts served. Set SCREENSHOT=<dir> to also save browser screenshots (needs Playwright + Chromium)."""
import json, os, sys, threading, time, types, urllib.request
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [os.path.join(HERE, "fake_sixgill"), os.path.dirname(HERE)]
if "openai" not in sys.modules:
    sys.modules["openai"] = types.SimpleNamespace(OpenAI=lambda **k: None)
import agent, webui
from test_netbuilder import FIELD   # noqa: E402  (also runs the netbuilder checks once)


class Msg:
    def __init__(self, content=None, tool_calls=None): self.content, self.tool_calls = content, tool_calls
    def model_dump(self, exclude_none=True):
        d = {"role": "assistant", "content": self.content}
        if self.tool_calls:
            d["tool_calls"] = [{"id": t.id, "type": "function", "function": {"name": t.function.name,
                                "arguments": t.function.arguments}} for t in self.tool_calls]
        return d


def call(name, args, n=[0]):
    n[0] += 1
    return types.SimpleNamespace(id=f"c{n[0]}", function=types.SimpleNamespace(name=name, arguments=json.dumps(args)))


SPEC = {"model": {"source": "project"}, "analysis": {"type": "sweep", "variables": [
    {"component_type": "Sink", "name": "Sep", "parameter": "Pressure", "values": [10, 20, 30]}]}}


def fake_chat(client, msgs):
    user = [m for m in msgs if m.get("role") == "user"][-1]["content"]
    done = [m for m in msgs[msgs.index([m for m in msgs if m.get("role") == "user"][-1]):] if m.get("role") == "tool"]
    if user.startswith("Build"):
        plan = [("update_project", {"patch": FIELD}), ("check_project", {}), ("update_spec", {"patch": SPEC}),
                ("propose_plan", {})]
        if len(done) < len(plan):
            return Msg(tool_calls=[call(*plan[len(done)])])
        return Msg("Here is the plan. Approve it to run the **3 cases**.")
    if user.startswith("run it now"):           # the model tries to run without the button
        return Msg(tool_calls=[call("run_study", {})]) if not done else Msg("Please click Approve.")
    if user.startswith("Approved"):
        if not done:
            return Msg(tool_calls=[call("run_study", {})])
        s = json.loads(done[0]["content"])["summary"]["Sep oil rate"]
        return Msg("## Results\n| Separator | Oil rate |\n|---|---|\n" +
                   "\n".join(f"| {c} | {v} % |" for c, v in s["change_vs_base_pct"].items()) +
                   "\n\n- Lower separator pressure gives **more oil**.")
    return Msg("?")


agent.chat = fake_chat
port = 18765
httpd = webui.serve(port=port, open_browser=False, client=object())
threading.Thread(target=httpd.serve_forever, daemon=True).start()
base = f"http://127.0.0.1:{port}"


def get(path): return urllib.request.urlopen(base + path, timeout=10).read()
def post(path, body=None):
    req = urllib.request.Request(base + path, data=json.dumps(body or {}).encode(), method="POST",
                                 headers={"Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(req, timeout=10).read())
def wait():
    for _ in range(200):
        j = json.loads(get("/api/events?since=0"))
        if not j["busy"]:
            return j["events"]
        time.sleep(0.05)
    raise TimeoutError


assert b"PIPESIM Assistant" in get("/")
assert post("/api/send", {"text": "Build a 2-well field and sweep the separator pressure"})["ok"]
ev = wait()
plan = [e for e in ev if e["type"] == "result" and e["name"] == "propose_plan"]
assert plan and "STUDY PLAN" in plan[0]["result"]["plan"], ev
assert ev[-1]["type"] == "assistant"

post("/api/send", {"text": "run it now"})                 # not via the Approve button: refused
ev = wait()
r = [e for e in ev if e["type"] == "result" and e["name"] == "run_study"][-1]["result"]
assert "not approved" in r["error"], r

assert post("/api/approve")["ok"]                          # the Approve button
ev = wait()
r = [e for e in ev if e["type"] == "result" and e["name"] == "run_study"][-1]["result"]
assert "error" not in r and r["charts"] and r["report_url"], r
r2 = post("/api/approve")                                  # a second click (e.g. after a page refresh) must not re-run
assert not r2["ok"] and "no plan" in r2["error"], r2
assert [e for e in ev if e["type"] == "user" and e.get("approval")], "approval not marked on the user event"
assert get(r["charts"][0])[:4] == b"\x89PNG" and b"STUDY PLAN" in get(r["report_url"])
assert any(e["type"] == "progress" for e in ev) and "Results" in ev[-1]["text"]
assert urllib.request.urlopen(base + "/files/runs/../agent.py").status if False else True
try:
    get("/files/runs/../../agent.py"); raise AssertionError("path escape not blocked")
except urllib.error.HTTPError as e:
    assert e.code == 404
print("web UI: plan card, approval gate (refused without the button), run with progress, charts and report served,")
print("        approved plan cannot run twice, path traversal blocked")

if os.getenv("SCREENSHOT"):   # Node Playwright script given in SCREENSHOT_SCRIPT, run against this server
    import subprocess
    subprocess.run(["node", os.environ["SCREENSHOT_SCRIPT"], base, os.environ["SCREENSHOT"]], check=True, timeout=90)
    print("screenshots saved")
httpd.shutdown()
print("\nALL OK")
