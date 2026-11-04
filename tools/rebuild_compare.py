"""
How close does a model built from a description get to the official PIPESIM case study?
For each case: run the original (temp copy) -> convert its data to a project description -> build it -> run ->
compare node by node. Then copy the detailed inputs the project format does not carry (pipe roughness, wall
thickness, ambient temperatures, full black-oil settings) into the rebuilt model and compare again.
  "D:\\Program\\Pipesim toolkit\\python.exe" tools\\rebuild_compare.py "D:\\Program\\Pipesim2023.1\\Case Studies"
Writes knowledge/compare.json and prints the comparison tables.
"""
import json, os, shutil, sys, tempfile, traceback
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from sixgill import definitions as d
import netbuilder, project as prj, sixgill_adapter as sa

PIPELINES = ["TF_M2A_Water_Pipeline", "TF_M2B_Gas_Pipeline", "TF_M2C_Multiphase_Pipeline"]
WELLS = ["TF_M3A_Base_Oil_Well"]
SV = [d.SystemVariables.PRESSURE, d.SystemVariables.TEMPERATURE, d.SystemVariables.VOLUME_FLOWRATE_LIQUID_STOCKTANK,
      d.SystemVariables.VOLUME_FLOWRATE_GAS_STOCKTANK]
FLUID_SKIP = {"Name", "IsActive", "IsTemplate", "IsBuiltinTemplate", "HasOverride", "Comment", "OverridesInitialized"}
FLOWLINE_EXTRA = ["Roughness", "WallThickness", "AmbientAirTemperature", "AmbientWaterTemperature", "AmbientFluidType",
                  "UndulationRate"]


def find(root, stem):
    for dp, _, fs in os.walk(root):
        for f in fs:
            if f.lower().endswith(".pips") and os.path.splitext(f)[0].replace(" ", "_").lower() == stem.lower():
                return os.path.join(dp, f)


def values(m, ctype, name):
    kw = {"Well": name.split(":", 1)[0], ctype: name.split(":", 1)[1]} if ":" in name else {ctype: name}
    v = m.get_values(**kw)
    return next(iter(v.values())) if isinstance(v, dict) and v else {}


def safe_name(name):
    return f"{name}_fluid" if str(name).strip().lower() in prj.RESERVED_FLUID_NAMES else name


def fluid_from(name, v, notes):
    name = safe_name(name)
    gr, wr = v.get("UseGasRatio"), v.get("UseWaterRatio")
    if gr == "OGR":
        return {"name": name, "type": "gas", "gas_sg": v.get("GasSpecificGravity"), "ogr": v.get("OGR") or 0,
                "wgr": (v.get("WGR") or 0) if wr == "WGR" else 0, "api": v.get("API") or 50}
    wc = (v.get("WaterCut") or 0) if wr == "WaterCut" else None
    if wc is None:
        notes.append(f"fluid {name}: water given as {wr}; not representable -> water cut 0 assumed")
        wc = 0
    if gr == "GOR":
        gor = v.get("GOR") or 0
    elif gr == "GLR":
        glr = v.get("GLR") or 0
        gor = 0 if glr == 0 or wc >= 100 else glr / (1 - wc / 100)
        notes.append(f"fluid {name}: GLR {glr} converted to GOR {gor:.4g}")
    else:
        notes.append(f"fluid {name}: gas ratio type {gr} not representable -> GOR 0")
        gor = 0
    return {"name": name, "type": "black_oil", "api": v.get("API"), "gor": gor, "water_cut": wc,
            "gas_sg": v.get("GasSpecificGravity")}


def run_network(m):
    r = m.tasks.networksimulation.run(system_variables=SV, profile_variables=[])
    node = getattr(r, "node", {}) or {}
    return str(getattr(r, "state", "")), {str(k): {c: x for c, x in comps.items() if ":" not in str(c)}
                                          for k, comps in node.items() if isinstance(comps, dict)}


def compare(orig, built):
    rows = []
    for var, comps in orig.items():
        for c, ov in comps.items():
            if c == "Unit" or not isinstance(ov, (int, float)):
                continue
            bv = (built.get(var) or {}).get(c)
            if isinstance(bv, (int, float)):
                diff = bv - ov
                rel = 100 * diff / abs(ov) if abs(ov) > 1e-9 else 0.0
                rows.append({"node": c, "variable": var, "unit": comps.get("Unit", ""), "original": round(ov, 4),
                             "rebuilt": round(bv, 4), "diff_pct": round(rel, 2)})
    return rows


def show(title, rows):
    print(f"   {title}")
    for r in rows:
        print(f"     {r['node']:<12} {r['variable']:<32} {r['original']:>12} {r['rebuilt']:>12} {r['unit']:<8} "
              f"{r['diff_pct']:+.2f} %")


