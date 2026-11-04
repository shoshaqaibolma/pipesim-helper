"""
PIPESIM study agent. Describe a study in plain language and it will:
  understand -> ask about missing parameters -> propose a plan -> (you approve) -> run -> analyze.
Usage:  python agent.py         (llama-server must be running, see start_llm.bat)
"""
import json, os, sys
from openai import OpenAI
import pipesim_tools as pt
import study, executor, netbuilder
import project as prj
from builder import TEMPLATES

BASE_URL = os.getenv("LLM_URL", "http://127.0.0.1:8080/v1")
MODEL = os.getenv("LLM_MODEL", "local")
MAX_STEPS = 25

SYSTEM = f"""You are a petroleum production engineer who runs SLB PIPESIM studies for the user through tools.

WORKFLOW (follow it strictly):
1. UNDERSTAND: turn the request into a study spec with update_spec. If the user names an existing
   .pips file, call inspect_model first so you use REAL component names.
2. ASK: call check_spec. If "missing" is not empty, ask the user about those items in ONE short numbered
   message. Show each suggested default and its unit, and say they can reply "use defaults".
   Never fill in a missing value yourself unless the user agrees. Fix any "errors" too.
3. PLAN: when check_spec says ready, call propose_plan and show the plan to the user word for word.
   Ask them to approve it or change it.
4. RUN: only after the user approves, call run_study. The user also confirms in the terminal.
5. ANALYZE: explain the results: trends, optimum, sensitivities, constraints, and anything that looks
   physically odd. Quote numbers ONLY from the returned "table" and "summary"; percentage changes, best and
   worst cases, tornado rankings and the optimum are precomputed there, so never calculate them yourself.
   summary.not_flowing lists wells that produce nothing in a case: say so explicitly. Give the report
   path. Suggest a sensible follow-up study.

NEW NETWORKS (the user wants to build/create a field, network, pipeline or project):
A. Put EVERYTHING the user gave into ONE update_project call, using exactly the field names below. Use only the
   components the user describes: do not add junctions, chokes or flowlines they did not mention. A single well
   or source can connect straight to its sink with one flowline.
B. Call check_project. If "missing" is not empty, ask the user about those items in ONE numbered message,
   grouped by component, with the suggested defaults. Never invent values that have no suggested default.
   If the user says "use defaults", call use_defaults(["all"]) and then check_project again.
C. When check_project is ready: if the user wants a PIPESIM file, call build_project(path). For a study on it,
   call update_spec with model.source = "project", then continue with steps 2-5 above.

PROJECT SCHEMA (every list item needs a unique "name"; units in brackets):
  fluids:    {{"name","type":"black_oil","api","gor"[sm3/sm3],"water_cut"[%, 20 means 20%],"gas_sg"}}
             or {{"name","type":"gas","gas_sg","ogr"[sm3/mmsm3],"wgr"[sm3/mmsm3],"api"}}
  wells:     {{"name","fluid","reservoir_pressure"[bara],"reservoir_temperature"[degC],"depth"[m],"tubing_id"[mm],
              "ipr":{{"model":"pi","liquid_pi"[sm3/d/bar]}}}}  (or {{"model":"vogel","aof"[sm3/d]}} or
              {{"model":"backpressure","c"[mmsm3/d/bar^2n],"n"}}); optional "gas_lift":{{"depth"[m],"rate"[mmsm3/d]}}
  sources:   {{"name","fluid","temperature"[degC]}} plus ONE of "pressure"[bara], "liquid_rate"[sm3/d], "gas_rate"[mmsm3/d].
             Sources are pipeline inlets or external streams, NOT wells.
  junctions: {{"name"}}  (manifolds, tie-in points)
  sinks:     {{"name","pressure"[bara]}}  (separator, delivery point)
  chokes:    {{"name","bean_size"[mm]}}  plus EITHER "from" (installed right after that node) OR a flowline ending at it
  separators:{{"name","efficiency"[%]}}  (two-phase; flowlines leaving it need "port":"gas" or "liquid")
  pumps / compressors: {{"name","efficiency"[%]}} plus ONE of "pressure"[bara discharge], "pressure_rise"[bar],
             "pressure_ratio", "power"[kW]; inlet like a choke ("from" or a flowline ending at it)
  flowlines: {{"name","from","to","length"[m],"id"[mm],"elevation_change"[m, + uphill]}} (+ "port" after a separator)
EXAMPLE (only for "2 wells into a manifold, 5 km trunkline to a separator at 15 bara"; copy the format, not the parts):
  {{"name":"Field A","fluids":[{{"name":"BO","type":"black_oil","api":35,"gor":100,"water_cut":20,"gas_sg":0.7}}],
   "wells":[{{"name":"W1","fluid":"BO","reservoir_pressure":250,"depth":2500,"ipr":{{"model":"pi","liquid_pi":10}}}},
            {{"name":"W2","fluid":"BO","reservoir_pressure":230,"depth":2400,"ipr":{{"model":"pi","liquid_pi":15}}}}],
   "junctions":[{{"name":"J1"}}],"sinks":[{{"name":"SEP","pressure":15}}],
   "flowlines":[{{"name":"FL-W1","from":"W1","to":"J1","length":1500,"id":100,"elevation_change":0}},
                {{"name":"FL-W2","from":"W2","to":"J1","length":900,"id":100,"elevation_change":0}},
                {{"name":"Trunk","from":"J1","to":"SEP","length":5000,"id":152,"elevation_change":10}}]}}
STUDY VARIABLES on a project (component_type / name / parameter):
  separator or sink pressure: Sink / <sink> / Pressure;  reservoir pressure: Completion / <well>:<well>_Comp / ReservoirPressure
  choke size: Choke / <choke> / BeanSize;  flowline diameter: Flowline / <flowline> / InnerDiameter
  gas lift rate: GasLiftInjection / <well>:<well>_GL / GasRate  (the well needs "gas_lift" in the project)
  compressor or pump: Compressor|Pump / <name> / Power | PressureDifferential | Pressure  (whichever it was specified by)

Analysis types: {json.dumps(study.ANALYSES)}
Model templates for new models: { {k: v['description'] for k, v in TEMPLATES.items()} }
Template sweep aliases: { {k: list(v['aliases']) for k, v in TEMPLATES.items()} }
Nodal analysis of a well: analysis = {{"type":"nodal","producer":"<well>","outlet_pressure":<bara>}}.
Gas lift allocation ("share X mmsm3/d of lift gas between the wells to maximize oil"): analysis =
  {{"type":"optimize","variables":[{{"component_type":"GasLiftInjection","name":"W1:W1_GL","parameter":"GasRate",
  "values":[0,0.05,0.1]}}, ... one per well ...],"max_total":X}}. The answer is summary.optimum.best.
P/T profiles need ONE boundary condition in analysis.conditions: {{"outlet_pressure": x}} OR {{"liquid_flowrate": x}} OR {{"gas_flowrate": x}}.
For existing models, refer to variables as component_type + name + parameter (e.g. Sink / "Sink-1" / "Pressure").
Use model units (METRIC unless the user says FIELD). Never invent results: every number comes from a tool.
Every check_spec and check_project result has a "next_step" field: always do exactly what it says.
Keep messages short."""

