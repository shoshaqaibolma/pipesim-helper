"""
Decisive test for the remaining gap: are the hidden heat-transfer / thermal settings the cause?

A .pips file is a zip whose "Model" entry is an SQLite database. The Python Toolkit does not expose some of its
tables (pipe heat transfer, fluid thermal data). For each training pipeline this script:
  1. builds our model from the description + the visible details (level 2, as in rebuild_compare.py) and saves it;
  2. prints the hidden rows of the original and the rebuilt model side by side;
  3. on TEMP COPIES of the rebuilt file, writes the original's hidden values into it, one table at a time,
     reopens it with the toolkit and reruns the same P/T profile.
The original case studies are only copied and read, never changed.
  "D:\\Program\\Pipesim toolkit\\python.exe" tools\\heat_transplant.py "D:\\Program\\Pipesim2023.1\\Case Studies"
Writes knowledge/heat_transplant.json.
"""
import json, os, shutil, sqlite3, sys, tempfile, traceback, zipfile
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [ROOT, os.path.join(ROOT, "tools")]
from sixgill import definitions as d
import netbuilder, sixgill_adapter as sa
from rebuild_compare import PIPELINES, FLUID_SKIP, FLOWLINE_EXTRA, find, values, fluid_from, run_pt, compare_pt

META = {"Id", "Version", "GUID", "Insert_Date", "Insert_User", "Produced_By", "SDAT_Label", "Update_Date",
        "Update_User", "Existence_Kind", "Name"}


def prepare(path, tmp):
    """Original P/T result + a saved level-2 rebuilt file. Returns a dict."""
    c = os.path.join(tmp, "orig.pips"); shutil.copy2(path, c)
    notes = []
    orig = sa.open_model(c)
    try:
        conns = orig.connections()
        comps = {t: [n for n in (orig.find(**{t: d.ALL}) or []) if ":" not in n] for t in ("Source", "Sink", "Flowline")}
        src, snk = comps["Source"][0], comps["Sink"][0]
        raw = orig.tasks.ptprofilesimulation.get_conditions(producer=src)
        raw = raw[0] if isinstance(raw, (list, tuple)) else raw
        cond = {k: v for k, v in (raw or {}).items() if k not in ("Producer", "BranchTerminator") and v is not None
                and not isinstance(v, (list, dict))}
        _, o = run_pt(orig, src, cond)
        sv = values(orig, "Source", src)
        fl = sv.get("AssociatedBlackOilFluid")
        fv = values(orig, "BlackOilFluid", fl)
        fluid = fluid_from(fl, fv, notes)
        item = {"name": src, "fluid": fluid["name"], "temperature": sv.get("Temperature")}
        if cond.get("LiquidFlowRate") is not None:
            item["liquid_rate"] = cond["LiquidFlowRate"]
        elif cond.get("GasFlowRate") is not None:
            item["gas_rate"] = cond["GasFlowRate"]
        else:
            item["pressure"] = cond.get("InletPressure")
        proj = {"name": os.path.basename(path), "fluids": [fluid], "sources": [item],
                "sinks": [{"name": snk, "pressure": cond.get("OutletPressure") or 1.0}], "flowlines": []}
        flv = {}
        for f in comps["Flowline"]:
            v = flv[f] = values(orig, "Flowline", f)
            up = next((x["Source"] for x in conns if x["Destination"] == f), None)
            dn = next((x["Destination"] for x in conns if x["Source"] == f), None)
            proj["flowlines"].append({"name": f, "from": up, "to": dn, "length": v.get("HorizontalDistance"),
                                      "id": v.get("InnerDiameter"), "elevation_change": v.get("ElevationDifference") or 0})
            amb = v.get("AmbientWaterTemperature") if v.get("AmbientFluidType") == "Water" else v.get("AmbientAirTemperature")
            if amb is not None:
                proj["ambient_temperature"] = amb
    finally:
        orig.close()
    bpath = os.path.join(tmp, "rebuilt.pips")
    built, _ = netbuilder.build(proj, bpath)
    try:
        for k, val in fv.items():
            if k not in FLUID_SKIP and val is not None and not isinstance(val, (list, dict)):
                try:
                    built.set_value(BlackOilFluid=fluid["name"], parameter=k, value=val)
                except Exception:
                    pass
        for f, v in flv.items():
            for k in FLOWLINE_EXTRA:
                if v.get(k) is not None:
                    try:
                        built.set_value(Flowline=f, parameter=k, value=v[k])
                    except Exception:
                        pass
        _, b = run_pt(built, src, cond)
        built.save()
    finally:
        built.close()
    return {"orig_path": c, "built_path": bpath, "src": src, "cond": cond, "o": o, "level2": compare_pt(o, b),
            "orig_fluid": fl, "built_fluid": fluid["name"], "flowlines": list(flv), "notes": notes}


