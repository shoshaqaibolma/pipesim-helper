"""Network builder + adapter tests with the fake sixgill (no PIPESIM needed). Numbers mean nothing."""
import os, sys, tempfile
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [os.path.join(HERE, "fake_sixgill"), os.path.dirname(HERE)]
import netbuilder, executor, study, sixgill_adapter as sa
import project as prj

FIELD = {"name": "Field A", "ambient_temperature": 12,
         "fluids": [{"name": "BO", "type": "black_oil", "api": 35, "gor": 120, "water_cut": 10, "gas_sg": 0.7}],
         "wells": [{"name": w, "fluid": "BO", "reservoir_pressure": p, "reservoir_temperature": 90,
                    "ipr": {"model": "pi", "liquid_pi": pi}, "depth": 2500, "tubing_id": 76}
                   for w, p, pi in (("W1", 260, 8), ("W2", 240, 12))],
         "chokes": [{"name": "CK1", "from": "W1", "bean_size": 32}],
         "junctions": [{"name": "J1"}], "sinks": [{"name": "Sep", "pressure": 15}],
         "flowlines": [{"name": "FL1", "from": "CK1", "to": "J1", "length": 1500, "id": 100, "elevation_change": 0},
                       {"name": "FL2", "from": "W2", "to": "J1", "length": 900, "id": 100, "elevation_change": 5},
                       {"name": "FL3", "from": "J1", "to": "Sep", "length": 4000, "id": 200, "elevation_change": 0}]}
assert prj.check_project(FIELD)["ready"], prj.check_project(FIELD)

# 1. build: every component and connection is created; the sink boundary condition is set and verified
tmp = tempfile.mkdtemp()
m, rep = netbuilder.build(FIELD, os.path.join(tmp, "field.pips"))
assert m.comps["Well"] == ["W1", "W2"] and m.comps["Completion"] == ["W1:Completion", "W2:Completion"], m.comps
assert m.edges == {"W1": ["CK1"], "CK1": ["FL1"], "FL1": ["J1"], "W2": ["FL2"], "FL2": ["J1"], "J1": ["FL3"], "FL3": ["Sep"]}, m.edges
assert rep["connections"] == 7 and rep["boundaries_synced"] and not rep["validation"], rep
assert rep["boundary_conditions"] == {"Sep.Pressure": "ok", "W1:Completion.Pressure": "ok", "W1:Completion.Temperature": "ok",
                                      "W2:Completion.Pressure": "ok", "W2:Completion.Temperature": "ok"}, rep
assert m.comps["Casing"] == ["W1:Casing", "W2:Casing"]
m.close()
assert os.path.exists(netbuilder.build_file(FIELD, os.path.join(tmp, "out.pips"))["file"])
print("build: 2 wells, choke, junction, sink; 7 connections; sink boundary condition verified")

# 2. the adapter is what makes a sink-pressure sweep work (a plain set_value does not move the boundary)
m, _ = netbuilder.build(FIELD, os.path.join(tmp, "f2.pips"))
r1 = m.tasks.networksimulation.run().node["VolumeFlowrateLiquidStockTank"]["Sep"]
m.set_value(Sink="Sep", parameter="Pressure", value=40)
assert m.tasks.networksimulation.run().node["VolumeFlowrateLiquidStockTank"]["Sep"] == r1  # like CSN_301 on 2023.1
sa.set_param(m, "Sink", "Sep", "Pressure", 40)
assert m.tasks.networksimulation.run().node["VolumeFlowrateLiquidStockTank"]["Sep"] < r1
assert sa.get_param(m, "Sink", "Sep", "Pressure") == 40
# in-well items: Completion="W1:Completion" is rejected (as on 2023.1); the adapter uses Well="W1", Completion="Completion"
try:
    m.get_value(Completion="W1:Completion", parameter="ReservoirPressure"); raise AssertionError("expected failure")
except LookupError:
    pass
assert sa.get_value(m, "Completion", "W1:Completion", "ReservoirPressure") == 260
r2 = m.tasks.networksimulation.run().node["VolumeFlowrateLiquidStockTank"]["W1"]
sa.set_param(m, "Completion", "W1:Completion", "ReservoirPressure", 300)   # reservoir pressure is a boundary value too
assert m.tasks.networksimulation.run().node["VolumeFlowrateLiquidStockTank"]["W1"] > r2
assert sa.get_param(m, "Completion", "W1:Completion", "ReservoirPressure") == 300
print("adapter: set_value alone leaves the network result unchanged; set_param moves the boundary condition "
      "(sink pressure and well reservoir pressure); in-well items addressed as Well=..., Completion=...")

# 3. a study on the described project: sweep the separator pressure, results must change, no warning
spec = {"objective": "Separator pressure vs field rate", "units": "METRIC", "model": {"source": "project"},
        "analysis": {"type": "sweep", "variables": [{"component_type": "Sink", "name": "Sep", "parameter": "Pressure",
                                                      "values": [10, 20, 30]}]}}
c = study.check(spec, project=FIELD)
assert c["ready"], c
assert "W1: fluid=BO" in study.plan_text(spec, FIELD)
r = executor.run(spec, progress=lambda s: None, project=FIELD)
assert "[sm3/d]" in r["table"][0], r["table"][0]          # units from the results go into the headers
liq = [float(row.split(" | ")[2]) for row in r["table"][2:]]
assert liq == sorted(liq, reverse=True) and liq[0] > liq[-1] and not r["warnings"], r
assert os.path.exists(os.path.join(r["output_dir"], "project.json"))
print("study on project: separator pressure 10->30 bara lowers field liquid", [round(x) for x in liq])

# 4. a variable with no effect on the outputs triggers the flat-result warning
spec2 = dict(spec, analysis={"type": "sweep", "variables": [{"component_type": "Flowline", "name": "FL3",
                                                             "parameter": "InnerDiameter", "values": [150, 250]}]})
r = executor.run(spec2, progress=lambda s: None, project=FIELD)
assert r["warnings"] and "No recorded result changed" in r["warnings"][0]
print("flat results are flagged:", r["warnings"][0][:70], "...")

# 5. checker: unknown component in a project study, incomplete project, non-metric units
bad = dict(spec, analysis={"type": "sweep", "variables": [{"component_type": "Sink", "name": "Nope",
                                                           "parameter": "Pressure", "values": [1, 2]}]})
assert any("Available Sink: ['Sep']" in e for e in study.check(bad, project=FIELD)["errors"])
assert any("not complete" in e for e in study.check(spec, project={"name": "x", "wells": [{"name": "W"}]})["errors"])
assert any("no project is described" in e for e in study.check(spec)["errors"])
assert any("METRIC" in e for e in study.check(dict(spec, units="FIELD"), project=FIELD)["errors"])
print("\nALL OK")
