"""Crash isolation with the fake sixgill: a native crash or a hang on one case marks only that case FAILED, and the
study finishes the other cases in a fresh process.  python tests/test_isolation.py"""
import os, shutil, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [HERE, os.path.join(HERE, "fake_sixgill"), os.path.dirname(HERE)]
import executor
from test_netbuilder import FIELD   # noqa: E402

SPEC = {"objective": "Separator pressure vs field rate", "units": "METRIC", "model": {"source": "project"},
        "analysis": {"type": "sweep", "variables": [{"component_type": "Sink", "name": "Sep", "parameter": "Pressure",
                                                      "values": [10, 20, 30]}]}}


def status(r):
    head = r["table"][0].split(" | ")
    i, c = head.index("_status"), head.index("case")
    return {row.split(" | ")[c]: row.split(" | ")[i] for row in r["table"][1:]}


def run(env, **kw):
    msgs = []
    os.environ.pop("PIPESIM_TEST_CRASH_CASE", None); os.environ.pop("PIPESIM_TEST_HANG_CASE", None)
    os.environ.update(env)
    try:
        r = executor.run_isolated(SPEC, progress=msgs.append, project=FIELD, **kw)
    finally:
        os.environ.pop("PIPESIM_TEST_CRASH_CASE", None); os.environ.pop("PIPESIM_TEST_HANG_CASE", None)
    shutil.rmtree(r["output_dir"], ignore_errors=True)
    return r, msgs


# 1. normal run in the child: same results as in-process
r, msgs = run({})
s = status(r)
assert len(s) == 4 and not r["failed_cases"] and all(not v.startswith("FAILED") for v in s.values()), s
assert any("case 2/4" in m for m in msgs), msgs

# 2. the engine crashes (process exits) on one case: that case FAILED, the others have results
r, msgs = run({"PIPESIM_TEST_CRASH_CASE": "Sep.Pressure=20"})
s = status(r)
assert r["failed_cases"] == ["Sep.Pressure=20"], r["failed_cases"]
assert s["Sep.Pressure=20"].startswith("FAILED: PIPESIM stopped unexpectedly (exit code 3)"), s
assert not s["Sep.Pressure=30"].startswith("FAILED") and not s["base"].startswith("FAILED"), s
assert any("restarting PIPESIM" in m for m in msgs), msgs

# 3. the engine hangs on one case: stopped after the timeout, marked FAILED, study continues
r, msgs = run({"PIPESIM_TEST_HANG_CASE": "Sep.Pressure=30"}, case_timeout=4)
s = status(r)
assert r["failed_cases"] == ["Sep.Pressure=30"] and "did not answer for 4 s" in s["Sep.Pressure=30"], s

# 4. a crash on the base case cannot be worked around: a clear error instead of partial results
try:
    run({"PIPESIM_TEST_CRASH_CASE": "base"}); raise AssertionError("expected an error")
except RuntimeError as e:
    assert "on case base" in str(e), e

# 5. an ordinary error inside the study still comes back as an error (as with executor.run)
bad = dict(SPEC, analysis={"type": "pt_profile", "producer": "NoSuchWell"})
try:
    executor.run_isolated(bad, progress=lambda t: None, project=FIELD); raise AssertionError("expected an error")
except RuntimeError as e:
    assert "NoSuchWell" in str(e) or "Error" in str(e), e

print("isolation: crash on one case -> FAILED, rest completed; hang -> stopped after timeout; base crash and "
      "study errors reported")
print("\nALL OK")
