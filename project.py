"""
Project description: a declarative PIPESIM network (what the case studies contain), independent of sixgill.
The agent fills it from the user's description; check_project() lists every missing input per component
and validates the topology, the same way study.check() does for studies. netbuilder.py turns it into a .pips.

{
  "name": "Field A gathering", "units": "METRIC",
  "fluids":    [{"name": "BO-1", "type": "black_oil", "api": 35, "gor": 120, "water_cut": 10, "gas_sg": 0.7}],
  "wells":     [{"name": "W1", "fluid": "BO-1", "reservoir_pressure": 260, "reservoir_temperature": 95,
                 "ipr": {"model": "pi", "liquid_pi": 8}, "depth": 2600, "tubing_id": 76}],
  "sources":   [{"name": "S1", "fluid": "BO-1", "pressure": 40, "temperature": 60, "liquid_rate": 500}],
  "junctions": [{"name": "J1"}],
  "sinks":     [{"name": "Separator", "pressure": 15}],
  "chokes":    [{"name": "CK-1", "from": "W1", "bean_size": 12.7}],  # mm; optional: sits right after its "from" node
  "flowlines": [{"name": "FL-1", "from": "CK-1", "to": "J1", "length": 2000, "id": 150, "elevation_change": 0},
                {"name": "FL-2", "from": "J1", "to": "Separator", "length": 5000, "id": 200, "elevation_change": 10}]
}
Topology: nodes are wells, sources, chokes, junctions and sinks; flowlines connect two nodes; a choke is
connected directly to its upstream node. Every well/source must reach a sink. Lists merge by "name"
(see merge_project), so the agent can change one well without resending the others.
"""
import copy

UNITS_METRIC = {"pressure": "bara", "temperature": "degC", "length": "m", "id": "mm", "bean": "mm", "rate": "sm3/d",
                "gas_rate": "mmsm3/d", "pi": "sm3/d/bar", "gor": "sm3/sm3", "pct": "%"}

