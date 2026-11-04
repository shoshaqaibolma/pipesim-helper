"""
PIPESIM study agent. Describe a study in plain language and it will:
  understand -> ask about missing parameters -> propose a plan -> (you approve) -> run -> analyze.
Usage:  python agent.py         (llama-server must be running, see start_llm.bat)
"""
import json, os, re, sys
from openai import OpenAI
import pipesim_tools as pt
import study, executor, netbuilder, recipes, numguard, structured
import project as prj
from builder import TEMPLATES

BASE_URL = os.getenv("LLM_URL", "http://127.0.0.1:8080/v1")
MODEL = os.getenv("LLM_MODEL", "local")
MAX_STEPS = 25
# A/B switches (both on by default): worked recipes + study-type table, and the invented-number check
KNOWLEDGE = os.getenv("PIPESIM_AGENT_KNOWLEDGE", "1") != "0"
NUMBER_GUARD = os.getenv("PIPESIM_NUMBER_GUARD", "1") != "0"
# narrow schema-constrained extraction calls + only the tools that fit the current stage of the workflow
# Experimental, OFF by default: in job 22 the 9B lost stated values under the grammar and the strict tool schema
# overflowed the 16k context (0/8 studies). Kept for larger models / future work: PIPESIM_AGENT_STRUCTURED=1.
STRUCTURED = os.getenv("PIPESIM_AGENT_STRUCTURED", "0") == "1"
NUMBER_RULE = ("\nNUMBERS: every number you write must be in a tool result or in the user's message. Do not estimate, "
               "add up or convert results yourself; if a number is not in the results, say it was not calculated. "
               "Replies are checked automatically.") if NUMBER_GUARD else ""

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
A. Put EVERYTHING the user gave into ONE update_project call, using exactly the field names below. After that,
   send only what changes (e.g. {{"flowlines":[{{"name":"FL-1","length":2000}}]}}), never the whole project again. Use only the
   components the user describes: do not add junctions, chokes or flowlines they did not mention. A single well
   or source can connect straight to its sink with one flowline.
B. Call check_project. If "missing" is not empty, ask the user about those items in ONE numbered message,
   grouped by component, with the suggested defaults. Never invent values that have no suggested default.
   If the user says "use defaults", call use_defaults(["all"]) and then check_project again.
C. When check_project is ready: for a study, call update_spec with model.source = "project" and continue with
   steps 2-5 above (the study builds its own model; do not call build_project for it). Call build_project(path)
   only when the user asks to keep a PIPESIM file.

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
  productivity index: Completion / <well>:<well>_Comp / LiquidPI;  water cut or GOR: BlackOilFluid / <fluid> / WaterCut | GOR
  choke size: Choke / <choke> / BeanSize;  flowline diameter: Flowline / <flowline> / InnerDiameter
  gas lift rate: GasLiftInjection / <well>:<well>_GL / GasRate  (the well needs "gas_lift" in the project)
  compressor or pump: Compressor|Pump / <name> / Power | PressureDifferential | Pressure  (whichever it was specified by)

