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

# VERIFIED: parameters are plain strings such as "Pressure"; component names inside a well are "<well>:<name>";
#           separators are TwoPhaseSeparator/ThreePhaseSeparator (no "Separator" type).
# ASSUMED : Units.METRIC uses bara, degC, m, mm (diameters), sm3/d, as in the PIPESIM metric unit set.


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


def add(model, ctype, name, context=None, parameters=None):
    kw = {"parameters": parameters or {}}
    if context:
        kw["context"] = context
    model.add(ctype, name, **kw)
    return f"{context}:{name}" if context else name


_connect_style = {}


def connect(model, a_type, a, b_type, b):
    """Connect a -> b (flow direction). ASSUMED: model.connect({type: name}, {type: name})."""
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
# VERIFIED (2023.1, CSN_301): changing Sink "Pressure" with set_value left every network result unchanged.
# Either the network task keeps its own boundary conditions, or that sink was isolated by a pump.
# ASSUMED: the network task exposes get_conditions()/set_conditions(); we set both and read back to verify.
BOUNDARY_PARAMS = {("Sink", "Pressure"), ("Sink", "Temperature"), ("Source", "Pressure"),
                   ("Source", "Temperature")}


def get_boundaries(model):
    nt = model.tasks.networksimulation
    if not hasattr(nt, "get_conditions"):
        return None
    try:
        return nt.get_conditions()
    except Exception:
        return None


def _key(entry, param):
    if param in entry:
        return param
    low = param.lower()
    return next((k for k in entry if isinstance(k, str) and k.lower() == low), None)


_set_style = {}


def set_boundary(model, node, param, value):
    """Set a network boundary condition and verify it by reading it back. Returns True when verified."""
    nt = model.tasks.networksimulation
    conds = get_boundaries(model)
    if not isinstance(conds, dict) or not isinstance(conds.get(node), dict):
        return False
    k = _key(conds[node], param)
    if k is None:
        return False
    new = copy.deepcopy(conds)
    new[node][k] = value
    styles = [_set_style["ok"]] if "ok" in _set_style else ["boundaries", "positional", "conditions"]
    for s in styles:
        try:
            if s == "boundaries":
                nt.set_conditions(boundaries=new)
            elif s == "positional":
                nt.set_conditions(new)
            else:
                nt.set_conditions(conditions=new)
        except Exception:
            continue
        back = get_boundaries(model)
        if isinstance(back, dict) and isinstance(back.get(node), dict) and back[node].get(k) == value:
            _set_style["ok"] = s
            return True
    return False


def set_param(model, ctype, name, param, value):
    """Set a component parameter; for boundary parameters also set the network boundary condition."""
    model.set_value(**{ctype: name}, parameter=param, value=value)
    if (ctype, param) in BOUNDARY_PARAMS:
        set_boundary(model, name, param, value)


def get_param(model, ctype, name, param):
    if (ctype, param) in BOUNDARY_PARAMS:
        conds = get_boundaries(model)
        if isinstance(conds, dict) and isinstance(conds.get(name), dict):
            k = _key(conds[name], param)
            if k is not None and conds[name][k] is not None:
                return conds[name][k]
    return model.get_value(**{ctype: name}, parameter=param)
