"""
Study spec: the structured form of the user's request. The LLM fills it in; this module decides
what is still missing (so the agent must ask) and renders the plan the user approves.

Spec shape (all keys optional until check() says ready):
{
  "objective": "Find how water cut affects oil rate",
  "units": "METRIC",                       # METRIC | FIELD | SI
  "model": {"source": "existing", "path": "C:/m.pips"}
         | {"source": "new", "template": "single_well", "params": {...}},
  "base_changes": [{"component_type": "Sink", "name": "Sink", "parameter": "Pressure", "value": 12}],
  "analysis": {
     "type": "single_run" | "sweep" | "grid" | "tornado" | "pt_profile",
     "variables": [ {"alias": "water_cut", "values": [0, 20, 40, 60]}
                  | {"component_type": "Well", "name": "W1", "parameter": "...", "start": 0, "stop": 50, "steps": 6}
                  | (tornado) {..., "low": 10, "high": 40} ],
     "producer": "Well",                   # pt_profile only
     "conditions": {"outlet_pressure": 15} # pt_profile only: EITHER outlet_pressure (rate is calculated)
                                           # OR liquid_flowrate / gas_flowrate (outlet pressure is calculated)
  },
  "kpis": [{"component": "Well", "variable": "VOLUME_FLOWRATE_OIL_STOCKTANK", "label": "Oil rate"}]
}
"""
import copy, os
from builder import TEMPLATES, alias_ref

ANALYSES = {
    "single_run": "one network simulation at base conditions",
    "sweep": "vary ONE variable over a range, everything else at base",
    "grid": "full-factorial combination of 2-3 variables",
    "tornado": "vary each variable to its low and high value one at a time, then rank the impacts",
    "pt_profile": "pressure/temperature/holdup profile along one well or flowline",
}
MAX_CASES = 300
SPEC_KEYS = {"objective", "units", "model", "base_changes", "analysis", "kpis"}
MODEL_KEYS = {"source", "path", "template", "params"}
ANALYSIS_KEYS = {"type", "variables", "producer", "conditions"}
# P/T profile boundary conditions: friendly key -> sixgill Parameters.PTProfileSimulation constant
PT_CONDITIONS = {"outlet_pressure": "OUTLETPRESSURE", "liquid_flowrate": "LIQUIDFLOWRATE",
                 "gas_flowrate": "GASFLOWRATE"}
DEFAULT_KPI_VARS = ["VOLUME_FLOWRATE_LIQUID_STOCKTANK", "VOLUME_FLOWRATE_OIL_STOCKTANK",
                    "VOLUME_FLOWRATE_GAS_STOCKTANK", "PRESSURE"]