{recipes.STUDY_TYPES if KNOWLEDGE else ""}
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
Keep messages short.{NUMBER_RULE}"""

SPEC = {}
PROJECT = {}
# Front-end hooks: the terminal asks with input(); the web window (webui.py) uses its Approve button.
HOOKS = {"confirm": lambda question: input(f"\n  {question} [y/N] ").strip().lower() == "y",
         "progress": lambda text: print("   " + text)}
STATE = {"plan_ok_for": None, "components": None, "recipes_given": set(), "turn": 0, "plan_turn": None,
         "ran_plan": None, "user_text": ""}
LEDGER = numguard.Ledger()   # numbers that really came from tools or the user in this conversation


def _plan_key():
    return json.dumps([SPEC, PROJECT if SPEC.get("model", {}).get("source") == "project" else None], sort_keys=True)


def update_spec(patch: dict):
    """Merge fields into the study spec. To replace a list (e.g. analysis.variables), send the whole list."""
    global SPEC
    SPEC, notes = study.clean(study.merge(SPEC, patch))
    STATE["plan_ok_for"] = None
    out = {"spec": SPEC, "next_step": "Call check_spec."}
    if notes:
        out["ignored"] = notes
    return out


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
    STATE["plan_turn"] = STATE["turn"]
    return {"plan": study.plan_text(SPEC, PROJECT),
            "next_step": "Show this plan to the user word for word and ask them to approve it. Do not call run_study "
                         "in this turn: wait for their answer."}


def run_study():
    """Execute the approved plan: runs every case and writes CSV, charts and report.md."""
    if STATE["plan_ok_for"] != _plan_key():
        return {"error": "The spec or project changed, or was never planned. Call propose_plan and get user "
                         "approval first."}
    if STATE["plan_turn"] == STATE["turn"]:
        return {"error": "The user has not seen the plan yet. Show it to them and wait for their approval; "
                         "call run_study only in a later turn, after they approve."}
    if not HOOKS["confirm"]("Run this study now?"):
        return {"error": "The user has not approved the run yet. Ask them to approve the plan (in the web window: "
                         "the Approve button), then call run_study again."}
    pt.close_model() if pt._state["model"] else None
    res = executor.run(SPEC, progress=HOOKS["progress"], project=PROJECT or None)
    STATE["ran_plan"] = _plan_key()
    return res


def update_project(patch: dict):
    """Add or change parts of the network being described. Lists (wells, flowlines, ...) merge by "name";
    {"name": "X", "_delete": true} removes X."""
    global PROJECT
    PROJECT, notes, errors = prj.apply_patch(PROJECT, patch)
    PROJECT, renamed = prj.replace_placeholders(PROJECT, recipes.PLACEHOLDERS, STATE["user_text"])
    STATE["plan_ok_for"] = None
    out = {"project": prj.summary(PROJECT), "next_step": "Call check_project."}
    if renamed:   # names copied from a recipe example, not given by the user
        out["renamed"] = [f"{a} -> {b} (example name, not the user's; use {b})" for a, b in renamed]
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
    if not HOOKS["confirm"](f"Build this PIPESIM model as {path}?"):
        return {"error": "The user has not approved building the file yet. Ask them to approve (in the web window: "
                         "the Approve button), then call build_project again."}
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
                               "analysis{type,variables[],producer,conditions,outlet_pressure,max_total}. "
                               "A key set to null is removed."}},
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
if STRUCTURED:   # exact field names in the tool schema: llama-server can constrain the call to them
    PARAMS["update_project"] = ({"patch": dict(structured.project_schema(for_tool=True),
                                               description=PARAMS["update_project"][0]["patch"]["description"])},
                                ["patch"])
TOOLS = [{"type": "function", "function": {"name": n, "description": FUNCS[n].__doc__,
          "parameters": {"type": "object", "properties": p, "required": r}}} for n, (p, r) in PARAMS.items()]


def offered_tools():
    """Only the tools that make sense now: no run_study before the user has seen and answered a plan, no
    propose_plan before the spec is ready, no build_project/use_defaults when they cannot do anything."""
    if not STRUCTURED:
        return TOOLS
    key, names = _plan_key(), set(FUNCS)
    if not (STATE["plan_ok_for"] == key and STATE["plan_turn"] != STATE["turn"] and STATE["ran_plan"] != key):
        names.discard("run_study")
    try:
        spec_ready = bool(SPEC) and check_spec()["ready"]
    except Exception:
        spec_ready = False
    if not spec_ready or (STATE["plan_ok_for"] == key and STATE["ran_plan"] != key):
        names.discard("propose_plan")
    pc = prj.check_project(PROJECT) if PROJECT else None
    if not pc or not pc["ready"]:
        names.discard("build_project")
    if not pc or not pc["missing"]:
        names.discard("use_defaults")
    return [t for t in TOOLS if t["function"]["name"] in names]


MAX_SPEC_CALLS = 10    # spec/project edit+check calls allowed per user turn before the agent must ask the user
MAX_REPLY_TOKENS = 1500


MAX_HISTORY_CHARS = 40000   # about 10k tokens: keeps long sessions inside the 16k context of the local model


def compact(msgs, limit=MAX_HISTORY_CHARS):
    """Shorten old tool results when the conversation gets long: first those before the latest user message, then,
    if a single turn has grown too long (many tool calls), older results inside that turn too (the last 4 stay)."""
    size = lambda ms: sum(len(str(m.get("content") or "")) + len(json.dumps(m.get("tool_calls") or "")) for m in ms)
    if size(msgs) <= limit:
        return msgs
    last_user = max(i for i, m in enumerate(msgs) if m.get("role") == "user")
    out = []
    for i, m in enumerate(msgs):
        if i < last_user and m.get("role") == "tool" and len(str(m.get("content") or "")) > 300:
            m = dict(m, content=str(m["content"])[:300] + " ...[older result shortened]")
        out.append(m)
    if size(out) > limit:
        for i in range(last_user + 1, len(out) - 4):
            m = out[i]
            if m.get("role") == "tool" and len(str(m.get("content") or "")) > 300:
                out[i] = dict(m, content=str(m["content"])[:300] + " ...[older result shortened]")
    return out


def chat(client, msgs):
    msgs[:] = compact(msgs)
    return client.chat.completions.create(
        model=MODEL, messages=msgs, tools=offered_tools(), temperature=0.0, max_tokens=MAX_REPLY_TOKENS,
        # Qwen 3.5 thinks by default; on a 16k context that can eat the whole window and return an empty reply.
        extra_body={"chat_template_kwargs": {"enable_thinking": False}}).choices[0].message


def new_conversation():
    global SPEC, PROJECT, LEDGER
    SPEC, PROJECT = {}, {}
    STATE.update(plan_ok_for=None, components=None, recipes_given=set(), turn=0, plan_turn=None, ran_plan=None,
                 user_text="")
    LEDGER = numguard.Ledger()
    return [{"role": "system", "content": SYSTEM}]


APPROVAL = re.compile(r"^\W*(yes|yeah|yep|y|ok|okay|sure|approved?|go( ahead)?|run( it)?|proceed|confirm(ed)?|do it|"
                      r"looks good|lgtm)\b", re.I)


CHANGE = re.compile(r"\d|\b(but|change|instead|except|also|modify|add|remove|not|no|wait|first)\b", re.I)


def approval_note(user):
    """Short approvals are answered by state, not guessed by the model: run the waiting plan, or say that the
    last plan already ran instead of inventing a new study."""
    if len(user) > 80 or not APPROVAL.match(user) or CHANGE.search(user):
        return None
    key = _plan_key()
    if STATE["plan_ok_for"] == key and STATE["ran_plan"] != key:
        return "The user approved the plan above. Call run_study now."
    if STATE["ran_plan"] is not None and STATE["ran_plan"] == key:
        return ("This is an approval, but no plan is waiting: the approved study already ran and its results were "
                "shown. Do NOT propose, plan or run another study. Reply in one or two sentences: say the study is "
                "done, give the report path, and ask what they want to do next.")
    if STATE["plan_ok_for"] is None:
        return ("No plan has been proposed yet, so there is nothing to approve. Continue the workflow: resolve "
                "check_project / check_spec, then propose_plan and show it.")
    return None


def check_numbers(client, msgs, text, emit):
    """Numbers in the final reply must come from tool results or the user. Ask for one rewrite without the
    unverified numbers; if some remain, flag them under the reply. msgs[-1] is the reply being checked."""
    bad = LEDGER.unverified(text)
    if not bad:
        return text
    emit({"type": "tool", "name": "(number check)", "args": {"unverified": bad}})
    reply = msgs.pop()
    try:
        fix = chat(client, msgs + [reply, {"role": "user", "content": numguard.rewrite_note(bad)}])
        new = fix.content if fix and not fix.tool_calls else None
    except Exception:
        new = None
    still = LEDGER.unverified(new) if new else bad
    final = (new or text) if not still else (new or text) + numguard.flag_line(still)
    msgs.append({"role": "assistant", "content": final})
    emit({"type": "result", "name": "(number check)",
          "result": {"unverified": bad, "rewritten": bool(new), "still_unverified": still}})
    return final


def _inject(msgs, emit, name, args):
    """Run a tool on the model's behalf and record it in the conversation as if the model had called it."""
    STATE["inject_n"] = STATE.get("inject_n", 0) + 1
    cid = f"pre{STATE['inject_n']}"
    emit({"type": "tool", "name": name, "args": args})
    try:
        result = FUNCS[name](**args)
    except Exception as e:
        result = {"error": f"{type(e).__name__}: {e}"}
    emit({"type": "result", "name": name, "result": result})
    LEDGER.add_result(name, result)
    msgs.append({"role": "assistant", "content": None, "tool_calls": [
        {"id": cid, "type": "function", "function": {"name": name, "arguments": json.dumps(args)}}]})
    msgs.append({"role": "tool", "tool_call_id": cid, "content": json.dumps(result, default=str)[:12000]})
    return result


