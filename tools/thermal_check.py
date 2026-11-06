"""
Does the builder now reproduce the training pipelines? For TF_M2A/B/C, rebuild from the description three ways
and compare the same P/T profile with the original (temp copies only):
  1. builder without thermal data (as before job 32)
  2. builder writes PIPESIM's standard fluid thermal data
  3. + each flowline gets the U-value the original uses (read from the .pips with read_pips)
  "D:\\Program\\Pipesim toolkit\\python.exe" tools\\thermal_check.py "D:\\Program\\Pipesim2023.1\\Case Studies"
Writes knowledge/thermal_check.json.
"""
import json, os, shutil, sys, tempfile, traceback
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [ROOT, os.path.join(ROOT, "tools")]
from heat_transplant import prepare
from rebuild_compare import PIPELINES, find

VARIANTS = [("1. builder, no thermal data", False, False), ("2. + standard fluid thermal data", True, False),
            ("3. + U-value read from the original", True, True)]


def main():
    root = sys.argv[1] if len(sys.argv) > 1 else r"D:\Program\Pipesim2023.1\Case Studies"
    results = {}
    for stem in PIPELINES:
        path = find(root, stem)
        print(f"\n===== {stem}")
        results[stem] = []
        for label, thermal, u in VARIANTS:
            tmp = tempfile.mkdtemp(prefix="pipesim_thermal_")
            try:
                p = prepare(path, tmp, thermal=thermal, u_from_original=u)
                rows = {x["variable"]: x for x in p["level2"]}
                results[stem].append({"variant": label, "compare": p["level2"], "notes": p["notes"]})
                show = lambda v: f"{rows[v]['rebuilt']} ({rows[v]['diff_pct']:+.2f} %)" if v in rows else "-"
                print(f" {label:<40} loss {show('SystemPressureLoss')}  outlet T {show('SystemOutletTemperature')}  "
                      f"liq {show('OutletVolumeFlowrateLiquid')}  gas {show('OutletVolumeFlowrateGas')}")
                for n in p["notes"]:
                    print(f"      {n}")
            except Exception as e:
                results[stem].append({"variant": label, "error": f"{type(e).__name__}: {e}",
                                      "trace": traceback.format_exc()[-1500:]})
                print(f" {label}: ERROR {type(e).__name__}: {e}\n{traceback.format_exc()[-1500:]}")
            finally:
                shutil.rmtree(tmp, ignore_errors=True)
        if results[stem] and "compare" in results[stem][0]:
            o = {x["variable"]: x["original"] for x in results[stem][0]["compare"]}
            print(f" {'original':<40} loss {o.get('SystemPressureLoss')}  outlet T {o.get('SystemOutletTemperature')}  "
                  f"liq {o.get('OutletVolumeFlowrateLiquid')}  gas {o.get('OutletVolumeFlowrateGas')}")
    json.dump(results, open(os.path.join(ROOT, "knowledge", "thermal_check.json"), "w", encoding="utf-8"), indent=1)
    print("\nwritten knowledge/thermal_check.json")


if __name__ == "__main__":
    main()
