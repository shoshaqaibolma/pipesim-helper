"""
Where does the remaining 1-4 % between a case study and our rebuilt model come from?

For each training pipeline (TF_M2A/B/C) it opens the original (temp copy) and our rebuilt model (as in
rebuild_compare.py, level 2), dumps every setting the Python Toolkit exposes in both, and then copies the
original's settings into the rebuilt model ONE GROUP AT A TIME, rerunning the same P/T profile after each:

  0. rebuilt (level 2: description + roughness, wall thickness, fluid details)
  1. + pipe route (detailed geometry profile)
  2. + heat transfer (ambient, U-values, burial, coatings, heat transfer options, global heat settings)
  3. + flow correlations (per pipe and global)
  4. + pipe segmentation and every other differing setting

If the gap closes at step 2, heat transfer explains it, and so on. Writes knowledge/gap_study.json.
  "D:\\Program\\Pipesim toolkit\\python.exe" tools\\gap_study.py "D:\\Program\\Pipesim2023.1\\Case Studies"
"""
import json, os, re, shutil, sys, tempfile, traceback
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [ROOT, os.path.join(ROOT, "tools")]
from sixgill import definitions as d
import netbuilder, project as prj, sixgill_adapter as sa
from rebuild_compare import (PIPELINES, FLUID_SKIP, FLOWLINE_EXTRA, find, values, fluid_from, safe_name, run_pt,
                             compare_pt)

GROUPS = [("pipe route", r"Geometry|Elevation|Undulation|Detailed|Survey|^HorizontalDistance$|^MeasuredDistance$|^Length$"),
          ("heat transfer", r"Heat|Ambient|UValue|Insulat|Burial|Soil|Coating|Thermal|Geothermal|Wind|Conductiv|"
                            r"Temperature|Film|Seabed|WaterInterpolation|UseEnvironmental"),
          ("flow correlations", r"Correlation|SwapAngle|OverrideGlobal|UseGlobalFlow|Friction|Holdup"),
          ("segmentation and other", r".")]
SKIP = re.compile(r"^(Name|IsActive|Comment|CatalogLabel|CatalogName|Latitude|Longitude|SchematicLatitude|"
                  r"SchematicLongitude|X|Y|Description|IsTemplate|IsBuiltinTemplate|HasOverride|OverridesInitialized|"
                  r"InnerDiameter|Roughness|WallThickness|AssociatedBlackOilFluid)$")
COMPONENT_TYPES = ["Flowline", "Source", "Sink", "HeatTransferOptions", "FlowCorrelation", "BlackOilFluid"]


def group_of(param, ctype=""):
    if ctype == "HeatTransferOptions":
        return 1
    if ctype in ("FlowCorrelation", "GlobalFlowCorrelation"):
        return 2
    for i, (_, rx) in enumerate(GROUPS):
        if re.search(rx, param):
            return i
    return len(GROUPS) - 1


def plain(v):
    if isinstance(v, (int, float, str, bool)) or v is None:
        return v
    return str(v)[:200]


def all_values(m, notes):
    """{(type, name): {param: value}} for every component type of interest, plus the global simulation settings."""
    out = {}
    for t in COMPONENT_TYPES:
        try:
            names = m.find(**{t: d.ALL}) or []
        except Exception as e:
            notes.append(f"find {t}: {type(e).__name__}: {str(e)[:120]}")
            continue
        for n in names:
            try:
                v = m.get_values(**{t: n})
                v = next(iter(v.values())) if isinstance(v, dict) and v and isinstance(next(iter(v.values())), dict) else v
                out[(t, n)] = {k: plain(x) for k, x in (v or {}).items() if not isinstance(x, (list, dict))}
            except Exception as e:
                notes.append(f"get_values {t}={n}: {type(e).__name__}: {str(e)[:120]}")
    ss = getattr(m, "sim_settings", None)
    if ss is not None:
        vals = {}
        for p in vars(d.Parameters.SimulationSetting).values():
            if isinstance(p, str) and not p.startswith("_"):
                try:
                    vals[p] = plain(ss[p])
                except Exception:
                    pass
        out[("SimulationSetting", "global")] = vals
        try:
            out[("GlobalFlowCorrelation", "global")] = {k: plain(x) for k, x in
                                                       (ss.global_flow_correlation() or {}).items()}
        except Exception as e:
            notes.append(f"global_flow_correlation(): {type(e).__name__}: {str(e)[:120]}")
    else:
        notes.append("model has no sim_settings attribute")
    return out


