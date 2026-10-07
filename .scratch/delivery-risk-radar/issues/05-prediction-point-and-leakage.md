# 05 - Prediction point and leakage rules

Type: grilling
Status: resolved
Blocked by: 03, 04

## Question

At what moment in a ticket's life is the prediction made (at creation, at first assignment, at first transition to in-progress, or re-scored at every status change)? That choice fixes which fields and history signals may be used as features without leaking the outcome. Decide the prediction point(s) and write the leakage rules (e.g. nothing observed after the prediction point, no resolution-derived fields).

## Answer

- **Prediction points:** two, using the same Late label. At creation, and at a fixed age of 7 days after creation. Only tickets still open at day 7 get a day-7 row. No re-scoring at every status change.
- **As-of values:** changing fields (priority, type, assignee, components, status) take their value as of the prediction point, rebuilt from the changelog, never the final value. Tickets with thin history are flagged.
- **Allowlist, default deny:** a feature is usable only if it can be reconstructed as of the prediction point. Never-use list: resolution, resolution date, final status, the "was reopened" flag, `updated`, fix versions, and any count or timestamp after the prediction point.
- **Splits:** a time split on prediction time. Train on tickets created before a cutoff, and set thresholds using only tickets resolved before it. Tickets created before the cutoff but resolved after it are dropped from training. Test on tickets created after the cutoff. Cutoff date and any gap are model-phase parameters.
- **Person-level features:** workload (open tickets of the assignee or project as of the prediction point) is allowed. No per-person historical late rate, and no per-person views in the dashboard. Project-level history is allowed.
- **Vocabulary:** Prediction point, As-of value and Allowlisted feature are in [GLOSSARY.md](../../../GLOSSARY.md).
