"""
Build a new PIPESIM model from a template, so a study can start from a plain-language description.

Template "single_well": vertical oil well (PI IPR) -> tubing -> wellhead -> flowline -> sink (separator).
VERIFY on first use: the sixgill Parameters/Constants names below follow the Python Toolkit docs, but they
differ slightly between PIPESIM versions. A missing name raises a clear error that says which one to fix.
"""
from sixgill.pipesim import Model
from sixgill import definitions as d

# Field -> (question, unit, suggested default in METRIC). Missing fields are asked of the user.
SINGLE_WELL_FIELDS = {
    "reservoir_pressure":    ("Reservoir (static) pressure?", "bara", 250.0),
    "reservoir_temperature": ("Reservoir temperature?", "degC", 90.0),
    "productivity_index":    ("Liquid productivity index?", "sm3/d/bar", 10.0),
    "well_depth":            ("Well depth to mid-perforation (vertical)?", "m", 2500.0),
    "tubing_id":             ("Tubing inner diameter?", "mm", 76.0),
    "oil_api":               ("Oil gravity?", "API", 35.0),
    "gor":                   ("Producing gas-oil ratio?", "sm3/sm3", 100.0),
    "water_cut":             ("Water cut?", "%", 20.0),
    "gas_sg":                ("Gas specific gravity?", "air=1", 0.7),
    "flowline_length":       ("Flowline length from wellhead to separator?", "m", 3000.0),
    "flowline_id":           ("Flowline inner diameter?", "mm", 150.0),
    "flowline_elevation":    ("Elevation change along the flowline (+ uphill)?", "m", 0.0),
    "separator_pressure":    ("Separator / arrival pressure?", "bara", 15.0),
    "ambient_temperature":   ("Ambient / surface temperature?", "degC", 15.0),
}

# Friendly names the LLM and the user can use for sweep variables on template models.
SINGLE_WELL_ALIASES = {
    "reservoir_pressure": ("Completion", "Well:Completion", "Completion.RESERVOIRPRESSURE"),
    "productivity_index": ("Completion", "Well:Completion", "IPRPIModel.LIQUIDPI"),
    "water_cut":          ("BlackOilFluid", "BO", "BlackOilFluid.WATERCUT"),
    "gor":                ("BlackOilFluid", "BO", "BlackOilFluid.GOR"),
    "separator_pressure": ("Sink", "Sink", "Sink.PRESSURE"),
    "tubing_id":          ("Tubing", "Well:Tubing", "Tubing.INNERDIAMETER"),
    "flowline_id":        ("Flowline", "FL", "Flowline.INNERDIAMETER"),
    "flowline_length":    ("Flowline", "FL", "Flowline.HORIZONTALDISTANCE"),
}


def alias_ref(template, alias):
    """Resolve a friendly alias to (component_type, name, sixgill parameter string)."""
    ctype, name, const = TEMPLATES[template]["aliases"][alias]
    return ctype, name, _p(*const.split("."))


TEMPLATES = {"single_well": {"fields": SINGLE_WELL_FIELDS, "aliases": SINGLE_WELL_ALIASES,
                             "producers": ["Well"], "description": "One vertical oil well, flowline, separator"}}


def _p(group, name):
    try:
        return getattr(getattr(d.Parameters, group), name)
    except AttributeError:
        raise AttributeError(f"sixgill has no Parameters.{group}.{name} in this PIPESIM version. Fix builder.py")


def _c(group, name):
    try:
        return getattr(getattr(d.Constants, group), name)
    except AttributeError:
        raise AttributeError(f"sixgill has no Constants.{group}.{name} in this PIPESIM version. Fix builder.py")


def build_single_well(path, p, units="METRIC"):
    m = Model.new(path, units=getattr(d.Units, units), overwrite=True)
    mc = d.ModelComponents
    m.add(mc.BLACKOILFLUID, "BO", parameters={
        _p("BlackOilFluid", "API"): p["oil_api"], _p("BlackOilFluid", "GOR"): p["gor"],
        _p("BlackOilFluid", "WATERCUT"): p["water_cut"], _p("BlackOilFluid", "GASSPECIFICGRAVITY"): p["gas_sg"]})
    m.add(mc.WELL, "Well", parameters={_p("Well", "AMBIENTTEMPERATURE"): p["ambient_temperature"]})
    m.add(mc.TUBING, "Tubing", context="Well", parameters={
        _p("Tubing", "TOPMEASUREDDEPTH"): 0.0, _p("Tubing", "LENGTH"): p["well_depth"],
        _p("Tubing", "INNERDIAMETER"): p["tubing_id"]})
    m.add(mc.COMPLETION, "Completion", context="Well", parameters={
        _p("Completion", "TOPMEASUREDDEPTH"): p["well_depth"],
        _p("Completion", "FLUIDENTRYTYPE"): _c("CompletionFluidEntry", "SINGLEPOINT"),
        _p("Completion", "IPRMODEL"): _c("IPRModels", "IPRPIMODEL"),
        _p("Completion", "RESERVOIRPRESSURE"): p["reservoir_pressure"],
        _p("Completion", "RESERVOIRTEMPERATURE"): p["reservoir_temperature"],
        _p("Completion", "FLUIDNAME"): "BO",
        _p("IPRPIModel", "LIQUIDPI"): p["productivity_index"]})
    m.add(mc.FLOWLINE, "FL", parameters={
        _p("Flowline", "HORIZONTALDISTANCE"): p["flowline_length"],
        _p("Flowline", "ELEVATIONDIFFERENCE"): p["flowline_elevation"],
        _p("Flowline", "INNERDIAMETER"): p["flowline_id"],
        _p("Flowline", "AMBIENTTEMPERATURE"): p["ambient_temperature"]})
    m.add(mc.SINK, "Sink", parameters={_p("Sink", "PRESSURE"): p["separator_pressure"]})
    m.connect({mc.WELL: "Well"}, {mc.FLOWLINE: "FL"})
    m.connect({mc.FLOWLINE: "FL"}, {mc.SINK: "Sink"})
    m.save()
    return m


BUILDERS = {"single_well": build_single_well}