def pre_steps(client, msgs, user, emit):
    """Narrow, schema-constrained extraction of the network and of the study before the free agent loop."""
    if APPROVAL.match(user) and len(user) < 80:
        return
    try:
        if structured.wants_project(user, PROJECT):
            patch, dropped = structured.extract_project(client, MODEL, user)
            if dropped:
                emit({"type": "tool", "name": "(extraction)", "args": {}})
                emit({"type": "result", "name": "(extraction)", "result": {"dropped_unstated": dropped}})
            if patch:
                _inject(msgs, emit, "update_project", {"patch": patch})
                _inject(msgs, emit, "check_project", {})
        new_study = not SPEC.get("analysis") or STATE["ran_plan"] == _plan_key()
        if new_study and structured.wants_study(user, PROJECT):
            a, dropped = structured.extract_study(client, MODEL, user, PROJECT)
            if a and a.get("type") in study.ANALYSES and a["type"] != "single_run":
                update_spec({"analysis": None})
                _inject(msgs, emit, "update_spec", {"patch": {"model": {"source": "project"}, "analysis": a}})
                _inject(msgs, emit, "check_spec", {})
    except Exception as e:   # extraction is an aid: on any failure the normal loop does the work
        reason = {"reason": f"{type(e).__name__}: {str(e)[:200]}"}
        emit({"type": "tool", "name": "(extraction skipped)", "args": reason})
        emit({"type": "result", "name": "(extraction skipped)", "result": reason})


