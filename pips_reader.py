"""
Read-only access to the database inside a .pips file, for values the Python Toolkit does not expose
(pipe heat transfer / U-values, conductivities, fluid thermal data, per-pipe flow correlations ...).

A .pips file is a zip archive; one entry ("Model") is an SQLite database. Each object type has a table
"AV_<Type>" (AV_Flowline, AV_PipeHeatTransfer, AV_BlackOilThermalData ...). Rows have an "Id"; rows point to
related rows with "<Something>_Id" columns (AV_PipeBase.HeatTransfer_Id -> AV_PipeHeatTransfer.Id).

Values are stored in PIPESIM's internal units, which are SI: temperatures in K, lengths in m, pressures in Pa.
Known conversions are applied (see UNITS); everything else is reported as stored, with that caveat.
The file is never modified: it is copied to a temp folder and the database opened read-only.
"""
import json, math, os, re, shutil, sqlite3, tempfile, zipfile

META = {"Insert_Date", "Insert_User", "Produced_By", "SDAT_Label", "Update_Date", "Update_User", "Existence_Kind",
        "GUID", "Version"}
UNITS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "knowledge", "pips_units.json")


def _load_units():
    """Column -> conversion learned by tools/pips_units.py from the case studies (stored value vs toolkit value)."""
    try:
        return json.load(open(UNITS_FILE, encoding="utf-8")).get("columns", {})
    except Exception:
        return {}


# SI column -> display unit, by name (for columns the toolkit never shows, so no verified conversion exists)
NAME_UNITS = [(r"^(UCoeff|HeatTransferCoeff)", 1.0, "W/m2/K"), (r"Conductivity$", 1.0, "W/m/K"),
              (r"HeatCapacity$", 1.0, "J/kg/K"), (r"LatentHeat", 1.0, "J/kg"), (r"Density$", 1.0, "kg/m3"),
              (r"(InnerDiameter|OuterDiameter|WallThickness|Thickness|Roughness)$", 1000.0, "mm"),
              (r"(Length|Distance|Depth|Elevation\w*)$", 1.0, "m"), (r"Velocity$", 1.0, "m/s")]
FLAGS = re.compile(r"^(Is|Use|Include|Enter|Enable|Annulus\w*Flow$|Show)")


def convert(column, value):
    """(display value, unit, how) for a stored value."""
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return value, "", "as stored"
    if FLAGS.match(column) and value in (0, 1):
        return bool(value), "", "flag"
    learned = _load_units().get(column)
    if learned and math.isfinite(learned.get("scale", float("nan"))):
        return round(value * learned["scale"] + learned.get("offset", 0.0), 6), learned.get("unit", ""), "verified"
    for rx, scale, unit in NAME_UNITS:
        if re.search(rx, column):
            return round(value * scale, 6), unit, "SI by name"
    if re.search(r"Temperature", column) and 150 < value < 1000:
        return round(value - 273.15, 4), "degC", "K -> degC (SI temperature)"
    return value, "SI (as stored)", "as stored"


# everyday words -> the database's column names (learned from the case-study files, job 28/29)
SYNONYMS = {"u value": "UCoeff|UType|UValue", "u-value": "UCoeff|UType|UValue", "u": "UCoeff|UType|UValue",
            "heat transfer coefficient": "UCoeff|HeatTransfer", "heat transfer": "UCoeff|UType|HeatTransfer|Conductivity",
            "insulation": "UType|Insulat", "conductivity": "Conductivity", "heat capacity": "HeatCapacity",
            "specific heat": "HeatCapacity", "thermal": "Thermal|Conductivity|HeatCapacity|Enthalpy",
            "enthalpy": "Enthalpy|LatentHeat", "correlation": "Correlation", "roughness": "Roughness",
            "ambient": "Ambient", "burial": "Burial|Buried"}


