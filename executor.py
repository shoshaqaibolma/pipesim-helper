"""
Deterministic study executor: takes an approved spec, runs every case in PIPESIM, and writes
CSV, charts and a report. The LLM never drives individual runs, so a 300-case grid is as reliable as one run.
"""
import csv, datetime, itertools, json, os, shutil
from sixgill import definitions as d
import study
import netbuilder
import sixgill_adapter as sa
from builder import TEMPLATES

RUNS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "runs")


def _sv(name):
    return getattr(d.SystemVariables, name, name)


SHORT = {"VOLUME_FLOWRATE_LIQUID_STOCKTANK": "liquid rate", "VOLUME_FLOWRATE_OIL_STOCKTANK": "oil rate",
         "VOLUME_FLOWRATE_GAS_STOCKTANK": "gas rate", "VOLUME_FLOWRATE_WATER_STOCKTANK": "water rate",
         "PRESSURE": "pressure", "TEMPERATURE": "temperature"}


def _find(model, t):
    try:
        # top-level components only: "Well:Source 1" etc. are internal parts of a well
        return [n for n in (model.find(**{t: d.ALL}) or []) if ":" not in n]
    except Exception:
        return []


def _project_for(spec, project):
    src = spec["model"]["source"]
    if src == "new":
        return TEMPLATES[spec["model"]["template"]]["to_project"](spec["model"]["params"])
    return project if src == "project" else None


def _producers(model, proj):
    if proj:
        return [w["name"] for w in proj.get("wells") or []] + [s["name"] for s in proj.get("sources") or []]
    return _find(model, "Well") + _find(model, "Source")


def _kpis(model, spec, proj=None):
    """Default results: rates delivered to each sink, plus rate and wellhead pressure of each producer."""
    if spec.get("kpis"):
        return spec["kpis"]
    rates = ["VOLUME_FLOWRATE_LIQUID_STOCKTANK", "VOLUME_FLOWRATE_OIL_STOCKTANK", "VOLUME_FLOWRATE_GAS_STOCKTANK"]
    sinks = [k["name"] for k in proj.get("sinks") or []] if proj else _find(model, "Sink")
    out = [{"component": s, "variable": v, "label": f"{s} {SHORT[v]}"} for s in sinks for v in rates]
    out += [{"component": p, "variable": v, "label": f"{p} {SHORT[v]}"} for p in _producers(model, proj)
            for v in ("VOLUME_FLOWRATE_LIQUID_STOCKTANK", "PRESSURE")]
    return out


def _by_variable(kpis, cols):
    """Group result columns by variable, so one chart shows e.g. every liquid rate together."""
    groups = {}
    for k in kpis:
        lab = k.get("label") or f"{k['component']} {k['variable']}"
        if lab in cols:
            groups.setdefault(SHORT.get(k["variable"], k["variable"]), []).append(lab)
    return groups


UNITS = {}  # result column label -> unit reported by PIPESIM (e.g. "sm3/d")


def _run_case(model, kpis):
    r = model.tasks.networksimulation.run(system_variables=[_sv(k["variable"]) for k in kpis])
    row = {}
    for k in kpis:
        label = k.get("label") or f"{k['component']} {k['variable']}"
        val = unit = None
        for tbl in (getattr(r, "node", None), getattr(r, "system", None)):
            val, unit = sa.result(tbl, _sv(k["variable"]), k["component"])
            if val is not None:
                break
        row[label] = val
        if unit:
            UNITS[label] = unit
    row["_status"] = str(getattr(r, "state", "ok"))
    if kpis and all(row.get(k.get("label") or f"{k['component']} {k['variable']}") is None for k in kpis):
        row["_status"] += ": no results - the system may not flow at these conditions"
    return row


def _head(col):
    """Column header with its unit, e.g. 'Sep liquid rate [sm3/d]'."""
    return f"{col} [{UNITS[col]}]" if col in UNITS else col


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
    sa.set_param(model, *ref, value)


def _get(model, ref):
    return sa.get_param(model, *ref)


def _summary(a, rows, kpi_cols, labels):
    """Numbers the LLM should quote instead of computing: change vs base per case, best/worst case, tornado ranking."""
    if a["type"] not in ("sweep", "grid", "tornado") or not rows:
        return {}
    base, cases = rows[0], rows[1:]
    out = {}
    for k in kpi_cols:
        b = base.get(k)
        vals = [(r.get(k), r["case"]) for r in cases if isinstance(r.get(k), (int, float))]
        if not isinstance(b, (int, float)) or not vals:
            continue
        hi, lo = max(vals), min(vals)
        s = {"unit": UNITS.get(k, ""), "base": round(b, 4), "highest": {"value": round(hi[0], 4), "case": hi[1]},
             "lowest": {"value": round(lo[0], 4), "case": lo[1]}}
        if b:
            s["change_vs_base_pct"] = {c: round(100 * (v - b) / abs(b), 2) for v, c in vals}
        out[k] = s
    if a["type"] == "tornado":
        for k, s in out.items():
            swings = []
            for i, l in enumerate(labels):
                lo_v, hi_v = rows[1 + 2 * i].get(k), rows[2 + 2 * i].get(k)
                if isinstance(lo_v, (int, float)) and isinstance(hi_v, (int, float)):
                    swings.append({"variable": l, "low_case": round(lo_v, 4), "high_case": round(hi_v, 4),
                                   "swing": round(abs(hi_v - lo_v), 4)})
            s["ranking"] = sorted(swings, key=lambda x: -x["swing"])
    return out


