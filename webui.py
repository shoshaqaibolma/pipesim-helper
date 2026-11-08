"""
Browser chat window for the PIPESIM agent (standard library only; nothing to install).
  "D:\\Program\\Pipesim toolkit\\python.exe" webui.py        then open http://127.0.0.1:8765  (agent_ui.bat does both)
Listens on 127.0.0.1 only. One conversation at a time (a demo / single-user tool).
"""
import json, os, sys, threading, time, urllib.request, webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs, unquote

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)
import agent

PORT = int(os.getenv("PIPESIM_UI_PORT", "8765"))
SERVED = {"runs": os.path.join(ROOT, "runs"), "projects": os.path.join(ROOT, "projects")}


class Session:
    def __init__(self, client=None):
        self.client = client
        self.lock = threading.Lock()
        self.reset()

    def reset(self):
        self.msgs = agent.new_conversation()
        self.events, self.busy, self.approved = [], False, False
        self.plan_pending = False   # a plan was shown and not yet approved (Approve runs it once)

    def add(self, ev):
        ev = dict(ev, t=time.time())
        if ev["type"] == "result":
            ev["result"] = ui_result(ev["name"], ev["result"])
        with self.lock:
            if ev["type"] == "result" and ev["name"] == "propose_plan" and ev["result"].get("plan"):
                self.plan_pending = True
            self.events.append(ev)

    def start_turn(self, text, approval=False):
        with self.lock:
            if self.busy or (approval and not self.plan_pending):
                return False
            self.busy, self.approved = True, approval
            if approval:
                self.plan_pending = False
            self.events.append({"type": "user", "text": text, "approval": approval, "t": time.time()})

        def work():
            try:
                agent.run_turn(self.client, self.msgs, text, self.add)
            finally:
                with self.lock:
                    self.busy = False
        threading.Thread(target=work, daemon=True).start()
        return True


def to_url(path):
    """Absolute path of a run/project file -> /files/<folder>/<relative path> (None if outside them)."""
    try:
        p = os.path.abspath(path)
    except Exception:
        return None
    for key, base in SERVED.items():
        if p.startswith(os.path.abspath(base) + os.sep):
            return "/files/" + key + "/" + os.path.relpath(p, base).replace(os.sep, "/")
    return None


def ui_result(name, result):
    """What the window shows for a tool result: plans, charts, reports, files; everything else compactly."""
    if not isinstance(result, dict):
        return {"text": str(result)[:500]}
    out = {k: result[k] for k in ("error", "plan", "next_step", "warnings", "summary", "file", "rejected")
           if k in result}
    if "charts" in result:
        out["charts"] = [u for u in (to_url(c) for c in result.get("charts") or []) if u]
    for k in ("report", "csv", "file"):
        if result.get(k):
            out[f"{k}_url"] = to_url(result[k])
    if "table" in result:
        out["table"] = result["table"][:41]
    if "missing" in result:
        out["missing"] = [m.get("question") for m in result["missing"]]
    if "project" in result and isinstance(result["project"], str):
        out["project"] = result["project"]
    return out


SESSION = Session()


def llm_ready():
    try:
        return urllib.request.urlopen(agent.BASE_URL.rsplit("/v1", 1)[0] + "/health", timeout=2).status == 200
    except Exception:
        return False


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, body, ctype="application/json"):
        data = body if isinstance(body, bytes) else json.dumps(body, default=str).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        u = urlparse(self.path)
        if u.path in ("/", "/index.html"):
            return self._send(200, open(os.path.join(ROOT, "webui", "index.html"), "rb").read(), "text/html; charset=utf-8")
        if u.path == "/api/events":
            since = int(parse_qs(u.query).get("since", ["0"])[0])
            with SESSION.lock:
                return self._send(200, {"events": SESSION.events[since:], "n": len(SESSION.events), "busy": SESSION.busy})
        if u.path == "/api/health":
            return self._send(200, {"model": llm_ready(), "busy": SESSION.busy})
        if u.path.startswith("/files/"):
            parts = unquote(u.path[len("/files/"):]).split("/", 1)
            base = SERVED.get(parts[0])
            if base and len(parts) == 2:
                p = os.path.abspath(os.path.join(base, parts[1]))
                if p.startswith(os.path.abspath(base) + os.sep) and os.path.isfile(p):
                    ctype = {".png": "image/png", ".md": "text/plain; charset=utf-8", ".csv": "text/csv; charset=utf-8",
                             ".json": "application/json"}.get(os.path.splitext(p)[1].lower(), "application/octet-stream")
                    return self._send(200, open(p, "rb").read(), ctype)
            return self._send(404, {"error": "not found"})
        self._send(404, {"error": "not found"})

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        try:
            body = json.loads(self.rfile.read(n) or b"{}")
        except ValueError:
            body = {}
        if self.path == "/api/send":
            text = (body.get("text") or "").strip()
            if not text:
                return self._send(400, {"error": "empty message"})
            ok = SESSION.start_turn(text)
            return self._send(200, {"ok": ok} if ok else {"ok": False, "error": "the assistant is still working"})
        if self.path == "/api/approve":
            ok = SESSION.start_turn("Approved. Go ahead.", approval=True)
            return self._send(200, {"ok": ok} if ok else {"ok": False, "error": "no plan waiting for approval"})
        if self.path == "/api/reset":
            if SESSION.busy:
                return self._send(409, {"error": "busy"})
            SESSION.reset()
            return self._send(200, {"ok": True})
        self._send(404, {"error": "not found"})


def install_hooks(session):
    # Studies and model files run only in a turn started by the Approve button.
    agent.HOOKS["confirm"] = lambda question: session.approved
    agent.HOOKS["progress"] = lambda text: session.add({"type": "progress", "text": text})


def serve(port=PORT, open_browser=True, client=None):
    from openai import OpenAI
    SESSION.client = client or OpenAI(base_url=agent.BASE_URL, api_key="sk-local", timeout=900, max_retries=1)
    install_hooks(SESSION)
    httpd = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    url = f"http://127.0.0.1:{port}"
    print(f"PIPESIM assistant running at {url}  (Ctrl+C to stop)")
    if open_browser:
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    return httpd


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    serve().serve_forever()
