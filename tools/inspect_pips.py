"""
Look inside .pips files for settings the Python Toolkit does not expose (heat transfer, thermal properties ...).
Works on temp copies only. For each training pipeline it inspects the original and a model rebuilt from its
description, finds what kind of file .pips is (zip / SQLite / text), and prints every entry that mentions heat
transfer, U-value, insulation, coating, burial, conductivity, heat capacity, enthalpy or temperature, side by side.
  "D:\\Program\\Pipesim toolkit\\python.exe" tools\\inspect_pips.py "D:\\Program\\Pipesim2023.1\\Case Studies"
Writes knowledge/pips_inspect.json.
"""
import json, os, re, shutil, sqlite3, sys, tempfile, zipfile
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [ROOT, os.path.join(ROOT, "tools")]

KEYS = re.compile(r"heat|uvalue|u[-_ ]?value|insulat|coating|burial|buried|conductiv|capacity|enthalp|thermal|"
                  r"temperature|ambient|joule|thomson|correlation", re.I)
MAX_HITS = 400


def kind_of(path):
    if zipfile.is_zipfile(path):
        return "zip"
    head = open(path, "rb").read(16)
    if head.startswith(b"SQLite format 3"):
        return "sqlite"
    return f"unknown (first bytes {head[:8]!r})"


def text_hits(name, data, hits):
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        try:
            text = data.decode("utf-16")
        except UnicodeDecodeError:
            return
    # XML/JSON-ish: report attribute or element names with their values
    for m in re.finditer(r"<([\w:.-]+)[^>]*>([^<]{0,80})</\1>|([\w:.-]+)=\"([^\"]{0,80})\"|\"([\w .-]+)\"\s*:\s*([^,}\]]{0,80})",
                         text):
        key = m.group(1) or m.group(3) or m.group(5)
        val = m.group(2) if m.group(1) else (m.group(4) if m.group(3) else m.group(6))
        if key and KEYS.search(key) and len(hits) < MAX_HITS:
            hits.append({"where": name, "key": key, "value": (val or "").strip()})


def inspect(path):
    out = {"kind": kind_of(path), "entries": [], "hits": []}
    if out["kind"] == "zip":
        with zipfile.ZipFile(path) as z:
            for info in z.infolist():
                out["entries"].append({"name": info.filename, "size": info.file_size})
                if info.file_size < 50_000_000:
                    data = z.read(info)
                    if data[:16].startswith(b"SQLite format 3"):
                        tmp = tempfile.mktemp(suffix=".db")
                        open(tmp, "wb").write(data)
                        out["hits"] += sqlite_hits(tmp, info.filename)
                        os.remove(tmp)
                    else:
                        text_hits(info.filename, data, out["hits"])
    elif out["kind"] == "sqlite":
        out["hits"] = sqlite_hits(path, "(db)")
    else:
        text_hits("(file)", open(path, "rb").read(), out["hits"])
    return out


def sqlite_hits(path, where):
    hits = []
    con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        tables = [r[0] for r in con.execute("select name from sqlite_master where type='table'")]
        for t in tables:
            cols = [r[1] for r in con.execute(f'pragma table_info("{t}")')]
            hot = [c for c in cols if KEYS.search(c)]
            if KEYS.search(t) or hot:
                rows = con.execute(f'select * from "{t}" limit 20').fetchall()
                for r in rows:
                    rec = dict(zip(cols, r))
                    show = {c: rec[c] for c in (cols if KEYS.search(t) else hot + [c for c in cols if c.lower() in ("name", "id")])}
                    hits.append({"where": f"{where}:{t}", "key": t, "value": json.dumps(show, default=str)[:400]})
    finally:
        con.close()
    return hits


def main():
    root = sys.argv[1] if len(sys.argv) > 1 else r"D:\Program\Pipesim2023.1\Case Studies"
    from rebuild_compare import PIPELINES, find
    import gap_study
    results = {}
    for stem in PIPELINES:
        path = find(root, stem)
        print(f"\n===== {stem}: {path}")
        if not path:
            continue
        tmp = tempfile.mkdtemp(prefix="pipesim_inspect_")
        try:
            c = os.path.join(tmp, "orig.pips"); shutil.copy2(path, c)
            o = inspect(c)
            # a rebuilt model saved to disk, for comparison
            reb = None
            try:
                import sixgill_adapter as sa, netbuilder, project as prj
                # reuse the gap study's conversion by running its case() and keeping the file
                orig_case = gap_study.case
                saved = {}
                def keep(p, t):
                    r = orig_case(p, t)
                    if os.path.exists(os.path.join(t, "rebuilt.pips")):
                        shutil.copy2(os.path.join(t, "rebuilt.pips"), os.path.join(tmp, "rebuilt_kept.pips"))
                    return r
                keep(path, tempfile.mkdtemp(prefix="pipesim_inspect_b_"))
                kept = os.path.join(tmp, "rebuilt_kept.pips")
                reb = inspect(kept) if os.path.exists(kept) else None
            except Exception as e:
                print(f"rebuilt model not inspected: {type(e).__name__}: {e}")
            results[stem] = {"original": o, "rebuilt": reb}
            print(f"file type: {o['kind']}; entries: {[e['name'] for e in o['entries']][:30]}")
            okeys = {(h["key"], h["value"]) for h in o["hits"]}
            rkeys = {(h["key"], h["value"]) for h in (reb or {}).get("hits", [])}
            print(f"heat/thermal entries: original {len(o['hits'])}, rebuilt {len(reb['hits']) if reb else '-'}")
            print("  only in the ORIGINAL (or different value):")
            for h in o["hits"]:
                if (h["key"], h["value"]) not in rkeys:
                    print(f"    {h['where']} | {h['key']} = {h['value']}")
            if reb:
                print("  only in the REBUILT (or different value):")
                for h in reb["hits"]:
                    if (h["key"], h["value"]) not in okeys:
                        print(f"    {h['where']} | {h['key']} = {h['value']}")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
    json.dump(results, open(os.path.join(ROOT, "knowledge", "pips_inspect.json"), "w", encoding="utf-8"), indent=1,
              default=str)
    print("\nwritten knowledge/pips_inspect.json")


if __name__ == "__main__":
    main()
