"""
Deterministic study executor: takes an approved spec, runs every case in PIPESIM, and writes
CSV, charts and a report. The LLM never drives individual runs, so a 300-case grid is as reliable as one run.
"""
import csv, datetime, itertools, json, os, shutil
from sixgill.pipesim import Model
from sixgill import definitions as d
import study
from builder import BUILDERS, TEMPLATES

RUNS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "runs")


def _sv(name):
    return getattr(d.SystemVariables, name, name)


def _lookup(table, var, comp):
    """sixgill result tables are nested dicts. Accept either [var][comp] or [comp][var]."""
    if not table:
        return None
    for a, b in ((var, comp), (comp, var)):
        try:
            return table[a][b]
        except (KeyError, TypeError, IndexError):
            pass
    return None


def _producers(model, spec):
    if spec["model"]["source"] == "new":
        return TEMPLATES[spec["model"]["template"]]["producers"]
    names = []
    for t in ("Well", "Source"):
        try:
            names += list(model.find(**{t: d.ALL}) or [])
        except Exception:
            pass
    return names


def _kpis(model, spec):
    if spec.get("kpis"):
        return spec["kpis"]
    return [{"component": p, "variable": v, "label": f"{p} {v}"} for p in _producers(model, spec)
            for v in study.DEFAULT_KPI_VARS]


def _run_case(model, kpis):
    r = model.tasks.networksimulation.run(system_variables=[_sv(k["variable"]) for k in kpis])
    row = {}
    for k in kpis:
        val = None
        for tbl in (getattr(r, "node", None), getattr(r, "system", None)):
            val = _lookup(tbl, _sv(k["variable"]), k["component"])
            if val is not None:
                break
        row[k.get("label") or f"{k['component']} {k['variable']}"] = val
    row["_status"] = str(getattr(r, "state", "ok"))
    return row


def _pt_parameters(conditions):
    """Translate friendly P/T conditions into the sixgill parameters dict, telling PIPESIM what to calculate."""
    P = getattr(d.Parameters, "PTProfileSimulation", None)
    C = getattr(d.Constants, "CalculatedVariable", None)
    out = {}
    for k, v in conditions.items():
        out[getattr(P, study.PT_CONDITIONS[k], None) or "".join(w.title() for w in k.split("_"))] = v
    if P is not None and C is not None and hasattr(P, "CALCULATEDVARIABLE"):
        calc = "FLOWRATE" if "outlet_pressure" in conditions else "OUTLETPRESSURE"
        if hasattr(C, calc):
            out[P.CALCULATEDVARIABLE] = getattr(C, calc)
    if "liquid_flowrate" in conditions or "gas_flowrate" in conditions:
        FT = getattr(d.Constants, "FlowRateType", None)
        kind = "LIQUIDFLOWRATE" if "liquid_flowrate" in conditions else "GASFLOWRATE"
        if P is not None and FT is not None and hasattr(P, "FLOWRATETYPE") and hasattr(FT, kind):
            out[P.FLOWRATETYPE] = getattr(FT, kind)
    return out


def _set(model, ref, value):
    ctype, name, param = ref
    model.set_value(**{ctype: name}, parameter=param, value=value)


def _get(model, ref):
    ctype, name, param = ref
    return model.get_value(**{ctype: name}, parameter=param)


def _chart(path, x, ys, xlabel, title):
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        return None
    fig, ax = plt.subplots(figsize=(7, 4.2))
    for label, vals in ys.items():
        ax.plot(x, vals, marker="o", label=label)
    ax.set_xlabel(xlabel); ax.set_title(title); ax.grid(alpha=.3); ax.legend(fontsize=8)
    fig.tight_layout(); fig.savefig(path, dpi=130); plt.close(fig)
    return path


