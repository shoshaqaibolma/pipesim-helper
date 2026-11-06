"""
Build a PIPESIM model (.pips) from a project description (see project.py).
Every sixgill name goes through sixgill_adapter.P/C/MC, so tests/test_api_names.py can check each one
against the API recorded on the real install (knowledge/api.json). Units: METRIC (bara, degC, m, mm, sm3/d).
"""
import os, zipfile
import project as prj
import sixgill_adapter as sa
from sixgill_adapter import P, C, MC

KIND_TYPE = {"wells": lambda: MC("WELL"), "sources": lambda: MC("SOURCE"), "junctions": lambda: MC("JUNCTION"),
             "sinks": lambda: MC("SINK"), "chokes": lambda: MC("CHOKE"), "flowlines": lambda: MC("FLOWLINE"),
             "separators": lambda: MC("TWOPHASESEPARATOR"), "pumps": lambda: MC("PUMP"),
             "compressors": lambda: MC("COMPRESSOR")}
EQUIP = {"pumps": ("Pump", "PUMP"), "compressors": ("Compressor", "COMPRESSOR")}
EQUIP_PARAM = {"pressure": "PRESSURE", "pressure_rise": "PRESSUREDIFFERENTIAL", "pressure_ratio": "PRESSURERATIO",
               "power": "POWER"}

IPR = {  # ipr.model -> (IPR model constant, {project field: sixgill parameter})
    "pi": (lambda: C("IPRModels", "IPRPIMODEL"), {"liquid_pi": lambda: P("IPRPIModel", "LIQUIDPI")}),
    "vogel": (lambda: C("IPRModels", "IPRVOGEL"), {"aof": lambda: P("IPRVogel", "ABSOLUTEOPENFLOWPOTENTIAL")}),
    "backpressure": (lambda: C("IPRModels", "IPRBACKPRESSURE"),
                     {"c": lambda: P("IPRBackPressure", "CONSTANTC"), "n": lambda: P("IPRBackPressure", "SLOPEN")}),
}
CASING_ID_MM = 159.4   # 7" 26 lb/ft production casing, used when the project gives none
CASING_WALL_MM = 9.19  # VERIFIED: validate() requires a wall thickness on casing and tubing
TUBING_WALL_MM = 6.45  # 3-1/2" 9.3 lb/ft tubing


def _fluid(m, f):
    if f.get("type", "black_oil") == "gas":   # gas/condensate: black-oil model driven by OGR and WGR (as in TF_M2B)
        params = {P("BlackOilFluid", "GASSPECIFICGRAVITY"): f["gas_sg"], P("BlackOilFluid", "API"): f["api"],
                  P("BlackOilFluid", "USEGASRATIO"): C("GasRatioOption", "OGR"), P("BlackOilFluid", "OGR"): f["ogr"],
                  P("BlackOilFluid", "USEWATERRATIO"): C("WaterRatioOption", "WGR"), P("BlackOilFluid", "WGR"): f["wgr"]}
    elif f.get("water_cut", 0) >= 100:   # VERIFIED (job 17): "GOR cannot be chosen when watercut is 100%"
        params = {P("BlackOilFluid", "API"): f["api"],
                  P("BlackOilFluid", "USEGASRATIO"): C("GasRatioOption", "GLR"), P("BlackOilFluid", "GLR"): 0.0,
                  P("BlackOilFluid", "USEWATERRATIO"): C("WaterRatioOption", "WATERCUT"),
                  P("BlackOilFluid", "WATERCUT"): 100.0, P("BlackOilFluid", "GASSPECIFICGRAVITY"): f["gas_sg"]}
    else:
        params = {P("BlackOilFluid", "API"): f["api"],
                  P("BlackOilFluid", "USEGASRATIO"): C("GasRatioOption", "GOR"), P("BlackOilFluid", "GOR"): f["gor"],
                  P("BlackOilFluid", "USEWATERRATIO"): C("WaterRatioOption", "WATERCUT"),
                  P("BlackOilFluid", "WATERCUT"): f["water_cut"], P("BlackOilFluid", "GASSPECIFICGRAVITY"): f["gas_sg"]}
    sa.add(m, MC("BLACKOILFLUID"), f["name"], parameters=params)


