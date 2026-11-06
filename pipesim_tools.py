"""
PIPESIM tool layer: a thin, LLM-friendly wrapper around SLB's PIPESIM Python Toolkit (sixgill).

Every tool returns plain JSON-able data and never raises. Errors come back as {"error": ...},
so the model can read them and correct itself.
Safety: the original .pips file is never overwritten. Edits stay in memory until save_model_as().

NOTE: sixgill signatures vary slightly between PIPESIM versions. Check against the Python
Toolkit docs installed with your PIPESIM (Help > Python Toolkit) and run selftest.py first.
"""
import json, os, traceback

from sixgill.pipesim import Model
from sixgill import definitions as d
import sixgill_adapter as sa

ALL = getattr(d, "ALL", None)
_state = {"model": None, "path": None}
MAX_LIST = 40  # downsample long profile arrays so a small-context local model isn't flooded


def _jsonable(o):
    if hasattr(o, "to_dict"):
        o = o.to_dict()
    if isinstance(o, dict):
        return {str(k): _jsonable(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        o = list(o)
        if len(o) > MAX_LIST:
            step = max(1, len(o) // MAX_LIST)
            o = o[::step] + [o[-1]]
        return [_jsonable(v) for v in o]
    if isinstance(o, float):
        return round(o, 4)
    if o is None or isinstance(o, (int, str, bool)):
        return o
    return str(o)


def _safe(fn):
    def wrapper(**kw):
        try:
            return _jsonable(fn(**kw))
        except Exception as e:
            return {"error": f"{type(e).__name__}: {e}", "trace": traceback.format_exc(limit=2)[-600:]}
    wrapper.__name__, wrapper.__doc__ = fn.__name__, fn.__doc__
    return wrapper


def _m():
    if _state["model"] is None:
        raise RuntimeError("No model open. Call open_model first.")
    return _state["model"]


def _consts(cls, names):
    return [getattr(cls, n) for n in names if hasattr(cls, n)]


DEFAULT_SYSTEM_VARS = _consts(d.SystemVariables, [
    "PRESSURE", "TEMPERATURE", "VOLUME_FLOWRATE_LIQUID_STOCKTANK", "VOLUME_FLOWRATE_OIL_STOCKTANK",
    "VOLUME_FLOWRATE_WATER_STOCKTANK", "VOLUME_FLOWRATE_GAS_STOCKTANK", "GOR_STOCKTANK", "WATER_CUT_STOCKTANK",
    "INLET_PRESSURE", "OUTLET_PRESSURE", "MAXIMUM_VELOCITY_FLUID", "MAXIMUM_EROSIONAL_VELOCITY_RATIO"])
DEFAULT_PROFILE_VARS = _consts(d.ProfileVariables, [
    "TOTAL_DISTANCE", "ELEVATION", "PRESSURE", "TEMPERATURE", "HOLDUP_FRACTION_LIQUID",
    "FLOW_PATTERN_GAS_LIQUID", "VELOCITY_MIXTURE"])


# ---------------------------------------------------------------- tools
@_safe
def open_model(path: str, units: str = "METRIC"):
    """Open a PIPESIM .pips model. units: METRIC, FIELD or SI."""
    if _state["model"] is not None:
        _state["model"].close()
    if not os.path.exists(path):
        raise FileNotFoundError(path)
    _state["model"] = Model.open(path, units=getattr(d.Units, units.upper()))
    _state["path"] = path
    return {"opened": path, "units": units, "about": str(_state["model"].about())[:500]}


@_safe
def model_summary():
    """List the component names in the open model, grouped by component type."""
    m, out = _m(), {}
    for t in ["Well", "Source", "Sink", "Junction", "Flowline", "Choke", "Pump", "Compressor",
              "TwoPhaseSeparator", "ThreePhaseSeparator", "HeatExchanger", "MultiplierAdder", "Completion", "Tubing", "Casing", "GasLiftInjection", "ESP"]:
        try:
            names = [n for n in m.find(**{t: ALL}) or []
                     if not (t == "Source" and ":" in n)]  # "Well:Source 1" etc. are internal parts of a well
            if names:
                out[t] = list(names)
        except Exception:
            pass
    return out


@_safe
def get_values(component_type: str, parameters: list, name: str = ""):
    """Read parameters (e.g. ["WellheadPressure"]) for one component, or for all of that type when name is empty."""
    m = _m()
    if name and ":" in name:  # in-well item, e.g. "Well:VertComp"
        return {name: {p: sa.get_value(m, component_type, name, p) for p in parameters}}
    return m.get_values(**{component_type: name or ALL}, parameters=parameters)


@_safe
def set_value(component_type: str, name: str, parameter: str, value):
    """Change one parameter on one component in memory (not saved to disk)."""
    m = _m()
    before = sa.get_param(m, component_type, name, parameter)
    sa.set_param(m, component_type, name, parameter, value)
    return {"changed": f"{component_type}:{name}.{parameter}", "before": before, "after": value, "saved": False}


@_safe
def run_network_simulation(system_variables: list = None, profile_variables: list = None, include_profiles: bool = False):
    """Run a steady-state network simulation and return node/system results (and profiles when requested)."""
    r = _m().tasks.networksimulation.run(
        system_variables=system_variables or DEFAULT_SYSTEM_VARS,
        profile_variables=profile_variables or DEFAULT_PROFILE_VARS)
    out = {"state": str(getattr(r, "state", "")), "summary": getattr(r, "summary", None),
           "messages": getattr(r, "messages", None), "system": getattr(r, "system", None),
           "node": getattr(r, "node", None)}
    if include_profiles:
        out["profile"] = getattr(r, "profile", None)
    return out


@_safe
def get_pt_profile_conditions(producer: str):
    """Show the current boundary conditions of the P/T profile task for a well or source."""
    return _m().tasks.ptprofilesimulation.get_conditions(producer=producer)


@_safe
def run_pt_profile(producer: str, conditions: dict = None):
    """Run a P/T profile simulation for one well or source. conditions: optional {parameter: value} overrides."""
    task = _m().tasks.ptprofilesimulation
    kw = dict(producer=producer, system_variables=DEFAULT_SYSTEM_VARS, profile_variables=DEFAULT_PROFILE_VARS)
    if conditions:
        kw["parameters"] = conditions
    r = task.run(**kw)
    out = {"state": str(getattr(r, "state", "")), "messages": getattr(r, "messages", None),
           "system": getattr(r, "system", None), "node": getattr(r, "node", None),
           "profile": getattr(r, "profile", None)}
    if out["state"] != "Completed":
        # PIPESIM gives no message here; the usual cause is a missing boundary condition (e.g. OutletPressure)
        out["hint"] = ("Run did not complete. Check that the boundary conditions are fully specified, "
                       "e.g. pass conditions={'OutletPressure': ...}.")
        out["current_conditions"] = task.get_conditions(producer=producer)
    return out


@_safe
def save_model_as(path: str):
    """Save the modified model to a NEW file. Overwriting the original is refused."""
    if _state["path"] and os.path.abspath(path) == os.path.abspath(_state["path"]):
        raise PermissionError("Refusing to overwrite the original model. Pick a new filename.")
    _m().save(path)
    return {"saved": path}


@_safe
def close_model():
    """Close the open model without saving."""
    _m().close()
    _state.update(model=None, path=None)
    return {"closed": True}


TOOLS = [open_model, model_summary, get_values, set_value, run_network_simulation,
         get_pt_profile_conditions, run_pt_profile, save_model_as, close_model]
WRITE_TOOLS = {"set_value", "save_model_as"}  # the agent asks the human before running these

# JSON schemas for OpenAI-style tool calling (llama.cpp llama-server --jinja)
_S = {"type": "string"}
SCHEMAS = {
    "open_model": {"path": _S, "units": {"type": "string", "enum": ["METRIC", "FIELD", "SI"]}},
    "model_summary": {},
    "get_values": {"component_type": _S, "name": _S, "parameters": {"type": "array", "items": _S}},
    "set_value": {"component_type": _S, "name": _S, "parameter": _S, "value": {"type": ["number", "string", "boolean"]}},
    "run_network_simulation": {"system_variables": {"type": "array", "items": _S},
                               "profile_variables": {"type": "array", "items": _S},
                               "include_profiles": {"type": "boolean"}},
    "get_pt_profile_conditions": {"producer": _S},
    "run_pt_profile": {"producer": _S, "conditions": {"type": "object"}},
    "save_model_as": {"path": _S},
    "close_model": {},
}
REQUIRED = {"open_model": ["path"], "get_values": ["component_type", "parameters"],
            "set_value": ["component_type", "name", "parameter", "value"],
            "get_pt_profile_conditions": ["producer"], "run_pt_profile": ["producer"], "save_model_as": ["path"]}


def openai_tools():
    return [{"type": "function", "function": {
        "name": f.__name__, "description": f.__doc__,
        "parameters": {"type": "object", "properties": SCHEMAS[f.__name__], "required": REQUIRED.get(f.__name__, [])}}}
        for f in TOOLS]


def call(name, args):
    fn = {f.__name__: f for f in TOOLS}.get(name)
    if fn is None:
        return {"error": f"Unknown tool {name}"}
    return fn(**(args or {}))


if __name__ == "__main__":
    print(json.dumps(openai_tools(), indent=1))
