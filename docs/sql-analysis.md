# SQL analysis: findings

Built by `sql/05_analysis.sql`; charts and tables in `notebooks/02_sql_analysis.ipynb`. Scope: 8 Apache projects, delivered tickets after the quality exclusions (101,118 tickets), unless stated.

## Where the time goes

| Workflow | Projects | Waiting | Building | In review |
|---|---|---|---|---|
| Review through Jira statuses (Patch Available) | AMBARI, HIVE, HBASE, CASSANDRA | 54% to 72% | 2% to 5% | 21% to 35% |
| Review on GitHub (no review status) | SPARK, FLINK, ARROW, CAMEL | 58% to 95% | 3% to 38% | not visible |

- Tickets spend most of their life waiting. The In Progress stage is a few percent of lead time in most projects (SPARK, at 38%, is the exception).
- The two workflow families cannot be compared on stage shares: the GitHub-review projects show no review time because review does not happen in Jira statuses. Only 9% to 34% of tickets in CAMEL, FLINK and ARROW ever enter an active stage, so cycle time exists for few of them.

## Review flow (projects that use Jira review statuses)

- 68% to 83% of tickets reach review. Median wait to first review is short (0.01 days in AMBARI to 1.6 days in CASSANDRA), but the slowest quarter waits 4.0 days (HIVE), 4.5 (HBASE) and 15.5 (CASSANDRA).
- Rework (a ticket sent back from review to waiting at least once): 6% AMBARI, 8% CASSANDRA, 13% HBASE, 21% HIVE. Among delivered tickets, the late rate is 25% with no review rounds, 37% with one and 46% with two or more. That is an outcome-side association, since rounds accumulate as a ticket lives; it is not a creation-time feature.

## What the late rate does and does not track

- **Priority barely separates.** Blocker 20%, Critical 27%, Major 26%, Minor 24%, Trivial 18%, against 25% overall.
- **Issue type** is flat (24% to 27%) except Wish (45%, 200 tickets).
- **Links, components and assignee are end-of-life values.** Tickets with 2 or more links are late 48% of the time (0 links: 22%), and tickets with no assignee at the snapshot 44% (assigned: 25%), but these values are measured at the snapshot and grow as a ticket lives. They are not creation-time facts and are leaks unless rebuilt as of the prediction point.
- **Late rates by project** are 23% to 31% (ARROW highest at 31%), as expected from the per-project P75.

## Consequences for the model

1. Carry the workflow family (Jira review statuses or GitHub review) as a feature. Stage-based features exist only for the first family.
2. Priority and issue type are weak signals; expect the peer-group history and workload features to carry more.
3. Rebuild links, components and assignee as of the prediction point from the changelog before using them.
4. Keep open, over-threshold tickets in the label (see `docs/data-audit.md`).