class Pips:
    def __init__(self, path):
        if not os.path.exists(path):
            raise FileNotFoundError(path)
        self.path = path
        self.tmp = tempfile.mkdtemp(prefix="pips_read_")
        copy = os.path.join(self.tmp, "copy.pips")
        shutil.copy2(path, copy)
        db = os.path.join(self.tmp, "model.db")
        if zipfile.is_zipfile(copy):
            with zipfile.ZipFile(copy) as z:
                entry = next((i for i in z.infolist() if z.read(i)[:16].startswith(b"SQLite format 3")), None)
                if entry is None:
                    raise ValueError("no database found inside the .pips file")
                open(db, "wb").write(z.read(entry))
        else:
            shutil.copy2(copy, db)
        self.con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
        self.con.row_factory = sqlite3.Row
        self.tables = [r[0] for r in self.con.execute("select name from sqlite_master where type='table'")]
        self.tables = [t for t in self.tables if not re.search(r"View$|Diagram|Layout|Symbol", t)]   # GUI layout only
        self.cols = {t: [r[1] for r in self.con.execute(f'pragma table_info("{t}")')] for t in self.tables}

    def close(self):
        self.con.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()

    def _rows(self, table, where="", args=()):
        return [dict(r) for r in self.con.execute(f'select * from "{table}"' + (f" where {where}" if where else ""), args)]

    def _clean(self, table, r):
        out = {}
        for k, v in r.items():
            if k in META or k == "Id" or v is None or k.endswith("_Id"):
                continue
            val, unit, how = convert(k, v)
            out[k] = {"value": val, "unit": unit} if unit else val
        return out

    def heat_transfer_in_use(self, name):
        """Which U-value actually applies to a pipe: the one for its surroundings (air or water)."""
        fl = self._rows("AV_Flowline", "Name = ?", (name,)) if "AV_Flowline" in self.tables else []
        pb = self._rows("AV_PipeBase", "Name = ?", (name,)) if "AV_PipeBase" in self.tables else []
        if not pb or pb[0].get("HeatTransfer_Id") is None or "AV_PipeHeatTransfer" not in self.tables:
            return None
        ht = self._rows("AV_PipeHeatTransfer", "Id = ?", (pb[0]["HeatTransfer_Id"],))
        if not ht:
            return None
        ht = ht[0]
        side = (fl[0].get("AmbientFluidType") if fl else None) or "Air"
        side = "Water" if str(side).lower().startswith("water") else "Air"
        utype = ht.get(f"UType{side}") or ht.get("UType")
        u = ht.get(f"UCoeffUser{side}") if ht.get(f"UCoeffUser{side}") is not None else ht.get("UCoeffUser")
        out = {"surroundings": side, "u_value_set_as": utype,
               "pipe_wall_conductivity": {"value": ht.get("PipeConductivity"), "unit": "W/m/K"}}
        if str(utype) == "UserSupplied":
            out["u_value"] = {"value": u, "unit": "W/m2/K"}
        else:
            out["u_value"] = f"calculated by PIPESIM ({utype}); no user U-value applies"
        out["note"] = (f"The pipe is in {side.lower()}, so the {side.lower()}-side settings apply; the other side's "
                       "values in the file are not used.")
        return out

    def _target_table(self, table, column):
        """Table a <Base>_Id column points to: AV_<Base>, or the table ending in <Base> that shares the longest
        prefix with the current one (AV_BlackOilFluid.ThermalData_Id -> AV_BlackOilThermalData)."""
        base = column[:-3].lower()
        cands = [t for t in self.tables if t.lower().endswith(base) and "Id" in self.cols[t]]
        if not cands:
            return None
        common = lambda t: len(os.path.commonprefix([t.lower(), table.lower()]))
        return max(cands, key=lambda t: (common(t), t.lower() == f"av_{base}", -len(t)))

    def _linked(self, table, r):
        """Rows this row points to through <X>_Id columns (one level)."""
        out = {}
        for k, v in r.items():
            if not k.endswith("_Id") or v is None:
                continue
            t = self._target_table(table, k)
            if t:
                rows = self._rows(t, "Id = ?", (v,))
                if rows:
                    out[f"{k} -> {t}"] = self._clean(t, rows[0])
        return out

    def components(self, name):
        """Every row named `name`, with the rows it points to (heat transfer, thermal data, correlations)."""
        found = {}
        for t in self.tables:
            if "Name" not in self.cols[t]:
                continue
            for r in self._rows(t, "Name = ?", (name,)):
                found[f"{t} (Id {r.get('Id')})"] = {"values": self._clean(t, r), "linked": self._linked(t, r)}
        return found

    def search(self, keyword, name=""):
        """Columns or tables whose name matches keyword (regex, case-insensitive), with values per component."""
        rx = re.compile(SYNONYMS.get(keyword.strip().lower(), keyword.replace(" ", ".?")), re.I)
        hits = []
        for t in self.tables:
            cols = [c for c in self.cols[t] if rx.search(c)] if not rx.search(t) else \
                [c for c in self.cols[t] if c not in META and c != "Id" and not c.endswith("_Id")]
            if not cols:
                continue
            for r in self._rows(t):
                label = r.get("Name") or self._owner(t, r.get("Id")) or f"Id {r.get('Id')}"
                if name and name.lower() not in str(label).lower():
                    continue
                vals = {c: self._clean(t, {c: r[c]}).get(c) for c in cols if r.get(c) is not None}
                if vals:
                    hits.append({"table": t, "component": label, "values": vals})
        return hits

    def _owner(self, table, rid):
        """Name of the component that points to this row (e.g. which pipe uses this heat-transfer row)."""
        if rid is None:
            return None
        for t in self.tables:
            if "Name" not in self.cols[t]:
                continue
            for c in self.cols[t]:
                if c.endswith("_Id") and table.lower().endswith(c[:-3].lower()):
                    r = self.con.execute(f'select Name from "{t}" where "{c}" = ?', (rid,)).fetchone()
                    if r and r[0]:
                        return r[0]
        return None


def read_pips(path, component="", keyword="", limit=60):
    """Agent-facing: values stored in a .pips file. component: a name (e.g. "FL"); keyword: e.g. "heat", "U",
    "conductivity", "thermal", "correlation". Read-only."""
    with Pips(path) as p:
        out = {"file": os.path.basename(path),
               "units_note": "Converted from PIPESIM's stored SI units to METRIC (degC, bara, mm, sm3/d ...); "
                             "'SI (as stored)' marks values whose unit is not known beyond being SI."}
        if component:
            ht = p.heat_transfer_in_use(component)
            if ht:
                out["heat_transfer_in_use"] = ht
        if component and not keyword:
            out["component"] = p.components(component) or f"no object named {component!r}"
        else:
            hits = p.search(keyword or ".", component)
            if not hits and component:   # e.g. heat capacities belong to the fluid, not to the pipe
                hits = p.search(keyword or ".", "")
                if hits:
                    out["note"] = (f"nothing matched {keyword!r} on {component!r} itself; these are the matches in the "
                                   "whole file (e.g. the fluid the pipe carries)")
            out["matches"] = hits[:limit]
            if len(hits) > limit:
                out["truncated"] = f"{len(hits)} matches; narrow the keyword or give a component name"
            if not hits:
                out["note"] = f"no stored column matches {keyword!r} anywhere in this file"
        return out


if __name__ == "__main__":
    import sys
    print(json.dumps(read_pips(sys.argv[1], *(sys.argv[2:4])), indent=1, default=str)[:20000])
