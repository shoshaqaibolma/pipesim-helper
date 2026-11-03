"""Run this first: checks that sixgill imports and that a model opens, summarizes and simulates without the LLM."""
import json, sys
import pipesim_tools as pt

path = sys.argv[1] if len(sys.argv) > 1 else input("Path to a test .pips model: ").strip('" ')
for name, args in [("open_model", {"path": path}), ("model_summary", {}),
                   ("run_network_simulation", {}), ("close_model", {})]:
    print(f"\n== {name}")
    print(json.dumps(pt.call(name, args), indent=1, default=str)[:3000])
