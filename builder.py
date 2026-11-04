"""
Model templates: quick starting points that become a full project description (project.py) and are
built by netbuilder.py, so there is a single build path to verify on real PIPESIM.

Template "single_well": vertical oil well (PI IPR) -> flowline -> sink (separator).
"""
from sixgill_adapter import P

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

# Friendly sweep-variable names -> (component type, component name, (Parameters group, constant)).
SINGLE_WELL_ALIASES = {
    "reservoir_pressure": ("Completion", "Well:Completion", ("Completion", "RESERVOIRPRESSURE")),
    "productivity_index": ("Completion", "Well:Completion", ("IPRPIModel", "LIQUIDPI")),
    "water_cut":          ("BlackOilFluid", "BO", ("BlackOilFluid", "WATERCUT")),
    "gor":                ("BlackOilFluid", "BO", ("BlackOilFluid", "GOR")),
    "separator_pressure": ("Sink", "Sink", ("Sink", "PRESSURE")),
    "tubing_id":          ("Tubing", "Well:Tubing", ("Tubing", "INNERDIAMETER")),
    "flowline_id":        ("Flowline", "FL", ("Flowline", "INNERDIAMETER")),
    "flowline_length":    ("Flowline", "FL", ("Flowline", "HORIZONTALDISTANCE")),
}


def single_well_project(p):
    return {"name": "Single well", "units": "METRIC", "ambient_temperature": p["ambient_temperature"],
            "fluids": [{"name": "BO", "type": "black_oil", "api": p["oil_api"], "gor": p["gor"],
                        "water_cut": p["water_cut"], "gas_sg": p["gas_sg"]}],
            "wells": [{"name": "Well", "fluid": "BO", "reservoir_pressure": p["reservoir_pressure"],
                       "reservoir_temperature": p["reservoir_temperature"],
                       "ipr": {"model": "pi", "liquid_pi": p["productivity_index"]},
                       "depth": p["well_depth"], "tubing_id": p["tubing_id"]}],
            "sinks": [{"name": "Sink", "pressure": p["separator_pressure"]}],
            "flowlines": [{"name": "FL", "from": "Well", "to": "Sink", "length": p["flowline_length"],
                           "id": p["flowline_id"], "elevation_change": p["flowline_elevation"]}]}


TEMPLATES = {"single_well": {"fields": SINGLE_WELL_FIELDS, "aliases": SINGLE_WELL_ALIASES,
                             "to_project": single_well_project,
                             "description": "One vertical oil well, flowline, separator"}}


def alias_ref(template, alias):
    """Resolve a friendly alias to (component_type, name, sixgill parameter string)."""
    ctype, name, (group, const) = TEMPLATES[template]["aliases"][alias]
    return ctype, name, P(group, const)
