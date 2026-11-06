"""
Before/after evaluation of the agent on the real PC (PIPESIM + llama-server).

Runs every scenario in tests/scripts under each condition in CONDITIONS (plain / + knowledge / + structured), scores
each conversation automatically from the study outputs it produced, and writes knowledge/eval_<condition>.json and
knowledge/eval_summary.md.

  "D:\\Program\\Pipesim toolkit\\python.exe" tests\\real_eval.py [scenario ...]
"""
import csv, io, json, os, re, subprocess, sys, tempfile, time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
from real_agent_test import healthy  # noqa: E402

SCENARIOS = ["field_project", "gaslift_nodal", "gaslift_allocation", "uncertainty", "debottleneck",
             "pipeline_sizing", "choke_sizing", "water_rise"]
HELD_OUT = {"water_rise"}   # no recipe written for it (a choke recipe was added after job 23)
CONDITIONS = {   # before: plain agent; knowledge: + recipes and number check; structured: + constrained extraction
    "before": {"PIPESIM_AGENT_KNOWLEDGE": "0", "PIPESIM_NUMBER_GUARD": "0", "PIPESIM_AGENT_STRUCTURED": "0"},
    "knowledge": {"PIPESIM_AGENT_KNOWLEDGE": "1", "PIPESIM_NUMBER_GUARD": "1", "PIPESIM_AGENT_STRUCTURED": "0"}}
# add {"structured": {..., "PIPESIM_AGENT_STRUCTURED": "1"}} to test the experimental mode (0/8 in job 22)


# ---------- reading a study output folder
def load_run(d):
    r = {"dir": d}
    for name in ("spec", "summary", "project"):
        p = os.path.join(d, name + ".json")
        r[name] = json.load(open(p, encoding="utf-8")) if os.path.exists(p) else {}
    p = os.path.join(d, "results.csv")
    r["rows"] = list(csv.DictReader(open(p, encoding="utf-8-sig"))) if os.path.exists(p) else []
    return r


def settings(case):
    """'Trunk.InnerDiameter=203, SEP.Pressure=8' -> {'InnerDiameter': 203.0, 'Pressure': 8.0}"""
    out = {}
    for part in str(case).split(","):
        m = re.search(r"([\w:\-]+)\.(\w+)\s*(?:low|high)?=\s*(-?[\d.]+)", part.strip())
        if m:
            out[m.group(2)] = float(m.group(3))
            out[m.group(1) + "." + m.group(2)] = float(m.group(3))
    return out


def params(run):
    return [v.get("parameter") for v in run["spec"].get("analysis", {}).get("variables", [])]


def primary(run):
    s = run["summary"]
    return s.get("summary", {}).get(s.get("primary"), {})


def runs_of(runs, typ, param=None):
    return [r for r in runs if r["summary"].get("type") == typ and (param is None or param in params(r))]


def near(a, b, tol=1e-6):
    return a is not None and abs(a - b) <= tol + 1e-9 * abs(b)