SPEC = {}
PROJECT = {}
STATE = {"plan_ok_for": None, "components": None}


def _plan_key():
    return json.dumps([SPEC, PROJECT if SPEC.get("model", {}).get("source") == "project" else None], sort_keys=True)


def update_spec(patch: dict):
    """Merge fields into the study spec. To replace a list (e.g. analysis.variables), send the whole list."""
    global SPEC
    SPEC = study.merge(SPEC, patch)
    STATE["plan_ok_for"] = None
    return {"spec": SPEC}


def check_spec():
    """Validate the spec. Returns missing items (ask the user about these), errors, and the number of cases."""
    src = SPEC.get("model", {}).get("source")
    return study.check(SPEC, None if src == "project" else STATE["components"], PROJECT or None)


def propose_plan():
    """Render the plan for the user to approve. Only works when check_spec says ready."""
    c = check_spec()
    if not c["ready"]:
        return {"error": "Spec not ready", **c}
    STATE["plan_ok_for"] = _plan_key()
    return {"plan": study.plan_text(SPEC, PROJECT)}


def run_study():
    """Execute the approved plan: runs every case and writes CSV, charts and report.md."""
    if STATE["plan_ok_for"] != _plan_key():
        return {"error": "The spec or project changed, or was never planned. Call propose_plan and get user "
                         "approval first."}
    print("\n" + study.plan_text(SPEC, PROJECT))
    if input("\n  Run this study now? [y/N] ").strip().lower() != "y":
        return {"error": "User did not approve the run in the terminal."}
    pt.close_model() if pt._state["model"] else None
    return executor.run(SPEC, progress=lambda s: print("   " + s), project=PROJECT or None)


def update_project(patch: dict):
    """Add or change parts of the network being described. Lists (wells, flowlines, ...) merge by "name";
    {"name": "X", "_delete": true} removes X."""
    global PROJECT
    PROJECT, notes, errors = prj.apply_patch(PROJECT, patch)
    STATE["plan_ok_for"] = None
    out = {"project": prj.summary(PROJECT), "next_step": "Call check_project."}
    if notes:
        out["normalized"] = notes
    if errors:
        out["rejected"] = errors
        out["next_step"] = "Fix the rejected items with exactly the schema field names, then call check_project."
    return out