# ---------- the database inside the .pips
def db_entry(zpath):
    with zipfile.ZipFile(zpath) as z:
        for info in z.infolist():
            if z.read(info)[:16].startswith(b"SQLite format 3"):
                return info.filename
    raise ValueError("no SQLite entry in the .pips file")


def extract_db(zpath, out):
    name = db_entry(zpath)
    with zipfile.ZipFile(zpath) as z:
        open(out, "wb").write(z.read(name))
    return name


def replace_db(zpath, name, db_file, out_path):
    """Write a copy of the .pips with its database entry replaced."""
    with zipfile.ZipFile(zpath) as zin, zipfile.ZipFile(out_path, "w") as zout:
        for info in zin.infolist():
            data = open(db_file, "rb").read() if info.filename == name else zin.read(info)
            zout.writestr(info, data, compress_type=info.compress_type)


def row(con, table, where, args):
    con.row_factory = sqlite3.Row
    r = con.execute(f'select * from "{table}" where {where}', args).fetchone()
    return dict(r) if r else None


def hidden_rows(con, fluid, flowlines):
    out = {}
    for f in flowlines:
        pb = row(con, "AV_PipeBase", "Name = ?", (f,))
        out[f"AV_PipeBase {f}"] = pb
        if pb and pb.get("HeatTransfer_Id") is not None:
            out[f"AV_PipeHeatTransfer {f}"] = row(con, "AV_PipeHeatTransfer", "Id = ?", (pb["HeatTransfer_Id"],))
        out[f"AV_Flowline {f}"] = row(con, "AV_Flowline", "Name = ?", (f,)) if pb is None else \
            row(con, "AV_Flowline", "Id = ?", (pb["Id"],)) or row(con, "AV_Flowline", "Name = ?", (f,))
    bo = row(con, "AV_BlackOilFluid", "Name = ?", (fluid,))
    out["AV_BlackOilFluid"] = bo
    if bo and bo.get("ThermalData_Id") is not None:
        out["AV_BlackOilThermalData"] = row(con, "AV_BlackOilThermalData", "Id = ?", (bo["ThermalData_Id"],))
    return out


def copy_row(con, table, target_id, source_row):
    cols = [k for k in source_row if k not in META and not k.endswith("_Id")]
    con.execute(f'update "{table}" set ' + ", ".join(f'"{c}" = ?' for c in cols) + " where Id = ?",
                [source_row[c] for c in cols] + [target_id])
    return cols


def diff(a, b):
    keys = [k for k in (a or {}) if k not in META and not k.endswith("_Id")]
    return {k: {"original": a.get(k), "rebuilt": (b or {}).get(k)} for k in keys if a.get(k) != (b or {}).get(k)}