def _well(m, w, ambient):
    sa.add(m, MC("WELL"), w["name"], parameters={P("Well", "AMBIENTTEMPERATURE"): ambient})
    # VERIFIED (2023.1): casing/tubing sections need TopMeasuredDepth AND Length (not BottomMeasuredDepth)
    sa.add(m, MC("CASING"), "Casing", context=w["name"], parameters={
        P("Casing", "TOPMEASUREDDEPTH"): 0.0, P("Casing", "LENGTH"): w["depth"],
        P("Casing", "INNERDIAMETER"): w.get("casing_id", CASING_ID_MM),
        P("Casing", "WALLTHICKNESS"): w.get("casing_wall", CASING_WALL_MM)})
    sa.add(m, MC("TUBING"), "Tubing", context=w["name"], parameters={
        P("Tubing", "TOPMEASUREDDEPTH"): 0.0, P("Tubing", "LENGTH"): w["depth"],
        P("Tubing", "INNERDIAMETER"): w["tubing_id"], P("Tubing", "WALLTHICKNESS"): w.get("tubing_wall", TUBING_WALL_MM)})
    ipr_const, fields = IPR[w["ipr"]["model"]]
    params = {P("Completion", "TOPMEASUREDDEPTH"): w["depth"],
              P("Completion", "FLUIDENTRYTYPE"): C("CompletionFluidEntry", "SINGLEPOINT"),
              P("Completion", "GEOMETRYPROFILETYPE"): C("Orientation", "VERTICAL"),
              P("Completion", "IPRMODEL"): ipr_const(),
              P("Completion", "RESERVOIRPRESSURE"): w["reservoir_pressure"],
              P("Completion", "RESERVOIRTEMPERATURE"): w["reservoir_temperature"],
              P("Completion", "ASSOCIATEDBLACKOILFLUID"): w["fluid"]}
    for field, param in fields.items():
        params[param()] = w["ipr"][field]
    sa.add(m, MC("COMPLETION"), prj.completion_name(w["name"]), context=w["name"], parameters=params)
    if w.get("gas_lift"):  # as in TF_M3B / Nodal_example: injection-gas-rate gas lift at a given depth
        sa.add(m, MC("GASLIFTINJECTION"), prj.gas_lift_name(w["name"]), context=w["name"], parameters={
            P("GasLiftInjection", "TOPMEASUREDDEPTH"): w["gas_lift"]["depth"],
            P("GasLiftInjection", "GASLIFTTYPE"): C("GasLiftType", "INJECTIONGASRATE"),
            P("GasLiftInjection", "GASRATE"): w["gas_lift"]["rate"]})


