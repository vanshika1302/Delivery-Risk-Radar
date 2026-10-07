"""Write the small, precomputed files the dashboard reads (dashboard/src/data/*.json).

The GitHub Pages build cannot rerun the 5.8 GB extraction, so everything the dashboard shows is computed here and committed:
scored tickets with their top reasons, global explanations, model quality, and the SQL analysis tables.
No person-level fields (assignee, reporter, author) are written, only counts about them.

Run from the repo root:  python -m radar.export
"""
from __future__ import annotations

import argparse
import json
import tomllib
from pathlib import Path

import duckdb
import joblib
import numpy as np
import pandas as pd

from radar import data, explain, modeling

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "dashboard" / "src" / "data"
MODELS = ROOT / "data" / "processed" / "models"
FORBIDDEN_KEYS = {"assignee", "reporter", "creator", "author"}   # asserted absent from the exported tickets


def _dump(path: Path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, separators=(",", ":"), allow_nan=False))
    return path.stat().st_size


def _ticket_rows(df: pd.DataFrame, ex: explain.Explainer, typ: explain.Typical, cutoff_top10: float, point: str, label_known: bool):
    raw, cal = ex.probabilities(df)
    contrib = ex.contributions(df)
    rows = []
    for i, (idx, row) in enumerate(df.iterrows()):
        item = explain.reasons(row, contrib.loc[idx], float(raw[i]), typ, point)
        rec = {"key": row["issue_key"], "project": row["project_key"], "type": row["issue_type"], "point": point,
               "created": pd.Timestamp(row["created"]).strftime("%Y-%m-%d"), "p": round(float(explain.display_probability(cal[i])), 3), "top10": bool(cal[i] >= cutoff_top10),
               "reasons": item["reasons"], "themes": item["themes"]}
        if label_known:
            rec["late"] = int(row["is_late"])
        else:
            rec["age_days"] = round(float((pd.Timestamp(SNAPSHOT) - pd.Timestamp(row["created"])).total_seconds() / 86400.0), 1)
        rows.append(rec)
    return rows


def _binned(sample: pd.DataFrame, pts: pd.DataFrame, feature: str, edges=None, labels=None, quantiles=None):
    x = sample[feature]
    if feature == "assignee_open":
        grp = np.where(x.isna(), "Not assigned", "Assigned")
        order = ["Not assigned", "Assigned"]
    else:
        cuts = pd.qcut(x, quantiles, duplicates="drop") if quantiles else pd.cut(x, edges, labels=labels, right=False)
        grp = cuts.astype(str).where(x.notna(), "missing")
        order = [str(c) for c in (cuts.cat.categories if hasattr(cuts, "cat") else [])] + ["missing"]
    d = pd.DataFrame({"g": grp, "pts": pts[feature].to_numpy()})
    g = d.groupby("g").agg(n=("pts", "size"), mean_points=("pts", "mean")).reindex([o for o in order if o in set(d["g"])])
    return [{"bin": str(k), "n": int(r["n"]), "mean_points": round(float(r["mean_points"]), 2)} for k, r in g.iterrows()]