def _primary(kpi_cols, base=None):
    """The result most studies are about: total oil (else liquid, else gas) rate when there are several sinks,
    otherwise the sink/producer with the largest base value of that kind."""
    for word in ("oil rate", "liquid rate", "gas rate"):
        if f"Total {word}" in kpi_cols:
            return f"Total {word}"
        cands = [k for k in kpi_cols if k.endswith(word)]
        if cands:
            return max(cands, key=lambda k: abs((base or {}).get(k) or 0))
    return kpi_cols[0] if kpi_cols else None


def _add_totals(row, sinks):
    """Field totals over several sinks (e.g. gas sales + oil facility)."""
    if len(sinks) < 2:
        return
    for var in ("liquid rate", "oil rate", "gas rate"):
        vals = [row.get(f"{s} {var}") for s in sinks]
        if any(isinstance(v, (int, float)) for v in vals):
            row[f"Total {var}"] = sum(v for v in vals if isinstance(v, (int, float)))
            unit = next((UNITS[f"{s} {var}"] for s in sinks if f"{s} {var}" in UNITS), None)
            if unit:
                UNITS[f"Total {var}"] = unit


def _flat_warning(rows, kpi_cols):
    """Warn when no recorded result changed across the cases: the varied input had no effect on these outputs."""
    vals = {k: [r.get(k) for r in rows if isinstance(r.get(k), (int, float))] for k in kpi_cols}
    vals = {k: v for k, v in vals.items() if len(v) >= 2}
    if vals and all(max(v) - min(v) <= 1e-9 * max(1.0, abs(max(v))) for v in vals.values()):
        return ("No recorded result changed across the cases. Either the varied input does not reach these "
                "outputs (for example a pump, compressor or a fixed-pressure node isolates it), or the change did "
                "not take effect in the simulation. Check the network layout before drawing conclusions.")
    return None


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


def _nodal_chart(path, curves, op, well, base="liquid"):
    if not curves:
        return None
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        return None
    fig, ax = plt.subplots(figsize=(7, 4.6))
    for name, cv in curves.items():
        pts = [(q, p) for q, p in zip(cv["rate"], cv["pressure"]) if q is not None and p is not None]
        if pts:
            ax.plot(*zip(*pts), label=("Inflow (IPR)" if name.startswith("inflow") else "Outflow (VLP)"))
    rate = op.get("liquid_rate") if base == "liquid" else op.get("gas_rate")
    q = (rate or {}).get("value")
    p = (op.get("bottomhole_pressure") or {}).get("value")
    if q is not None and p is not None:
        ax.plot([q], [p], "ko", label=f"Operating point ({q:.4g}, {p:.1f} bara)")
    unit = (rate or {}).get("unit") or ""
    ax.set_xlabel(f"{base.title()} rate{f' [{unit}]' if unit else ''}")
    ax.set_ylabel("Pressure at nodal point [bara]")
    ax.set_title(f"Nodal analysis: {well}"); ax.grid(alpha=.3); ax.legend(fontsize=8)
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