# ---------- scoring: (study completed with the right analysis, correct key answer, note)
def score(name, runs):
    if name == "field_project":
        rs = runs_of(runs, "sweep", "Pressure")
        if not rs:
            return False, False, "no separator-pressure sweep"
        hi = settings(primary(rs[-1]).get("highest", {}).get("case")).get("Pressure")
        return True, hi is not None and hi <= 10.5, f"most oil at separator {hi} bara (expected the lowest, 10)"
    if name == "gaslift_nodal":
        nod, sw = runs_of(runs, "nodal"), runs_of(runs, "sweep", "GasRate")
        if not (nod and sw):
            return False, False, f"nodal run: {bool(nod)}, gas lift sweep: {bool(sw)}"
        best = settings(primary(sw[-1]).get("highest", {}).get("case")).get("GasRate")
        # the optimum is about 0.1 mmsm3/d; "0 to 0.2 in 5 steps" may be read as steps of 0.04 (0.08 or 0.12 best)
        return True, best is not None and 0.075 <= best <= 0.125, f"best lift rate {best} mmsm3/d (expected about 0.1)"
    if name == "gaslift_allocation":
        rs = runs_of(runs, "optimize", "GasRate")
        if not rs:
            return False, False, "no optimize run"
        best = (rs[-1]["summary"].get("summary", {}).get("optimum") or {}).get("best") or {}
        st = {k.split(":")[0].split(".")[0]: v for k, v in (best.get("settings") or {}).items()}
        ok = near(st.get("W1"), 0.05, 1e-3) and near(st.get("W2"), 0.1, 1e-3)
        return True, ok, f"best split {st} (expected W1 0.05, W2 0.1)"
    if name == "uncertainty":
        rs = runs_of(runs, "tornado")
        if not rs:
            return False, False, "no tornado run"
        rank = [x.get("variable") for x in primary(rs[-1]).get("ranking", [])]
        return True, bool(rank) and "WaterCut" in rank[0], f"ranking {rank} (expected water cut first)"
    if name == "debottleneck":
        rs = runs_of(runs, "grid")
        if not rs:
            return False, False, "no grid run"
        pct = primary(rs[-1]).get("change_vs_base_pct", {})
        val = {}
        for case, v in pct.items():
            s = settings(case)
            val[(s.get("InnerDiameter"), s.get("Pressure"))] = v
        big, low = val.get((203.0, 12.0)), val.get((152.0, 8.0))
        ok = big is not None and low is not None and big > low
        return True, ok, f"203 mm @12 bara: {big} %, 152 mm @8 bara: {low} % (expected 203 mm better)"
    if name == "pipeline_sizing":
        rs = runs_of(runs, "sweep", "InnerDiameter")
        if not rs:
            return False, False, "no diameter sweep"
        r = rs[-1]
        srcs = [s.get("name") for s in r["project"].get("sources", [])]
        cols = [c for c in (r["rows"][0].keys() if r["rows"] else []) if any(c.startswith(f"{s} pressure") for s in srcs)]
        lab = [c for c in (r["rows"][0].keys() if r["rows"] else []) if c.endswith(".InnerDiameter")]
        if not (cols and lab):
            return True, False, "inlet pressure column not found"
        ok_d = sorted(float(row[lab[0]]) for row in r["rows"][1:]
                      if row.get(cols[0]) not in (None, "") and float(row[cols[0]]) <= 90)
        smallest = ok_d[0] if ok_d else None
        return True, near(smallest, 254, 0.5), f"smallest diameter with inlet <= 90 bara: {smallest} (expected 254)"
    if name == "choke_sizing":
        rs = runs_of(runs, "sweep", "BeanSize")
        if not rs:
            return False, False, "no choke-size sweep"
        hi = settings(primary(rs[-1]).get("highest", {}).get("case")).get("BeanSize")
        vals = [v for v in (rs[-1]["spec"]["analysis"]["variables"][0].get("values") or [])]
        top = max(vals) if vals else 32
        return True, near(hi, top, 0.01), f"most oil at {hi} mm (expected the largest choke, {top} mm)"
    if name == "water_rise":
        rs = runs_of(runs, "sweep", "WaterCut")
        if not rs:
            return False, False, "no water-cut sweep"
        lo = settings(primary(rs[-1]).get("lowest", {}).get("case")).get("WaterCut")
        nf = rs[-1]["summary"].get("summary", {}).get("not_flowing", {}).get("cases", {})
        dead = sorted(settings(c).get("WaterCut") for c in nf)
        ok = near(lo, 70, 0.01) or (bool(dead) and max(dead) >= 69.9)   # least oil at 70 %, or no flow at 70 %
        return True, ok, f"least oil at water cut {lo} %, wells not flowing at {dead} % (expected the least at 70)"
    return False, False, "unknown scenario"


# ---------- one conversation
def run_one(name, env_extra, tmp):
    script = os.path.join(HERE, "scripts", name + ".txt")
    log = os.path.join(tmp, f"{name}_{''.join(env_extra.values())}.jsonl")
    runs_dir = os.path.join(ROOT, "runs")
    before = set(os.listdir(runs_dir)) if os.path.isdir(runs_dir) else set()
    t0 = time.time()
    env = dict(os.environ, PYTHONIOENCODING="utf-8", **env_extra)
    try:
        p = subprocess.run([sys.executable, os.path.join(ROOT, "agent.py"), "--script", script, "--log", log],
                           cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace", env=env,
                           timeout=1500)
        code = p.returncode
    except subprocess.TimeoutExpired:
        code = "timeout"
    dt = time.time() - t0
    new = sorted(set(os.listdir(runs_dir)) - before) if os.path.isdir(runs_dir) else []
    runs = [load_run(os.path.join(runs_dir, d)) for d in new]
    m = {"scenario": name, "held_out": name in HELD_OUT, "seconds": round(dt), "exit": code, "runs": len(runs),
         "tool_calls": 0, "checker_errors": 0, "json_retries": 0, "model_unreachable": False,
         "unverified_numbers": [], "numbers_flagged_after_rewrite": [], "replies": []}
    for line in open(log, encoding="utf-8") if os.path.exists(log) else []:
        e = json.loads(line)
        if "tool" in e:
            t = e["tool"]
            if t == "(retry)":
                m["json_retries"] += 1
                continue
            if t in ("(number check)", "(number audit)"):
                try:
                    res = json.loads(e["result"])
                except Exception:
                    res = {}
                m["unverified_numbers"] += res.get("unverified", [])
                m["numbers_flagged_after_rewrite"] += res.get("still_unverified", res.get("unverified", []))
                continue
            if t.startswith("("):
                if t == "(extraction skipped)":
                    m["extraction_skipped"] = m.get("extraction_skipped", 0) + 1
                continue
            m["tool_calls"] += 1
            try:
                res = json.loads(e["result"])
                if isinstance(res, dict) and (res.get("errors") or res.get("error")):
                    m["checker_errors"] += 1
            except Exception:
                pass
        elif "agent" in e:
            m["replies"].append(e["agent"].strip()[:1200])
            if "could not reach the model" in e["agent"]:
                m["model_unreachable"] = True
    m["completed"], m["correct"], m["note"] = score(name, runs)
    m["run_dirs"] = [r["dir"] for r in runs]
    return m


