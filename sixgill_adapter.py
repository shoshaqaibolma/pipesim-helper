"""
Every PIPESIM-version-specific detail lives here, so the rest of the code never guesses sixgill names.

Status of each fact for PIPESIM 2023.1:
  VERIFIED - observed on the user's install;
  ASSUMED  - from the Python Toolkit docs. Every P(...)/C(...)/MC(...) name in the code base is checked by
             tests/test_api_names.py against knowledge/api.json once tools/introspect.py has recorded the real API.
"""
import copy
from sixgill.pipesim import Model
from sixgill import definitions as d

# VERIFIED (2023.1, knowledge/api.json + case-study dumps):
#   - parameters are plain strings such as "Pressure"; find() returns in-well items as "<well>:<item>";
#   - separators are TwoPhaseSeparator/ThreePhaseSeparator (no "Separator" type);
#   - Units.METRIC = "PIPESIM_METRIC": bara, degC, m, mm (pipe and choke diameters), sm3/d, mmsm3/d (gas);
#     OGR/WGR in sm3/mmsm3, GOR in sm3/sm3, back-pressure IPR C in mmsm3/d/bar2n (describe() on the install);
#   - results come as node[variable] = {"Unit": "<unit>", <component>: value, ...};
#   - connect(source, destination, source_port=None) takes {type: name} dicts or context strings.


def P(group, const):
    """sixgill parameter name, e.g. P("Sink", "PRESSURE") -> "Pressure"."""
    try:
        return getattr(getattr(d.Parameters, group), const)
    except AttributeError:
        raise AttributeError(f"sixgill has no Parameters.{group}.{const} in this PIPESIM version "
                             f"(see knowledge/api.json; fix the name in the calling module)") from None


def C(group, const):
    """sixgill constant, e.g. C("IPRModels", "IPRPIMODEL")."""
    try:
        return getattr(getattr(d.Constants, group), const)
    except AttributeError:
        raise AttributeError(f"sixgill has no Constants.{group}.{const} in this PIPESIM version "
                             f"(see knowledge/api.json)") from None


def MC(const):
    """Model component type, e.g. MC("WELL") -> "Well"."""
    try:
        return getattr(d.ModelComponents, const)
    except AttributeError:
        raise AttributeError(f"sixgill has no ModelComponents.{const} (see knowledge/api.json)") from None


def new_model(path, units="METRIC"):
    return Model.new(path, units=getattr(d.Units, units), overwrite=True)


def open_model(path, units="METRIC"):
    return Model.open(path, units=getattr(d.Units, units))


def ctx(ctype, name):
    """Context keywords for get/set_value. VERIFIED: Completion="Well:VertComp" fails with 'No such context';
    in-well items are addressed as Well="<well>", <type>="<item>" (documented sixgill form)."""
    if ":" in name:
        well, item = name.split(":", 1)
        return {"Well": well, ctype: item}
    return {ctype: name}


def get_value(model, ctype, name, parameter):
    try:
        return model.get_value(**ctx(ctype, name), parameter=parameter)
    except Exception as first:
        try:
            return model.get_value(context=name, component=ctype, parameter=parameter)
        except Exception:
            raise first from None


def set_value(model, ctype, name, parameter, value):
    try:
        model.set_value(**ctx(ctype, name), parameter=parameter, value=value)
    except Exception as first:
        try:
            model.set_value(context=name, component=ctype, parameter=parameter, value=value)
        except Exception:
            raise first from None


def add(model, ctype, name, context=None, parameters=None):
    kw = {"parameters": parameters or {}}
    if context:
        kw["context"] = context
    model.add(ctype, name, **kw)
    return f"{context}:{name}" if context else name


_connect_style = {}


SEPARATOR_PORTS = {"gas": "TOP", "liquid": "BOTTOM"}  # VERIFIED: Connection.Separator TOP/BOTTOM/BOOT = "... Port"


def port(name):
    return getattr(d.Connection.Separator, SEPARATOR_PORTS[name])


def connect(model, a_type, a, b_type, b, source_port=None):
    """Connect a -> b (flow direction): model.connect({type: name}, {type: name}, source_port) (documented form).
    source_port is required when a is a separator ("gas" or "liquid")."""
    kw = {"source_port": port(source_port)} if source_port else {}
    styles = [_connect_style["ok"]] if "ok" in _connect_style else ["dict", "names"]
    last = None
    for s in styles:
        try:
            if s == "dict":
                model.connect({a_type: a}, {b_type: b}, **kw)
            else:
                model.connect(a, b, **kw)
            _connect_style["ok"] = s
            return
        except TypeError as e:  # wrong call style for this version: try the next one
            last = e
    raise last


