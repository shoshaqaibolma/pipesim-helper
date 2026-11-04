"""
One-command end-to-end test on the real PC: starts llama-server (if not already up), runs agent.py with a
scripted conversation on a TEMP COPY of a model, and prints a compact transcript for review.

  "D:\\Program\\Pipesim toolkit\\python.exe" tests\\real_agent_test.py "C:\\path\\to\\model.pips" [script.txt]

The script file has one user message per line; {MODEL} is replaced with the temp copy's path.
"""
import io, json, os, shutil, subprocess, sys, tempfile, time, urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_SCRIPT = [
    "Open {MODEL} and sweep the sink pressure from 10 to 40 bara in 4 steps. How does the total liquid rate change?",
    "Use the suggested defaults for anything else.",
    "Yes, the plan is approved. Run it.",
    "exit",
]


def healthy():
    try:
        return urllib.request.urlopen("http://127.0.0.1:8080/health", timeout=3).status == 200
    except Exception:
        return False


def main():
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True)
    model = sys.argv[1]
    lines = open(sys.argv[2], encoding="utf-8").read().splitlines() if len(sys.argv) > 2 else DEFAULT_SCRIPT
    tmp = tempfile.mkdtemp(prefix="pipesim_agenttest_")
    copy = os.path.join(tmp, os.path.basename(model))
    shutil.copy2(model, copy)
    script = os.path.join(tmp, "script.txt")
    open(script, "w", encoding="utf-8").write("\n".join(l.replace("{MODEL}", copy) for l in lines))
    log = os.path.join(tmp, "log.jsonl")

    server = None
    if not healthy():
        print("starting llama-server ...")
        server = subprocess.Popen(["cmd", "/c", os.path.join(ROOT, "start_llm.bat")], cwd=ROOT,
                                  stdout=open(os.path.join(tmp, "llama.log"), "w"), stderr=subprocess.STDOUT)
        for _ in range(180):
            if healthy() or server.poll() is not None:
                break
            time.sleep(1)
        if not healthy():
            print("LLAMA-SERVER DID NOT START. Last log lines:")
            print("".join(open(os.path.join(tmp, "llama.log"), errors="replace").readlines()[-25:]))
            return
    t0 = time.time()
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    p = subprocess.run([sys.executable, os.path.join(ROOT, "agent.py"), "--script", script, "--log", log],
                       cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace", env=env)
    dt = time.time() - t0
    print(f"=== agent finished in {dt:.0f}s, exit code {p.returncode}")
    if p.returncode:
        print(p.stderr[-3000:])
    print("=== transcript (tool results shortened)")
    for line in open(log, encoding="utf-8"):
        e = json.loads(line)
        if "user" in e:
            print(f"\nUSER: {e['user']}")
        elif "agent" in e:
            print(f"AGENT: {e['agent'].strip()[:1500]}")
        elif "tool" in e:
            print(f"  TOOL {e['tool']}({e['args'][:300]}) -> {e['result'][:400]}")
        elif "final_spec" in e:
            print(f"\n=== final spec\n{json.dumps(e['final_spec'], indent=1)[:2000]}")
    runs = os.path.join(ROOT, "runs")
    if os.path.isdir(runs):
        latest = max((os.path.join(runs, d) for d in os.listdir(runs)), key=os.path.getmtime, default=None)
        if latest and os.path.getmtime(latest) > t0:
            print(f"\n=== study output {latest}: {sorted(os.listdir(latest))}")
            rep = os.path.join(latest, "report.md")
            if os.path.exists(rep):
                print(open(rep, encoding="utf-8").read()[:3000])
    if server is not None:
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(server.pid)], capture_output=True)
        print("\n(llama-server stopped)")
    print(f"\n(temp files in {tmp})")


if __name__ == "__main__":
    main()
