"""Quick check on the PC that llama-server accepts the JSON-schema calls (constrained extraction) and the strict
update_project tool schema. Prints the extracted project and study for two scenarios."""
import io, json, os, subprocess, sys, tempfile, time
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path[:0] = [ROOT, HERE]
from real_agent_test import healthy  # noqa: E402
from openai import OpenAI
import structured, project as prj
import agent

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True)
tmp = tempfile.mkdtemp(prefix="pipesim_smoke_")
server = None
if not healthy():
    server = subprocess.Popen(["cmd", "/c", os.path.join(ROOT, "start_llm.bat")], cwd=ROOT,
                              stdout=open(os.path.join(tmp, "llama.log"), "w"), stderr=subprocess.STDOUT)
    for _ in range(180):
        if healthy():
            break
        time.sleep(1)
client = OpenAI(base_url="http://127.0.0.1:8080/v1", api_key="sk-local", timeout=300)
try:
    for name in ("field_project", "pipeline_sizing", "choke_sizing"):
        text = open(os.path.join(HERE, "scripts", name + ".txt"), encoding="utf-8").readline().strip()
        t0 = time.time()
        try:
            p, dropped = structured.extract_project(client, "local", text)
            c = prj.check_project(p)
            print(f"\n=== {name}: project in {time.time() - t0:.1f}s; dropped {dropped}")
            print(prj.summary(p))
            print("check:", json.dumps({"errors": c["errors"], "missing": [m["field"] for m in c["missing"]]}))
            p = prj.apply_defaults(p, ["all"]); p = prj.apply_defaults(p, ["all"])
            t0 = time.time()
            a, dropped = structured.extract_study(client, "local", text, p)
            print(f"study in {time.time() - t0:.1f}s; dropped {dropped}: {json.dumps(a)}")
        except Exception as e:
            print(f"\n=== {name}: FAILED {type(e).__name__}: {str(e)[:500]}")
    # the strict tool schema is accepted by the server
    r = client.chat.completions.create(model="local", temperature=0, max_tokens=400, tools=agent.TOOLS,
                                       messages=[{"role": "system", "content": "Call update_project."},
                                                 {"role": "user", "content": "Add a sink SEP at 12 bara."}],
                                       extra_body={"chat_template_kwargs": {"enable_thinking": False}})
    m = r.choices[0].message
    print("\nstrict tool schema accepted; call:", [(t.function.name, t.function.arguments) for t in m.tool_calls or []])
finally:
    if server is not None:
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(server.pid)], capture_output=True)
