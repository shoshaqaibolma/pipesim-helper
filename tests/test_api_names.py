"""
Check every sixgill name the code uses (P("Group", "CONST"), C(...), MC(...) and template aliases)
against the API recorded on the real PIPESIM install by tools/introspect.py (knowledge/api.json).
Without that file the test lists the names that still need verifying.
"""
import glob, json, os, re, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, "tests", "fake_sixgill"), ROOT]

used = set()
for f in glob.glob(os.path.join(ROOT, "*.py")):
    src = open(f, encoding="utf-8").read()
    used |= {("Parameters", g, c) for g, c in re.findall(r'\bP\("(\w+)",\s*"(\w+)"\)', src)}
    used |= {("Constants", g, c) for g, c in re.findall(r'\bC\("(\w+)",\s*"(\w+)"\)', src)}
    used |= {("ModelComponents", None, c) for c in re.findall(r'\bMC\("(\w+)"\)', src)}
from builder import TEMPLATES
for t in TEMPLATES.values():
    used |= {("Parameters", g, c) for _, _, (g, c) in t["aliases"].values()}

api_path = os.path.join(ROOT, "knowledge", "api.json")
if not os.path.exists(api_path):
    print(f"SKIPPED: knowledge/api.json not recorded yet. {len(used)} names to verify:")
    for u in sorted(used, key=str):
        print("  ", ".".join(x for x in u if x))
    sys.exit(0)

api = json.load(open(api_path, encoding="utf-8"))
missing = []
for kind, g, c in sorted(used, key=str):
    if kind == "ModelComponents":
        ok = c in (api.get("ModelComponents") or {})
    else:
        ok = c in ((api.get(kind) or {}).get(g) or {})
    if not ok:
        near = [k for k in ((api.get(kind) or {}).get(g) or {})][:40] if g else []
        missing.append(f"{kind}.{g + '.' if g else ''}{c}" + (f"   (group has: {near})" if near else
                       ("   (no such group)" if g and g not in (api.get(kind) or {}) else "")))
if missing:
    print("NAMES NOT IN THIS PIPESIM VERSION:\n  " + "\n  ".join(missing))
    sys.exit(1)
print(f"all {len(used)} sixgill names exist in knowledge/api.json")
