# 07 - Model and validation

Type: grilling
Status: resolved
Blocked by:

## Question

Which model family and evaluation plan? Decide: baseline (for example a per-project base rate or a simple rule), the main model (for example logistic regression versus gradient boosting in scikit-learn), the time-split cutoff and any gap, handling of class imbalance, metrics (for example PR-AUC, recall at a fixed precision, calibration), whether the two prediction points are one model with a feature or two models, and what result would count as good enough to show in a portfolio.

## Answer

- **Model families:** logistic regression as the transparent baseline, and scikit-learn gradient boosting (`HistGradientBoostingClassifier`, which handles missing values natively) as the main model. A project base-rate baseline too.
- **Prediction points:** two separate models, one at creation and one at day 7 (open tickets only), sharing the same code.
- **Pooled across projects:** one model per prediction point across the chosen projects, with project as a feature. Per-project metrics are reported.
- **Split rule:** time-based. The test window ends early enough that at least 90% of its tickets are labelable (resolved, or already older than their threshold). The cutoff sits at about 80% of the labelable time range, with a gap between train and test. Exact dates, the labelable share and the gap are recorded as parameters from the data in the SQL phase. Tuning uses rolling-origin validation, never random folds.
- **Metrics:** PR-AUC primary; ROC-AUC, calibration (Brier score and reliability curve), and precision at the top 10% riskiest tickets.
- **Imbalance:** no resampling. Calibrate probabilities, and choose the operating threshold on a validation set.
- **Good enough:** the main model must beat both the project base-rate baseline and the logistic regression on test-period PR-AUC, with bootstrap confidence intervals. A weak creation-time signal is reported honestly.
