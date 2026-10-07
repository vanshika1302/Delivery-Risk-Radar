# 03 - Define "late"

Type: grilling
Status: resolved
Blocked by: 01

## Question

How do we define a "late" ticket? Apache Jira rarely has due dates or estimates, so candidates include: resolution time above a per-project percentile (e.g. P75/P90), above a fixed number of days, above a multiple of the project/type median, or a reopen/missed-target signal if the data has one. Decide the definition, whether it is relative per project and issue type, and how unresolved (still open) tickets are treated. Record the term in `GLOSSARY.md`; offer an ADR if the choice is hard to reverse.

## Answer

- **Clock:** lead time (created to final resolution, calendar days) is the label clock. Cycle time stays an analysis metric.
- **Threshold:** a ticket is late when its lead time is above the P75 of its peer group (same project and issue type). The percentile is a single configurable parameter.
- **Small groups:** a peer group needs at least 30 delivered tickets, otherwise fall back to the project-wide P75, then the issue-type-wide P75.
- **Delivered only:** keep tickets resolved as Fixed or Done. Exclude Duplicate, Won't Fix, Invalid and similar, and report how many that removes.
- **Reopened tickets:** the final resolution counts. A "was reopened" flag is outcome information, so it is not a feature.
- **Unresolved tickets:** late if their age already exceeds the threshold. Younger ones are unlabelled and feed the dashboard's at-risk view only.
- **Thresholds are computed on the training period only** and reused on later tickets, to avoid leakage.
- **Label is binary.** A graded view (P75 and P90) is for analysis and the dashboard.
- **Vocabulary:** terms recorded in [GLOSSARY.md](../../../GLOSSARY.md): Ticket, Lead time, Cycle time, Peer group, Delivered ticket, Late.
