# Explanations

Built by `radar/explain.py` and exported by `radar/export.py` to `dashboard/src/data/`. Decisions followed: "Explainability" in `.scratch/delivery-risk-radar/issues/`.

## Method

- **Exact SHAP values on the gradient boosting model**, one set per prediction point. Every call checks that the values add up to the model's own output (log-odds) and fails if they do not. This check matters: with scikit-learn's native categorical splits, SHAP's tree explainer silently produced values that were off by up to 2.3 log-odds at creation and 4.1 at day 7. The boosting model therefore one-hot encodes its categories, which costs nothing in accuracy (PR-AUC 0.622 vs 0.621 at creation), and the values are exact (error about 1e-15, including rows with missing values). `tests/test_explain.py` guards this.
- **Features, not columns.** One-hot columns are summed back to the feature they came from (for example all `project_key_*` columns become `project_key`).
- **Size in points.** A ticket's reasons are shown as approximate percentage points: SHAP value x p x (1 - p), where p is the model's raw probability (a local linear approximation, so the points are indicative and do not add up exactly to the displayed probability).
- **Themes.** Features are grouped into four reason themes so that correlated features do not split credit misleadingly: **Ownership** (assigned when filed, reporter experience, commenters), **Scope** (priority, type, components, links, title and description length), **Workload** (open tickets in the project), **History** (project and peer-group history, workflow, and the ticket's own first-week activity and stage). Each ticket shows its theme totals as well as its individual reasons.
- **Plain-English wording.** Each feature has a sentence that states the fact about the ticket and compares it with what is typical in its project where that helps ("Long description (2411 characters; typical here 288)"). The wording states facts; the direction (raises or lowers risk) comes from the sign of the points. A test requires every model feature to have a theme and wording that handles missing values.
- **Displayed probability** is the calibrated probability limited to 5% to 95% (see `docs/model-results.md`). The "riskiest 10%" flag uses the unclipped score against the 90th percentile of test scores (0.648 at creation, 0.940 at day 7).

## What is exported

| File | Size | Contents |
|---|---|---|
| `backtest_tickets.json` | 3,055 KB | 2,000 random test-period tickets per prediction point with probability, top 5 reasons, theme totals and the actual outcome |
| `open_tickets.json` | 1,016 KB | The 715 tickets still open at the snapshot and not yet past their threshold, scored at creation and (where older than 7 days) at day 7 |
| `global.json` | 13 KB | Overall importance, importance by theme and by project, how risk changes with five key features, and the stability results |
| `model_quality.json` | 13 KB | Metrics, calibration tables, per-project results, bootstrap comparisons |
| `overview.json` | 14 KB | The SQL analysis tables behind the overview page |
| `meta.json` | under 2 KB | Snapshot date, split window, base rates, cutoffs, disclaimer |

The files are committed because the GitHub Pages build cannot rerun the 5.8 GB extraction. No person-level field is exported (no assignee, reporter or author identifiers; only counts such as "Reporter has filed 4 earlier tickets"), and the export asserts this.

## Are the explanations stable?

The global importance ranking was recomputed after refitting the model on five bootstrap resamples of the training data and on earlier data only (trained on tickets known before 2017 and before 2018):

| | Bootstrap refits (rank correlation with the main model) | Earlier-data refits | Top 3 features in common (of 3) |
|---|---|---|---|
| Creation | 0.97 to 0.99 | 0.95 to 0.97 | 2 to 3 |
| Day 7 | 0.94 to 0.97 | 0.96 to 0.97 | 2 to 3 |

The ranking barely moves; the top drivers are assigned-when-filed, project and workflow, and reporter experience at creation, and assigned-by-day-7, project, workflow and recent activity at day 7.

## Limits to state wherever explanations are shown

- Reasons describe what the model associates with lateness, not what causes it. Assigning a ticket does not make it faster.
- `project_key`, `workflow_family` and the project history features overlap; the theme totals are the safer thing to read.
- Points are approximate; probabilities near 5% or 95% are bounds, not estimates.
- Only a 2,000-ticket sample per point of the test period is exported with reasons, plus the open tickets. The model itself scores every ticket.
- The open tickets scored are the 715 that were open at the snapshot and not yet late. The much larger group of open tickets already past their threshold is late by definition, so there is nothing to predict for them.