def use_defaults(fields: list):
    """Fill missing project inputs with their suggested defaults. fields: ["all"] or field paths from check_project."""
    global PROJECT
    for _ in range(2):  # a filled field can reveal dependent ones (e.g. fluid type -> fluid properties)
        PROJECT = prj.apply_defaults(PROJECT, fields)
    STATE["plan_ok_for"] = None
    c = check_project()
    return {"project": prj.summary(PROJECT), "still_missing": c["missing"], "errors": c["errors"],
            "next_step": c["next_step"]}


def check_project():
    """Validate the described network: missing inputs per component (ask the user) and layout errors."""
    c = prj.check_project(PROJECT)
    if c["ready"]:
        c["next_step"] = ("Project complete. If the user wants a PIPESIM file, call build_project(path). For a study, "
                          "call update_spec with model.source = \"project\" and continue the study workflow.")
    return c


def build_project(path: str):
    """Build the described network as a new PIPESIM .pips file the user can open. Never overwrites a file."""
    c = prj.check_project(PROJECT)
    if not c["ready"]:
        return {"error": "Project not complete. Call check_project first.", **c}
    path = path if path.lower().endswith(".pips") else path + ".pips"
    if not os.path.isabs(path):  # relative names go to the projects folder, not the code folder
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "projects", path)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if os.path.exists(path):
        return {"error": f"{path} already exists. Ask the user for a new file name."}
    print("\n" + prj.summary(PROJECT) + f"\n\n  -> {path}")
    if input("\n  Build this PIPESIM model now? [y/N] ").strip().lower() != "y":
        return {"error": "User did not approve the build in the terminal."}
    rep = netbuilder.build_file(PROJECT, path)
    with open(os.path.splitext(path)[0] + ".project.json", "w", encoding="utf-8") as f:
        json.dump(PROJECT, f, indent=2)
    return rep


def inspect_model(path: str, units: str = "METRIC"):
    """Open an existing .pips model read-only and list its components, so the spec can use real names."""
    r = pt.open_model(path=path, units=units)
    if "error" in r:
        return r
    STATE["components"] = pt.model_summary()
    return {"components": STATE["components"]}


def get_values(component_type: str, parameters: list, name: str = ""):
    """Read current parameter values from the inspected model (e.g. to find base-case values)."""
    return pt.get_values(component_type=component_type, parameters=parameters, name=name)


FUNCS = {f.__name__: f for f in (update_spec, check_spec, propose_plan, run_study, inspect_model, get_values,
                                  update_project, check_project, build_project, use_defaults)}
_S = {"type": "string"}
PARAMS = {
    "update_spec": ({"patch": {"type": "object", "description": "Partial spec to merge. Keys: objective, units, "
                               "model{source: existing|new|project, path|template,params}, base_changes[], "
                               "analysis{type,variables[],producer,conditions}, kpis[]"}},
                    ["patch"]),
    "check_spec": ({}, []), "propose_plan": ({}, []), "run_study": ({}, []),
    "inspect_model": ({"path": _S, "units": {"type": "string", "enum": ["METRIC", "FIELD", "SI"]}}, ["path"]),
    "get_values": ({"component_type": _S, "name": _S, "parameters": {"type": "array", "items": _S}},
                   ["component_type", "parameters"]),
    "update_project": ({"patch": {"type": "object", "description": "Partial project following the PROJECT SCHEMA in "
                                  "the instructions: name, fluids[], wells[], sources[], junctions[], sinks[], chokes[], "
                                  "flowlines[]; every item has a unique name"}}, ["patch"]),
    "use_defaults": ({"fields": {"type": "array", "items": _S,
                                 "description": "[\"all\"] or field paths from check_project's missing list"}}, ["fields"]),
    "check_project": ({}, []),
    "build_project": ({"path": {"type": "string", "description": "Where to save the new .pips file"}}, ["path"]),
}
TOOLS = [{"type": "function", "function": {"name": n, "description": FUNCS[n].__doc__,
          "parameters": {"type": "object", "properties": p, "required": r}}} for n, (p, r) in PARAMS.items()]


MAX_SPEC_CALLS = 10    # spec/project edit+check calls allowed per user turn before the agent must ask the user
MAX_REPLY_TOKENS = 1500


MAX_HISTORY_CHARS = 40000   # about 10k tokens: keeps long sessions inside the 16k context of the local model


def compact(msgs, limit=MAX_HISTORY_CHARS):
    """Shorten old tool results (before the latest user message) when the conversation gets long."""
    size = sum(len(str(m.get("content") or "")) for m in msgs)
    if size <= limit:
        return msgs
    last_user = max(i for i, m in enumerate(msgs) if m.get("role") == "user")
    out = []
    for i, m in enumerate(msgs):
        if i < last_user and m.get("role") == "tool" and len(str(m.get("content") or "")) > 300:
            m = dict(m, content=str(m["content"])[:300] + " ...[older result shortened]")
        out.append(m)
    return out


