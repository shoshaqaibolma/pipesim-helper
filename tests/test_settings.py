"""settings.toml: migration from config.bat, round trip with Windows paths, validation of Settings-panel input,
and the web UI's settings endpoints.  python tests/test_settings.py  (no PIPESIM or LLM needed)"""
import json, os, sys, tempfile, threading, tomllib, types, urllib.error, urllib.request
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [os.path.join(HERE, "fake_sixgill"), os.path.dirname(HERE)]
if "openai" not in sys.modules:
    sys.modules["openai"] = types.SimpleNamespace(OpenAI=lambda **k: None)
import settings

tmp = tempfile.mkdtemp(prefix="settings_test_")
settings.ROOT, settings.PATH = tmp, os.path.join(tmp, "settings.toml")

# 1. no files: defaults, nothing written
s = settings.load()
assert s["model"]["context"] == 16384 and s["app"]["number_check"] is True and not os.path.exists(settings.PATH)
assert settings.problems(s) and "install.bat" in settings.problems(s)[0]

# 2. first start after updating: config.bat is migrated into settings.toml
open(os.path.join(tmp, "config.bat"), "w").write(
    '@echo off\nset PIPESIM_PY=D:\\Program\\Pipesim toolkit\\python.exe\nset LLAMA_DIR=D:\\llama.cpp\\b12081\n'
    'set MODEL_PATH=D:\\models\\Qwen3.5-9B-Q4_K_M.gguf\nset LLM_CTX=8192\nset LLM_GPU_LAYERS=0\n')
s = settings.load()
assert os.path.exists(settings.PATH)
assert s["paths"]["pipesim_python"] == "D:\\Program\\Pipesim toolkit\\python.exe"
assert s["paths"]["llama_server"] == os.path.join("D:\\llama.cpp\\b12081", "llama-server.exe")
assert s["model"]["context"] == 8192 and s["model"]["gpu_layers"] == 0

# 3. the file is valid TOML that Notepad users can read; odd paths survive a round trip
s["paths"]["model"] = "C:\\Users\\O'Brien\\models\\my model.gguf"
settings.save(s)
raw = open(settings.PATH, encoding="utf-8").read()
assert "pipesim_python = 'D:\\Program\\Pipesim toolkit\\python.exe'" in raw, raw
assert tomllib.loads(raw)["paths"]["model"] == s["paths"]["model"]
assert settings.load()["paths"]["model"] == s["paths"]["model"]

# 4. Settings-panel input: numbers and checkboxes are typed; bad numbers are refused with the field's name
s2, err = settings.coerce({"model": {"context": "4096", "gpu_layers": "x"}, "app": {"number_check": False}})
assert err == ["Layers on the GPU: enter a whole number of 0 or more"], err
assert s2["model"]["context"] == 4096 and s2["app"]["number_check"] is False

# 5. command line and environment for the agent
cmd = settings.llama_command(s2)
assert cmd[cmd.index("-c") + 1] == "4096" and "--jinja" in cmd
settings.apply_env(s2)
assert os.environ["PIPESIM_NUMBER_GUARD"] == "0" and os.environ["LLM_URL"] == "http://127.0.0.1:8080/v1"
os.environ["PIPESIM_NUMBER_GUARD"] = "1"

# 6. the web UI's endpoints
import webui, agent
httpd = webui.serve(port=18767, open_browser=False, client=object())
threading.Thread(target=httpd.serve_forever, daemon=True).start()
base = "http://127.0.0.1:18767"


def call(path, body=None):
    req = urllib.request.Request(base + path, data=None if body is None else json.dumps(body).encode(),
                                 method="GET" if body is None else "POST", headers={"Content-Type": "application/json"})
    try:
        return json.loads(urllib.request.urlopen(req, timeout=10).read())
    except urllib.error.HTTPError as e:
        return json.loads(e.read())


j = call("/api/settings")
assert {f["key"] for f in j["fields"]} >= {"model", "context", "number_check"} and j["file"] == settings.PATH
r = call("/api/settings", {"values": {"model": {"context": "-5"}}})
assert not r["ok"] and "Context size" in r["error"], r
r = call("/api/settings", {"values": {"app": {"number_check": False}}})
assert r["ok"] and not r["restart"] and agent.NUMBER_GUARD is False, r          # applied at once, no model restart
r = call("/api/settings", {"values": {"model": {"context": 12288}}})
assert r["ok"] and not r["restart"], r      # needs a restart, but there is no launcher here to do it
assert settings.load()["model"]["context"] == 12288
h = call("/api/health")
assert h["launcher"] is False and "detail" in h
assert not call("/api/quit", {})["ok"]       # only the launcher can stop the app
httpd.shutdown()
agent.NUMBER_GUARD = True

print("settings: config.bat migrated, Windows paths round-trip, panel input validated, endpoints work")
print("\nALL OK")
