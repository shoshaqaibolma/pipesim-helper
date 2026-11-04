"""
Narrow, schema-constrained steps for a small model.

Instead of one free agent loop that has to describe the network, pick the study type, name the variables and run
the workflow at once, two single-purpose calls run first, each forced into a JSON schema by llama-server
(response_format json_schema -> grammar-constrained decoding, so the JSON is always valid and only allowed field
names / component names can appear):

  extract_project(text)  -> the network the user described (only the values they stated)
  extract_study(text, p) -> the study: type and variables chosen from the components that really exist

Numbers in the extracted JSON that the user never wrote are dropped (the checker then asks for them), so an
extraction cannot invent inputs. The agent injects the results as ordinary tool calls; the main loop then only has
to ask for missing inputs, show the plan, run and explain.
"""
import json, re
import project as prj
import study
import numguard
import recipes

NUM = {"type": "number"}
STR = {"type": "string"}


# ---------- schemas
def _item_schema(kind, for_tool=False):
    props = {}
    for k in sorted(prj.allowed_keys(kind) - {"_delete"}, key=lambda k: (k != "name", k)):
        if k in ("name", "fluid", "from", "to"):
            props[k] = STR
        elif k == "type":
            props[k] = {"type": "string", "enum": list(prj.FLUID_FIELDS)}
        elif k == "port":
            props[k] = {"type": "string", "enum": list(prj.PORTS)}
        elif k == "ipr":
            props[k] = {"type": "object", "additionalProperties": False,
                        "properties": {"model": {"type": "string", "enum": list(prj.IPR_FIELDS)},
                                       "liquid_pi": NUM, "aof": NUM, "c": NUM, "n": NUM}, "required": ["model"]}
        elif k == "gas_lift":
            props[k] = {"type": "object", "additionalProperties": False,
                        "properties": {"depth": NUM, "rate": NUM}}
        else:
            props[k] = NUM
    if for_tool:
        props["_delete"] = {"type": "boolean"}
    return {"type": "object", "additionalProperties": False, "properties": props, "required": ["name"]}


def project_schema(for_tool=False):
    props = {"name": STR}
    for kind in prj.FIELDS:
        props[kind] = {"type": "array", "items": _item_schema(kind, for_tool)}
    return {"type": "object", "additionalProperties": False, "properties": props}


def study_variables(p):
    """'Type|Name|Parameter' strings for every study variable the described project offers."""
    out = []
    for s in p.get("sinks") or []:
        out.append(f"Sink|{s['name']}|Pressure")
    for w in p.get("wells") or []:
        c = f"{w['name']}:{prj.completion_name(w['name'])}"
        out += [f"Completion|{c}|ReservoirPressure", f"Completion|{c}|LiquidPI"]
        if w.get("gas_lift"):
            out.append(f"GasLiftInjection|{w['name']}:{prj.gas_lift_name(w['name'])}|GasRate")
    for f in p.get("fluids") or []:
        if f.get("type", "black_oil") == "black_oil":
            out += [f"BlackOilFluid|{f['name']}|WaterCut", f"BlackOilFluid|{f['name']}|GOR"]
    for c in p.get("chokes") or []:
        out.append(f"Choke|{c['name']}|BeanSize")
    for fl in p.get("flowlines") or []:
        out += [f"Flowline|{fl['name']}|InnerDiameter", f"Flowline|{fl['name']}|Length"]
    for kind, ctype in (("compressors", "Compressor"), ("pumps", "Pump")):
        for e in p.get(kind) or []:
            par = {"power": "Power", "pressure_rise": "PressureDifferential", "pressure": "Pressure",
                   "pressure_ratio": "PressureRatio"}
            for k, v in par.items():
                if k in e:
                    out.append(f"{ctype}|{e['name']}|{v}")
    return [o for o in out if "|None|" not in o]


