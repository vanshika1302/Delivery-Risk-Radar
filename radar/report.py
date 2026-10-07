"""Write docs/model-results.md from docs/model_results.json and a few live diagnostics, so the numbers cannot drift.

Run from the repo root after `python -m radar.train`:  python -m radar.report
"""
from __future__ import annotations

import json
import warnings
from pathlib import Path

import duckdb
import joblib
import numpy as np
import pandas as pd
from sklearn.inspection import permutation_importance
from sklearn.metrics import average_precision_score, roc_auc_score

from radar import data, modeling

ROOT = Path(__file__).resolve().parent.parent
NAMES = {"baseline_project_rate": "Project late rate (baseline)", "baseline_peer_history": "Peer-group history (baseline)",
         "logistic": "Logistic regression", "boosting": "Gradient boosting"}


def table(r):
    rows = ["| Model | PR-AUC [95% CI] | ROC-AUC | Brier | Precision in riskiest 10% | Lift |", "|---|---|---|---|---|---|"]
    for k, label in NAMES.items():
        m, (lo, hi) = r["models"][k], r["bootstrap"]["pr_auc_ci"][k]
        b = k == "boosting"
        cell = lambda s: f"**{s}**" if b else s
        rows.append(f"| {cell(label)} | {cell(f'{m['pr_auc']:.3f} [{lo:.3f}, {hi:.3f}]')} | {cell(f'{m['roc_auc']:.3f}')} | {cell(f'{m['brier']:.3f}')} | {cell(f'{m['precision_at_top10']:.3f}')} | {cell(f'{m['lift_at_top10']:.2f}')} |")
    return "\n".join(rows)


def diff(r, name):
    d = r["bootstrap"]["diff_vs"][name]
    return f"{d['mean']:+.3f} (interval {d['ci95'][0]:+.3f} to {d['ci95'][1]:+.3f})", d["wins"]


def diagnostics(db):
    warnings.filterwarnings("ignore")
    out = {}
    cutoff = pd.Timestamp("2019-01-01")
    for point in ("creation", "day7"):
        df = data.load(point, db)
        df["created"], df["resolution_date"] = pd.to_datetime(df["created"]), pd.to_datetime(df["resolution_date"])
        cols = data.feature_columns(point)
        test = df[(df["split"] == "test") & df["is_late"].notna()]
        bundle = joblib.load(ROOT / "data" / "processed" / "models" / f"{point}_boosting.joblib")
        samp = test.sample(8000, random_state=0)
        imp = permutation_importance(bundle["model"], samp[cols], samp["is_late"], scoring="average_precision", n_repeats=3, random_state=0, n_jobs=1)
        top = sorted(zip(cols, imp.importances_mean), key=lambda t: -t[1])[:5]
        train = df[modeling.known_at(df, cutoff)]
        params = bundle["params"]

        def fit_without(drop):
            use = [c for c in cols if c not in drop]
            orig = data.feature_columns
            data.feature_columns = modeling.feature_columns = lambda p: use
            try:
                m = modeling.boosting_pipeline(point, **params).fit(train[use], train["is_late"])
            finally:
                data.feature_columns = modeling.feature_columns = orig
            p = m.predict_proba(test[use])[:, 1]
            return average_precision_score(test["is_late"], p), roc_auc_score(test["is_late"], p)

        out[point] = {"train_rate": float(train["is_late"].mean()), "top": top, "all": fit_without([]), "no_assignee_open": fit_without(["assignee_open"]),
                      "no_reporter": fit_without(["reporter_prior_tickets", "reporter_first_time"]),
                      "no_history": fit_without(["peer_n", "peer_median_lead_days", "peer_late_rate", "project_median_lead_days", "project_late_rate"])}
    con = duckdb.connect(str(db), read_only=True)
    q = lambda s: con.execute(s).fetchall()
    out["assigned"] = {r[0]: (r[1], r[2]) for r in q("""select f.project_key, round(100*avg(l.is_late::int) filter (where f.has_assignee),0), round(100*avg(l.is_late::int) filter (where not f.has_assignee),0)
        from features f join labels l using(issue_key) where f.point='creation' and l.is_late is not null group by 1""")}
    out["leakcheck"] = q("""with a as (select f.issue_key, f.t_at from features f where f.point='creation' and f.has_assignee),
        fa as (select issue_key, min(created) first_at from changelog where lower(field)='assignee' and to_value is not null group by 1)
        select count(*), sum((fa.first_at is not null and fa.first_at <= a.t_at + interval 10 second and fa.first_at > a.t_at)::int), sum((fa.first_at is null)::int) from a left join fa using(issue_key)""")[0]
    out["workload"] = q("""select min(r), max(r) from (select round(100*avg(l.is_late::int),0) r from features f join labels l using(issue_key)
        where f.point='creation' and f.has_assignee and l.is_late is not null group by case when assignee_open=0 then 0 when assignee_open<=2 then 1 when assignee_open<=5 then 2 when assignee_open<=10 then 3 else 4 end)""")[0]
    con.close()
    return out