def table(results):
    lines = ["| scenario | condition | study done | correct answer | tool calls | checker errors | JSON retries | "
             "invented numbers (first reply) | still flagged | time s |", "|" + "---|" * 10]
    for name in SCENARIOS:
        for cond in CONDITIONS:
            m = results.get(cond, {}).get(name)
            if not m:
                continue
            lines.append(f"| {name}{' (held out)' if m['held_out'] else ''} | {cond} | {'yes' if m['completed'] else 'NO'} | "
                         f"{'yes' if m['correct'] else 'NO'} | {m['tool_calls']} | {m['checker_errors']} | "
                         f"{m['json_retries']} | {len(m['unverified_numbers'])} | "
                         f"{len(m['numbers_flagged_after_rewrite']) if cond != 'before' else '-'} | {m['seconds']} |")
    lines.append("")
    for cond, res in results.items():
        n = len(res)
        drops = [n for n, m in res.items() if m.get("model_unreachable")]
        if drops:
            lines.append(f"**{cond}**: model server dropped during {drops} (counted as failures)")
        lines.append(f"**{cond}**: studies done {sum(m['completed'] for m in res.values())}/{n}, correct answers "
                     f"{sum(m['correct'] for m in res.values())}/{n}, invented numbers in replies "
                     f"{sum(len(m['unverified_numbers']) for m in res.values())}"
                     + (f" (left after rewrite: {sum(len(m['numbers_flagged_after_rewrite']) for m in res.values())})"
                        if cond != "before" else "")
                     + f", checker errors {sum(m['checker_errors'] for m in res.values())}, "
                     f"time {sum(m['seconds'] for m in res.values()) // 60} min")
    lines.append("")
    for cond, res in results.items():
        for name, m in res.items():
            lines.append(f"- {cond} / {name}: {m['note']}")
    return "\n".join(lines)


class Server:
    """llama-server, started fresh for every conversation (as real_agent_test.py does: in job 19 one long-lived
    server vanished after about 3 minutes without an error in its log)."""

    def __init__(self, tmp):
        self.tmp, self.proc, self.n, self.log = tmp, None, 0, None

    def start(self):
        self.stop()
        self.n += 1
        self.log = os.path.join(self.tmp, f"llama_{self.n}.log")
        self.proc = subprocess.Popen(["cmd", "/c", os.path.join(ROOT, "start_llm.bat")], cwd=ROOT,
                                     stdout=open(self.log, "w"), stderr=subprocess.STDOUT)
        for _ in range(180):
            if healthy() or self.proc.poll() is not None:
                break
            time.sleep(1)
        return healthy()

    def tail(self, n=20):
        return "".join(open(self.log, errors="replace").readlines()[-n:]) if self.log and os.path.exists(self.log) else ""

    def stop(self):
        if self.proc is not None:
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(self.proc.pid)], capture_output=True)
            self.proc = None
            for _ in range(30):
                if not healthy():
                    break
                time.sleep(1)


def main():
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True)
    names = sys.argv[1:] or SCENARIOS
    tmp = tempfile.mkdtemp(prefix="pipesim_eval_")
    if healthy():
        print("a llama-server is already running on port 8080; using it (it is not restarted between scenarios)")
        server = None
    else:
        server = Server(tmp)
    results = {}
    try:
        for cond, env in CONDITIONS.items():
            results[cond] = {}
            for name in names:
                for attempt in (1, 2):
                    if server is not None and not server.start():
                        print("LLAMA-SERVER DID NOT START\n" + server.tail(25))
                        return
                    m = run_one(name, env, tmp)
                    m["attempt"] = attempt
                    if not m["model_unreachable"]:
                        break
                    m["llama_log_tail"] = server.tail() if server else ""
                    print(f"{cond} {name}: model server dropped (attempt {attempt}); log tail:\n{m['llama_log_tail']}")
                results[cond][name] = m
                print(f"{cond:6s} {name:20s} done={m['completed']} correct={m['correct']} tools={m['tool_calls']} "
                      f"invented={m['unverified_numbers']} {m['seconds']}s :: {m['note']}")
                json.dump(results[cond], open(os.path.join(ROOT, "knowledge", f"eval_{cond}.json"), "w",
                                              encoding="utf-8"), indent=1, default=str)
    finally:
        md = table(results)
        open(os.path.join(ROOT, "knowledge", "eval_summary.md"), "w", encoding="utf-8").write(md + "\n")
        print("\n" + md)
        if server is not None:
            server.stop()
            print("\n(llama-server stopped)")


if __name__ == "__main__":
    main()