def study_schema(p):
    var = {"type": "object", "additionalProperties": False,
           "properties": {"variable": {"type": "string", "enum": study_variables(p) or ["none"]},
                          "values": {"type": "array", "items": NUM}, "start": NUM, "stop": NUM, "steps": NUM,
                          "low": NUM, "high": NUM},
           "required": ["variable"]}
    producers = [w["name"] for w in p.get("wells") or []] + [s["name"] for s in p.get("sources") or []]
    return {"type": "object", "additionalProperties": False,
            "properties": {"type": {"type": "string", "enum": list(study.ANALYSES)},
                           "variables": {"type": "array", "items": var},
                           "producer": {"type": "string", "enum": producers or ["none"]},
                           "outlet_pressure": NUM, "max_total": NUM,
                           "conditions": {"type": "object", "additionalProperties": False,
                                          "properties": {"outlet_pressure": NUM, "liquid_flowrate": NUM,
                                                         "gas_flowrate": NUM}}},
            "required": ["type"]}


# ---------- prompts
PROJECT_PROMPT = """Convert the engineer's description of a production network into JSON for PIPESIM.
Rules:
- Include ONLY values the user stated. Leave out anything not stated (a checker asks the user for it).
- Units: pressure bara, temperature degC, length/depth/elevation m (km x 1000), diameters mm, PI sm3/d/bar,
  GOR sm3/sm3, water cut in % (30 means 30 %), gas rates mmsm3/d (MMsm3/d is the same), OGR/WGR sm3/mmsm3.
- Use the user's names. If they give none: wells W1, W2...; fluid BO (black oil) or Gas; manifold M; sink SEP;
  flowlines FL-<from>. A separator the production ends in is a SINK (with its pressure), not a separators item.
- Wells (with reservoir and IPR) are wells, never sources. A source is a pipeline inlet / plant with a fixed rate
  or pressure. "Flat" means elevation_change 0. Gas lift: "gas_lift": {"depth", "rate"} on the well.
- A sink accepts ONE inlet: with several wells, each well line ends at the manifold and one line goes on to the sink.
- A choke right after the wellhead: {"name", "from": <well>, "bean_size"} and the flowline starts at the choke.
- ipr with a productivity index: {"model": "pi", "liquid_pi": x}.
Example: "2 wells W1 (250 bara, 2500 m, PI 10) and W2 into manifold J1, 5 km 152 mm line to a separator at 15 bara,
black oil 35 API" ->
{"fluids":[{"name":"BO","type":"black_oil","api":35}],
 "wells":[{"name":"W1","fluid":"BO","reservoir_pressure":250,"depth":2500,"ipr":{"model":"pi","liquid_pi":10}},
          {"name":"W2","fluid":"BO"}],
 "junctions":[{"name":"J1"}],"sinks":[{"name":"SEP","pressure":15}],
 "flowlines":[{"name":"FL-W1","from":"W1","to":"J1"},{"name":"FL-W2","from":"W2","to":"J1"},
              {"name":"Trunk","from":"J1","to":"SEP","length":5000,"id":152}]}"""

STUDY_PROMPT = """Turn the engineer's question into ONE PIPESIM study, as JSON.
""" + recipes.STUDY_TYPES + """
Rules:
- "variable" must be one of the listed options; pick the one the question is about.
- sweep: exactly ONE variable with "values" (or start/stop/steps); grid: 2-3 variables with "values";
  tornado: each variable with "low" and "high"; optimize: one variable per well with "values", plus "max_total"
  when the user gives a limit on their sum; nodal: "producer" and "outlet_pressure" (the wellhead pressure the
  user gives); pt_profile: "producer" and ONE condition.
- Use only numbers the user wrote. "from A to B in N steps" -> start A, stop B, steps N.
- If the message asks for several studies one after the other, describe only the FIRST one."""


# ---------- guards
def _user_numbers(text):
    vals = {abs(v) for _, v, _ in numguard.numbers_in_text(text)}
    return vals | {v * f for v in vals for f in (1000.0, 0.001)}


def _stated(v, said):
    return v == 0 or any(abs(v - s) <= max(1e-9, abs(s) * 0.005) for s in said)


