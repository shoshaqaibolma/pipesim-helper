"""
Short worked recipes for the local model. A small model does better with one or two concrete examples that match
the request than with a long manual, so only the recipes whose keywords appear in the user's message are added
to that message (select()). Each recipe shows the exact calls; names and numbers in it are placeholders.
"""
import re

GUIDANCE = "\n\n[Guidance for the assistant - matching recipes; use the user's own names and numbers]\n"

STUDY_TYPES = """CHOOSING THE STUDY TYPE:
- one input over a range ("how does X change", "which diameter", "from A to B") -> sweep (ONE variable)
- two or three inputs combined ("compare all combinations", "A or B and C or D") -> grid (2-3 variables)
- which uncertain input matters most ("rank", "most sensitive", "uncertainty") -> tornado (low/high per input)
- best split / best setting under a limit ("share", "allocate", "split", "maximize ... with only X") -> optimize
- operating point of one well, inflow vs outflow ("nodal") -> nodal
- pressure/temperature along one well or line ("profile", "holdup along") -> pt_profile
- just run it once -> single_run"""

RECIPES = [
    {"name": "one well to a separator",
     "keys": r"\bone (oil |gas )?well\b|\bsingle well\b|\bwell W1\b",
     "text": """RECIPE one well -> separator (no manifold needed):
update_project {"name":"Well study","fluids":[{"name":"OilA","type":"black_oil","api":28,"gor":60,"water_cut":10,"gas_sg":0.75}],
 "wells":[{"name":"P-1","fluid":"OilA","reservoir_pressure":180,"depth":1900,"ipr":{"model":"pi","liquid_pi":4}}],
 "sinks":[{"name":"Sep","pressure":20}],
 "flowlines":[{"name":"FL-P1","from":"P-1","to":"Sep","length":1200,"id":80,"elevation_change":0}]}"""},
    {"name": "wells into a manifold and a trunkline",
     "keys": r"manifold|trunk ?line|gathering|\b(two|three|four|2|3|4) (oil |gas )?wells\b",
     "text": """RECIPE N wells -> manifold -> trunkline -> separator. Wells A and B here; a sink accepts ONE inlet, so every well line ends at the
manifold and only the trunkline reaches the sink. Exactly one junction (the manifold); no extra junctions or 0 m lines:
"junctions":[{"name":"Hub"}], "sinks":[{"name":"Plant","pressure":25}],
"flowlines":[{"name":"FL-A","from":"A","to":"Hub","length":700,"id":75,"elevation_change":0},
             {"name":"FL-B","from":"B","to":"Hub","length":2100,"id":75,"elevation_change":0},
             {"name":"Export","from":"Hub","to":"Plant","length":9000,"id":200,"elevation_change":-20}]"""},
    {"name": "pipeline from a fixed-rate source",
     "keys": r"pipeline|export line|\bsource\b|plant|terminal|line siz|diameter",
     "text": """RECIPE pipeline: a source with a fixed rate, ONE flowline straight to the delivery sink (no junctions):
"fluids":[{"name":"Gas1","type":"gas","gas_sg":0.68,"ogr":5,"wgr":1,"api":55}],
"sources":[{"name":"Inlet","fluid":"Gas1","temperature":30,"gas_rate":1.2}],
"sinks":[{"name":"Outlet","pressure":45}],
"flowlines":[{"name":"Line","from":"Inlet","to":"Outlet","length":12000,"id":150,"elevation_change":0}]
Then a diameter question is a SWEEP: {"type":"sweep","variables":[{"component_type":"Flowline","name":"Line",
 "parameter":"InnerDiameter","values":[100,150,200]}]}; the inlet pressure is the result "<source> pressure"
 (here "Inlet pressure"); compare it with the user's pressure limit."""},
    {"name": "gas lift",
     "keys": r"gas[- ]?lift|lift gas",
     "text": """RECIPE gas lift: add "gas_lift":{"depth":1500,"rate":0.03} to the well (rate in mmsm3/d). Study variable:
{"component_type":"GasLiftInjection","name":"P-1:P-1_GL","parameter":"GasRate","values":[0,0.02,0.04,0.06]}.
Sharing limited lift gas between wells -> {"type":"optimize","max_total":0.08,"variables":[one GasRate variable per well,
each with the rates to try]}; the answer is summary.optimum.best."""},
    {"name": "separator, compressor and pump facility",
     "keys": r"compressor|pump|separator.*(gas|liquid) (line|outlet)|facility",
     "text": """RECIPE facility: "separators":[{"name":"SEP1","efficiency":99.9}], "compressors":[{"name":"C1","efficiency":70,"power":1000}],
"pumps":[{"name":"P1","efficiency":70,"pressure_rise":10}]; flowlines leaving SEP1 carry "port":"gas" or "port":"liquid";
gas: SEP1 -(GL-1, port gas)-> C1 -(GL-2)-> GasSales sink; liquid: SEP1 -(LL-1, port liquid)-> P1 -(LL-2)-> Oil sink."""},
    {"name": "nodal analysis",
     "keys": r"nodal|operating point|inflow.*outflow|ipr.*vlp",
     "text": """RECIPE nodal analysis of one well: analysis {"type":"nodal","producer":"P-1","outlet_pressure":25}
(outlet_pressure = the wellhead pressure the user gives, bara). The answer is the operating point (liquid rate and
bottomhole pressure). A follow-up study on the same well: update_spec with ONLY the new "analysis"; the project stays."""},
    {"name": "uncertainty ranking",
     "keys": r"uncertain|unsure|rank|most (sensitive|important)|tornado|matters most",
     "text": """RECIPE uncertainty ranking -> tornado with low/high per input, e.g.
{"type":"tornado","variables":[
 {"component_type":"Completion","name":"P-1:P-1_Comp","parameter":"ReservoirPressure","low":160,"high":195},
 {"component_type":"BlackOilFluid","name":"OilA","parameter":"GOR","low":40,"high":90}]}
The ranking is in summary[<result>].ranking - quote it, do not compute it."""},
    {"name": "compare combinations",
     "keys": r"combination|which gives more|compare .* (or|and)|debottleneck",
     "text": """RECIPE compare options -> grid of 2-3 variables, e.g. trunkline size and separator pressure:
{"type":"grid","variables":[{"component_type":"Flowline","name":"Export","parameter":"InnerDiameter","values":[200,250]},
 {"component_type":"Sink","name":"Plant","parameter":"Pressure","values":[25,18]}]}; summary.highest names the best case."""},
]


def select(text, limit=2):
    """Recipes whose keywords appear in the user's message, most specific first (at most `limit`)."""
    t = text.lower()
    hits = [r for r in RECIPES if re.search(r["keys"], t)]
    return hits[:limit]


def augment(text, limit=2):
    """The user's message plus the matching recipes (marked as guidance, not as the user's words)."""
    hits = select(text, limit)
    if not hits:
        return text
    return text + GUIDANCE + "\n\n".join(r["text"] for r in hits)