# ---------------------------------------------------------------- boundary conditions
# VERIFIED (2023.1, CSN_301 probe): the network task keeps its own boundary conditions. set_value on a Sink's
# "Pressure" left every result unchanged; set_conditions(boundaries=<full dict from get_conditions()>) changed
# the result. Wells appear in get_conditions() under their completion, e.g. "Well:VertComp", with the
# reservoir pressure/temperature as "Pressure"/"Temperature".
BOUNDARY_MAP = {("Sink", "Pressure"): "Pressure", ("Sink", "Temperature"): "Temperature",
                ("Source", "Pressure"): "Pressure", ("Source", "Temperature"): "Temperature",
                ("Source", "LiquidFlowRate"): "LiquidFlowRate", ("Source", "GasFlowRate"): "GasFlowRate",
                ("Completion", "ReservoirPressure"): "Pressure", ("Completion", "ReservoirTemperature"): "Temperature"}


def get_boundaries(model):
    nt = model.tasks.networksimulation
    if not hasattr(nt, "get_conditions"):
        return None
    try:
        return nt.get_conditions()
    except Exception:
        return None


def _same(a, b):
    try:
        return abs(float(a) - float(b)) <= 1e-6 * max(1.0, abs(float(b)))
    except (TypeError, ValueError):
        return a == b


def set_boundary(model, node, key, value):
    """Set one network boundary value (node = sink/source name or "<well>:<completion>") and verify it."""
    nt = model.tasks.networksimulation
    conds = get_boundaries(model)
    if not isinstance(conds, dict) or not isinstance(conds.get(node), dict) or key not in conds[node]:
        return False
    new = copy.deepcopy(conds)
    new[node][key] = value
    try:
        nt.set_conditions(boundaries=new)
    except Exception:
        return False
    back = get_boundaries(model)
    return isinstance(back, dict) and _same((back.get(node) or {}).get(key), value)


def set_boundaries(model, node, values):
    """Set several boundary values of one node in a single call, then verify them all."""
    nt = model.tasks.networksimulation
    conds = get_boundaries(model)
    if not isinstance(conds, dict) or not isinstance(conds.get(node), dict):
        return False
    new = copy.deepcopy(conds)
    new[node].update(values)
    try:
        nt.set_conditions(boundaries=new)
    except Exception:
        return False
    back = (get_boundaries(model) or {}).get(node) or {}
    return all(_same(back.get(k), v) for k, v in values.items())


def sync_boundaries(model):
    """Re-synchronise the network boundary conditions with the component values (after building a model)."""
    nt = model.tasks.networksimulation
    try:
        nt.reset_conditions()
        return True
    except Exception:
        return False


# VERIFIED (2023.1, job 03): completion boundary entries also hold the fluid's GOR / WaterCut (copied at sync), so a
# change to the fluid alone may not reach the network simulation. Propagate it to every node that uses the fluid.
FLUID_BC = {"WaterCut": "WaterCut", "GOR": "GOR", "OGR": "OGR", "WGR": "WGR", "GLR": "GLR"}


def _fluid_nodes(model, fluid):
    nodes = []
    for node, b in (get_boundaries(model) or {}).items():
        t = (b or {}).get("BoundaryNodeType")
        if t not in ("Completion", "Source"):
            continue
        try:
            if get_value(model, t, node, "AssociatedBlackOilFluid") == fluid:
                nodes.append(node)
        except Exception:
            pass
    return nodes


def set_param(model, ctype, name, param, value):
    """Set a component parameter; for boundary parameters also set the network boundary condition."""
    set_value(model, ctype, name, param, value)
    key = BOUNDARY_MAP.get((ctype, param))
    if key:
        set_boundary(model, name, key, value)
    if ctype == "BlackOilFluid" and param in FLUID_BC:
        for node in _fluid_nodes(model, name):
            entry = (get_boundaries(model) or {}).get(node) or {}
            if entry.get(FLUID_BC[param]) is not None:
                set_boundary(model, node, FLUID_BC[param], value)


def get_param(model, ctype, name, param):
    key = BOUNDARY_MAP.get((ctype, param))
    if key:
        conds = get_boundaries(model)
        if isinstance(conds, dict) and isinstance(conds.get(name), dict) and conds[name].get(key) is not None:
            return conds[name][key]
    return get_value(model, ctype, name, param)


def result(table, variable, component):
    """(value, unit) from a result table node[variable] = {"Unit": ..., component: value}."""
    if not isinstance(table, dict):
        return None, None
    row = table.get(variable)
    if isinstance(row, dict):
        return row.get(component), row.get("Unit")
    row = table.get(component)  # older layout: [component][variable]
    if isinstance(row, dict):
        return row.get(variable), None
    return None, None


def _plain(o, depth=0):
    """Public data attributes of a sixgill result object as plain Python (lists/dicts/numbers)."""
    if depth > 3:
        return None
    if hasattr(o, "tolist"):
        try:
            return o.tolist()
        except Exception:
            pass
    if hasattr(o, "to_dict"):
        try:
            o = o.to_dict()
        except Exception:
            pass
    if isinstance(o, dict):
        return {str(k): _plain(v, depth + 1) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_plain(v, depth + 1) for v in o]
    if o is None or isinstance(o, (int, float, str, bool)):
        return o
    out = {}
    for k in dir(o):
        if k.startswith("_"):
            continue
        try:
            v = getattr(o, k)
        except Exception:
            continue
        if not callable(v):
            out[k] = _plain(v, depth + 1)
    return out