def build(db=data.DEFAULT_DB, out=OUT, n_sample=2000, n_global=6000, stability_runs=5, seed=0):
    global SNAPSHOT
    params = tomllib.loads((ROOT / "config" / "params.toml").read_text())
    SNAPSHOT = params["scope"]["snapshot"]
    cutoff = pd.Timestamp(params["split"]["train_cutoff"])
    results = json.loads((ROOT / "docs" / "model_results.json").read_text())
    out = Path(out)
    meta = {"snapshot": SNAPSHOT, "train_cutoff": params["split"]["train_cutoff"], "test_window": [params["split"]["test_start"], params["split"]["test_end"]],
            "late_percentile": params["late"]["percentile"], "projects": params["scope"]["projects"], "points": {}}
    backtest, open_now, global_expl, quality, sizes = [], [], {}, {"points": {}}, {}
    for point in ("creation", "day7"):
        df = data.load(point, db)
        df["created"] = pd.to_datetime(df["created"])
        df["resolution_date"] = pd.to_datetime(df["resolution_date"])
        train = df[modeling.known_at(df, cutoff)]
        typ = explain.Typical(train)
        bundle = joblib.load(MODELS / f"{point}_boosting.joblib")
        ex = explain.Explainer(bundle)
        test = df[(df["split"] == "test") & df["is_late"].notna()]
        cal_all = ex.probabilities(test)[1]
        top10 = float(np.quantile(cal_all, 0.90))
        sample = test.sample(min(n_sample, len(test)), random_state=seed)
        backtest += _ticket_rows(sample, ex, typ, top10, point, True)
        young = df[df["label_status"] == "open_unlabelled"]
        open_now += _ticket_rows(young, ex, typ, top10, point, False)
        meta["points"][point] = {"base_rate_train": round(float(train["is_late"].mean()), 4), "base_rate_test": round(float(test["is_late"].mean()), 4),
                                 "n_train": int(len(train)), "n_test": int(len(test)), "top10_cutoff": round(top10, 4), "n_open_scored": int(len(young)),
                                 "boosting_params": bundle["params"], "ex_base_logit": round(ex.base, 4)}
        # Global explanations on a larger test sample.
        gs = test.sample(min(n_global, len(test)), random_state=seed + 1)
        contrib = ex.contributions(gs)
        raw = ex.probabilities(gs)[0]
        pts = contrib.mul(100.0 * raw * (1.0 - raw), axis=0)
        imp = contrib.abs().mean().sort_values(ascending=False)
        by_theme = {t: float(sum(contrib[f] for f in contrib.columns if explain.THEMES[f] == t).abs().mean()) for t in explain.THEME_ORDER}
        per_project = {p: [{"feature": f, "theme": explain.THEMES[f], "mean_abs": round(float(v), 4)} for f, v in contrib[gs["project_key"] == p].abs().mean().sort_values(ascending=False).head(5).items()]
                       for p in sorted(gs["project_key"].unique())}
        dep = {"assignee_open": _binned(gs, pts, "assignee_open"),
               "description_length": _binned(gs, pts, "description_length", quantiles=6),
               "reporter_prior_tickets": _binned(gs, pts, "reporter_prior_tickets", edges=[0, 1, 2, 5, 15, 1e9], labels=["0", "1", "2-4", "5-14", "15+"]),
               "project_open": _binned(gs, pts, "project_open", quantiles=5),
               "priority_rank": _binned(gs, pts, "priority_rank", edges=[0, 0.15, 0.4, 0.65, 0.9, 1.01], labels=["bottom", "lower", "middle", "upper", "top"])}
        global_expl[point] = {"importance": [{"feature": f, "theme": explain.THEMES[f], "mean_abs": round(float(v), 4)} for f, v in imp.items()],
                              "theme_importance": {t: round(v, 4) for t, v in by_theme.items()}, "per_project": per_project, "dependence": dep, "n_rows": int(len(gs))}
        if stability_runs:
            global_expl[point]["stability"] = explain.stability(point, train, gs.head(2500), bundle["params"], ex, n_boot=stability_runs)
        r = results["points"][point]
        quality["points"][point] = {k: v for k, v in r.items() if k in ("n_train", "n_test", "best_params", "bootstrap", "robustness_delivered_only")}
        quality["points"][point]["models"] = {name: {k: v for k, v in m.items() if k != "per_project" or name == "boosting"} for name, m in r["models"].items()}

    for rec in backtest + open_now:
        assert not FORBIDDEN_KEYS & set(rec), "person-level field in export"
        assert not FORBIDDEN_KEYS & {r["feature"] for r in rec["reasons"]}
    sizes["backtest_tickets.json"] = _dump(out / "backtest_tickets.json", backtest)
    sizes["open_tickets.json"] = _dump(out / "open_tickets.json", open_now)
    sizes["global.json"] = _dump(out / "global.json", global_expl)
    sizes["model_quality.json"] = _dump(out / "model_quality.json", quality)
    sizes["overview.json"] = _dump(out / "overview.json", overview(db))
    meta["files"] = sizes
    meta["disclaimer"] = "Reasons describe what the model associates with lateness, not what causes it. Data is a snapshot as of the date shown."
    sizes["meta.json"] = _dump(out / "meta.json", meta)
    return sizes


def overview(db) -> dict:
    con = duckdb.connect(str(db), read_only=True)
    try:
        tab = lambda sql: json.loads(con.execute(sql).df().to_json(orient="records"))
        return {
            "lead_time_by_project": tab("select project_key, sum(tickets)::int tickets, round(sum(tickets*median_days)/sum(tickets),1) median_days, round(sum(tickets*p75_days)/sum(tickets),1) p75_days, round(sum(tickets*late_pct)/sum(tickets),1) late_pct from analysis_lead_time group by 1 order by 2 desc"),
            "stage_share": tab("select * from analysis_stage_share order by tickets desc"),
            "review_flow": tab("select * from analysis_review_flow order by tickets desc"),
            "late_by_factor": tab("select * from analysis_late_by_factor order by factor, tickets desc"),
            "late_trend": tab("""select year(created)::int AS "year", count(*)::int AS tickets, round(100*avg(is_late::int),1) all_labelled,
                                  round(100*avg(is_late_delivered_only::int),1) delivered_only
                                from labels where label_status in ('labelled','open_known_late') and year(created) between 2008 and 2021 group by 1 order by 1"""),
            "late_by_project_year": tab('select project_key, created_year::int AS "year", tickets::int AS tickets, median_days, late_pct from analysis_trend where created_year between 2008 and 2021 order by 1, 2'),
        }
    finally:
        con.close()


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--db", default=str(data.DEFAULT_DB))
    p.add_argument("--out", default=str(OUT))
    p.add_argument("--no-stability", action="store_true", help="skip the bootstrap refits (faster)")
    a = p.parse_args(argv)
    sizes = build(a.db, a.out, stability_runs=0 if a.no_stability else 5)
    for k, v in sizes.items():
        print(f"  {k:<24}{v / 1024:>9,.0f} KB")


if __name__ == "__main__":
    main()