def run_turn(client, msgs, user, emit):
    """One user turn: let the model call tools until it answers. emit(event) receives
    {"type": "tool", "name", "args"}, {"type": "result", "name", "result"}, {"type": "assistant", "text"},
    {"type": "error", "text"}. msgs is updated in place."""
    turn_start = len(msgs)
    STATE["turn"] += 1
    LEDGER.add_user(user)
    STATE["user_text"] += "\n" + user
    content = user
    note = approval_note(user)
    if note:
        content += "\n\n[Guidance for the assistant - state] " + note
    if KNOWLEDGE:   # recipes matching this message, each one only once per conversation
        hits = [r for r in recipes.select(user) if r["name"] not in STATE["recipes_given"]]
        if hits:
            STATE["recipes_given"].update(r["name"] for r in hits)
            content += recipes.GUIDANCE + "\n\n".join(r["text"] for r in hits)
    msgs.append({"role": "user", "content": content})
    if STRUCTURED:
        pre_steps(client, msgs, user, emit)
    spec_calls, bad_json, ran = 0, 0, False
    try:
        for _ in range(MAX_STEPS):
            try:
                msg = chat(client, msgs)
            except Exception as e:   # llama-server rejects a tool call whose arguments are not valid JSON
                if "parse tool call" not in str(e) or bad_json >= 2:
                    raise
                bad_json += 1
                emit({"type": "tool", "name": "(retry)", "args": {"reason": "invalid tool-call JSON"}})
                msgs.append({"role": "user", "content": "(system note) Your last tool call was not valid JSON. "
                             "Retry with a smaller call: send only the items that change."})
                continue
            msgs.append(msg.model_dump(exclude_none=True))
            if not msg.tool_calls:
                text = msg.content or "(empty reply: try rephrasing, or start a new chat)"
                # only replies that explain simulation results are checked: while planning, the model rightly
                # proposes values of its own (sweep steps 16, 24, 28 between the user's 12 and 32, job 22)
                if NUMBER_GUARD and ran:
                    text = check_numbers(client, msgs, text, emit)
                elif ran and LEDGER.unverified(text):   # guard off: only record it (for the before/after evaluation)
                    emit({"type": "tool", "name": "(number audit)", "args": {}})
                    emit({"type": "result", "name": "(number audit)", "result": {"unverified": LEDGER.unverified(text)}})
                emit({"type": "assistant", "text": text})
                return
            for tc in msg.tool_calls:
                name = tc.function.name
                try:
                    targs = json.loads(tc.function.arguments or "{}")
                    emit({"type": "tool", "name": name, "args": targs})
                    if name in ("update_spec", "check_spec", "update_project", "check_project", "use_defaults"):
                        spec_calls += 1
                    if spec_calls > MAX_SPEC_CALLS:
                        result = {"error": "Too many edits this turn. STOP calling tools and ask the user the open "
                                           "questions from the last check_project/check_spec in one message."}
                    else:
                        result = FUNCS[name](**targs) if name in FUNCS else {"error": f"unknown tool {name}"}
                except Exception as e:
                    result = {"error": f"{type(e).__name__}: {e}"}
                emit({"type": "result", "name": name, "result": result})
                LEDGER.add_result(name, result)
                if name == "run_study" and isinstance(result, dict) and "error" not in result:
                    ran = True
                text = json.dumps(result, default=str)
                if len(text) > 12000:
                    text = text[:12000] + "...[truncated]"
                msgs.append({"role": "tool", "tool_call_id": tc.id, "content": text})
        emit({"type": "assistant", "text": "(stopped: step limit reached)"})
    except Exception as e:  # server down, timeout, context overflow...
        del msgs[turn_start:]  # drop the half-finished turn so the conversation stays valid
        kind = type(e).__name__
        hint = ("Is llama-server running? Start start_llm.bat and check http://127.0.0.1:8080/health"
                if "Connection" in kind else "Try again, or start a new chat if the conversation got too long.")
        emit({"type": "error", "text": f"could not reach the model: {kind}: {str(e)[:200]}. {hint}"})


