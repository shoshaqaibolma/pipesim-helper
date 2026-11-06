"""
Real-PIPESIM end-to-end test of a study on a described project (no LLM): builds the smoke-test field and runs a
3-case separator-pressure sweep through executor.run, exactly as the agent would after the user approves.
  "D:\\Program\\Pipesim toolkit\\python.exe" tests\\real_project_study.py
"""
import io, json, os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import executor, study
from real_build_test import FIELD

sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)

spec = {"objective": "Separator pressure vs field liquid rate", "units": "METRIC", "model": {"source": "project"},
        "analysis": {"type": "sweep", "variables": [{"component_type": "Sink", "name": "Sep", "parameter": "Pressure",
                                                      "values": [10, 20, 30]}]}}
c = study.check(spec, project=FIELD)
print("check:", json.dumps(c)[:600])
if c["ready"]:
    r = executor.run(spec, progress=print, project=FIELD)
    print("\n".join(r["table"]))
    print("warnings:", r["warnings"], "| failed cases:", r["failed_cases"])
    print("outputs:", r["output_dir"], sorted(os.listdir(r["output_dir"])))
