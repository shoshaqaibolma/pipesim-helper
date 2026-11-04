"""
Build a PIPESIM model (.pips) from a project description (see project.py).
Every sixgill name goes through sixgill_adapter.P/C/MC, so tests/test_api_names.py can check each one
against the API recorded on the real install (knowledge/api.json). Units: METRIC (bara, degC, m, mm, sm3/d).
"""
import project as prj
import sixgill_adapter as sa
from sixgill_adapter import P, C, MC

KIND_TYPE = {"wells": lambda: MC("WELL"), "sources": lambda: MC("SOURCE"), "junctions": lambda: MC("JUNCTION"),
             "sinks": lambda: MC("SINK"), "chokes": lambda: MC("CHOKE"), "flowlines": lambda: MC("FLOWLINE")}

IPR = {  # ipr.model -> (IPR model constant, {project field: sixgill parameter})
    "pi": (lambda: C("IPRModels", "IPRPIMODEL"), {"liquid_pi": lambda: P("IPRPIModel", "LIQUIDPI")}),
    "vogel": (lambda: C("IPRModels", "IPRVOGEL"), {"aof": lambda: P("IPRVogel", "ABSOLUTEOPENFLOWPOTENTIAL")}),
    "backpressure": (lambda: C("IPRModels", "IPRBACKPRESSURE"),
                     {"c": lambda: P("IPRBackPressure", "CONSTANTC"), "n": lambda: P("IPRBackPressure", "SLOPEN")}),
}
CASING_ID_MM = 159.4   # 7" 26 lb/ft production casing, used when the project gives none


def _fluid(m, f):
    if f.get("type", "black_oil") != "black_oil":
        raise NotImplementedError(f"Fluid {f['name']}: only black_oil fluids can be built so far")
    sa.add(m, MC("BLACKOILFLUID"), f["name"], parameters={
        P("BlackOilFluid", "API"): f["api"], P("BlackOilFluid", "GOR"): f["gor"],
        P("BlackOilFluid", "WATERCUT"): f["water_cut"], P("BlackOilFluid", "GASSPECIFICGRAVITY"): f["gas_sg"]})


def _well(m, w, ambient):
    sa.add(m, MC("WELL"), w["name"], parameters={P("Well", "AMBIENTTEMPERATURE"): ambient})
    # VERIFIED (2023.1): casing/tubing sections need TopMeasuredDepth AND Length (not BottomMeasuredDepth)
    sa.add(m, MC("CASING"), "Casing", context=w["name"], parameters={
        P("Casing", "TOPMEASUREDDEPTH"): 0.0, P("Casing", "LENGTH"): w["depth"],
        P("Casing", "INNERDIAMETER"): w.get("casing_id", CASING_ID_MM)})
    sa.add(m, MC("TUBING"), "Tubing", context=w["name"], parameters={
        P("Tubing", "TOPMEASUREDDEPTH"): 0.0, P("Tubing", "LENGTH"): w["depth"],
        P("Tubing", "INNERDIAMETER"): w["tubing_id"]})
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
    sa.add(m, MC("COMPLETION"), "Completion", context=w["name"], parameters=params)


def build(project, path, units="METRIC"):
    """Create the .pips at path. Returns (open model, build report). The caller closes the model."""
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
            params = {P("Source", "PRESSURE"): s["pressure"], P("Source", "TEMPERATURE"): s["temperature"],
                      P("Source", "ASSOCIATEDBLACKOILFLUID"): s["fluid"]}
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
        for fl in project.get("flowlines") or []:
            sa.add(m, MC("FLOWLINE"), fl["name"], parameters={
                P("Flowline", "HORIZONTALDISTANCE"): fl["length"], P("Flowline", "ELEVATIONDIFFERENCE"): fl["elevation_change"],
                P("Flowline", "INNERDIAMETER"): fl["id"], P("Flowline", "AMBIENTTEMPERATURE"): ambient})
        links = 0
        for c in project.get("chokes") or []:
            sa.connect(m, KIND_TYPE[kind_of[c["from"]]](), c["from"], MC("CHOKE"), c["name"])
            links += 1
        for fl in project.get("flowlines") or []:
            sa.connect(m, KIND_TYPE[kind_of[fl["from"]]](), fl["from"], MC("FLOWLINE"), fl["name"])
            sa.connect(m, MC("FLOWLINE"), fl["name"], KIND_TYPE[kind_of[fl["to"]]](), fl["to"])
            links += 2
        # the network task keeps its own boundary conditions: sync them with the components, then verify each one
        synced = sa.sync_boundaries(m)
        bcs = {}
        targets = [(k["name"], "Pressure", k["pressure"]) for k in project.get("sinks") or []]
        targets += [(s["name"], key, s[f]) for s in project.get("sources") or []
                    for key, f in (("Pressure", "pressure"), ("Temperature", "temperature"))]
        targets += [(f"{w['name']}:Completion", key, w[f]) for w in project.get("wells") or []
                    for key, f in (("Pressure", "reservoir_pressure"), ("Temperature", "reservoir_temperature"))]
        for node, key, value in targets:
            cur = ((sa.get_boundaries(m) or {}).get(node) or {}).get(key)
            bcs[f"{node}.{key}"] = ("ok" if cur is not None and sa._same(cur, value)
                                    else "set" if sa.set_boundary(m, node, key, value) else "NOT SET")
        issues = sa.validate(m)
        m.save()
    except Exception:
        try:
            m.close()
        finally:
            raise
    n = sum(len(project.get(k) or []) for k in prj.FIELDS)
    return m, {"file": path, "components": n, "connections": links, "boundaries_synced": synced,
               "boundary_conditions": bcs, "validation": issues}


def build_file(project, path):
    """Build and save a .pips the user can open in PIPESIM; closes the model."""
    m, report = build(project, path)
    m.close()
    return report
