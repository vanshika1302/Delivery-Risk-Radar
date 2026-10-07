# "Late" is peer-relative: lead time above the P75 of the ticket's peer group

Apache Jira rarely has due dates (under 1% of tickets), so "late versus a due date" cannot be the label. We define a delivered ticket as late when its lead time (creation to final resolution, calendar days) is above the P75 of its peer group: the same project and issue type, with fallback to the project, then the issue type, when a group has fewer than 30 delivered tickets. Thresholds are computed from tickets created and resolved before the training cutoff only. Open tickets already older than their threshold count as late. The label is binary.

**Considered options**

- A fixed number of days: makes every Epic look late and every quick fix look on time.
- A multiple of the peer median: the share of late tickets would vary by group, and the heavy tails (P90 is 30 to 40 times the median) make medians a poor anchor.
- The whole dataset as one peer group: compares a Spark ticket with a Cassandra ticket.

**Consequences**

- About a quarter of delivered tickets are late by construction, which keeps enough positives to learn from and makes the label comparable across projects with very different speeds (project P75s range from about 6 to 49 days).
- "Late" means slower than comparable tickets in the same project, not slower than a promise. The dashboard must say so.
- Changing the percentile, group definition or fallback changes every downstream number, so the percentile and minimum group size live in `config/params.toml`.
- Counting open, over-threshold tickets as late adds a stale-backlog population (about 13% of labelled training tickets and 26% in the test window). `labels.is_late_delivered_only` keeps a delivered-only variant so the effect can be measured. See `docs/data-audit.md`.
