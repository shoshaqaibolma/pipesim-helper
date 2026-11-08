"""
Starts the PIPESIM Assistant: the local model server (llama-server) in the background, the app, and a window.
The desktop shortcut made by install.bat runs this with PIPESIM's pythonw.exe (no console window).

  launch.py               app in its own window (Microsoft Edge app mode; the default browser if Edge is missing).
                          Closing the window stops the assistant and the model server.
  launch.py --terminal    chat in this console instead
  launch.py --model-only  only the model server, in the foreground (for tests; Ctrl+C stops it)
"""
import json, os, socket, subprocess, sys, threading, time, urllib.request, webbrowser

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)
LOG_DIR = os.path.join(ROOT, "logs")
os.makedirs(LOG_DIR, exist_ok=True)
if sys.stdout is None or sys.stderr is None:      # pythonw.exe: no console, so print() goes to a log file
    sys.stdout = sys.stderr = open(os.path.join(LOG_DIR, "app.log"), "a", encoding="utf-8", buffering=1)

import settings

NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def answers(url, timeout=2):
    try:
        return urllib.request.urlopen(url, timeout=timeout).status == 200
    except Exception:
        return False


def is_our_app(url):
    try:
        return "busy" in json.loads(urllib.request.urlopen(url + "/api/health", timeout=2).read())
    except Exception:
        return False


def port_taken(port):
    with socket.socket() as sock:
        sock.settimeout(1)
        return sock.connect_ex(("127.0.0.1", port)) == 0


def free_port(start):
    for p in range(start + 1, start + 50):
        if not port_taken(p):
            return p
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class ModelServer:
    """llama-server in the background. status: {"state": "starting"|"ready"|"error", "detail": text}."""

    def __init__(self, s):
        self.s, self.proc = s, None
        self.status = {"state": "starting", "detail": "starting the language model..."}
        self.health = f"http://127.0.0.1:{s['model']['port']}/health"
        self.log = os.path.join(LOG_DIR, "model-server.log")

    def start(self):
        if answers(self.health):
            self.status = {"state": "ready", "detail": "model ready"}
            return True
        missing = settings.problems(self.s)
        if missing:
            self.status = {"state": "error", "detail": " ".join(missing)}
            return False
        self.status = {"state": "starting", "detail": "loading the language model (up to a minute)..."}
        self.proc = subprocess.Popen(settings.llama_command(self.s), cwd=os.path.dirname(self.s["paths"]["llama_server"]),
                                     stdout=open(self.log, "w", encoding="utf-8"), stderr=subprocess.STDOUT,
                                     creationflags=NO_WINDOW)
        for _ in range(240):
            if answers(self.health):
                self.status = {"state": "ready", "detail": "model ready"}
                return True
            if self.proc.poll() is not None:
                break
            time.sleep(0.5 if _ < 20 else 1)
        self.status = {"state": "error", "detail": "The language model did not start. " + self._hint()}
        self.stop()
        return False

    def _hint(self):
        try:
            tail = open(self.log, encoding="utf-8", errors="replace").read()[-3000:].lower()
        except OSError:
            tail = ""
        if "out of memory" in tail or "failed to allocate" in tail:
            return "The GPU ran out of memory: close other GPU programs, or lower the context size to 8192 in Settings."
        if "address already in use" in tail or "bind" in tail:
            return f"Port {self.s['model']['port']} is used by another program: change the model server port in Settings."
        return f"Details are in {self.log}."

    def stop(self):
        if self.proc and self.proc.poll() is None:
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(self.proc.pid)], capture_output=True,
                           creationflags=NO_WINDOW)
        self.proc = None

    def restart(self, s):
        self.stop()
        self.s = s
        self.health = f"http://127.0.0.1:{s['model']['port']}/health"
        threading.Thread(target=self.start, daemon=True).start()


def find_edge():
    for base in (os.environ.get("ProgramFiles(x86)"), os.environ.get("ProgramFiles"), os.environ.get("LOCALAPPDATA")):
        p = os.path.join(base or "", "Microsoft", "Edge", "Application", "msedge.exe")
        if base and os.path.exists(p):
            return p
    return None


def open_window(url):
    """Opens the app window and returns the window's process (None if only a browser tab could be opened)."""
    edge = find_edge()
    if edge:
        profile = os.path.join(os.environ.get("LOCALAPPDATA", ROOT), "PIPESIM Assistant", "window")
        return subprocess.Popen([edge, f"--app={url}", f"--user-data-dir={profile}", "--window-size=1280,900",
                                 "--no-first-run", "--no-default-browser-check"])
    webbrowser.open(url)
    return None


def main():
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    s = settings.load()
    mode = sys.argv[1] if len(sys.argv) > 1 else ""
    port = s["model"]["port"]
    if mode != "--model-only" and port_taken(port) and not answers(f"http://127.0.0.1:{port}/health"):
        s["model"]["port"] = free_port(port)   # another program uses the model port: take a free one this time
        print(f"Port {port} is used by another program; the model server uses port {s['model']['port']} instead.")
    settings.apply_env(s)
    server = ModelServer(s)

    if mode == "--model-only":
        if settings.problems(s):
            sys.exit(" ".join(settings.problems(s)))
        sys.exit(subprocess.call(settings.llama_command(s), cwd=os.path.dirname(s["paths"]["llama_server"])))

    if mode == "--terminal":
        print("Starting the language model (up to a minute)...")
        if not server.start():
            print(server.status["detail"])
            input("Press Enter to close.")
            return
        import agent
        try:
            agent.main()
        finally:
            server.stop()
        return

    url = f"http://127.0.0.1:{s['app']['ui_port']}"
    if is_our_app(url):                       # already running: just show it
        open_window(url)
        return
    import webui
    stop = threading.Event()
    webui.APP.update(model=lambda: server.status,
                     restart_model=lambda: server.restart(settings.load()), quit=stop.set)
    httpd = webui.serve(port=s["app"]["ui_port"], open_browser=False, any_port=True)
    url = f"http://127.0.0.1:{httpd.server_address[1]}"   # another program may have had the usual port
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    threading.Thread(target=server.start, daemon=True).start()
    print(f"PIPESIM Assistant at {url}")
    window = open_window(url)
    try:
        if window:
            while window.poll() is None and not stop.is_set():
                time.sleep(0.5)
        else:
            stop.wait()
    except KeyboardInterrupt:
        pass
    finally:
        if window and window.poll() is None:
            window.terminate()
        httpd.shutdown()
        server.stop()


if __name__ == "__main__":
    main()