def case(path, tmp):
    p = prepare(path, tmp)
    out = {"level2": p["level2"], "notes": p["notes"], "steps": []}
    odb, bdb = os.path.join(tmp, "orig.db"), os.path.join(tmp, "rebuilt.db")
    extract_db(p["orig_path"], odb)
    entry = extract_db(p["built_path"], bdb)
    oc, bc = sqlite3.connect(odb), sqlite3.connect(bdb)
    orow, brow = hidden_rows(oc, p["orig_fluid"], p["flowlines"]), hidden_rows(bc, p["built_fluid"], p["flowlines"])
    out["hidden_differences"] = {k: diff(orow.get(k), brow.get(k)) for k in orow}
    bc.close(); oc.close()
    steps = [("A. rebuilt file reopened (level 2)", []),
             ("B. + pipe heat transfer (hidden table)", ["AV_PipeHeatTransfer"]),
             ("C. + pipe thermal properties (AV_PipeBase)", ["AV_PipeHeatTransfer", "AV_PipeBase"]),
             ("D. + fluid thermal data", ["AV_PipeHeatTransfer", "AV_PipeBase", "AV_BlackOilThermalData"]),
             ("E. + every other hidden flowline column", ["AV_PipeHeatTransfer", "AV_PipeBase", "AV_BlackOilThermalData",
                                                          "AV_Flowline"])]
    for label, tables in steps:
        work_db = os.path.join(tmp, "work.db"); shutil.copy2(bdb, work_db)
        con = sqlite3.connect(work_db)
        applied = []
        try:
            for key in orow:
                table = key.split(" ")[0]
                if table in tables and orow[key] and brow.get(key):
                    cols = copy_row(con, table, brow[key]["Id"], orow[key])
                    applied.append(f"{key}: {len(cols)} columns")
            con.commit()
        finally:
            con.close()
        wpath = os.path.join(tmp, f"work_{len(out['steps'])}.pips")
        replace_db(p["built_path"], entry, work_db, wpath)
        try:
            m = sa.open_model(wpath)
            try:
                st, b = run_pt(m, p["src"], p["cond"])
            finally:
                m.close()
            out["steps"].append({"step": label, "applied": applied, "state": st, "compare": compare_pt(p["o"], b)})
        except Exception as e:
            out["steps"].append({"step": label, "applied": applied, "error": f"{type(e).__name__}: {str(e)[:300]}"})
    return out


def main():
    root = sys.argv[1] if len(sys.argv) > 1 else r"D:\Program\Pipesim2023.1\Case Studies"
    results = {}
    for stem in PIPELINES:
        path = find(root, stem)
        print(f"\n===== {stem}")
        if not path:
            continue
        tmp = tempfile.mkdtemp(prefix="pipesim_heat_")
        try:
            r = case(path, tmp)
        except Exception as e:
            r = {"error": f"{type(e).__name__}: {e}", "trace": traceback.format_exc()[-2500:]}
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
        results[stem] = r
        if "error" in r:
            print("ERROR", r["error"]); print(r.get("trace", "")); continue
        print("hidden settings that differ (original / rebuilt):")
        for k, dd in r["hidden_differences"].items():
            for col, v in dd.items():
                print(f"   {k}.{col}: {v['original']} / {v['rebuilt']}")
        orig_row = {x["variable"]: x["original"] for x in r["level2"]}
        print(f" original:                                 loss {orig_row.get('SystemPressureLoss')}  outlet T "
              f"{orig_row.get('SystemOutletTemperature')}  liq {orig_row.get('OutletVolumeFlowrateLiquid')}  gas "
              f"{orig_row.get('OutletVolumeFlowrateGas')}")
        for s in [{"step": "level 2 (in memory)", "compare": r["level2"]}] + r["steps"]:
            if "error" in s:
                print(f" {s['step']:<45} ERROR {s['error']}"); continue
            row_ = {x["variable"]: x for x in s["compare"]}
            show = lambda v: (f"{row_[v]['rebuilt']} ({row_[v]['diff_pct']:+.2f} %)" if v in row_ else "-")
            print(f" {s['step']:<45} loss {show('SystemPressureLoss')}  outlet T {show('SystemOutletTemperature')}  "
                  f"liq {show('OutletVolumeFlowrateLiquid')}  gas {show('OutletVolumeFlowrateGas')}")
    json.dump(results, open(os.path.join(ROOT, "knowledge", "heat_transplant.json"), "w", encoding="utf-8"),
              indent=1, default=str)
    print("\nwritten knowledge/heat_transplant.json")


if __name__ == "__main__":
    main()