def run(spec, progress=print, project=None):
    UNITS.clear()
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S-%f")[:-3]
    out = os.path.join(RUNS_DIR, stamp)
    os.makedirs(out, exist_ok=True)
    json.dump(spec, open(os.path.join(out, "spec.json"), "w"), indent=2)
    units = spec.get("units", "METRIC")
    work = os.path.join(out, "model.pips")

    # 1. model: always a copy, never the user's original
    proj = _project_for(spec, project)
    if spec["model"]["source"] == "existing":
        shutil.copy2(spec["model"]["path"], work)
        model = sa.open_model(work, units)
    else:
        progress("Building the model...")
        json.dump(proj, open(os.path.join(out, "project.json"), "w"), indent=2)
        model, _ = netbuilder.build(proj, work, "METRIC")
    try:
        for c in spec.get("base_changes", []):
            _set(model, (c["component_type"], c["name"], c["parameter"]), c["value"])
        a, kpis = spec["analysis"], _kpis(model, spec, proj)
        sinks = list(dict.fromkeys(k["component"] for k in kpis if k["label"].endswith(" oil rate")
                                   and k["component"] not in _producers(model, proj)))
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
                _add_totals(row, sinks)
            except Exception as e:
                row = {"_status": f"FAILED: {e}"}
            for r, b in zip(refs, base_vals):  # restore the base case
                _set(model, r, b)
            row = {"case": name, **{l: dict((rr, vv) for rr, vv in settings).get(r, b)
                                    for l, r, b in zip(labels, refs, base_vals)}, **row}
            rows.append(row)
            return row

        if a["type"] == "nodal":
            comp = None
            if proj:
                import project as prj
                comp = prj.completion_name(a["producer"])
            res = sa.nodal(model, a["producer"], a["outlet_pressure"], completion=comp)
            json.dump(res["raw"], open(os.path.join(out, "nodal_raw.json"), "w"), indent=1, default=str)
            op = res["operating_point"]
            rows = [{"case": "operating point", **{f"{k} [{v.get('unit') or ''}]": v.get("value") for k, v in op.items()},
                     "_status": res["state"]}]
            for name, cv in res["curves"].items():
                for q, p in zip(cv["rate"], cv["pressure"]):
                    rows.append({"case": name, "curve rate": q, "curve pressure [bara]": p})
            charts.append(_nodal_chart(os.path.join(out, "nodal.png"), res["curves"], op, a["producer"], res["rate_basis"]))
            if not res["curves"]:
                charts.append(None)
                warnings_extra = ["Inflow/outflow curve points could not be read from this PIPESIM version; "
                                  "the operating point is still valid. Raw data saved to nodal_raw.json."]
            else:
                warnings_extra = []
            if not op.get("liquid_rate") and not op.get("gas_rate"):
                warnings_extra.append("No operating point found: the well may not flow at this outlet pressure "
                                      f"(PIPESIM summary: {str(res.get('summary_messages'))[:300]}).")
        elif a["type"] == "pt_profile":
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
                for var, ks in _by_variable(kpis, kpi_cols).items():
                    unit = next((UNITS[k] for k in ks if k in UNITS), "")
                    charts.append(_chart(os.path.join(out, f"sweep_{var.replace(' ', '_')}.png"),
                                         [r[labels[0]] for r in sw], {k: [r.get(k) for r in sw] for k in ks},
                                         labels[0], f"{var}{f' [{unit}]' if unit else ''} vs {labels[0]}"))
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

        warnings, summary = (list(warnings_extra) if a["type"] == "nodal" else []), {}
        if a["type"] == "nodal":
            summary = {"operating_point": rows[0]}
        if a["type"] in ("sweep", "grid", "tornado"):
            w = _flat_warning(rows, kpi_cols)
            if w:
                warnings.append(w)
            summary = _summary(a, rows, kpi_cols, labels)
            p = _primary(kpi_cols, rows[0])
            if p and summary.get(p, {}).get("change_vs_base_pct"):  # precomputed % change column for the main result
                col = f"{p} change vs base [%]"
                for r in rows[1:]:
                    r[col] = summary[p]["change_vs_base_pct"].get(r["case"])
                rows[0][col] = 0.0
        # write outputs
        csv_path = os.path.join(out, "results.csv")
        cols = list(dict.fromkeys(c for r in rows for c in r))
        with open(csv_path, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow([_head(c) for c in cols])
            w.writerows([[r.get(c) for c in cols] for r in rows])
        charts = [c for c in charts if c]
        model.save()
        report = os.path.join(out, "report.md")
        with open(report, "w") as f:
            f.write(study.plan_text(spec, proj) + "\n\n## Results\n\n")
            for w in warnings:
                f.write(f"> **Warning:** {w}\n\n")
            f.write("| " + " | ".join(_head(c) for c in cols) + " |\n|" + "---|" * len(cols) + "\n")
            for r in rows[:60]:
                f.write("| " + " | ".join(_fmt(r.get(c)) for c in cols) + " |\n")
            for c in charts:
                f.write(f"\n![]({os.path.basename(c)})\n")
        failed = [r["case"] for r in rows if str(r.get("_status", "")).startswith("FAILED")]
        return {"output_dir": out, "report": report, "csv": csv_path, "charts": charts, "warnings": warnings,
                "n_rows": len(rows), "failed_cases": failed, "table": _compact(rows, cols), "summary": summary}
    finally:
        model.close()


def _fmt(v):
    return f"{v:.4g}" if isinstance(v, float) else ("" if v is None else str(v))


def _compact(rows, cols, limit=40):
    """Small text table for the LLM to interpret (long profiles are downsampled)."""
    step = max(1, len(rows) // limit)
    sel = rows[::step]
    return [" | ".join(_head(c) for c in cols)] + [" | ".join(_fmt(r.get(c)) for c in cols) for r in sel]