# entity -> field -> (question, unit, default). None default = must be asked, no sensible default.
FIELDS = {
    "fluids": {
        "type": ("Fluid model: black_oil (oil: API, GOR, water cut) or gas (gas/condensate: gas SG, OGR, WGR)?",
                 "", "black_oil"),
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
    "sources": {   # plus exactly one of SOURCE_BC
        "fluid":       ("Which fluid enters at this source?", "", None),
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
    "chokes": {"from": ("Which well, source or junction is the choke installed right after?", "", None),
               "bean_size": ("Choke bean size (diameter)?", "mm", 12.7)},
    "junctions": {},
}
IPR_FIELDS = {"pi": ["liquid_pi"], "vogel": ["aof"], "backpressure": ["c", "n"]}
FLUID_FIELDS = {
    "black_oil": {"api":       ("Oil gravity?", "API", 35.0),
                  "gor":       ("Producing gas-oil ratio?", "sm3/sm3", 100.0),
                  "water_cut": ("Water cut?", "%", 0.0),
                  "gas_sg":    ("Gas specific gravity?", "air=1", 0.7)},
    "gas":       {"gas_sg":    ("Gas specific gravity?", "air=1", 0.65),
                  "ogr":       ("Condensate-gas ratio (0 for dry gas)?", "sm3/mmsm3", 0.0),
                  "wgr":       ("Water-gas ratio?", "sm3/mmsm3", 0.0),
                  "api":       ("Condensate gravity?", "API", 50.0)},
}
SOURCE_BC = {"pressure": "bara", "liquid_rate": "sm3/d", "gas_rate": "mmsm3/d"}


def completion_name(well):
    """Completions get unique names: PIPESIM reports results by short name, so two "Completion"s would collide."""
    return f"{well}_Comp"
NODE_KINDS = ("wells", "sources", "junctions", "sinks", "chokes")


def check_project(p):
    missing, errors = [], []

    def ask(path, q, unit="", default=None):
        missing.append({"field": path, "question": q, "unit": unit, "suggested_default": default})

    if not p.get("name"):
        ask("project.name", "Project name?", "", "New project")
    for k in p:
        if k not in ("name", "units", "ambient_temperature", *FIELDS):
            errors.append(f"Remove project key '{k}'. Allowed: {['name', 'units', 'ambient_temperature', *FIELDS]}")
    if p.get("units", "METRIC") != "METRIC":
        errors.append("Projects are described in METRIC units (bara, degC, m, mm, sm3/d); set units to METRIC.")
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
            if kind == "fluids":
                ftype = e.get("type", "black_oil")
                if ftype not in FLUID_FIELDS:
                    errors.append(f"Fluid {n}: type must be one of {list(FLUID_FIELDS)}")
                else:
                    for f, (q, unit, dflt) in FLUID_FIELDS[ftype].items():
                        if f not in e:
                            ask(f"fluids.{n}.{f}", f"{n}: {q}", unit, dflt)
            if kind == "sources":
                given = [k for k in SOURCE_BC if k in e]
                if not given:
                    ask(f"sources.{n}.pressure", f"{n}: fixed pressure (bara), OR fixed flow rate: liquid_rate (sm3/d) "
                        "or gas_rate (mmsm3/d)? Give exactly one; PIPESIM calculates the rest.", "", None)
                elif len(given) > 1:
                    errors.append(f"Source {n}: give only one of {list(SOURCE_BC)} (got {given}); "
                                  "PIPESIM calculates the others.")
    fluids = {f.get("name") for f in p.get("fluids") or []}
    for kind in ("wells", "sources"):
        for e in p.get(kind) or []:
            if e.get("fluid") and e["fluid"] not in fluids:
                errors.append(f"{e.get('name')}: fluid '{e['fluid']}' is not defined in fluids {sorted(fluids)}")

    # topology: edges are flowlines and chokes; every well/source must reach a sink, no cycles, no dead ends
    edges = [(e.get("from"), e.get("to"), e.get("name")) for e in p.get("flowlines") or []]
    edges += [(e.get("from"), e.get("name"), e.get("name")) for e in p.get("chokes") or []]
    for e in p.get("flowlines") or []:
        for end in ("from", "to"):
            if names.get(e.get(end)) == "flowlines":
                errors.append(f"{e.get('name')}: '{e[end]}' is a flowline. Flowlines connect nodes "
                              "(wells, sources, chokes, junctions, sinks); add a junction between two flowlines.")
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
        for kind in ("junctions", "chokes"):
            for j in p.get(kind) or []:
                n = j.get("name")
                if n and n not in out:
                    errors.append(f"{kind[:-1].title()} {n} has no outgoing flowline")
        for kind in ("wells", "sources", "chokes"):
            for e in p.get(kind) or []:
                n = e.get("name")
                if n and len(out.get(n, [])) > 1:
                    errors.append(f"{n} has {len(out[n])} outgoing connections; a {kind[:-1]} can feed only one. "
                                  "Put a junction after it to split the flow.")
    errors = list(dict.fromkeys(errors))
    if errors:
        nxt = "Fix every item in 'errors' with ONE update call, then check again."
    elif missing:
        nxt = ("STOP calling tools. Ask the user about every item in 'missing' in ONE numbered message "
               "(group by component), with the suggested defaults. Wait for the answer.")
    else:
        nxt = "Project complete. Continue with the study spec (model.source = \"project\")."
    return {"ready": not missing and not errors, "next_step": nxt, "missing": missing, "errors": errors}


def merge_project(base, patch):
    """Merge a partial project into the current one. Lists merge by name; {"name": x, "_delete": true} removes x."""
    out = copy.deepcopy(base or {})
    for k, v in (patch or {}).items():
        if isinstance(v, list) and k in FIELDS:
            cur = {e.get("name"): e for e in out.get(k, [])}
            order = [e.get("name") for e in out.get(k, [])]
            for e in v:
                n = e.get("name")
                if e.get("_delete"):
                    cur.pop(n, None)
                    order = [o for o in order if o != n]
                elif n in cur:
                    merged = copy.deepcopy(cur[n])
                    for kk, vv in e.items():
                        merged[kk] = (dict(merged[kk], **vv) if isinstance(vv, dict) and isinstance(merged.get(kk), dict)
                                      else copy.deepcopy(vv))
                    cur[n] = merged
                else:
                    cur[n] = copy.deepcopy(e)
                    order.append(n)
            out[k] = [cur[n] for n in order if n in cur]
        else:
            out[k] = copy.deepcopy(v)
    return out


def known_components(p):
    """Component names the built model will have, by sixgill component type (for validating study variables)."""
    wells = [w["name"] for w in p.get("wells") or [] if w.get("name")]
    return {"Well": wells, "Completion": [f"{w}:{completion_name(w)}" for w in wells],
            "Tubing": [f"{w}:Tubing" for w in wells],
            "Source": [e["name"] for e in p.get("sources") or []], "Sink": [e["name"] for e in p.get("sinks") or []],
            "Junction": [e["name"] for e in p.get("junctions") or []], "Choke": [e["name"] for e in p.get("chokes") or []],
            "Flowline": [e["name"] for e in p.get("flowlines") or []],
            "BlackOilFluid": [e["name"] for e in p.get("fluids") or []]}


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