def main():
    import argparse
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    ap = argparse.ArgumentParser()
    ap.add_argument("--script", help="text file with one user message per line (for unattended tests); "
                                     "approvals are answered 'y' automatically")
    ap.add_argument("--log", help="write the full conversation as JSONL to this file")
    args = ap.parse_args()
    script = [l.rstrip("\n") for l in open(args.script, encoding="utf-8") if l.strip()] if args.script else None
    log = open(args.log, "a", encoding="utf-8") if args.log else None

    def ask(prompt):
        if script is None:
            return input(prompt)
        if not script:
            raise EOFError
        line = script.pop(0)
        print(prompt + line)
        return line
    if script is not None:
        HOOKS["confirm"] = lambda q: (print(f"  {q} [y/N] y (auto, --script)"), True)[1]

    def show(text):
        try:
            print(text)
        except UnicodeEncodeError:
            print(text.encode("ascii", "replace").decode())
        if log:
            log.write(json.dumps({"agent": text}) + "\n"); log.flush()

    last_args = {}

    def emit(ev):
        if ev["type"] == "tool":
            last_args["v"] = json.dumps(ev["args"])
            print(f"  [{ev['name']}] {last_args['v'][:160]}")
        elif ev["type"] == "result":
            if log:
                log.write(json.dumps({"tool": ev["name"], "args": last_args.get("v", ""),
                                      "result": json.dumps(ev["result"], default=str)[:3000]}) + "\n")
        elif ev["type"] == "assistant":
            show(f"\nagent> {ev['text']}\n")
        else:
            show(f"\nagent> ({ev['text']})\n")

    client = OpenAI(base_url=BASE_URL, api_key="sk-local", timeout=600, max_retries=1)
    msgs = new_conversation()
    show("PIPESIM study agent. Describe what you want to simulate. Commands: 'spec', 'reset', 'exit'.\n")
    while True:
        try:
            user = ask("you> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if log:
            log.write(json.dumps({"user": user}) + "\n")
        if user.lower() in {"exit", "quit"}:
            break
        if user.lower() == "spec":
            show(json.dumps(SPEC, indent=2) + ("\n" + prj.summary(PROJECT) if PROJECT else "")); continue
        if user.lower() == "reset":
            msgs = new_conversation(); show("(new study)\n"); continue
        if not user:
            continue
        errors = []
        run_turn(client, msgs, user, lambda ev: (errors.append(ev) if ev["type"] == "error" else None, emit(ev)))
        if errors and script is not None:
            break
    if log:
        log.write(json.dumps({"final_spec": SPEC}) + "\n"); log.close()


if __name__ == "__main__":
    main()
