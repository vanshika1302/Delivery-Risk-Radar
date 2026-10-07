# Model results

Produced by `python -m radar.train` (code in `radar/`). Full numbers: `docs/model_results.json`. Decisions followed: "Model and validation" and "Prediction point and leakage rules" in `.scratch/delivery-risk-radar/issues/`.

## Setup

- **Two models per point**, one at creation and one at day 7, pooled over the 8 projects. Each point is compared with two baselines: the project's late rate in training, and the late rate of the peer group's last 200 delivered tickets.
- **Models:** logistic regression (the transparent baseline) and scikit-learn gradient boosting (the main model). Hyperparameters are tuned with rolling-origin validation (train before 2016, 2017 or 2018, validate on the next year, labels known at each cutoff). Probabilities are calibrated with an isotonic map learned on the last validation year.
- **Split by time.** Training: tickets created before 2019-01-01 whose label was already known then (86,467 at creation, 43,142 at day 7). **Test: tickets created 2019-03-01 to 2021-10-01** (30,988 and 18,168), never used for tuning or calibration.
- **Label:** `labels.is_late` (open tickets already past their threshold count as late). Test late rate is 42.7% at creation and 72.0% at day 7.
- Confidence intervals are 95% bootstrap intervals over test tickets; "beats" means the paired interval for the PR-AUC difference excludes zero.

## Results on the test period

**At creation** (30,988 tickets, 42.7% late)

| Model | PR-AUC [95% CI] | ROC-AUC | Brier | Precision in riskiest 10% | Lift |
|---|---|---|---|---|---|
| Project late rate (baseline) | 0.470 [0.463, 0.478] | 0.557 | 0.246 | 0.548 | 1.28 |
| Peer-group history (baseline) | 0.476 [0.469, 0.485] | 0.546 | 0.271 | 0.526 | 1.23 |
| Logistic regression | 0.603 [0.594, 0.611] | 0.694 | 0.218 | 0.714 | 1.67 |
| **Gradient boosting** | **0.622 [0.613, 0.631]** | **0.709** | **0.214** | **0.730** | **1.71** |

Boosting beats both baselines (+0.152 and +0.145 PR-AUC) and the logistic regression (+0.019, interval +0.014 to +0.024). **The success rule from the model decision is met at creation.**

**At day 7** (18,168 tickets still open on day 7, 72.0% late)

| Model | PR-AUC [95% CI] | ROC-AUC | Brier | Precision in riskiest 10% | Lift |
|---|---|---|---|---|---|
| Project late rate (baseline) | 0.762 [0.754, 0.770] | 0.558 | 0.206 | 0.825 | 1.15 |
| Peer-group history (baseline) | 0.749 [0.741, 0.758] | 0.542 | 0.404 | 0.763 | 1.06 |
| Logistic regression | 0.887 [0.882, 0.893] | 0.777 | 0.162 | 0.972 | 1.35 |
| Gradient boosting | 0.886 [0.881, 0.891] | 0.778 | 0.162 | 0.958 | 1.33 |

Both models beat both baselines clearly (boosting +0.124 and +0.137). **Boosting does not beat the logistic regression at day 7** (difference -0.001, interval -0.004 to +0.001), so the rule is not met for boosting there; the two are tied. The peer-history baseline's Brier score is poor because its scores are raw rates, not calibrated probabilities.

## How to read these numbers

- **The signal at creation is moderate.** ROC-AUC is 0.71. The riskiest tenth of tickets is 73% late against a 43% base rate, a lift of 1.7. That is useful for triage, not a verdict on any one ticket.
- **Day 7 is a different population.** Tickets still open on day 7 are late 72% of the time, so PR-AUC is high for every model, including the baselines. ROC-AUC (0.78 against 0.56 for the baselines) and the Brier score are the fairer measures of what the model adds.
- **Calibration is good.** Predicted and observed late rates agree within a few points across all ten deciles at both points; calibration changes the Brier score by about 0.001.
- **It is not an artifact of stale open tickets.** Restricted to delivered tickets only (no open tickets in the label), the creation model reaches PR-AUC 0.341 against a base rate of 0.226 and a project-rate baseline of 0.234 (ROC-AUC 0.674). At day 7 the delivered-only subset gives 0.727 against a base rate of 0.500.
- **Every project beats its own base rate at creation:** ARROW 0.63 vs 0.44, FLINK 0.59 vs 0.43, SPARK 0.52 vs 0.37, HIVE 0.75 vs 0.55, HBASE 0.59 vs 0.42, CASSANDRA 0.68 vs 0.52, AMBARI 0.84 vs 0.69. CAMEL is weakest (0.34 vs 0.27, lift 1.3). AMBARI's test set is small (419 tickets at creation) because most of its tickets predate 2019.

## What drives the predictions

Permutation importance on the test period (drop in PR-AUC when a feature is scrambled), top features:

- **Creation:** `assignee_open` 0.09, `project_key` 0.07, `reporter_prior_tickets` 0.04, `description_length` 0.02, `issue_type` 0.02. Without `assignee_open`, PR-AUC falls from 0.630 to 0.592 (ROC-AUC 0.709 to 0.659); without the reporter features, to 0.618; without peer and project history, it does not fall (0.634).
- **Day 7:** `project_key` 0.03, `assignee_open` 0.03, `days_since_activity_day7` 0.01, `events_by_day7` 0.01. No single feature group matters much; dropping any one changes PR-AUC by at most 0.004.

`assignee_open` is empty when nobody is assigned, so in practice it works as "was this ticket assigned when it was filed". That is a real and consistent signal: tickets filed with an assignee are late far less often (HIVE 34% vs 72%, AMBARI 25% vs 69%, SPARK 14% vs 34%). I checked it is not a leak: only 14 of 52,727 assigned-at-creation tickets have an assignment event within 10 seconds after creation, and 47,128 have no assignment event at all (they were created with the assignee). The workload count itself adds little: late rates are flat at 22% to 27% across workload buckets. The explanation layer should phrase this as "assigned when filed" or "unassigned when filed", not as a workload number.

Priority matters less than expected (permutation importance 0.01), consistent with the SQL analysis.

## Caveats

- One time split, one test window (2019-03 to 2021-10). Results are not a rolling backtest.
- The late rate drifts upward over time (36.2% in training, 42.7% in test at creation) because more recent tickets stay open. The test set reflects this, and calibration (learned on 2018 tickets) holds up anyway.
- Run-to-run variation is about ±0.002 PR-AUC. The tuner's chosen tree depth for boosting changed between two identical runs because the grid scores are nearly tied; this does not change the conclusions.
- Thresholds, and so the label, come from the training period only. Tickets created near the end of the data may still be young; the test window ends 2021-10-01 so that 99.8% are labelable.
- The model describes associations in this data, not causes. The dashboard must say so.

## Open for the owner

- At day 7 the logistic regression matches boosting. Using the logistic model there would be simpler and transparent; the explainability decision assumed SHAP on boosting, which still works either way.