def merge(base, patch):
    out = copy.deepcopy(base)
    for k, v in (patch or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = merge(out[k], v)
        else:
            out[k] = copy.deepcopy(v)
    return out


def values_of(var):
    if "values" in var:
        return list(var["values"])
    if all(k in var for k in ("start", "stop", "steps")):
        n = int(var["steps"])
        if n < 2:
            return [var["start"]]
        return [round(var["start"] + i * (var["stop"] - var["start"]) / (n - 1), 6) for i in range(n)]
    if "low" in var and "high" in var:
        return [var["low"], var["high"]]
    return None


def resolve_var(var, spec):
    """Return (component_type, name, parameter) for a variable, resolving template aliases."""
    if "alias" in var:
        tname = spec.get("model", {}).get("template", "")
        tpl = TEMPLATES.get(tname, {})
        if var["alias"] not in tpl.get("aliases", {}):
            raise KeyError(f"Unknown alias '{var['alias']}'. Known: {sorted(tpl.get('aliases', {}))}")
        return alias_ref(tname, var["alias"])
    return var["component_type"], var["name"], var["parameter"]


def n_cases(spec):
    a = spec.get("analysis", {})
    vs = [values_of(v) or [] for v in a.get("variables", [])]
    t = a.get("type")
    if t == "sweep":
        return 1 + len(vs[0]) if vs else 1
    if t == "grid":
        n = 1
        for v in vs:
            n *= max(1, len(v))
        return n + 1
    if t == "tornado":
        return 1 + 2 * len(vs)
    return 1


def check(spec, known_components=None):
    """Return what is missing or wrong. known_components: {type: [names]} from the open model, if any."""
    missing, errors = [], []

    def ask(field, question, unit="", default=None):
        missing.append({"field": field, "question": question, "unit": unit, "suggested_default": default})

    for k in spec:
        if k not in SPEC_KEYS:
            errors.append(f"Remove top-level key '{k}'. Allowed keys: {sorted(SPEC_KEYS)}. "
                          "Results come from run_study and are never written into the spec.")
    for part, allowed in (("model", MODEL_KEYS), ("analysis", ANALYSIS_KEYS)):
        for k in (spec.get(part) or {}):
            if k not in allowed:
                errors.append(f"Remove '{part}.{k}'. Allowed keys in {part}: {sorted(allowed)}.")
    if not spec.get("objective"):
        ask("objective", "What question should this study answer?")
    model = spec.get("model", {})
    src = model.get("source")
    if src is not None and src not in ("existing", "new"):
        errors.append(f"model.source is '{src}' but must be exactly \"existing\" or \"new\". "
                      + ("The file path belongs in model.path, e.g. {\"model\": {\"source\": \"existing\", "
                         "\"path\": \"...\"}}." if (".pips" in str(src).lower() or "\\" in str(src) or "/" in str(src)) else ""))
    elif src is None:
        ask("model.source", "Use an existing .pips model (then give its path), or build a new one from a description? "
            "[spec: model.source = \"existing\" + model.path, or model.source = \"new\" + model.template]")
    elif src == "existing":
        if not model.get("path"):
            ask("model.path", "Full path to the .pips model?")
        elif not os.path.exists(model["path"]):
            errors.append(f"Model file not found: {model['path']}")
    else:
        tname = model.get("template")
        if tname not in TEMPLATES:
            ask("model.template", f"Which template? Options: { {k: v['description'] for k, v in TEMPLATES.items()} }")
        else:
            given = model.get("params", {})
            for f, (q, unit, dflt) in TEMPLATES[tname]["fields"].items():
                if f not in given:
                    ask(f"model.params.{f}", q, unit, dflt)

    a = spec.get("analysis", {})
    t = a.get("type")
    if t is not None and t not in ANALYSES:
        errors.append(f"analysis.type is '{t}' but must be exactly one of {list(ANALYSES)}.")
    elif t is None:
        ask("analysis.type", f"Which analysis? [spec: analysis.type = one of {list(ANALYSES)}] {ANALYSES}")
    else:
        vs = a.get("variables", [])
        if t == "sweep" and len(vs) != 1:
            ask("analysis.variables", "Which ONE variable should be swept, and over what range?")
        if t == "grid" and not 2 <= len(vs) <= 3:
            ask("analysis.variables", "Which 2-3 variables should be combined, and the values for each?")
        if t == "tornado" and len(vs) < 2:
            ask("analysis.variables", "Which uncertain variables (at least 2), with a low and high value for each?")
        if t == "pt_profile":
            if not a.get("producer"):
                ask("analysis.producer", "Which well or source should the profile be run for?")
            cond = a.get("conditions") or {}
            unknown = [k for k in cond if k not in PT_CONDITIONS]
            given = [k for k in cond if k in PT_CONDITIONS]
            if unknown:
                errors.append(f"Unknown P/T condition(s) {unknown}. Use one of {list(PT_CONDITIONS)}.")
            elif not given:
                ask("analysis.conditions", "P/T profile boundary condition: give EITHER the outlet pressure "
                    "(PIPESIM calculates the rate) OR a liquid or gas flow rate (PIPESIM calculates the "
                    "outlet pressure)?", "model units", {"outlet_pressure": 15})
            elif len(given) > 1:
                errors.append("Give only ONE P/T condition: outlet_pressure OR a flow rate, not both.")
        for i, v in enumerate(vs):
            try:
                ctype, name, _ = resolve_var(v, spec)
                if known_components is not None and name not in known_components.get(ctype, []):
                    errors.append(f"Variable {i}: no {ctype} named '{name}' in the model. "
                                  f"Available {ctype}: {known_components.get(ctype, [])}")
            except KeyError as e:
                errors.append(f"Variable {i}: {e}. Use an alias, or give component_type, name and parameter.")
            keys = set(v)
            if t in ("sweep", "grid") and keys & {"low", "high"}:
                errors.append(f"Variable {i}: low/high are only for tornado. For a {t} use \"values\": [...] "
                              "or \"start\", \"stop\", \"steps\".")
            if t == "tornado" and keys & {"values", "start", "stop", "steps"}:
                errors.append(f"Variable {i}: a tornado uses only \"low\" and \"high\", not values/start/stop/steps.")
            if t == "tornado" and not ("low" in v and "high" in v):
                ask(f"analysis.variables[{i}]", f"Low and high value for variable {i}?")
            elif t in ("sweep", "grid") and values_of(v) is None:
                ask(f"analysis.variables[{i}]", f"Range for variable {i}: a list of values, or start/stop/steps?")
        if n_cases(spec) > MAX_CASES:
            errors.append(f"{n_cases(spec)} cases is too many (max {MAX_CASES}). Use fewer steps.")
    if errors:
        nxt = "Fix every item in 'errors' with ONE update_spec call (exact keys/values as stated), then check_spec once."
    elif missing:
        nxt = ("STOP calling tools. Ask the user about every item in 'missing' in ONE numbered message, "
               "with the suggested defaults. Wait for the answer.")
    else:
        nxt = "Call propose_plan and show the plan to the user word for word."
    return {"ready": not missing and not errors, "next_step": nxt, "missing": missing, "errors": errors,
            "n_cases": n_cases(spec) if t in ANALYSES else None}


def plan_text(spec):
    m, a = spec["model"], spec["analysis"]
    lines = [f"STUDY PLAN: {spec['objective']}", f"Units: {spec.get('units', 'METRIC')}"]
    if m["source"] == "existing":
        lines.append(f"1. Open a COPY of {m['path']} (the original is not modified)")
    else:
        lines.append(f"1. Build a new '{m['template']}' model with:")
        lines += [f"     {k} = {v}" for k, v in m["params"].items()]
    for c in spec.get("base_changes", []):
        lines.append(f"   Base change: {c['component_type']}:{c['name']}.{c['parameter']} = {c['value']}")
    lines.append(f"2. Analysis: {a['type']} ({ANALYSES[a['type']]})")
    for v in a.get("variables", []):
        label = v.get("alias") or f"{v['component_type']}:{v['name']}.{v['parameter']}"
        lines.append(f"     {label}: {values_of(v)}")
    if a["type"] == "pt_profile":
        lines.append(f"     producer: {a['producer']}")
        for k, v in (a.get("conditions") or {}).items():
            lines.append(f"     fixed {k} = {v} -> PIPESIM calculates "
                         + ("the flow rate" if k == "outlet_pressure" else "the outlet pressure"))
    kpis = spec.get("kpis") or [{"variable": k, "component": "(each producer)"} for k in DEFAULT_KPI_VARS]
    lines.append("3. Results recorded: " + ", ".join(f"{k.get('label') or k['variable']} @ {k['component']}" for k in kpis))
    lines.append(f"4. Total simulation runs: {n_cases(spec)}. Outputs: CSV, charts, report.md in runs/<timestamp>/")
    return "\n".join(lines)