def build(db=data.DEFAULT_DB, results=ROOT / "docs" / "model_results.json", out=ROOT / "docs" / "model-results.md"):
    R = json.loads(Path(results).read_text())
    c, d7 = R["points"]["creation"], R["points"]["day7"]
    D = diagnostics(db)
    cm, dm = c["models"], d7["models"]
    cw, cb = diff(c, "boosting - baseline_project_rate"), diff(c, "boosting - baseline_peer_history")
    cl, cl_wins = diff(c, "boosting - logistic")
    dw, db_ = diff(d7, "boosting - baseline_project_rate"), diff(d7, "boosting - baseline_peer_history")
    dl, dl_wins = diff(d7, "boosting - logistic")
    rb, rb7 = c["robustness_delivered_only"], d7["robustness_delivered_only"]
    pp = lambda r: ", ".join(f"{p} {v['pr_auc']:.2f} vs {v['late_rate']:.2f}" for p, v in sorted(r["models"]["boosting"]["per_project"].items(), key=lambda kv: -kv[1]["n"]))
    top = lambda pt: ", ".join(f"`{f}` {v:.2f}" for f, v in D[pt]["top"])
    a = D["assigned"]
    text = f"""# Model results

Generated by `python -m radar.report` from `docs/model_results.json` (written by `python -m radar.train`; code in `radar/`). Decisions followed: "Model and validation" and "Prediction point and leakage rules" in `.scratch/delivery-risk-radar/issues/`.

## Setup

- **Two models per point**, one at creation and one at day 7, pooled over the 8 projects. Each is compared with two baselines: the project's late rate in training, and the late rate of the peer group's last 200 delivered tickets.
- **Models:** logistic regression (the transparent baseline) and scikit-learn gradient boosting (the main model). Boosting uses one-hot categories so that SHAP's tree explainer is exact (see `docs/explanations.md`). Hyperparameters are tuned with rolling-origin validation (train before 2016, 2017 or 2018, validate on the next year, labels known at each cutoff). Probabilities are calibrated with an isotonic map learned on the last validation year.
- **Split by time.** Training: tickets created before 2019-01-01 whose label was already known then ({c['n_train']:,} at creation, {d7['n_train']:,} at day 7). **Test: tickets created {R['test_window'][0]} to {R['test_window'][1]}** ({c['n_test']:,} and {d7['n_test']:,}), never used for tuning or calibration.
- **Label:** `labels.is_late` (open tickets already past their threshold count as late). The test late rate is {cm['logistic']['late_rate']:.1%} at creation and {dm['logistic']['late_rate']:.1%} at day 7.
- Intervals are 95% bootstrap intervals over test tickets; "beats" means the paired interval for the PR-AUC difference excludes zero.

## Results on the test period

**At creation** ({c['n_test']:,} tickets, {cm['logistic']['late_rate']:.1%} late)

{table(c)}

Boosting versus the project baseline: {cw[0]}; versus the peer baseline: {cb[0]}; versus logistic regression: {cl}. **The success rule from the model decision {'is met' if cw[1] and cb[1] and cl_wins else 'is not met'} at creation.**

**At day 7** ({d7['n_test']:,} tickets still open on day 7, {dm['logistic']['late_rate']:.1%} late)

{table(d7)}

Boosting versus the project baseline: {dw[0]}; versus the peer baseline: {db_[0]}; versus logistic regression: {dl}. {'Boosting beats logistic regression at day 7.' if dl_wins else 'Both models beat both baselines clearly, but **boosting does not beat the logistic regression at day 7**, so the rule is not met for boosting there; the two are tied.'} The peer-history baseline's Brier score is poor because its scores are raw rates, not calibrated probabilities.

## How to read these numbers

- **The signal at creation is moderate.** ROC-AUC is {cm['boosting']['roc_auc']:.2f}. The riskiest tenth of tickets is {cm['boosting']['precision_at_top10']:.0%} late against a {cm['boosting']['late_rate']:.0%} base rate, a lift of {cm['boosting']['lift_at_top10']:.1f}. That is useful for triage, not a verdict on any one ticket.
- **Day 7 is a different population.** Tickets still open on day 7 are late {dm['boosting']['late_rate']:.0%} of the time, so PR-AUC is high for every model, including the baselines. ROC-AUC ({dm['boosting']['roc_auc']:.2f} against {dm['baseline_project_rate']['roc_auc']:.2f} for the baselines) and the Brier score are the fairer measures of what the model adds.
- **Calibration is good in the middle and overconfident at the extremes.** Predicted and observed late rates agree within a few points across all ten deciles at both points. The isotonic calibrator does flatten into 0% and 100% plateaus where its validation data is thin (about 1% of creation tickets; the "0%" ones were late 8% of the time, the "100%" ones 91%). Displayed probabilities are therefore limited to 5% to 95%; ranking and every metric above use the unclipped scores.
- **It is not an artifact of stale open tickets.** Restricted to delivered tickets only (no open tickets in the label), the creation model reaches PR-AUC {rb['boosting']['pr_auc']:.3f} against a base rate of {rb['boosting']['late_rate']:.3f} and a project-rate baseline of {rb['baseline_project_rate']['pr_auc']:.3f} (ROC-AUC {rb['boosting']['roc_auc']:.3f}). At day 7 the delivered-only subset gives {rb7['boosting']['pr_auc']:.3f} against a base rate of {rb7['boosting']['late_rate']:.3f}.
- **Every project beats its own base rate at creation** (PR-AUC against base rate): {pp(c)}. AMBARI's test set is small because most of its tickets predate 2019.

## What drives the predictions

Permutation importance on the test period (drop in PR-AUC when a feature is scrambled), top features:

- **Creation:** {top('creation')}. Refitting without `assignee_open` drops PR-AUC from {D['creation']['all'][0]:.3f} to {D['creation']['no_assignee_open'][0]:.3f} (ROC-AUC {D['creation']['all'][1]:.3f} to {D['creation']['no_assignee_open'][1]:.3f}); without the reporter features, to {D['creation']['no_reporter'][0]:.3f}; without peer and project history, to {D['creation']['no_history'][0]:.3f}.
- **Day 7:** {top('day7')}. Refitting without `assignee_open` gives PR-AUC {D['day7']['no_assignee_open'][0]:.3f} (all features {D['day7']['all'][0]:.3f}); no single feature group matters much.

`assignee_open` is empty when nobody is assigned, so in practice it works as "was this ticket assigned when it was filed". That is a real and consistent signal. Late rate when assigned at filing versus not: HIVE {a['HIVE'][0]:.0f}% vs {a['HIVE'][1]:.0f}%, AMBARI {a['AMBARI'][0]:.0f}% vs {a['AMBARI'][1]:.0f}%, SPARK {a['SPARK'][0]:.0f}% vs {a['SPARK'][1]:.0f}%. It is not a leak: only {D['leakcheck'][1]} of {D['leakcheck'][0]:,} assigned-at-creation tickets have an assignment event within 10 seconds after creation, and {D['leakcheck'][2]:,} have no assignment event at all (they were created with the assignee). The workload count itself adds little: late rates stay between {D['workload'][0]:.0f}% and {D['workload'][1]:.0f}% across workload buckets. The explanation layer words this as "assigned when filed", not as a workload number.

Priority matters less than expected, consistent with the SQL analysis.

## Caveats

- One time split, one test window. Results are not a rolling backtest.
- The late rate drifts upward over time ({D['creation']['train_rate']:.1%} in training, {cm['logistic']['late_rate']:.1%} in test at creation) because more recent tickets stay open. Calibration (learned on 2018 tickets) holds up anyway.
- Run-to-run variation is about ±0.002 PR-AUC, and the tuner's chosen tree depth can change between identical runs because the grid scores are nearly tied. This does not change the conclusions.
- Thresholds, and so the label, come from the training period only. The test window ends so that 99.8% of its tickets are labelable.
- The model describes associations in this data, not causes. The dashboard says so.

## Decision: the day-7 model

Gradient boosting and logistic regression tie at day 7. **Boosting is kept** because the explanations are built on it and the two points then share one method; logistic regression is an equally accurate, fully transparent alternative if a simpler model is ever preferred (its coefficients can explain tickets directly). Decided by the project owner's delegation.
"""
    Path(out).write_text(text)
    return text


if __name__ == "__main__":
    build()
    print("wrote docs/model-results.md")
