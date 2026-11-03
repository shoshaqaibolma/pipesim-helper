"""
Project description: a declarative PIPESIM network (what the case studies contain), independent of sixgill.
The agent fills it from the user's description; check_project() lists every missing input per component
and validates the topology, the same way study.check() does for studies. netbuilder.py turns it into a .pips.

{
  "name": "Field A gathering", "units": "METRIC",
  "fluids":    [{"name": "BO-1", "type": "black_oil", "api": 35, "gor": 120, "water_cut": 10, "gas_sg": 0.7}],
  "wells":     [{"name": "W1", "fluid": "BO-1", "reservoir_pressure": 260, "reservoir_temperature": 95,
                 "ipr": {"model": "pi", "liquid_pi": 8}, "depth": 2600, "tubing_id": 76,
                 "gas_lift": {"injection_depth": 2000, "rate": 0.05}}],          # gas_lift optional
  "sources":   [{"name": "S1", "fluid": "BO-1", "pressure": 40, "temperature": 60, "liquid_rate": 500}],
  "junctions": [{"name": "J1"}],
  "sinks":     [{"name": "Separator", "pressure": 15}],
  "flowlines": [{"name": "FL-1", "from": "W1", "to": "J1", "length": 2000, "id": 150, "elevation_change": 0}],
  "chokes":    [{"name": "CK-1", "from": "J1", "to": "FL-2", "bean_size": 32}]   # optional, in-line
}
"""
import copy

UNITS_METRIC = {"pressure": "bara", "temperature": "degC", "length": "m", "id": "mm", "rate": "sm3/d",
                "gas_rate": "mmsm3/d", "pi": "sm3/d/bar", "gor": "sm3/sm3", "pct": "%"}

# entity -> field -> (question, unit, default). None default = must be asked, no sensible default.
FIELDS = {
    "fluids": {
        "type":      ("Fluid model: black_oil (oil/water/gas by API, GOR, water cut) or dry_gas?", "", "black_oil"),
        "api":       ("Oil gravity?", "API", 35.0),
        "gor":       ("Producing gas-oil ratio?", "sm3/sm3", 100.0),
        "water_cut": ("Water cut?", "%", 0.0),
        "gas_sg":    ("Gas specific gravity?", "air=1", 0.7),
    },
    "wells": {
        "fluid":                 ("Which fluid does this well produce?", "", None),
        "reservoir_pressure":    ("Reservoir pressure?", "bara", None),
        "reservoir_temperature": ("Reservoir temperature?", "degC", 90.0),
        "ipr":                   ("Inflow (IPR): productivity index (liquid_pi), Vogel (aof), or gas back-pressure (c, n)?",
                                  "", {"model": "pi", "liquid_pi": 10.0}),
        "depth":                 ("Depth to mid-perforation (vertical)?", "m", None),
        "tubing_id":             ("Tubing inner diameter?", "mm", 76.0),
    },
    "sources": {
        "fluid":       ("Which fluid enters at this source?", "", None),
        "pressure":    ("Source pressure?", "bara", None),
        "temperature": ("Source temperature?", "degC", 60.0),
    },
    "sinks": {"pressure": ("Delivery / separator pressure?", "bara", None)},
    "flowlines": {
        "from": ("Upstream end (well, source, junction or choke)?", "", None),
        "to":   ("Downstream end (junction, sink or choke)?", "", None),
        "length": ("Flowline length?", "m", None),
        "id": ("Flowline inner diameter?", "mm", 150.0),
        "elevation_change": ("Elevation change, positive uphill?", "m", 0.0),
    },
    "chokes": {"from": ("Upstream end?", "", None), "to": ("Downstream end?", "", None),
               "bean_size": ("Choke bean size?", "1/64 in", 32.0)},
    "junctions": {},
}
IPR_FIELDS = {"pi": ["liquid_pi"], "vogel": ["aof"], "backpressure": ["c", "n"]}
NODE_KINDS = ("wells", "sources", "junctions", "sinks", "chokes")


