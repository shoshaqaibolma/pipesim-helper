"""TEST-ONLY fake PIPESIM: toy physics, used only to exercise the plumbing. Numbers mean nothing.

Mirrors behaviour seen on PIPESIM 2023.1 where it matters for the code under test:
- a P/T profile run fails silently without a boundary condition, and its profile is keyed by case name;
- the network task keeps its own boundary conditions: changing a Sink's "Pressure" component value alone
  does NOT change the network result (set_conditions does).
"""
import copy

DEFAULT_COMPS = {"Well": ["Well"], "Sink": ["Sink"], "Flowline": ["FL"]}  # what Model.open() "finds"


class _R:
    def __init__(s, node, profile=None, state="Completed"):
        s.node, s.system, s.profile, s.state = node, {}, profile or {}, state


class _PT:
    def __init__(s, m): s.m = m
    def get_conditions(s, producer=None): return {"OutletPressure": None}
    def run(s, producer=None, parameters=None, system_variables=None, profile_variables=None, **kw):
        bc = {"OUTLETPRESSURE", "LIQUIDFLOWRATE", "GASFLOWRATE"}
        if not bc & set(parameters or {}):
            return _R({}, {}, state="Failed")
        pr = s.m.v.get(("Completion", "Well:Completion", "ReservoirPressure"), 250)
        prof = {"Flowrate=1000 sm3/d": {"TotalDistance": [0, 1000, 2000], "Pressure": [pr - 50, pr - 120, 15],
                                        "Temperature": [90, 60, 30], "BranchEquipment": [None, "Choke", None]}}
        return _R({}, prof)


class _Net:
    def __init__(s, m): s.m, s.bc = m, None

    def _bcs(s):
        if s.bc is None:  # initialised from the component values the first time the task is used
            s.bc = {n: {"Pressure": s.m.v.get((t, n, "Pressure")), "Temperature": s.m.v.get((t, n, "Temperature"))}
                    for t in ("Sink", "Source") for n in s.m.comps.get(t, [])}
        return s.bc

    def get_conditions(s):
        return copy.deepcopy(s._bcs())

    def set_conditions(s, boundaries=None, **kw):
        if boundaries is None:
            raise TypeError("set_conditions() needs boundaries=")
        s._bcs()
        for k, v in boundaries.items():
            s.bc[k] = dict(v)

    def run(s, system_variables=None, profile_variables=None, **kw):
        m, bcs = s.m, s._bcs()
        sinks = m.comps.get("Sink", [])
        node = {k: {} for k in ("StockTankLiquidFlowrate", "StockTankOilFlowrate", "StockTankGasFlowrate", "Pressure")}
        totals = {k: [0.0, 0.0, 0.0] for k in sinks}
        for w in m.comps.get("Well", []):
            c = f"{w}:Completion"
            pr = m.v.get(("Completion", c, "ReservoirPressure"), 250)
            pi = m.v.get(("Completion", c, "LiquidPI"), 10)
            fl = m.v.get(("Completion", c, "FluidName"), "BO")
            wc = m.v.get(("BlackOilFluid", fl, "WaterCut"), 20)
            gor = m.v.get(("BlackOilFluid", fl, "GOR"), 100)
            dest = s._sink_of(w) or (sinks[0] if sinks else None)
            psink = (bcs.get(dest) or {}).get("Pressure")
            psink = 15 if psink is None else psink
            liq = max(0.0, pi * (pr - psink - 120 - 0.6 * wc))
            oil = liq * (1 - wc / 100)
            node["StockTankLiquidFlowrate"][w], node["StockTankOilFlowrate"][w] = liq, oil
            node["StockTankGasFlowrate"][w], node["Pressure"][w] = oil * gor, psink + 0.002 * liq
            if dest in totals:
                t = totals[dest]
                t[0] += liq; t[1] += oil; t[2] += oil * gor
        for k, (l, o, g) in totals.items():
            node["StockTankLiquidFlowrate"][k], node["StockTankOilFlowrate"][k] = l, o
            node["StockTankGasFlowrate"][k] = g
            node["Pressure"][k] = (bcs.get(k) or {}).get("Pressure")
        return _R(node)

    def _sink_of(s, start):
        seen, todo = set(), [start]
        while todo:
            n = todo.pop()
            if n in s.m.comps.get("Sink", []):
                return n
            if n not in seen:
                seen.add(n)
                todo += s.m.edges.get(n, [])
        return None


class _Tasks:
    def __init__(s, m):
        s.networksimulation, s.ptprofilesimulation = _Net(m), _PT(m)


class Model:
    def __init__(s, path, comps=None):
        s.path, s.v, s.edges = path, {}, {}
        s.comps = copy.deepcopy(comps) if comps is not None else {}
        s.tasks = _Tasks(s)

    @classmethod
    def new(c, path, units=None, overwrite=False):
        return c(path, {})

    @classmethod
    def open(c, path, units=None):
        return c(path, DEFAULT_COMPS)

    def add(s, t, name, context=None, parameters=None):
        full = f"{context}:{name}" if context else name
        if full in s.comps.get(t, []):
            raise ValueError(f"{t} {full} already exists")
        s.comps.setdefault(t, []).append(full)
        for k, val in (parameters or {}).items():
            s.v[(t, full, k)] = val

    def connect(s, a, b):
        (ta, na), = a.items(); (tb, nb), = b.items()
        for t, n in ((ta, na), (tb, nb)):
            if n not in s.comps.get(t, []):
                raise ValueError(f"connect: no {t} named {n}")
        s.edges.setdefault(na, []).append(nb)

    def find(s, **kw):
        (t, _), = kw.items()
        return list(s.comps.get(t, []))

    def get_value(s, **kw):
        p = kw.pop("parameter"); (t, n), = kw.items()
        return s.v.get((t, n, p), 0)

    def set_value(s, **kw):
        p, val = kw.pop("parameter"), kw.pop("value"); (t, n), = kw.items()
        s.v[(t, n, p)] = val

    def get_values(s, **kw): return {}
    def save(s, path=None): open(path or s.path, "w").write("fake")
    def close(s): pass
    def about(s): return "FAKE PIPESIM (tests only)"
