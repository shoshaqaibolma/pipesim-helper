"""
Learn how values are stored in the .pips database by comparing them with what the Python Toolkit reports
(METRIC units) for the same component and parameter, across the bundled case studies (temp copies, read-only).
For every column found both ways it fits  toolkit = stored * scale + offset  and records the toolkit's unit.
Writes knowledge/pips_units.json, used by pips_reader.py to convert stored values.
  "D:\\Program\\Pipesim toolkit\\python.exe" tools\\pips_units.py "D:\\Program\\Pipesim2023.1\\Case Studies"
"""
import json, os, shutil, statistics, sys, tempfile
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [ROOT, os.path.join(ROOT, "tools")]
from sixgill import definitions as d
import sixgill_adapter as sa
import pips_reader

TYPES = ["Flowline", "Source", "Sink", "BlackOilFluid", "Junction", "Choke", "TwoPhaseSeparator", "Pump",
         "Compressor", "Well"]
MAX_MODELS = 20


def model_files(root):
    out = []
    for dp, _, fs in os.walk(root):
        for f in fs:
            if f.lower().endswith(".pips"):
                out.append(os.path.join(dp, f))
    return sorted(out)[:MAX_MODELS]


def main():
    root = sys.argv[1] if len(sys.argv) > 1 else r"D:\Program\Pipesim2023.1\Case Studies"
    pairs = {}   # column -> list of (stored, toolkit, unit, table)
    for path in model_files(root):
        tmp = tempfile.mkdtemp(prefix="pips_units_")
        try:
            c = os.path.join(tmp, "m.pips"); shutil.copy2(path, c)
            p = pips_reader.Pips(c)
            m = sa.open_model(c)
            try:
                for t in TYPES:
                    table = f"AV_{t}"
                    if table not in p.tables:
                        continue
                    try:
                        names = [n for n in (m.find(**{t: d.ALL}) or []) if ":" not in n]
                    except Exception:
                        continue
                    for n in names:
                        try:
                            vals = m.get_values(**{t: n})
                            vals = next(iter(vals.values())) if vals and isinstance(next(iter(vals.values())), dict) else vals
                        except Exception:
                            continue
                        rows = p._rows(table, "Name = ?", (n,))
                        if not rows:
                            continue
                        r = rows[0]
                        for k, tv in (vals or {}).items():
                            sv = r.get(k)
                            if isinstance(tv, (int, float)) and isinstance(sv, (int, float)) and not isinstance(tv, bool) \
                                    and abs(sv) > 1e-12 and abs(tv) > 1e-12:
                                try:
                                    unit = str(m.describe(context=n, parameter=k).units)
                                except Exception:
                                    unit = ""
                                pairs.setdefault(k, []).append((sv, tv, unit, table))
            finally:
                m.close()
                p.close()
        except Exception as e:
            print(f"skip {os.path.basename(path)}: {type(e).__name__}: {str(e)[:150]}")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
        print(f"read {os.path.basename(path)}; columns so far {len(pairs)}")

    columns, report = {}, []
    for k, ps in sorted(pairs.items()):
        ps = [x for x in ps if all(map(lambda v: v == v and abs(v) != float("inf"), x[:2]))]
        if not ps:
            continue
        offsets = [tv - sv for sv, tv, _, _ in ps]
        scales = [tv / sv for sv, tv, _, _ in ps]
        unit = statistics.mode([u for *_, u, _ in ps]) if ps else ""
        if all(abs(o + 273.15) < 0.01 for o in offsets):
            fit = {"scale": 1.0, "offset": -273.15}
        elif all(s == s for s in scales) and max(scales) - min(scales) <= 1e-4 * max(abs(x) for x in scales):
            fit = {"scale": statistics.median(scales), "offset": 0.0}
        else:
            report.append(f"{k}: no single conversion ({len(ps)} samples, scales {min(scales):.4g}..{max(scales):.4g})")
            continue
        fit.update(unit=unit, samples=len(ps), tables=sorted({t for *_, t in ps}))
        columns[k] = fit
        report.append(f"{k}: toolkit = stored x {fit['scale']:.6g} {fit['offset']:+g}  [{unit}]  ({len(ps)} samples)")
    out = {"note": "toolkit (METRIC) value = stored value * scale + offset; learned from the bundled case studies",
           "columns": columns, "report": report}
    json.dump(out, open(os.path.join(ROOT, "knowledge", "pips_units.json"), "w", encoding="utf-8"), indent=1)
    print("\n".join(report))
    print("\nwritten knowledge/pips_units.json")


if __name__ == "__main__":
    main()