def chat(client, msgs):
    msgs[:] = compact(msgs)
    return client.chat.completions.create(
        model=MODEL, messages=msgs, tools=TOOLS, temperature=0.0, max_tokens=MAX_REPLY_TOKENS,
        # Qwen 3.5 thinks by default; on a 16k context that can eat the whole window and return an empty reply.
        extra_body={"chat_template_kwargs": {"enable_thinking": False}}).choices[0].message


def main():
    import argparse
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    ap = argparse.ArgumentParser()
    ap.add_argument("--script", help="text file with one user message per line (for unattended tests); "
                                     "terminal approvals are answered 'y' automatically")
    ap.add_argument("--log", help="write the full conversation as JSONL to this file")
    args = ap.parse_args()
    global SPEC, PROJECT, input
    script = [l.rstrip("\n") for l in open(args.script, encoding="utf-8") if l.strip()] if args.script else None
    if script is not None:
        import builtins
        _real_input = builtins.input

        def input(prompt=""):
            if "[y/N]" in prompt:
                print(prompt + "y (auto, --script)"); return "y"
            if not script:
                raise EOFError
            line = script.pop(0); print(prompt + line); return line
        builtins.input = input  # run_study's approval prompt uses input() too
    log = open(args.log, "a", encoding="utf-8") if args.log else None

    def show(text):
        try:
            print(text)
        except UnicodeEncodeError:
            print(text.encode("ascii", "replace").decode())
        if log:
            log.write(json.dumps({"agent": text}) + "\n"); log.flush()

    client = OpenAI(base_url=BASE_URL, api_key="sk-local", timeout=600, max_retries=1)
    msgs = [{"role": "system", "content": SYSTEM}]
    show("PIPESIM study agent. Describe what you want to simulate. Commands: 'spec', 'reset', 'exit'.\n")
    while True:
        try:
            user = input("you> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if log:
            log.write(json.dumps({"user": user}) + "\n")
        if user.lower() in {"exit", "quit"}:
            break
        if user.lower() == "spec":
            show(json.dumps(SPEC, indent=2) + ("\n" + prj.summary(PROJECT) if PROJECT else "")); continue
        if user.lower() == "reset":
            SPEC = {}; PROJECT = {}; STATE.update(plan_ok_for=None, components=None)
            msgs = msgs[:1]; show("(new study)\n"); continue
        if not user:
            continue
        turn_start = len(msgs)
        msgs.append({"role": "user", "content": user})
        spec_calls = 0
        try:
            for _ in range(MAX_STEPS):
                msg = chat(client, msgs)
                msgs.append(msg.model_dump(exclude_none=True))
                if not msg.tool_calls:
                    show(f"\nagent> {msg.content or '(empty reply: try rephrasing, or type reset)'}\n"); break
                for tc in msg.tool_calls:
                    name = tc.function.name
                    try:
                        targs = json.loads(tc.function.arguments or "{}")
                        print(f"  [{name}] {json.dumps(targs)[:160]}")
                        if name in ("update_spec", "check_spec", "update_project", "check_project", "use_defaults"):
                            spec_calls += 1
                        if spec_calls > MAX_SPEC_CALLS:
                            result = {"error": "Too many edits this turn. STOP calling tools and ask the user the open "
                                               "questions from the last check_project/check_spec in one message."}
                        else:
                            result = FUNCS[name](**targs) if name in FUNCS else {"error": f"unknown tool {name}"}
                    except Exception as e:
                        result = {"error": f"{type(e).__name__}: {e}"}
                    text = json.dumps(result, default=str)
                    if len(text) > 12000:
                        text = text[:12000] + "...[truncated]"
                    if log:
                        log.write(json.dumps({"tool": name, "args": tc.function.arguments, "result": text[:3000]}) + "\n")
                    msgs.append({"role": "tool", "tool_call_id": tc.id, "content": text})
            else:
                show("\nagent> (stopped: step limit reached)\n")
        except Exception as e:  # server down, timeout, context overflow...
            del msgs[turn_start:]  # drop the half-finished turn so the conversation stays valid
            kind = type(e).__name__
            hint = ("Is llama-server running? Start start_llm.bat and check http://127.0.0.1:8080/health"
                    if "Connection" in kind else "Try again, or type reset if the conversation got too long.")
            show(f"\nagent> (could not reach the model: {kind}: {str(e)[:200]}. {hint})\n")
            if script is not None:
                break
    if log:
        log.write(json.dumps({"final_spec": SPEC}) + "\n"); log.close()


if __name__ == "__main__":
    main()