def copy_details(orig, built, fluids, flowlines, notes):
    n = 0
    for f in fluids:
        for k, v in values(orig, "BlackOilFluid", f).items():
            if k in FLUID_SKIP or v is None or isinstance(v, (list, dict)):
                continue
            try:
                built.set_value(BlackOilFluid=f, parameter=k, value=v); n += 1
            except Exception as e:
                notes.append(f"fluid {f}.{k}: not copied ({type(e).__name__})")
    for fl in flowlines:
        v = values(orig, "Flowline", fl)
        for k in FLOWLINE_EXTRA:
            if v.get(k) is not None:
                try:
                    built.set_value(Flowline=fl, parameter=k, value=v[k]); n += 1
                except Exception as e:
                    notes.append(f"flowline {fl}.{k}: not copied ({type(e).__name__})")
        if v.get("AmbientTemperatureOptions") not in (None, "InputSingleValue"):
            notes.append(f"flowline {fl}: ambient temperature given as {v['AmbientTemperatureOptions']} (not copied)")
        if v.get("DetailedModel"):
            notes.append(f"flowline {fl}: detailed geometry profile in the original (rebuilt as a simple line)")
    sa.sync_boundaries(built)
    return n


PT_KEYS = ("InletPressure", "OutletPressure", "FlowRateType", "GasFlowRate", "LiquidFlowRate", "MassFlowRate",
           "CalculatedVariable")
PT_MAIN = ("SystemInletPressure", "SystemOutletPressure", "SystemOutletTemperature", "InletVolumeFlowrateLiquid",
           "OutletVolumeFlowrateLiquid", "OutletVolumeFlowrateGas", "SystemPressureLoss", "TotalLiquidHoldup")


def run_pt(m, src, cond):
    r = m.tasks.ptprofilesimulation.run(producer=src, parameters=cond)
    sysr = getattr(r, "system", {}) or {}
    out = {}
    for var, vals in sysr.items():
        if isinstance(vals, dict):
            nums = [v for k, v in vals.items() if k != "Unit" and isinstance(v, (int, float))]
            if nums:
                out[var] = (nums[0], vals.get("Unit", ""))
    return str(getattr(r, "state", "")), out


def compare_pt(o, b):
    rows = []
    for var in PT_MAIN:
        if var in o and var in b:
            ov, unit = o[var]; bv = b[var][0]
            rows.append({"node": "system", "variable": var, "unit": unit, "original": round(ov, 4), "rebuilt": round(bv, 4),
                         "diff_pct": round(100 * (bv - ov) / abs(ov), 2) if abs(ov) > 1e-9 else 0.0})
    return rows


def pipeline_case(path, tmp):
    """Training pipelines are single-branch P/T profile exercises: compare through the P/T profile task."""
    notes = []
    out = {"type": "pipeline (P/T profile)", "notes": notes}
    c = os.path.join(tmp, "orig.pips"); shutil.copy2(path, c)
    orig = sa.open_model(c)
    try:
        conns = orig.connections()
        comps = {t: [n for n in (orig.find(**{t: d.ALL}) or []) if ":" not in n] for t in ("Source", "Sink", "Junction", "Flowline")}
        src, snk = comps["Source"][0], comps["Sink"][0]
        raw = orig.tasks.ptprofilesimulation.get_conditions(producer=src)
        raw = raw[0] if isinstance(raw, (list, tuple)) else raw
        cond = {k: raw[k] for k in PT_KEYS if isinstance(raw, dict) and raw.get(k) is not None}
        out["pt_conditions"] = cond
        out["original_state"], o = run_pt(orig, src, cond)
        sv = values(orig, "Source", src)
        fl = sv.get("AssociatedBlackOilFluid")
        fluid = fluid_from(fl, values(orig, "BlackOilFluid", fl), notes)
        item = {"name": src, "fluid": fluid["name"], "temperature": sv.get("Temperature")}
        if cond.get("LiquidFlowRate") is not None:
            item["liquid_rate"] = cond["LiquidFlowRate"]
        elif cond.get("GasFlowRate") is not None:
            item["gas_rate"] = cond["GasFlowRate"]
        else:
            item["pressure"] = cond.get("InletPressure")
        proj = {"name": os.path.basename(path), "fluids": [fluid], "sources": [item],
                "sinks": [{"name": snk, "pressure": cond.get("OutletPressure") or 1.0}], "junctions": [], "flowlines": []}
        for f in comps["Flowline"]:
            v = values(orig, "Flowline", f)
            up = next((x["Source"] for x in conns if x["Destination"] == f), None)
            dn = next((x["Destination"] for x in conns if x["Source"] == f), None)
            proj["flowlines"].append({"name": f, "from": up, "to": dn, "length": v.get("HorizontalDistance"),
                                      "id": v.get("InnerDiameter"), "elevation_change": v.get("ElevationDifference") or 0})
            amb = v.get("AmbientWaterTemperature") if v.get("AmbientFluidType") == "Water" else v.get("AmbientAirTemperature")
            if amb is not None:
                proj["ambient_temperature"] = amb
        out["project"] = proj
        chk = prj.check_project(proj)
        if not chk["ready"]:
            out["error"] = f"converted project not ready: {chk['missing'][:3]} {chk['errors'][:3]}"
            return out
        built, rep = netbuilder.build(proj, os.path.join(tmp, "rebuilt.pips"))
        try:
            out["build"] = {k: rep[k] for k in ("boundary_conditions", "validation")}
            out["rebuilt_state"], b = run_pt(built, src, cond)
            out["level1"] = compare_pt(o, b)
            n = 0
            for k, val in values(orig, "BlackOilFluid", fl).items():
                if k not in FLUID_SKIP and val is not None and not isinstance(val, (list, dict)):
                    try:
                        built.set_value(BlackOilFluid=fluid["name"], parameter=k, value=val); n += 1
                    except Exception:
                        pass
            for f in comps["Flowline"]:
                v = values(orig, "Flowline", f)
                for k in FLOWLINE_EXTRA:
                    if v.get(k) is not None:
                        try:
                            built.set_value(Flowline=f, parameter=k, value=v[k]); n += 1
                        except Exception:
                            pass
                if v.get("DetailedModel"):
                    notes.append(f"flowline {f}: detailed geometry in the original (rebuilt as a simple line)")
            out["copied_details"] = n
            out["rebuilt2_state"], b2 = run_pt(built, src, cond)
            out["level2"] = compare_pt(o, b2)
        finally:
            built.close()
    finally:
        orig.close()
    return out