def _series(d, prefix=""):
    """All numeric lists inside a (nested) dict, keyed by their path."""
    found = {}
    if isinstance(d, dict):
        for k, v in d.items():
            path = f"{prefix}{k}"
            if isinstance(v, list) and len(v) > 1 and all(isinstance(x, (int, float)) or x is None for x in v):
                found[path] = v
            elif isinstance(v, dict):
                vals = list(v.values())
                if len(vals) > 1 and all(isinstance(x, (int, float)) or x is None for x in vals):
                    found[path] = vals
                else:
                    found.update(_series(v, path + "."))
    return found


def _num(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool) and x == x  # x == x is False for NaN


RATE_KEYS = {"liquid": "NodalPointVolumeFlowrateLiquidStockTank", "gas": "NodalPointVolumeFlowrateGasStockTank"}


def curve_xy(curve, base="liquid"):
    """(rates, pressures, raw) of a nodal curve. VERIFIED layout (2023.1): curve.curve_data holds unsorted
    NodalPointVolumeFlowrate*StockTank / NodalPointPressure lists, with NaN gaps."""
    raw = _plain(curve)
    data = raw.get("curve_data") if isinstance(raw, dict) else None
    data = data if isinstance(data, dict) else _series(raw)
    q = data.get(RATE_KEYS[base]) or next((v for k, v in data.items() if base in k.lower() and "rate" in k.lower()), None)
    p = data.get("NodalPointPressure") or next((v for k, v in data.items() if "press" in k.lower()), None)
    if not q or not p:
        return None, None, raw
    pts = sorted((a, b) for a, b in zip(q, p) if _num(a) and _num(b))
    return [a for a, _ in pts], [b for _, b in pts], raw


def nodal(model, producer, outlet_pressure, completion=None):
    """Run nodal analysis at a given outlet pressure (VERIFIED on 2023.1). Returns the operating point (rates and
    pressure at the nodal point, which is the bottom hole by default), the inflow/outflow curves, and raw data."""
    r = model.tasks.nodalanalysis.run(producer, parameters={P("NodalAnalysisSimulation", "OUTLETPRESSURE"): outlet_pressure})
    base = "gas" if str(getattr(r, "fluid_base", "Liquid")).lower().startswith("gas") else "liquid"
    out = {"state": str(getattr(r, "state", "")), "cases": list(getattr(r, "cases", []) or []), "rate_basis": base}
    case = out["cases"][0] if out["cases"] else None
    node = (getattr(r, "node", {}) or {}).get(case, {}) if case else {}
    comp = completion
    if comp is None:
        comps = [c.split(":", 1)[1] for c in model.find(Completion=d.ALL) or [] if c.startswith(f"{producer}:")]
        comp = comps[0] if comps else None
    op = {}
    # rates at the completion = what the reservoir delivers (gas lift gas enters higher up the well)
    for key, var in (("liquid_rate", "VolumeFlowrateLiquidStockTank"), ("oil_rate", "VolumeFlowrateOilStockTank"),
                     ("reservoir_gas_rate", "VolumeFlowrateGasStockTank"), ("water_rate", "VolumeFlowrateWaterStockTank")):
        row = node.get(var) or {}
        if comp in row and _num(row[comp]):
            op[key] = {"value": row[comp], "unit": row.get("Unit")}
    pts = _plain(getattr(r, "operating_points", None)) or []
    if pts and isinstance(pts[0], dict):   # PIPESIM's own operating point
        pd, units = pts[0].get("point_data") or {}, pts[0].get("units") or {}
        for key, var in (("liquid_rate", RATE_KEYS["liquid"]), ("reservoir_gas_rate", RATE_KEYS["gas"]),
                         ("bottomhole_pressure", "NodalPointPressure")):
            if _num(pd.get(var)):
                op[key] = {"value": pd[var], "unit": units.get(var)}
    op["outlet_pressure"] = {"value": outlet_pressure, "unit": "bara"}
    out["operating_point"] = op
    curves, raw = {}, {}
    for kind in ("inflow", "outflow"):
        for i, c in enumerate(getattr(r, f"{kind}_curves", []) or []):
            x, y, rc = curve_xy(c, base)
            raw[f"{kind}_{i}"] = rc
            if x and y:
                curves[f"{kind}_{i}"] = {"rate": x, "pressure": y}
    raw["operating_points"] = pts
    out["curves"], out["raw"] = curves, raw
    out["summary_messages"] = _plain(getattr(r, "summary", None))
    return out


def validate(model):
    """Model validation messages (empty list when valid)."""
    try:
        return [f"{getattr(i, 'path', '')} {getattr(i, 'property_name', '')}: {getattr(i, 'message', i)}".strip()
                for i in model.validate()]
    except Exception as e:
        return [f"validate() failed: {type(e).__name__}: {e}"]
