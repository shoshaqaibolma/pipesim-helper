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
assert m.comps["Well"] == ["W1", "W2"] and m.comps["Completion"] == ["W1:W1_Comp", "W2:W2_Comp"], m.comps
assert m.edges == {"W1": ["CK1"], "CK1": ["FL1"], "FL1": ["J1"], "W2": ["FL2"], "FL2": ["J1"], "J1": ["FL3"], "FL3": ["Sep"]}, m.edges
assert rep["connections"] == 7 and rep["boundaries_synced"] and not rep["validation"], rep
assert rep["boundary_conditions"] == {"Sep": "ok", "W1:W1_Comp": "ok", "W2:W2_Comp": "ok"}, rep
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
    m.get_value(Completion="W1:W1_Comp", parameter="ReservoirPressure"); raise AssertionError("expected failure")
except LookupError:
    pass
assert sa.get_value(m, "Completion", "W1:W1_Comp", "ReservoirPressure") == 260
r2 = m.tasks.networksimulation.run().node["VolumeFlowrateLiquidStockTank"]["W1"]
sa.set_param(m, "Completion", "W1:W1_Comp", "ReservoirPressure", 300)   # reservoir pressure is a boundary value too
assert m.tasks.networksimulation.run().node["VolumeFlowrateLiquidStockTank"]["W1"] > r2
assert sa.get_param(m, "Completion", "W1:W1_Comp", "ReservoirPressure") == 300
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
sm = r["summary"]["Sep oil rate"]       # precomputed numbers the LLM quotes instead of calculating
assert sm["highest"]["case"] == "Sep.Pressure=10" and sm["lowest"]["case"] == "Sep.Pressure=30", sm
b, v30 = sm["base"], next(float(x.split(" | ")[3]) for x in r["table"] if x.startswith("Sep.Pressure=30"))
assert abs(sm["change_vs_base_pct"]["Sep.Pressure=30"] - round(100 * (v30 - b) / b, 2)) < 0.02, sm
assert "Sep oil rate change vs base [%]" in r["table"][0]
print("study on project: separator pressure 10->30 bara lowers field liquid", [round(x) for x in liq])

# 4. a variable with no effect on the outputs triggers the flat-result warning
spec2 = dict(spec, analysis={"type": "sweep", "variables": [{"component_type": "Flowline", "name": "FL3",
                                                             "parameter": "InnerDiameter", "values": [150, 250]}]})
r = executor.run(spec2, progress=lambda s: None, project=FIELD)
assert r["warnings"] and "No recorded result changed" in r["warnings"][0]
print("flat results are flagged:", r["warnings"][0][:70], "...")

# 5. a gas pipeline: rate-specified source (PIPESIM calculates its pressure), gas fluid by OGR/WGR
PIPE = {"name": "Gas export", "fluids": [{"name": "DryGas", "type": "gas", "gas_sg": 0.65, "ogr": 0, "wgr": 0, "api": 50}],
        "sources": [{"name": "Plant", "fluid": "DryGas", "temperature": 40, "gas_rate": 2.0}],
        "sinks": [{"name": "Terminal", "pressure": 50}],
        "flowlines": [{"name": "Export", "from": "Plant", "to": "Terminal", "length": 20000, "id": 254, "elevation_change": 0}]}
assert prj.check_project(PIPE)["ready"], prj.check_project(PIPE)
m, rep = netbuilder.build(PIPE, os.path.join(tmp, "pipe.pips"))
assert rep["boundary_conditions"] == {"Terminal": "ok", "Plant": "ok"}, rep
assert m.v[("BlackOilFluid", "DryGas", "UseGasRatio")] == "OGR" and m.v[("Source", "Plant", "GasFlowRate")] == 2.0
r = m.tasks.networksimulation.run().node
assert r["VolumeFlowrateGasStockTank"]["Terminal"] == 2.0 and r["Pressure"]["Plant"] > 50, r
m.close()
print("gas pipeline: rate-specified source, OGR/WGR gas fluid, boundary conditions verified")