def well_case(path, tmp, outlet_pressure=20.0):
    notes = []
    out = {"type": "well (nodal analysis)", "notes": notes}
    c = os.path.join(tmp, "orig.pips"); shutil.copy2(path, c)
    orig = sa.open_model(c)
    try:
        well = [w for w in orig.find(Well=d.ALL) if ":" not in w][0]
        comp = [x for x in orig.find(Completion=d.ALL) if x.startswith(well + ":")][0]
        cv = values(orig, "Completion", comp)
        tub = [values(orig, "Tubing", t) for t in orig.find(Tubing=d.ALL) if t.startswith(well + ":")]
        cas = [values(orig, "Casing", t) for t in orig.find(Casing=d.ALL) if t.startswith(well + ":")]
        get = lambda p: sa.get_value(orig, "Completion", comp, p)
        out["completion"] = {k: cv.get(k) for k in ("ReservoirPressure", "ReservoirTemperature", "IPRModel",
                                                    "AssociatedBlackOilFluid", "FluidEntryType", "GeometryProfileType")}
        try:
            depth = get("TopMeasuredDepth")
        except Exception:
            depth = None
        depth = depth or sum(t.get("Length") or 0 for t in tub)
        pi = get("LiquidPI") if cv.get("IPRModel") == "IPRPIModel" else None
        if cv.get("IPRModel") != "IPRPIModel" or not pi:
            out["error"] = f"IPR {cv.get('IPRModel')} (PI {pi}) not converted yet"
            return out
        try:
            traj = orig.get_trajectory(Well=well)
            out["trajectory_rows"] = len(traj) if traj is not None else 0
            if traj is not None and len(traj) > 2:
                notes.append("original well has a deviation survey; rebuilt well is vertical")
        except Exception:
            pass
        if len(tub) > 1:
            notes.append(f"original tubing has {len(tub)} sections; rebuilt with one (first section ID)")
        fl = cv.get("AssociatedBlackOilFluid")
        w = {"name": "W", "fluid": safe_name(fl), "reservoir_pressure": cv.get("ReservoirPressure"),
             "reservoir_temperature": cv.get("ReservoirTemperature"), "depth": depth,
             "tubing_id": tub[0].get("InnerDiameter"), "tubing_wall": tub[0].get("WallThickness") or 6.45,
             "ipr": {"model": "pi", "liquid_pi": pi}}
        if cas:
            w["casing_id"], w["casing_wall"] = cas[0].get("InnerDiameter"), cas[0].get("WallThickness") or 9.19
        proj = {"name": os.path.basename(path), "fluids": [fluid_from(fl, values(orig, "BlackOilFluid", fl), notes)],
                "wells": [w], "sinks": [{"name": "S", "pressure": outlet_pressure}],
                "flowlines": [{"name": "F", "from": "W", "to": "S", "length": 10, "id": 150, "elevation_change": 0}]}
        out["project"] = proj
        o = sa.nodal(orig, well, outlet_pressure)
        out["original"] = {k: v.get("value") for k, v in o["operating_point"].items()}
        op = lambda m, w, comp=None: {k: round(v.get("value"), 3) for k, v in
                                       sa.nodal(m, w, outlet_pressure, completion=comp)["operating_point"].items()
                                       if isinstance(v.get("value"), (int, float))}
        steps = []

        def factor(label, apply):
            """Build the well afresh, apply one difference from the original, run nodal analysis."""
            built, _ = netbuilder.build(proj, os.path.join(tmp, f"rebuilt_{len(steps)}.pips"))
            try:
                msg = apply(built) if apply else None
                sa.sync_boundaries(built)
                steps.append({"step": label, "result": op(built, "W", "W_Comp"), "note": msg})
            except Exception as e:
                steps.append({"step": label, "error": f"{type(e).__name__}: {str(e)[:200]}"})
            finally:
                built.close()

        def fluid_details(b):
            for k, v in values(orig, "BlackOilFluid", fl).items():
                if k not in FLUID_SKIP and v is not None and not isinstance(v, (list, dict)):
                    try:
                        b.set_value(BlackOilFluid=safe_name(fl), parameter=k, value=v)
                    except Exception:
                        pass

        def trajectory(b):
            b.set_trajectory(Well="W", value=orig.get_trajectory(Well=well))

        def geothermal(b):
            b.set_geothermal_profile(Well="W", value=orig.get_geothermal_profile(Well=well))

        def tubulars(b):
            sa.set_value(b, "Tubing", "W:Tubing", "Length", tub[0].get("Length"))
            if cas:
                sa.set_value(b, "Casing", "W:Casing", "Length", cas[0].get("Length"))
            return f"tubing {tub[0].get('Length')} m, casing {cas[0].get('Length') if cas else '-'} m"

        def well_settings(b):
            for k, v in values(orig, "Well", well).items():
                if k not in ("Name", "IsActive") and v is not None and not isinstance(v, (list, dict)):
                    try:
                        b.set_value(Well="W", parameter=k, value=v)
                    except Exception:
                        pass

        def everything(b):
            for f in (fluid_details, trajectory, geothermal, tubulars, well_settings):
                try:
                    f(b)
                except Exception:
                    pass

        out["original"] = op(orig, well)
        factor("rebuilt from the description", None)
        for label, f in (("+ full fluid settings", fluid_details), ("+ deviation survey", trajectory),
                         ("+ geothermal profile", geothermal), ("+ exact tubing/casing lengths", tubulars),
                         ("+ well settings", well_settings), ("+ all of the above", everything)):
            factor(label, f)
        out["steps"] = steps
    finally:
        orig.close()
    return out


