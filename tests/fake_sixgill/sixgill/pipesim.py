"""TEST-ONLY fake PIPESIM: a toy rate formula, used only to exercise the agent's plumbing."""
import json
from .definitions import ALL
class _R:
    def __init__(s, node, profile=None, state="Completed"): s.node, s.system, s.profile, s.state = node, {}, profile or {}, state
class _Tasks:
    def __init__(s, m): s.networksimulation = s.ptprofilesimulation = s; s.m = m
    def get_conditions(s, producer=None): return {"OutletPressure": None}
    def run(s, system_variables=None, producer=None, parameters=None, **kw):
        bc = {"OUTLETPRESSURE", "LIQUIDFLOWRATE", "GASFLOWRATE"}
        if producer is not None and not bc & set(parameters or {}):
            return _R({}, {}, state="Failed")  # 2023.1: silent failure without a boundary condition
        v = s.m.v; pr = v.get(("Completion","Well:Completion","ReservoirPressure"), 250)
        sep = v.get(("Sink","Sink","Pressure"), 15); wc = v.get(("BlackOilFluid","BO","WaterCut"), 20)
        pi = v.get(("Completion","Well:Completion","LiquidPI"), 10); gor = v.get(("BlackOilFluid","BO","GOR"), 100)
        liq = max(0.0, pi * (pr - sep - 120 - 0.6 * wc)); oil = liq * (1 - wc / 100)
        node = {"StockTankLiquidFlowrate": {"Well": liq}, "StockTankOilFlowrate": {"Well": oil},
                "StockTankGasFlowrate": {"Well": oil * gor}, "Pressure": {"Well": sep + 0.002 * liq}}
        prof = {"Flowrate=1000 sm3/d": {"TotalDistance": [0, 1000, 2000], "Pressure": [pr-50, pr-120, sep], "Temperature": [90, 60, 30]}}
        return _R(node, prof)
class Model:
    def __init__(s, path): s.path, s.v, s.comps = path, {}, {"Well": ["Well"], "Sink": ["Sink"], "Flowline": ["FL"]}; s.tasks = _Tasks(s)
    @classmethod
    def new(c, path, units=None, overwrite=False): return c(path)
    @classmethod
    def open(c, path, units=None): return c(path)
    def add(s, t, name, context=None, parameters=None):
        full = f"{context}:{name}" if context else name
        for k, val in (parameters or {}).items(): s.v[(t, full, k)] = val
    def connect(s, a, b): pass
    def find(s, **kw): (t, _), = kw.items(); return s.comps.get(t, [])
    def get_value(s, **kw):
        p = kw.pop("parameter"); (t, n), = kw.items(); return s.v.get((t, n, p), 0)
    def set_value(s, **kw):
        p, val = kw.pop("parameter"), kw.pop("value"); (t, n), = kw.items(); s.v[(t, n, p)] = val
    def get_values(s, **kw): return {}
    def save(s, path=None): open(path or s.path, "w").write("fake")
    def close(s): pass
    def about(s): return "FAKE PIPESIM (tests only)"
