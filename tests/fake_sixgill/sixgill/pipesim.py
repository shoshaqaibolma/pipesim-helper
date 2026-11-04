"""TEST-ONLY fake PIPESIM: toy physics, used only to exercise the plumbing. Numbers mean nothing.

Mirrors behaviour VERIFIED on PIPESIM 2023.1 where it matters for the code under test:
- in-well items are found as "<well>:<item>" but must be addressed as Well=<well>, <type>=<item>;
  Completion="W1:Completion" raises "No such context";
- the network task keeps its own boundary conditions (sinks, sources, and wells keyed by completion);
  set_value on a component does not change them; set_conditions(boundaries=...) and reset_conditions() do;
- results are node[variable] = {"Unit": ..., component: value};
- a P/T profile run fails silently without a boundary condition, and its profile is keyed by case name.
"""
import copy

DEFAULT_COMPS = {"Well": ["Well"], "Sink": ["Sink"], "Flowline": ["FL"]}  # what Model.open() "finds"
IN_WELL = {"Completion", "Tubing", "Casing", "Packer", "GasLiftInjection"}
UNITS = {"Pressure": "bara", "VolumeFlowrateLiquidStockTank": "sm3/d", "VolumeFlowrateOilStockTank": "sm3/d",
         "VolumeFlowrateGasStockTank": "mmsm3/d"}


class _R:
    def __init__(s, node, profile=None, state="Completed"):
        s.node, s.system, s.profile, s.state = node, {}, profile or {}, state


class _PT:
    def __init__(s, m): s.m = m
    def get_conditions(s, producer=None): return {"OutletPressure": None}
    def run(s, producer=None, parameters=None, system_variables=None, profile_variables=None, **kw):
        if not {"OUTLETPRESSURE", "LIQUIDFLOWRATE", "GASFLOWRATE", "OutletPressure"} & set(parameters or {}):
            return _R({}, {}, state="Failed")
        pr = s.m.v.get(("Completion", "Well:Completion", "ReservoirPressure"), 250)
        prof = {"Flowrate=1000 sm3/d": {"TotalDistance": [0, 1000, 2000], "Pressure": [pr - 50, pr - 120, 15],
                                        "Temperature": [90, 60, 30], "BranchEquipment": [None, "Choke", None]}}
        return _R({}, prof)


