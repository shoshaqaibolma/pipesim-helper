"""
PIPESIM study agent. Describe a study in plain language and it will:
  understand -> ask about missing parameters -> propose a plan -> (you approve) -> run -> analyze.
Usage:  python agent.py         (llama-server must be running, see start_llm.bat)
"""
import json, os
from openai import OpenAI
import pipesim_tools as pt
import study, executor
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
5. ANALYZE: explain the results from the returned table: trends, optimum, sensitivities, constraints,
   and anything that looks physically odd. Give the report path. Suggest a sensible follow-up study.

Analysis types: {json.dumps(study.ANALYSES)}
Model templates for new models: { {k: v['description'] for k, v in TEMPLATES.items()} }
Template sweep aliases: { {k: list(v['aliases']) for k, v in TEMPLATES.items()} }
P/T profiles need ONE boundary condition in analysis.conditions: {{"outlet_pressure": x}} OR {{"liquid_flowrate": x}} OR {{"gas_flowrate": x}}.
For existing models, refer to variables as component_type + name + parameter (e.g. Sink / "Sink-1" / "Pressure").
Use model units (METRIC unless the user says FIELD). Never invent results: every number comes from a tool.
Keep messages short."""

SPEC = {}
STATE = {"plan_ok_for": None, "components": None}


def update_spec(patch: dict):
    """Merge fields into the study spec. To replace a list (e.g. analysis.variables), send the whole list."""
    global SPEC
    SPEC = study.merge(SPEC, patch)
    STATE["plan_ok_for"] = None
    return {"spec": SPEC}


def check_spec():
    """Validate the spec. Returns missing items (ask the user about these), errors, and the number of cases."""
    return study.check(SPEC, STATE["components"])


def propose_plan():
    """Render the plan for the user to approve. Only works when check_spec says ready."""
    c = check_spec()
    if not c["ready"]:
        return {"error": "Spec not ready", **c}
    STATE["plan_ok_for"] = json.dumps(SPEC, sort_keys=True)
    return {"plan": study.plan_text(SPEC)}


def run_study():
    """Execute the approved plan: runs every case and writes CSV, charts and report.md."""
    if STATE["plan_ok_for"] != json.dumps(SPEC, sort_keys=True):
        return {"error": "The spec changed or was never planned. Call propose_plan and get user approval first."}
    print("\n" + study.plan_text(SPEC))
    if input("\n  Run this study now? [y/N] ").strip().lower() != "y":
        return {"error": "User did not approve the run in the terminal."}
    pt.close_model() if pt._state["model"] else None
    return executor.run(SPEC, progress=lambda s: print("   " + s))


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


FUNCS = {f.__name__: f for f in (update_spec, check_spec, propose_plan, run_study, inspect_model, get_values)}
_S = {"type": "string"}
PARAMS = {
    "update_spec": ({"patch": {"type": "object", "description": "Partial spec to merge. Keys: objective, units, "
                               "model{source,path|template,params}, base_changes[], analysis{type,variables[],producer,conditions}, kpis[]"}},
                    ["patch"]),
    "check_spec": ({}, []), "propose_plan": ({}, []), "run_study": ({}, []),
    "inspect_model": ({"path": _S, "units": {"type": "string", "enum": ["METRIC", "FIELD", "SI"]}}, ["path"]),
    "get_values": ({"component_type": _S, "name": _S, "parameters": {"type": "array", "items": _S}},
                   ["component_type", "parameters"]),
}
TOOLS = [{"type": "function", "function": {"name": n, "description": FUNCS[n].__doc__,
          "parameters": {"type": "object", "properties": p, "required": r}}} for n, (p, r) in PARAMS.items()]


def main():
    client = OpenAI(base_url=BASE_URL, api_key="sk-local")
    msgs = [{"role": "system", "content": SYSTEM}]
    print("PIPESIM study agent. Describe what you want to simulate. Commands: 'spec', 'reset', 'exit'.\n")
    global SPEC
    while True:
        try:
            user = input("you> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if user.lower() in {"exit", "quit"}:
            break
        if user.lower() == "spec":
            print(json.dumps(SPEC, indent=2)); continue
        if user.lower() == "reset":
            SPEC = {}; STATE.update(plan_ok_for=None, components=None)
            msgs = msgs[:1]; print("(new study)\n"); continue
        if not user:
            continue
        msgs.append({"role": "user", "content": user})
        for _ in range(MAX_STEPS):
            msg = client.chat.completions.create(model=MODEL, messages=msgs, tools=TOOLS,
                                                 temperature=0.0).choices[0].message
            msgs.append(msg.model_dump(exclude_none=True))
            if not msg.tool_calls:
                print(f"\nagent> {msg.content}\n"); break
            for tc in msg.tool_calls:
                name = tc.function.name
                try:
                    args = json.loads(tc.function.arguments or "{}")
                    print(f"  [{name}]")
                    result = FUNCS[name](**args) if name in FUNCS else {"error": f"unknown tool {name}"}
                except Exception as e:
                    result = {"error": f"{type(e).__name__}: {e}"}
                text = json.dumps(result, default=str)
                if len(text) > 12000:
                    text = text[:12000] + "...[truncated]"
                msgs.append({"role": "tool", "tool_call_id": tc.id, "content": text})
        else:
            print("\nagent> (stopped: step limit reached)\n")


if __name__ == "__main__":
    main()
