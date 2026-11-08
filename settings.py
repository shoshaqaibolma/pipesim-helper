"""
The assistant's settings, kept in settings.toml next to this file (replaces config.bat).
The installer writes it, the app's Settings panel edits it, and you can also edit it in Notepad.
"""
import os, re, tomllib

ROOT = os.path.dirname(os.path.abspath(__file__))
PATH = os.path.join(ROOT, "settings.toml")

# (section, key, default, label, help) - the Settings panel is built from this list
FIELDS = [
    ("paths", "pipesim_python", "", "PIPESIM Python",
     "python.exe of the PIPESIM Python Toolkit (has the sixgill package). Found by the installer."),
    ("paths", "llama_server", "", "Model server program", "llama-server.exe from llama.cpp. Installed by the installer."),
    ("paths", "model", "", "Language model file", "The .gguf file, e.g. Qwen3.5-9B-Q4_K_M.gguf (about 6 GB)."),
    ("model", "context", 16384, "Context size (tokens)", "16384 fits an 8 GB GPU. Use 8192 after an out-of-memory error."),
    ("model", "gpu_layers", 99, "Layers on the GPU", "99 = whole model on the GPU. 0 = CPU only (works, but much slower)."),
    ("model", "port", 8080, "Model server port", "Change only if another program uses 8080."),
    ("app", "ui_port", 8765, "App port", "Change only if another program uses 8765."),
    ("app", "number_check", True, "Number check",
     "Every number in a results answer must come from the simulation results; others are rewritten or flagged."),
    ("app", "recipes", True, "Worked examples (recipes)", "Short examples that help the small model set up studies."),
    ("app", "case_timeout_s", 600, "Case time limit (s)",
     "A case that runs longer is stopped and marked failed; the study continues with the rest."),
]
DEFAULTS = {s: {k: d for (sec, k, d, *_r) in FIELDS if sec == s} for s in ("paths", "model", "app")}


def _from_config_bat():
    """Values from the old config.bat (first start after updating), or {}."""
    path = os.path.join(ROOT, "config.bat")
    if not os.path.exists(path):
        return {}
    v = {}
    for line in open(path, encoding="utf-8", errors="replace"):
        m = re.match(r"\s*set\s+(\w+)=(.*)$", line, re.I)
        if m:
            v[m.group(1).upper()] = m.group(2).strip().strip('"')
    out = {"paths": {}, "model": {}}
    if v.get("PIPESIM_PY"):
        out["paths"]["pipesim_python"] = v["PIPESIM_PY"]
    if v.get("LLAMA_DIR"):
        out["paths"]["llama_server"] = os.path.join(v["LLAMA_DIR"], "llama-server.exe")
    if v.get("MODEL_PATH"):
        out["paths"]["model"] = v["MODEL_PATH"]
    for key, name in (("LLM_CTX", "context"), ("LLM_GPU_LAYERS", "gpu_layers")):
        if v.get(key, "").isdigit():
            out["model"][name] = int(v[key])
    return out


def load():
    """Settings with defaults filled in. Creates settings.toml from config.bat the first time."""
    s = {sec: dict(vals) for sec, vals in DEFAULTS.items()}
    if os.path.exists(PATH):
        with open(PATH, "rb") as f:
            stored = tomllib.load(f)
    else:
        stored = _from_config_bat()
        if stored:
            for sec, vals in stored.items():
                s[sec].update(vals)
            save(s)
    for sec, vals in stored.items():
        if sec in s:
            s[sec].update({k: v for k, v in vals.items() if k in s[sec]})
    return s


def _toml_value(v):
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return str(v)
    v = str(v)
    if "'" not in v and "\n" not in v:
        return f"'{v}'"          # literal string: Windows paths need no escaping
    return '"' + v.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n") + '"'


def coerce(values):
    """Type-check values from the Settings panel against FIELDS. Returns (settings, errors)."""
    s, errors = load(), []
    for sec, key, default, label, _h in FIELDS:
        if key not in values.get(sec, {}):
            continue
        v = values[sec][key]
        try:
            if isinstance(default, bool):
                v = v if isinstance(v, bool) else str(v).lower() in ("1", "true", "yes", "on")
            elif isinstance(default, int):
                v = int(v)
                if v < 0:
                    raise ValueError
            else:
                v = str(v).strip().strip('"')
        except (TypeError, ValueError):
            errors.append(f"{label}: enter a whole number of 0 or more")
            continue
        s[sec][key] = v
    return s, errors


def save(s):
    lines = ["# PIPESIM Assistant settings. Edit them in the app (Settings) or here; restart the app afterwards.", ""]
    for sec in ("paths", "model", "app"):
        lines.append(f"[{sec}]")
        for f_sec, key, *_r in FIELDS:
            if f_sec == sec:
                lines.append(f"{key} = {_toml_value(s[sec][key])}")
        lines.append("")
    tmp = PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\r\n") as f:
        f.write("\n".join(lines))
    os.replace(tmp, PATH)


def problems(s):
    """Missing files, in plain words, for the launcher and the Settings panel."""
    out = []
    for key, what in (("llama_server", "Model server program"), ("model", "Language model file")):
        p = s["paths"][key]
        if not p or not os.path.isfile(p):
            out.append(f"{what} not found{': ' + p if p else ''}. Run install.bat, or set it in Settings (or in settings.toml).")
    return out


def llm_url(s):
    return f"http://127.0.0.1:{s['model']['port']}/v1"


def apply_env(s):
    """Hand the settings to the agent modules, which read environment variables at import."""
    os.environ["LLM_URL"] = llm_url(s)
    os.environ["PIPESIM_UI_PORT"] = str(s["app"]["ui_port"])
    os.environ["PIPESIM_NUMBER_GUARD"] = "1" if s["app"]["number_check"] else "0"
    os.environ["PIPESIM_AGENT_KNOWLEDGE"] = "1" if s["app"]["recipes"] else "0"
    os.environ["PIPESIM_CASE_TIMEOUT"] = str(s["app"]["case_timeout_s"])


def llama_command(s):
    return [s["paths"]["llama_server"], "-m", s["paths"]["model"], "--jinja", "-c", str(s["model"]["context"]),
            "-ngl", str(s["model"]["gpu_layers"]), "-fa", "on", "--reasoning-budget", "0",
            "--host", "127.0.0.1", "--port", str(s["model"]["port"]), "--temp", "0"]