class _Net:
    def __init__(s, m): s.m, s.bc = m, None

    def _bcs(s):
        if s.bc is None:  # synchronised from the component values
            v, s.bc = s.m.v, {}
            for t in ("Sink", "Source"):
                for n in s.m.comps.get(t, []):
                    s.bc[n] = {"BoundaryNodeType": t, "Pressure": v.get((t, n, "Pressure")),
                               "Temperature": v.get((t, n, "Temperature")),
                               "FlowRateType": v.get((t, n, "SelectedRateType"), "LiquidFlowRate"),
                               "LiquidFlowRate": v.get((t, n, "LiquidFlowRate")), "GasFlowRate": v.get((t, n, "GasFlowRate"))}
            for c in s.m.comps.get("Completion", []):
                s.bc[c] = {"BoundaryNodeType": "Completion", "Pressure": v.get(("Completion", c, "ReservoirPressure")),
                           "Temperature": v.get(("Completion", c, "ReservoirTemperature"))}
        return s.bc

    def get_conditions(s, use_surface_condition=None, study=None):
        return copy.deepcopy(s._bcs())

    def set_conditions(s, boundaries=None, constraints=None, use_surface_condition=None, study=None):
        s._bcs()
        for k, val in (boundaries or {}).items():
            if k not in s.bc:
                raise KeyError(f"no boundary node {k}")
            s.bc[k] = dict(val)

    def reset_conditions(s, study=None):
        s.bc = None
        return True

    def run(s, system_variables=None, profile_variables=None, **kw):
        m, bcs = s.m, s._bcs()
        sinks = m.comps.get("Sink", [])
        node = {k: {"Unit": u} for k, u in UNITS.items()}
        totals = {k: [0.0, 0.0, 0.0] for k in sinks}
        for src in m.comps.get("Source", []):
            b, dest = bcs.get(src) or {}, s._sink_of(src) or (sinks[0] if sinks else None)
            psink = (bcs.get(dest) or {}).get("Pressure") or 15
            liq = b.get("LiquidFlowRate") or 0.0 if b.get("FlowRateType") == "LiquidFlowRate" else 0.0
            gas = b.get("GasFlowRate") or 0.0 if b.get("FlowRateType") == "GasFlowRate" else 0.0
            if b.get("Pressure") is not None:
                liq = max(0.0, 10 * (b["Pressure"] - psink))
            node["VolumeFlowrateLiquidStockTank"][src], node["VolumeFlowrateGasStockTank"][src] = liq, gas
            node["Pressure"][src] = b.get("Pressure") if b.get("Pressure") is not None else psink + 0.01 * liq + 5 * gas
            if dest in totals:
                totals[dest][0] += liq; totals[dest][2] += gas
        for w in m.comps.get("Well", []):
            c = next((x for x in m.comps.get("Completion", []) if x.startswith(f"{w}:")), f"{w}:Completion")
            pr = (bcs.get(c) or {}).get("Pressure")
            pr = 250 if pr is None else pr
            pi = m.v.get(("Completion", c, "LiquidPI"), 10)
            fl = m.v.get(("Completion", c, "AssociatedBlackOilFluid"), "BO")
            wc = m.v.get(("BlackOilFluid", fl, "WaterCut"), 20)
            gor = m.v.get(("BlackOilFluid", fl, "GOR"), 100)
            dest = s._sink_of(w) or (sinks[0] if sinks else None)
            psink = (bcs.get(dest) or {}).get("Pressure")
            psink = 15 if psink is None else psink
            liq = max(0.0, pi * (pr - psink - 120 - 0.6 * wc))
            oil, gas = liq * (1 - wc / 100), liq * (1 - wc / 100) * gor / 1e6
            for k, val in (("VolumeFlowrateLiquidStockTank", liq), ("VolumeFlowrateOilStockTank", oil),
                           ("VolumeFlowrateGasStockTank", gas), ("Pressure", psink + 0.002 * liq)):
                node[k][w] = val
            if dest in totals:
                t = totals[dest]
                t[0] += liq; t[1] += oil; t[2] += gas
        for k, (l, o, g) in totals.items():
            node["VolumeFlowrateLiquidStockTank"][k], node["VolumeFlowrateOilStockTank"][k] = l, o
            node["VolumeFlowrateGasStockTank"][k] = g
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

    def connect(s, source, destination, source_port=None):
        (ta, na), = source.items(); (tb, nb), = destination.items()
        for t, n in ((ta, na), (tb, nb)):
            if n not in s.comps.get(t, []):
                raise ValueError(f"connect: no {t} named {n}")
        s.edges.setdefault(na, []).append(nb)

    def _resolve(s, kw):
        if "context" in kw:
            return kw.pop("component"), kw.pop("context")
        well = kw.pop("Well", None)
        (t, n), = kw.items()
        if well is not None:
            return t, f"{well}:{n}"
        if t in IN_WELL and ":" in n:
            raise LookupError(f"No such context: ModelContext({{'{t}': '{n}'}})")
        return t, n

    def find(s, **kw):
        (t, _), = kw.items()
        return list(s.comps.get(t, []))

    def get_value(s, parameter=None, **kw):
        t, n = s._resolve(kw)
        return s.v.get((t, n, parameter), 0)

    def set_value(s, parameter=None, value=None, **kw):
        t, n = s._resolve(kw)
        s.v[(t, n, parameter)] = value

    def get_values(s, **kw): return {}
    def describe(s, parameter=None, **kw):
        return type("D", (), {"units": {"ConstantC": "mmsm3/d/bar2n"}.get(parameter, "fake-unit")})()
    def validate(s): return []
    def save(s, path=None): open(path or s.path, "w").write("fake")
    def close(s): pass
    def about(s): return "FAKE PIPESIM (tests only)"