def _tornado_chart(path, bars, kpi):
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        return None
    bars = sorted(bars, key=lambda b: abs(b["high"] - b["low"]))
    fig, ax = plt.subplots(figsize=(7, 0.6 * len(bars) + 1.5))
    for i, b in enumerate(bars):
        ax.barh(i, b["low"] - b["base"], left=b["base"], color="#4C78A8")
        ax.barh(i, b["high"] - b["base"], left=b["base"], color="#F58518")
    ax.set_yticks(range(len(bars))); ax.set_yticklabels([b["var"] for b in bars])
    ax.axvline(bars[0]["base"] if bars else 0, color="k", lw=.8)
    ax.set_title(f"Tornado: {kpi}\nblue = low value, orange = high value", fontsize=10)
    fig.tight_layout(); fig.savefig(path, dpi=130); plt.close(fig)
    return path


def run(spec, progress=print):
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S-%f")[:-3]
    out = os.path.join(RUNS_DIR, stamp)
    os.makedirs(out, exist_ok=True)
    json.dump(spec, open(os.path.join(out, "spec.json"), "w"), indent=2)
    units = spec.get("units", "METRIC")
    work = os.path.join(out, "model.pips")

    # 1. model: always a copy, never the user's original
    if spec["model"]["source"] == "existing":
        shutil.copy2(spec["model"]["path"], work)
        model = Model.open(work, units=getattr(d.Units, units))
    else:
        progress("Building model from template...")
        model = BUILDERS[spec["model"]["template"]](work, spec["model"]["params"], units)
    try:
        for c in spec.get("base_changes", []):
            _set(model, (c["component_type"], c["name"], c["parameter"]), c["value"])
        a, kpis = spec["analysis"], _kpis(model, spec)
        refs = [study.resolve_var(v, spec) for v in a.get("variables", [])]
        labels = [v.get("alias") or f"{r[1]}.{r[2]}" for v, r in zip(a.get("variables", []), refs)]
        base_vals = [_get(model, r) for r in refs]
        rows, charts = [], []

        def case(name, settings):
            for r, val in settings:
                _set(model, r, val)
            progress(f"  case {len(rows) + 1}/{study.n_cases(spec)}: {name}")
            try:
                row = _run_case(model, kpis)
            except Exception as e:
                row = {"_status": f"FAILED: {e}"}
            for r, b in zip(refs, base_vals):  # restore the base case
                _set(model, r, b)
            row = {"case": name, **{l: dict((rr, vv) for rr, vv in settings).get(r, b)
                                    for l, r, b in zip(labels, refs, base_vals)}, **row}
            rows.append(row)
            return row

        if a["type"] == "pt_profile":
            task = model.tasks.ptprofilesimulation
            r = task.run(
                producer=a["producer"], parameters=_pt_parameters(a.get("conditions") or {}),
                system_variables=[_sv(k["variable"]) for k in kpis],
                profile_variables=[getattr(d.ProfileVariables, n) for n in
                                   ("TOTAL_DISTANCE", "ELEVATION", "PRESSURE", "TEMPERATURE", "HOLDUP_FRACTION_LIQUID")
                                   if hasattr(d.ProfileVariables, n)])
            if str(getattr(r, "state", "Completed")) != "Completed":
                try:
                    current = task.get_conditions(producer=a["producer"])
                except Exception:
                    current = "unavailable"
                raise RuntimeError(f"P/T profile for {a['producer']} did not complete (state {r.state}). "
                                   f"Conditions sent: {a.get('conditions')}. Conditions in the model: {current}")
            prof = getattr(r, "profile", {}) or {}
            if isinstance(prof, dict) and a["producer"] in prof:
                prof = prof[a["producer"]]
            elif isinstance(prof, dict) and prof and all(isinstance(v, dict) for v in prof.values()):
                prof = next(iter(prof.values()))  # PIPESIM 2023.1 keys the profile by case, e.g. "Flowrate=..."
            cols = list(prof.keys()) if isinstance(prof, dict) else []
            n = max((len(prof[c]) for c in cols), default=0)
            rows = [{c: prof[c][i] if i < len(prof[c]) else None for c in cols} for i in range(n)]
            dist = next((c for c in cols if "distance" in c.lower()), None)
            if dist:
                for c in cols:
                    # skip text columns such as BranchEquipment (2023.1), which matplotlib cannot plot
                    if c != dist and any(isinstance(v, (int, float)) and not isinstance(v, bool) for v in prof[c]):
                        charts.append(_chart(os.path.join(out, f"profile_{c}.png".replace(" ", "_")),
                                             prof[dist], {c: prof[c]}, dist, f"{a['producer']}: {c}"))
        else:
            base = case("base", [])
            kpi_cols = [c for c in base if c not in ("case", "_status", *labels)]
            if a["type"] == "sweep":
                for v in study.values_of(a["variables"][0]):
                    case(f"{labels[0]}={v}", [(refs[0], v)])
                sw = rows[1:]
                for k in kpi_cols:
                    charts.append(_chart(os.path.join(out, f"sweep_{len(charts)}.png"),
                                         [r[labels[0]] for r in sw], {k: [r.get(k) for r in sw]},
                                         labels[0], f"{k} vs {labels[0]}"))
            elif a["type"] == "grid":
                for combo in itertools.product(*[study.values_of(v) for v in a["variables"]]):
                    case(", ".join(f"{l}={c}" for l, c in zip(labels, combo)), list(zip(refs, combo)))
                if len(refs) == 2:  # one line per value of variable 2
                    sw = rows[1:]
                    for k in kpi_cols:
                        series = {}
                        for v2 in study.values_of(a["variables"][1]):
                            pts = [r for r in sw if r[labels[1]] == v2]
                            series[f"{labels[1]}={v2}"] = [p.get(k) for p in pts]
                        charts.append(_chart(os.path.join(out, f"grid_{len(charts)}.png"),
                                             study.values_of(a["variables"][0]), series, labels[0], k))
            elif a["type"] == "tornado":
                for v, r, l in zip(a["variables"], refs, labels):
                    case(f"{l} low={v['low']}", [(r, v["low"])])
                    case(f"{l} high={v['high']}", [(r, v["high"])])
                for k in kpi_cols:
                    if base.get(k) is None:
                        continue
                    bars = []
                    for i, l in enumerate(labels):
                        lo, hi = rows[1 + 2 * i].get(k), rows[2 + 2 * i].get(k)
                        if lo is not None and hi is not None:
                            bars.append({"var": l, "low": lo, "high": hi, "base": base[k]})
                    charts.append(_tornado_chart(os.path.join(out, f"tornado_{len(charts)}.png"), bars, k))

        # write outputs
        csv_path = os.path.join(out, "results.csv")
        cols = list(dict.fromkeys(c for r in rows for c in r))
        with open(csv_path, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=cols); w.writeheader(); w.writerows(rows)
        charts = [c for c in charts if c]
        model.save()
        report = os.path.join(out, "report.md")
        with open(report, "w") as f:
            f.write(study.plan_text(spec) + "\n\n## Results\n\n")
            f.write("| " + " | ".join(cols) + " |\n|" + "---|" * len(cols) + "\n")
            for r in rows[:60]:
                f.write("| " + " | ".join(_fmt(r.get(c)) for c in cols) + " |\n")
            for c in charts:
                f.write(f"\n![]({os.path.basename(c)})\n")
        failed = [r["case"] for r in rows if str(r.get("_status", "")).startswith("FAILED")]
        return {"output_dir": out, "report": report, "csv": csv_path, "charts": charts,
                "n_rows": len(rows), "failed_cases": failed, "table": _compact(rows, cols)}
    finally:
        model.close()


def _fmt(v):
    return f"{v:.4g}" if isinstance(v, float) else ("" if v is None else str(v))


def _compact(rows, cols, limit=40):
    """Small text table for the LLM to interpret (long profiles are downsampled)."""
    step = max(1, len(rows) // limit)
    sel = rows[::step]
    return [" | ".join(cols)] + [" | ".join(_fmt(r.get(c)) for c in cols) for r in sel]
