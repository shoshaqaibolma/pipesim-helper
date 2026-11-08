"""
Real test of the browser chat backend with the local LLM and PIPESIM (no browser needed): starts llama-server if
needed, starts webui on port 8799, sends the field description, "use defaults", then presses Approve through the API.
Prints the conversation and copies the charts to runner\\artifacts\\.
  "D:\\Program\\Pipesim toolkit\\python.exe" tests\\real_webui_test.py
"""
import json, os, shutil, subprocess, sys, threading, time, urllib.request
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


def healthy(url="http://127.0.0.1:8080/health"):
    try:
        return urllib.request.urlopen(url, timeout=3).status == 200
    except Exception:
        return False


def main():
    server = None
    if not healthy():
        server = subprocess.Popen([sys.executable, os.path.join(ROOT, "launch.py"), "--model-only"], cwd=ROOT,
                                  stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
        for _ in range(180):
            if healthy():
                break
            time.sleep(1)
    import webui
    httpd = webui.serve(port=8799, open_browser=False)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    base = "http://127.0.0.1:8799"

    def post(path, body=None):
        req = urllib.request.Request(base + path, data=json.dumps(body or {}).encode(), method="POST",
                                     headers={"Content-Type": "application/json"})
        return json.loads(urllib.request.urlopen(req, timeout=30).read())

    def wait(limit=900):
        t0 = time.time()
        while time.time() - t0 < limit:
            j = json.loads(urllib.request.urlopen(base + "/api/events?since=0", timeout=30).read())
            if not j["busy"]:
                return j["events"]
            time.sleep(1)
        raise TimeoutError

    try:
        print("health:", urllib.request.urlopen(base + "/api/health").read().decode())
        assert b"PIPESIM Assistant" in urllib.request.urlopen(base + "/").read()
        script = open(os.path.join(ROOT, "tests", "scripts", "field_project.txt"), encoding="utf-8").read().splitlines()
        post("/api/send", {"text": script[0]}); wait()
        post("/api/send", {"text": "Use the suggested defaults for everything else."}); ev = wait()
        for attempt in range(2):   # press Approve once a plan card exists (the model may need one more turn)
            if any(e["type"] == "result" and e["name"] == "propose_plan" and "plan" in e["result"] for e in ev):
                post("/api/approve"); ev = wait(); break
            post("/api/send", {"text": "Please show me the plan."}); ev = wait()
        for e in ev:
            if e["type"] in ("user", "assistant", "error"):
                print(f"\n{e['type'].upper()}: {e['text'][:1500]}")
            elif e["type"] == "tool":
                print(f"  TOOL {e['name']}")
            elif e["type"] == "result" and e["name"] == "run_study":
                r = e["result"]
                print("  RESULT run_study:", json.dumps({k: r.get(k) for k in ("error", "charts", "report_url", "warnings")})[:600])
                os.makedirs(os.path.join(ROOT, "runner", "artifacts"), exist_ok=True)
                for u in r.get("charts") or []:
                    data = urllib.request.urlopen(base + u).read()
                    open(os.path.join(ROOT, "runner", "artifacts", "webui_" + u.rsplit("/", 1)[1]), "wb").write(data)
        print("\nchart files served:", sum(1 for e in ev if e["type"] == "result" and e["name"] == "run_study"
                                           and e["result"].get("charts")))
    finally:
        httpd.shutdown()
        if server is not None:
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(server.pid)], capture_output=True)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
    main()
