# 06 - Feature set

Type: grilling
Status: resolved
Blocked by:

## Question

Which allowlisted features does the model use at each prediction point (creation, and day 7)? Walk the candidates: ticket attributes (type, priority, project, components, title and description length or text signals), reporter history, workload (open tickets per assignee and project), history signals available at day 7 (assigned or not, status moves, comment activity), and project-level history (recent lead-time medians, recent late rate). For each, confirm it is reconstructible as of the prediction point under the leakage rules, and decide include, defer or exclude. Decide whether text features are in scope for v1.

## Evidence from the real-data sample

Priority is populated on every sampled ticket but with two schemes: Blocker/Critical/Major/Minor/Trivial (KAFKA, HDFS) and Urgent/High/Normal/Low (CASSANDRA), so priority needs normalising across projects. Status vocabularies differ per project. See [research/08-apache-sample-findings.md](../research/08-apache-sample-findings.md). The sample is resolved-only and skews to early-year tickets.

## Answer

All features are allowlisted: reconstructed as of the prediction point.

**At creation (and carried to day 7, as of day 7)**
- Issue type, priority, project, component count, linked-ticket count. No creation weekday or month.
- Priority is ranked within each project's own scheme and scaled 0-1. The mapping table goes in the spec.
- Text: numeric signals only (title length, description length, and perhaps whether the description has a stack trace or code block). No TF-IDF or embeddings in v1.
- Workload: open tickets in the project at the prediction point, and the assignee's open tickets if one is set (empty when unassigned). Aggregates only.
- Peer-group history: median lead time and late rate of the last 200 delivered tickets in the peer group resolved before the prediction point.
- Reporter bucket: first-time versus experienced, from prior ticket counts as of the prediction point. No per-person late rate.

**Added at day 7 only**
- Assigned or not, number of changelog events, comment count, number of distinct commenters, days since last activity.

**Deferred until the status stages ticket resolves**
- Stage-based day-7 features, for example "has reached a review stage" and time spent in each stage so far.

**Excluded:** the never-use list from the leakage rules, per-person historical late rates, creation weekday and month, real text features.
