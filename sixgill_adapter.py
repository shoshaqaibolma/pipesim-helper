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


def connect(model, a_type, a, b_type, b):
    """Connect a -> b (flow direction): model.connect({type: name}, {type: name}) (documented form)."""
    styles = [_connect_style["ok"]] if "ok" in _connect_style else ["dict", "names"]
    last = None
    for s in styles:
        try:
            if s == "dict":
                model.connect({a_type: a}, {b_type: b})
            else:
                model.connect(a, b)
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


def set_param(model, ctype, name, param, value):
    """Set a component parameter; for boundary parameters also set the network boundary condition."""
    set_value(model, ctype, name, param, value)
    key = BOUNDARY_MAP.get((ctype, param))
    if key:
        set_boundary(model, name, key, value)


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


def curve_xy(curve):
    """(rates, pressures, raw) of a nodal Curve, found by attribute name (rate/flow vs pressure)."""
    raw = _plain(curve)
    s = _series(raw)
    x = next((v for k, v in s.items() if any(w in k.lower() for w in ("flow", "rate"))), None)
    y = next((v for k, v in s.items() if "press" in k.lower()), None)
    return x, y, raw


def nodal(model, producer, outlet_pressure, completion=None):
    """Run nodal analysis at a given outlet pressure (VERIFIED call). Returns the operating point (rates and
    flowing bottom-hole pressure at the completion), the inflow/outflow curves, and raw data for inspection."""
    r = model.tasks.nodalanalysis.run(producer, parameters={P("NodalAnalysisSimulation", "OUTLETPRESSURE"): outlet_pressure})
    out = {"state": str(getattr(r, "state", "")), "cases": list(getattr(r, "cases", []) or [])}
    case = out["cases"][0] if out["cases"] else None
    node = (getattr(r, "node", {}) or {}).get(case, {}) if case else {}
    comp = completion
    if comp is None:
        comps = [c.split(":", 1)[1] for c in model.find(Completion=d.ALL) or [] if c.startswith(f"{producer}:")]
        comp = comps[0] if comps else None
    op = {}
    for key, var in (("liquid_rate", "VolumeFlowrateLiquidStockTank"), ("oil_rate", "VolumeFlowrateOilStockTank"),
                     ("gas_rate", "VolumeFlowrateGasStockTank"), ("water_rate", "VolumeFlowrateWaterStockTank"),
                     ("bottomhole_pressure", "Pressure")):
        row = node.get(var) or {}
        if comp in row:
            op[key] = {"value": row[comp], "unit": row.get("Unit")}
    prof = (getattr(r, "profile", {}) or {}).get(case, {}) if case else {}
    if "bottomhole_pressure" not in op and prof.get("BranchEquipment") and prof.get("Pressure"):
        for eq, p in zip(prof["BranchEquipment"], prof["Pressure"]):
            if eq == comp:
                op["bottomhole_pressure"] = {"value": p, "unit": "bara"}
                break
    op["outlet_pressure"] = {"value": outlet_pressure, "unit": "bara"}
    out["operating_point"] = op
    curves, raw = {}, {}
    for kind in ("inflow", "outflow"):
        for i, c in enumerate(getattr(r, f"{kind}_curves", []) or []):
            x, y, rc = curve_xy(c)
            raw[f"{kind}_{i}"] = rc
            if x and y:
                curves[f"{kind}_{i}"] = {"rate": x, "pressure": y}
    raw["operating_points"] = _plain(getattr(r, "operating_points", None))
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