def differences(o, b, fluid_map):
    diffs = []
    for (t, n), ov in o.items():
        bn = fluid_map.get(n, n) if t == "BlackOilFluid" else n
        bv = b.get((t, bn))
        if bv is None:
            diffs.append({"type": t, "name": n, "param": "(whole component)", "original": "present", "rebuilt": "missing"})
            continue
        for k, x in ov.items():
            if SKIP.match(k) or x is None:
                continue
            y = bv.get(k)
            same = (x == y) or (isinstance(x, (int, float)) and isinstance(y, (int, float))
                                and abs(x - y) <= 1e-6 * max(1, abs(x)))
            if not same:
                diffs.append({"type": t, "name": bn, "param": k, "original": x, "rebuilt": y})
    return diffs


def apply(m, diff, notes):
    t, n, k, v = diff["type"], diff["name"], diff["param"], diff["original"]
    try:
        if t == "SimulationSetting":
            m.sim_settings[k] = v
        elif t == "GlobalFlowCorrelation":
            m.sim_settings.global_flow_correlation({k: v})
        else:
            m.set_value(**{t: n}, parameter=k, value=v)
        return True
    except Exception as e:
        notes.append(f"could not set {t} {n}.{k} = {v}: {type(e).__name__}: {str(e)[:120]}")
        return False


def case(path, tmp):
    notes, out = [], {"steps": [], "notes": None}
    c = os.path.join(tmp, "orig.pips"); shutil.copy2(path, c)
    orig = sa.open_model(c)
    try:
        conns = orig.connections()
        comps = {t: [n for n in (orig.find(**{t: d.ALL}) or []) if ":" not in n] for t in ("Source", "Sink", "Flowline")}
        src, snk = comps["Source"][0], comps["Sink"][0]
        raw = orig.tasks.ptprofilesimulation.get_conditions(producer=src)
        raw = raw[0] if isinstance(raw, (list, tuple)) else raw
        cond = {k: v for k, v in (raw or {}).items() if k not in ("Producer", "BranchTerminator") and v is not None
                and not isinstance(v, (list, dict))}
        state, o = run_pt(orig, src, cond)
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
                "sinks": [{"name": snk, "pressure": cond.get("OutletPressure") or 1.0}], "flowlines": []}
        for f in comps["Flowline"]:
            v = values(orig, "Flowline", f)
            up = next((x["Source"] for x in conns if x["Destination"] == f), None)
            dn = next((x["Destination"] for x in conns if x["Source"] == f), None)
            proj["flowlines"].append({"name": f, "from": up, "to": dn, "length": v.get("HorizontalDistance"),
                                      "id": v.get("InnerDiameter"), "elevation_change": v.get("ElevationDifference") or 0})
            amb = v.get("AmbientWaterTemperature") if v.get("AmbientFluidType") == "Water" else v.get("AmbientAirTemperature")
            if amb is not None:
                proj["ambient_temperature"] = amb
        built, _ = netbuilder.build(proj, os.path.join(tmp, "rebuilt.pips"))
        try:
            # level 2, as in rebuild_compare.py
            for k, val in values(orig, "BlackOilFluid", fl).items():
                if k not in FLUID_SKIP and val is not None and not isinstance(val, (list, dict)):
                    try:
                        built.set_value(BlackOilFluid=fluid["name"], parameter=k, value=val)
                    except Exception:
                        pass
            for f in comps["Flowline"]:
                v = values(orig, "Flowline", f)
                for k in FLOWLINE_EXTRA:
                    if v.get(k) is not None:
                        try:
                            built.set_value(Flowline=f, parameter=k, value=v[k])
                        except Exception:
                            pass
            fluid_map = {fl: fluid["name"]}
            ov, bv = all_values(orig, notes), all_values(built, notes)
            diffs = differences(ov, bv, fluid_map)
            out["settings_dump"] = {"original": {f"{t}|{n}": v for (t, n), v in ov.items()},
                                    "rebuilt": {f"{t}|{n}": v for (t, n), v in bv.items()}}
            out["differences"] = diffs
            st, b = run_pt(built, src, cond)
            out["steps"].append({"step": "0. rebuilt (level 2)", "state": st, "compare": compare_pt(o, b)})
            for gi, (gname, _) in enumerate(GROUPS):
                applied = []
                if gi == 0:   # the route itself: copy the original's geometry table
                    for f in comps["Flowline"]:
                        try:
                            g = orig.get_geometry(Flowline=f)
                            if g is not None and len(g) > 2:
                                built.set_geometry(Flowline=f, value=g)
                                applied.append(f"{f}: geometry profile with {len(g)} points")
                            else:
                                applied.append(f"{f}: original is a simple line ({0 if g is None else len(g)} points)")
                        except Exception as e:
                            notes.append(f"geometry {f}: {type(e).__name__}: {str(e)[:120]}")
                for df in diffs:
                    if group_of(df["param"], df["type"]) == gi and df["param"] != "(whole component)" and apply(built, df, notes):
                        applied.append(f"{df['type']} {df['name']}.{df['param']}: {df['rebuilt']} -> {df['original']}")
                try:
                    sa.sync_boundaries(built)
                except Exception:
                    pass
                st, b = run_pt(built, src, cond)
                out["steps"].append({"step": f"{gi + 1}. + {gname}", "applied": applied, "state": st,
                                     "compare": compare_pt(o, b)})
            remaining = differences(ov, all_values(built, notes), fluid_map)
            out["remaining_differences"] = remaining
        finally:
            built.close()
    finally:
        orig.close()
    out["notes"] = notes
    return out