def build(project, path, units="METRIC", thermal=None):
    """Create the .pips at path. Returns (open model, build report). The caller closes the model.
    thermal (default on, PIPESIM_THERMAL_DEFAULTS=0 turns it off): after saving, write PIPESIM's standard black-oil
    thermal data and any flowline "u_value" into the file (the toolkit cannot set them, see pips_writer.py)."""
    if thermal is None:
        thermal = os.getenv("PIPESIM_THERMAL_DEFAULTS", "1") != "0"
    chk = prj.check_project(project)
    if not chk["ready"]:
        raise ValueError(f"Project is not complete: missing {[x['field'] for x in chk['missing']]}, "
                         f"errors {chk['errors']}")
    if units != "METRIC":
        raise ValueError("Projects are described in METRIC units; build them with units='METRIC'.")
    ambient = project.get("ambient_temperature", 15.0)
    m = sa.new_model(path, units)
    kind_of = {}
    try:
        for f in project.get("fluids") or []:
            _fluid(m, f)
        for w in project.get("wells") or []:
            _well(m, w, ambient)
            kind_of[w["name"]] = "wells"
        for s in project.get("sources") or []:
            params = {P("Source", "TEMPERATURE"): s["temperature"], P("Source", "ASSOCIATEDBLACKOILFLUID"): s["fluid"]}
            if "pressure" in s:
                params[P("Source", "PRESSURE")] = s["pressure"]
            elif "liquid_rate" in s:
                params.update({P("Source", "SELECTEDRATETYPE"): C("FlowRateType", "LIQUIDFLOWRATE"),
                               P("Source", "LIQUIDFLOWRATE"): s["liquid_rate"]})
            else:
                params.update({P("Source", "SELECTEDRATETYPE"): C("FlowRateType", "GASFLOWRATE"),
                               P("Source", "GASFLOWRATE"): s["gas_rate"]})
            sa.add(m, MC("SOURCE"), s["name"], parameters=params)
            kind_of[s["name"]] = "sources"
        for j in project.get("junctions") or []:
            sa.add(m, MC("JUNCTION"), j["name"])
            kind_of[j["name"]] = "junctions"
        for k in project.get("sinks") or []:
            sa.add(m, MC("SINK"), k["name"], parameters={P("Sink", "PRESSURE"): k["pressure"]})
            kind_of[k["name"]] = "sinks"
        for c in project.get("chokes") or []:
            sa.add(m, MC("CHOKE"), c["name"], parameters={P("Choke", "BEANSIZE"): c["bean_size"]})
            kind_of[c["name"]] = "chokes"
        for sep in project.get("separators") or []:
            ports = {f.get("port") for f in project.get("flowlines") or [] if f.get("from") == sep["name"]}
            prod, disc = ("liquid", "gas") if ports == {"liquid"} else ("gas", "liquid")  # as in CSN_301
            sa.add(m, MC("TWOPHASESEPARATOR"), sep["name"], parameters={
                P("TwoPhaseSeparator", "EFFICIENCY"): sep["efficiency"],
                P("TwoPhaseSeparator", "PRODUCTIONSTREAM"): C("SeparatorProductFluid", prod.upper()),
                P("TwoPhaseSeparator", "DISCARDEDSTREAM"): C("SeparatorProductFluid", disc.upper())})
            kind_of[sep["name"]] = "separators"
        for kind, (group, const) in EQUIP.items():   # pumps and compressors: efficiency + one specification
            for e in project.get(kind) or []:
                params = {P(group, "EFFICIENCY"): e["efficiency"]}
                for f, pconst in EQUIP_PARAM.items():
                    if f in e:
                        params[P(group, pconst)] = e[f]
                sa.add(m, MC(const), e["name"], parameters=params)
                kind_of[e["name"]] = kind
        for fl in project.get("flowlines") or []:
            sa.add(m, MC("FLOWLINE"), fl["name"], parameters={
                P("Flowline", "HORIZONTALDISTANCE"): fl["length"], P("Flowline", "ELEVATIONDIFFERENCE"): fl["elevation_change"],
                P("Flowline", "INNERDIAMETER"): fl["id"], P("Flowline", "AMBIENTTEMPERATURE"): ambient})
        links = 0
        for kind in prj.INLINE:   # equipment installed right after its "from" node (no flowline in between)
            for c in project.get(kind) or []:
                if c.get("from"):
                    sa.connect(m, KIND_TYPE[kind_of[c["from"]]](), c["from"], KIND_TYPE[kind](), c["name"])
                    links += 1
        for fl in project.get("flowlines") or []:
            sa.connect(m, KIND_TYPE[kind_of[fl["from"]]](), fl["from"], MC("FLOWLINE"), fl["name"],
                       source_port=fl.get("port") if kind_of[fl["from"]] == "separators" else None)
            sa.connect(m, MC("FLOWLINE"), fl["name"], KIND_TYPE[kind_of[fl["to"]]](), fl["to"])
            links += 2
        # the network task keeps its own boundary conditions: sync them with the components, then verify each node
        synced = sa.sync_boundaries(m)
        wanted = {k["name"]: {"Pressure": k["pressure"]} for k in project.get("sinks") or []}
        for s in project.get("sources") or []:
            if "pressure" in s:
                wanted[s["name"]] = {"Pressure": s["pressure"], "Temperature": s["temperature"]}
            else:
                kind = "LiquidFlowRate" if "liquid_rate" in s else "GasFlowRate"
                wanted[s["name"]] = {"FlowRateType": kind, kind: s.get("liquid_rate", s.get("gas_rate")),
                                     "Pressure": None, "Temperature": s["temperature"]}
        for w in project.get("wells") or []:
            wanted[f"{w['name']}:{prj.completion_name(w['name'])}"] = {"Pressure": w["reservoir_pressure"],
                                                                      "Temperature": w["reservoir_temperature"]}
        bcs = {}
        for node, values in wanted.items():
            cur = (sa.get_boundaries(m) or {}).get(node) or {}
            bcs[node] = ("ok" if cur and all(sa._same(cur.get(k), v) for k, v in values.items())
                         else "set" if sa.set_boundaries(m, node, values) else "NOT SET")
        issues = sa.validate(m)
        m.save()
    except Exception:
        try:
            m.close()
        finally:
            raise
    thermal_report = None
    if thermal and zipfile.is_zipfile(path):
        import pips_writer
        m.close()
        fluids = [f["name"] for f in project.get("fluids") or [] if f.get("type", "black_oil") in ("black_oil", "gas")]
        pipes = {f["name"]: {"u_value": f["u_value"]} for f in project.get("flowlines") or [] if f.get("u_value") is not None}
        try:
            thermal_report = pips_writer.apply(path, fluids=fluids, pipes=pipes)
        finally:
            m = sa.open_model(path)
        for node, values in wanted.items():   # boundary conditions must survive the reopen
            cur = (sa.get_boundaries(m) or {}).get(node) or {}
            if not (cur and all(sa._same(cur.get(k), v) for k, v in values.items())):
                bcs[node] = "set after reopen" if sa.set_boundaries(m, node, values) else "NOT SET"
    n = sum(len(project.get(k) or []) for k in prj.FIELDS)
    return m, {"file": path, "components": n, "connections": links, "boundaries_synced": synced,
               "boundary_conditions": bcs, "validation": issues, "thermal": thermal_report}


def build_file(project, path):
    """Build and save a .pips the user can open in PIPESIM; closes the model."""
    m, report = build(project, path)
    m.close()
    return report
