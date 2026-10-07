# Delivery Risk Radar: Glossary

**Ticket**:
A unit of tracked work in a Jira project. Use "ticket" in prose and the dashboard. The dataset's own name for it, "issue", appears only in raw-data identifiers.
_Avoid_: issue (outside raw-data identifiers)

**Lead time**:
Calendar days from a ticket's creation to its final resolution. For a reopened ticket, the clock stops at the last resolution, not the first. This is the clock "late" is judged on.
_Avoid_: duration, age (age is for tickets not yet resolved)

**Cycle time**:
Calendar days from a ticket's first entry into an active stage to its final resolution. Empty for tickets that never enter an active stage; the share of those is reported per project. An analysis metric for the SQL phase, not the "late" label.

**Peer group**:
The tickets of the same project and issue type that a ticket's lead time is compared against.

**Delivered ticket**:
A ticket resolved as Fixed or Done. Tickets resolved as Duplicate, Won't Fix, Invalid and similar non-delivery values are excluded from lead-time percentiles and from labels.

**Late**:
A delivered ticket whose lead time is above the P75 of its peer group. A peer group with fewer than 30 delivered tickets falls back to the project-wide P75, then the issue-type-wide P75. Thresholds are computed on the training period only and reused on later tickets. A ticket still unresolved is late once its age already exceeds its threshold; a younger unresolved ticket is unlabelled. The model label is binary, and a graded view (P75 and P90) is for analysis and the dashboard only.
_Avoid_: delayed, overdue (overdue implies a due date, which under 1% of tickets have)

**Prediction point**:
The moment in a ticket's life at which its risk of being late is scored. There are two: at creation, and at a fixed age after creation (7 days) for tickets still open then. Both use the same Late label.

**As-of value**:
The value a field had at the prediction point, rebuilt by replaying the changelog backwards. Never the final value, which can leak the future.
_Avoid_: current value, final value

**Allowlisted feature**:
A feature usable by the model only because it can be reconstructed as of the prediction point. Anything not on the allowlist is excluded by default.

**Stage**:
One of four groups that every status maps into, using a mapping table per project: Waiting (for example Open, Triage Needed, Awaiting Feedback), Building (In Progress), In review (for example Patch Available, Review In Progress, Changes Suggested, Ready to Commit) and Done (Resolved, Closed). An active stage is Building or In review.

**Review round**:
One loop from In review back to Waiting (for example Patch Available back to Open). The count of review rounds is a rework signal.

**Reason theme**:
A group of related features (Ownership, Scope, Workload, History) used to present a ticket's explanation without splitting credit across correlated features.