def check_project(p):
    missing, errors = [], []

    def ask(path, q, unit="", default=None):
        missing.append({"field": path, "question": q, "unit": unit, "suggested_default": default})

    if not p.get("name"):
        ask("project.name", "Project name?", "", "New project")
    for k in p:
        if k not in ("name", "units", *FIELDS):
            errors.append(f"Remove project key '{k}'. Allowed: {['name', 'units', *FIELDS]}")
    if not p.get("wells") and not p.get("sources"):
        ask("project.wells", "How many wells (or sources), and their names?")
    if not p.get("sinks"):
        ask("project.sinks", "Where does the production go (sink/separator name and pressure)?", "bara",
            [{"name": "Separator", "pressure": 15.0}])

    names = {}
    for kind in FIELDS:
        for i, e in enumerate(p.get(kind) or []):
            n = e.get("name")
            if not n:
                errors.append(f"{kind}[{i}] has no name"); continue
            if n in names:
                errors.append(f"Duplicate name '{n}' ({names[n]} and {kind}). Names must be unique.")
            names[n] = kind
            for f, (q, unit, dflt) in FIELDS[kind].items():
                if f not in e:
                    ask(f"{kind}.{n}.{f}", f"{n}: {q}", unit, dflt)
            if kind == "wells" and isinstance(e.get("ipr"), dict):
                model = e["ipr"].get("model")
                if model not in IPR_FIELDS:
                    errors.append(f"{n}: ipr.model must be one of {list(IPR_FIELDS)}")
                else:
                    for f in IPR_FIELDS[model]:
                        if f not in e["ipr"]:
                            ask(f"wells.{n}.ipr.{f}", f"{n}: IPR parameter {f}?",
                                {"liquid_pi": "sm3/d/bar", "aof": "sm3/d", "c": "sm3/d/bar^2n", "n": ""}[f])
            if kind == "fluids" and e.get("type") not in (None, "black_oil", "dry_gas"):
                errors.append(f"Fluid {n}: type must be black_oil or dry_gas")
    fluids = {f.get("name") for f in p.get("fluids") or []}
    for kind in ("wells", "sources"):
        for e in p.get(kind) or []:
            if e.get("fluid") and e["fluid"] not in fluids:
                errors.append(f"{e.get('name')}: fluid '{e['fluid']}' is not defined in fluids {sorted(fluids)}")

    # topology: edges are flowlines and chokes; every well/source must reach a sink, no cycles, no dead ends
    edges = [(e.get("from"), e.get("to"), e.get("name")) for k in ("flowlines", "chokes") for e in p.get(k) or []]
    for a, b, n in edges:
        for end in (a, b):
            if end is not None and end not in names:
                errors.append(f"{n}: unknown endpoint '{end}'")
        if names.get(a) == "sinks":
            errors.append(f"{n}: a sink cannot be upstream")
        if names.get(b) in ("wells", "sources"):
            errors.append(f"{n}: a well/source cannot be downstream")
    out = {}
    for a, b, n in edges:
        out.setdefault(a, []).append(b)
    def reaches_sink(node, seen=()):
        if names.get(node) == "sinks":
            return True
        if node in seen:
            errors.append(f"Loop in the network at '{node}' (looped networks are not supported yet)")
            return False
        return any(reaches_sink(nx, seen + (node,)) for nx in out.get(node, []))
    has_nodes = p.get("wells") or p.get("sources")
    if has_nodes and not edges:
        ask("project.flowlines", "How are the wells connected to the sink? For each flowline: from, to, length, "
            "inner diameter, elevation change (or: 'one flowline per well straight to the sink').")
    elif all(not m["field"].endswith((".from", ".to")) for m in missing):
        for kind in ("wells", "sources"):
            for e in p.get(kind) or []:
                n = e.get("name")
                if n and not reaches_sink(n):
                    errors.append(f"{n} is not connected to any sink. Add a flowline from {n} towards a sink.")
        for j in p.get("junctions") or []:
            n = j.get("name")
            if n and n not in out:
                errors.append(f"Junction {n} has no outgoing flowline")
    errors = list(dict.fromkeys(errors))
    if errors:
        nxt = "Fix every item in 'errors' with ONE update call, then check again."
    elif missing:
        nxt = ("STOP calling tools. Ask the user about every item in 'missing' in ONE numbered message "
               "(group by component), with the suggested defaults. Wait for the answer.")
    else:
        nxt = "Project complete. Continue with the study spec (model.source = \"project\")."
    return {"ready": not missing and not errors, "next_step": nxt, "missing": missing, "errors": errors}


def apply_defaults(p, fields):
    """Fill the given missing fields (paths from check_project) with their suggested defaults."""
    p = copy.deepcopy(p)
    for m in check_project(p)["missing"]:
        if m["field"] in fields and m["suggested_default"] is not None:
            kind, name, *rest = m["field"].split(".")
            if kind == "project":
                p[name] = copy.deepcopy(m["suggested_default"])
                continue
            ent = next(e for e in p[kind] if e.get("name") == name)
            if len(rest) == 2:
                ent.setdefault(rest[0], {})[rest[1]] = m["suggested_default"]
            else:
                ent[rest[0]] = copy.deepcopy(m["suggested_default"])
    return p


def summary(p):
    lines = [f"PROJECT: {p.get('name')} ({p.get('units', 'METRIC')})"]
    for kind in FIELDS:
        for e in p.get(kind) or []:
            attrs = ", ".join(f"{k}={v}" for k, v in e.items() if k != "name")
            lines.append(f"  {kind[:-1]:<9} {e['name']}: {attrs}")
    return "\n".join(lines)
