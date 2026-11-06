"""
Write settings the Python Toolkit cannot set into a .pips file we built ourselves (never into a user's file).

Why: a model created through the toolkit leaves the black-oil THERMAL DATA empty (heat capacities,
conductivities) and gives every pipe a calculated "Insulated" U-value. Models made in the PIPESIM GUI, like
the case studies, carry PIPESIM's standard thermal data. In job 29, writing those values into our rebuilt
pipelines made them match the case studies to 0.01 % (pressure loss, rates and outlet temperature).

The .pips file is a zip whose "Model" entry is an SQLite database (docs/PIPS_FILE.md). The model must be closed
while this runs. Values are written in the database's SI units.
"""
import os, shutil, sqlite3, tempfile, zipfile

# PIPESIM's standard black-oil thermal data, as stored in every bundled case-study fluid (job 29), SI units.
# EnthalpyCalcMethod is NULL in those fluids (toolkit-created fluids get "Method2009").
STANDARD_THERMAL = {"OilHeatCapacity": 1884.06, "GasHeatCapacity": 2302.74, "WaterHeatCapacity": 4186.8,
                    "OilConductivity": 0.1384, "GasConductivity": 0.0346, "WaterConductivity": 0.6055,
                    "LatentHeatOfVaporization": 325638.99, "EnthalpyCalcMethod": None}


def _db_entry(z):
    for info in z.infolist():
        if z.read(info)[:16].startswith(b"SQLite format 3"):
            return info
    raise ValueError("no database inside the .pips file")


def _columns(con, table):
    return {r[1] for r in con.execute(f'pragma table_info("{table}")')}


def apply(path, fluids=(), pipes=None):
    """fluids: black-oil fluid names that get the standard thermal data.
    pipes: {flowline name: {"u_value": W/m2/K}} -> user-supplied U-value on the side of its surroundings.
    Returns a report {"fluids": [...], "pipes": [...], "skipped": [...]}. Edits `path` in place."""
    pipes = pipes or {}
    report = {"fluids": [], "pipes": [], "skipped": []}
    tmp = tempfile.mkdtemp(prefix="pips_write_")
    try:
        db = os.path.join(tmp, "model.db")
        with zipfile.ZipFile(path) as z:
            entry = _db_entry(z)
            open(db, "wb").write(z.read(entry))
            infos = z.infolist()
            others = {i.filename: z.read(i) for i in infos if i.filename != entry.filename}
        con = sqlite3.connect(db)
        try:
            tcols = _columns(con, "AV_BlackOilThermalData") if fluids else set()
            for name in fluids:
                r = con.execute('select ThermalData_Id from "AV_BlackOilFluid" where Name = ?', (name,)).fetchone()
                if not r or r[0] is None:
                    report["skipped"].append(f"fluid {name}: no thermal data row")
                    continue
                vals = {k: v for k, v in STANDARD_THERMAL.items() if k in tcols}
                con.execute('update "AV_BlackOilThermalData" set ' + ", ".join(f'"{k}" = ?' for k in vals) +
                            " where Id = ?", [*vals.values(), r[0]])
                report["fluids"].append(name)
            for name, spec in pipes.items():
                if spec.get("u_value") is None:
                    continue
                pb = con.execute('select HeatTransfer_Id from "AV_PipeBase" where Name = ?', (name,)).fetchone()
                fl = con.execute('select AmbientFluidType from "AV_Flowline" where Name = ?', (name,)).fetchone()
                if not pb or pb[0] is None:
                    report["skipped"].append(f"pipe {name}: no heat transfer row")
                    continue
                side = "Water" if fl and str(fl[0] or "").lower().startswith("water") else "Air"
                hcols = _columns(con, "AV_PipeHeatTransfer")
                vals = {f"UType{side}": "UserSupplied", f"UCoeffUser{side}": float(spec["u_value"]),
                        "IsUCalculated": 0}
                vals = {k: v for k, v in vals.items() if k in hcols}
                con.execute('update "AV_PipeHeatTransfer" set ' + ", ".join(f'"{k}" = ?' for k in vals) +
                            " where Id = ?", [*vals.values(), pb[0]])
                report["pipes"].append(f"{name}: U = {spec['u_value']} W/m2/K ({side.lower()} side)")
            con.commit()
        finally:
            con.close()
        out = os.path.join(tmp, "out.pips")
        with zipfile.ZipFile(out, "w") as zout:
            for info in infos:
                data = open(db, "rb").read() if info.filename == entry.filename else others[info.filename]
                zout.writestr(info, data, compress_type=info.compress_type)
        shutil.copy2(out, path)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return report