def main():
    root = sys.argv[1]
    results = {}
    for stem in PIPELINES + WELLS:
        path = find(root, stem)
        print(f"\n===== {stem}: {path}")
        if not path:
            continue
        tmp = tempfile.mkdtemp(prefix="pipesim_cmp_")
        try:
            r = (pipeline_case if stem in PIPELINES else well_case)(path, tmp)
        except Exception:
            r = {"error": traceback.format_exc()[-1500:]}
        results[stem] = r
        if r.get("error"):
            print("   ERROR:", r["error"])
        for n in r.get("notes", []):
            print("   note:", n)
        if "project" in r:
            print("   converted project:\n" + "\n".join("     " + l for l in prj.summary(r["project"]).splitlines()))
        if "level1" in r:
            print("   build:", json.dumps(r.get("build")))
            show(f"level 1 - built from the description only (state {r.get('rebuilt_state')}):  "
                 "node / variable / original / rebuilt / unit / diff", r["level1"])
            show(f"level 2 - plus {r.get('copied_details')} detailed inputs copied (state {r.get('rebuilt2_state')}):",
                 r["level2"])
        if "steps" in r:
            o = r["original"]
            print(f"   nodal analysis at 20 bara outlet; original: liquid {o.get('liquid_rate')} sm3/d, "
                  f"Pwf {o.get('bottomhole_pressure')} bara")
            for s in r["steps"]:
                if "error" in s:
                    print(f"     {s['step']:<34} ERROR {s['error']}"); continue
                q, p = s["result"].get("liquid_rate"), s["result"].get("bottomhole_pressure")
                dq = 100 * (q - o["liquid_rate"]) / o["liquid_rate"] if q and o.get("liquid_rate") else float("nan")
                print(f"     {s['step']:<34} liquid {q} sm3/d ({dq:+.1f} %), Pwf {p} bara {s.get('note') or ''}")
        shutil.rmtree(tmp, ignore_errors=True)
    os.makedirs(os.path.join(ROOT, "knowledge"), exist_ok=True)
    json.dump(results, open(os.path.join(ROOT, "knowledge", "compare.json"), "w"), indent=1, default=str)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
    main()