# 6. gas lift: injection point inside the well; a gas-lift-rate sweep through the adapter changes the well rate
GL = dict(FIELD, wells=[dict(FIELD["wells"][0], gas_lift={"depth": 2000, "rate": 0.05}), FIELD["wells"][1]])
assert prj.check_project(GL)["ready"], prj.check_project(GL)
m, rep = netbuilder.build(GL, os.path.join(tmp, "gl.pips"))
assert m.comps["GasLiftInjection"] == ["W1:W1_GL"] and m.v[("GasLiftInjection", "W1:W1_GL", "GasRate")] == 0.05
m.close()
spec_gl = dict(spec, analysis={"type": "sweep", "variables": [{"component_type": "GasLiftInjection", "name": "W1:W1_GL",
                                                               "parameter": "GasRate", "values": [0.0, 0.05, 0.1]}]})
assert study.check(spec_gl, project=GL)["ready"], study.check(spec_gl, project=GL)
r = executor.run(spec_gl, progress=lambda s: None, project=GL)
assert not r["warnings"] and r["summary"]["W1 liquid rate"]["highest"]["case"] != "W1_GL.GasRate=0.0", r["summary"]
bad = dict(FIELD, wells=[dict(FIELD["wells"][0], gas_lift={"depth": 3000, "rate": 5}), FIELD["wells"][1]])
errs = prj.check_project(bad)["errors"]
assert any("above the completion" in e for e in errs) and any("very high" in e for e in errs), errs
print("gas lift: injection point built in the well; gas-lift-rate sweep changes the well rate; bad depth/rate caught")

# 7. nodal analysis of a built well: operating point, curves, nodal plot
spec_n = dict(spec, analysis={"type": "nodal", "producer": "W1", "outlet_pressure": 20})
assert study.check(spec_n, project=FIELD)["ready"], study.check(spec_n, project=FIELD)
assert "outlet pressure: 20 bara" in study.plan_text(spec_n, FIELD)
r = executor.run(spec_n, progress=lambda s: None, project=FIELD)
opp = r["summary"]["operating_point"]
assert opp["liquid_rate [sm3/d]"] > 0 and opp["bottomhole_pressure [bara]"] < 260, opp
assert any(c.endswith("nodal.png") for c in r["charts"]) and not r["warnings"], r
import sixgill_adapter as _sa
m2, _ = netbuilder.build(FIELD, os.path.join(tmp, "nodal2.pips"))
res = _sa.nodal(m2, "W1", 20, completion="W1_Comp")
q, p = res["curves"]["inflow_0"]["rate"], res["curves"]["inflow_0"]["pressure"]
assert q == sorted(q) and all(x == x for x in q + p) and max(q) > 100, q[:5]   # liquid basis, sorted, no NaN
assert p[0] > p[-1]                                                              # IPR falls with rate
m2.close()
assert any("Ask" in m["question"] or "pressure" in m["question"] for m in
           study.check(dict(spec, analysis={"type": "nodal", "producer": "W1"}), project=FIELD)["missing"])
assert any("No well named" in e for e in
           study.check(dict(spec, analysis={"type": "nodal", "producer": "X", "outlet_pressure": 5}), project=FIELD)["errors"])
print("nodal: operating point", round(opp["liquid_rate [sm3/d]"]), "sm3/d at Pwf", round(opp["bottomhole_pressure [bara]"], 1),
      "bara; IPR/VLP chart written; missing outlet pressure asked; unknown well caught")

# 8. checker: unknown component in a project study, incomplete project, non-metric units
bad = dict(spec, analysis={"type": "sweep", "variables": [{"component_type": "Sink", "name": "Nope",
                                                           "parameter": "Pressure", "values": [1, 2]}]})
assert any("Available Sink: ['Sep']" in e for e in study.check(bad, project=FIELD)["errors"])
assert any("not complete" in e for e in study.check(spec, project={"name": "x", "wells": [{"name": "W"}]})["errors"])
assert any("no project is described" in e for e in study.check(spec)["errors"])
assert any("METRIC" in e for e in study.check(dict(spec, units="FIELD"), project=FIELD)["errors"])
print("\nALL OK")