def drop_unstated(obj, said, path="", dropped=None):
    """Remove numbers the user never wrote (an extraction must not invent inputs). Returns (obj, dropped)."""
    dropped = [] if dropped is None else dropped
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                if _stated(abs(v), said):
                    out[k] = v
                else:
                    dropped.append(f"{path}{k}={v}")
            else:
                out[k] = drop_unstated(v, said, f"{path}{k}.", dropped)[0]
        return out, dropped
    if isinstance(obj, list):
        nums = [v for v in obj if isinstance(v, (int, float)) and not isinstance(v, bool)]
        if nums and len(nums) == len(obj):   # a list of values: its range must be stated (steps between may not be)
            if _stated(abs(min(nums)), said) and _stated(abs(max(nums)), said):
                return obj, dropped
            dropped.append(f"{path.rstrip('.')}={obj}")
            return [], dropped
        return [drop_unstated(v, said, path, dropped)[0] for v in obj], dropped
    return obj, dropped


def _clean_lists(p):
    """Drop empty lists and items that lost everything but their name where that makes them useless (ipr)."""
    for kind in list(p):
        if isinstance(p[kind], list) and not p[kind]:
            del p[kind]
    for w in p.get("wells") or []:
        ipr = w.get("ipr")
        if isinstance(ipr, dict) and set(ipr) <= {"model"}:
            del w["ipr"]
    return p


# ---------- calls (the client is an OpenAI-compatible llama-server)
def complete_json(client, model, system, user, schema, max_tokens=1500):
    r = client.chat.completions.create(
        model=model, temperature=0.0, max_tokens=max_tokens,
        messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
        response_format={"type": "json_schema", "json_schema": {"name": "out", "schema": schema}},
        extra_body={"chat_template_kwargs": {"enable_thinking": False}})
    return json.loads(r.choices[0].message.content)


def extract_project(client, model, text):
    p = complete_json(client, model, PROJECT_PROMPT, text, project_schema())
    p, dropped = drop_unstated(p, _user_numbers(text))
    return _clean_lists(p), dropped


def extract_study(client, model, text, project):
    options = study_variables(project)
    if not options:
        return None, []
    system = STUDY_PROMPT + "\nVariable options:\n" + "\n".join(f"- {o}" for o in options)
    a = complete_json(client, model, system, text, study_schema(project), max_tokens=800)
    a, dropped = drop_unstated(a, _user_numbers(text))
    variables = []
    for v in a.get("variables") or []:
        ctype, name, par = (v.get("variable") or "||").split("|")[:3] if "|" in str(v.get("variable")) else ("", "", "")
        if not ctype:
            continue
        nv = {"component_type": ctype, "name": name, "parameter": par}
        nv.update({k: v[k] for k in ("values", "start", "stop", "steps", "low", "high") if k in v})
        variables.append(nv)
    out = {"type": a.get("type")}
    if variables:
        out["variables"] = variables
    for k in ("producer", "outlet_pressure", "max_total", "conditions"):
        if a.get(k) not in (None, "none", {}):
            out[k] = a[k]
    if out["type"] not in ("nodal", "pt_profile"):
        out.pop("producer", None)
    return out, dropped


# ---------- when to use them
NETWORK = re.compile(r"\b(wells?|pipeline|source|separator|manifold|flowline|trunk ?line|field)\b", re.I)
QUESTION = re.compile(r"\?|\b(sweep|sensitiv|how does|how do|change|which|rank|compare|optimi[sz]e|split|nodal|"
                      r"profile|vary|best|smallest|largest|tornado|uncertain|effect|impact|run)\b", re.I)


def wants_project(text, project):
    return (not project and len(text) > 120 and ".pips" not in text.lower() and bool(NETWORK.search(text))
            and len(numguard.numbers_in_text(text)) >= 3)


def wants_study(text, project):
    return bool(project) and len(text) > 25 and ".pips" not in text.lower() and bool(QUESTION.search(text))