def main():
    root = sys.argv[1] if len(sys.argv) > 1 else r"D:\Program\Pipesim2023.1\Case Studies"
    results = {}
    for stem in PIPELINES:
        path = find(root, stem)
        print(f"\n===== {stem}: {path}")
        if not path:
            results[stem] = {"error": "file not found"}
            continue
        tmp = tempfile.mkdtemp(prefix="pipesim_gap_")
        try:
            r = case(path, tmp)
        except Exception as e:
            r = {"error": f"{type(e).__name__}: {e}", "trace": traceback.format_exc()[-2000:]}
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
        results[stem] = r
        if "error" in r:
            print("ERROR", r["error"]); print(r.get("trace", ""))
            continue
        print(f"settings that differ after level 2: {len(r['differences'])}")
        for df in r["differences"]:
            print(f"   [{GROUPS[group_of(df['param'], df['type'])][0]}] {df['type']} {df['name']}.{df['param']}: "
                  f"original {df['original']} / rebuilt {df['rebuilt']}")
        for s in r["steps"]:
            row = {x["variable"]: x for x in s["compare"]}
            show = lambda v: (f"{row[v]['rebuilt']} ({row[v]['diff_pct']:+.2f} %)" if v in row else "-")
            print(f" {s['step']:<32} loss {show('SystemPressureLoss')}  outlet T {show('SystemOutletTemperature')}  "
                  f"liq {show('OutletVolumeFlowrateLiquid')}  gas {show('OutletVolumeFlowrateGas')}")
            for a in s.get("applied", [])[:25]:
                print(f"      applied {a}")
        orig_row = {x["variable"]: x["original"] for x in r["steps"][0]["compare"]}
        print(f" original: loss {orig_row.get('SystemPressureLoss')}  outlet T {orig_row.get('SystemOutletTemperature')}"
              f"  liq {orig_row.get('OutletVolumeFlowrateLiquid')}  gas {orig_row.get('OutletVolumeFlowrateGas')}")
        print(f" still different at the end: {len(r['remaining_differences'])}")
        for df in r["remaining_differences"][:20]:
            print(f"   {df['type']} {df['name']}.{df['param']}: original {df['original']} / rebuilt {df['rebuilt']}")
        for n in r["notes"][:30]:
            print(f"   note: {n}")
    json.dump(results, open(os.path.join(ROOT, "knowledge", "gap_study.json"), "w", encoding="utf-8"), indent=1,
              default=str)
    print("\nwritten knowledge/gap_study.json")


if __name__ == "__main__":
    main()
