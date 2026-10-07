# Features (as of each prediction point)

Built by `sql/06_features.sql` into the DuckDB table `features`: one row per ticket per prediction point. Population and rules follow the "Prediction point and leakage rules" and "Feature set" decisions.

## Population

| Point | Rows | Who gets a row |
|---|---|---|
| `creation` | 122,831 | Every ticket that has a label or can be scored: labelled, open past its threshold, or open and young. Excluded and non-delivered tickets get none. |
| `day7` | 64,799 | Tickets that were still open on day 7, using what was known on day 7, and whose day 7 falls inside the data (on or before the 2022-01-06 snapshot). |

## Columns

- **Both points:** `workflow_family`, `issue_type`, `priority_rank` (0 to 1 within each project's own scheme, `config/priority_rank.csv`), `component_count`, `link_count`, `title_length`, `description_length`, `project_open`, `assignee_open`, `has_assignee`, `reporter_prior_tickets`, `reporter_first_time`, `peer_n` and `peer_median_lead_days` and `peer_late_rate` (last 200 delivered tickets of the peer group resolved before the point), and the same three for the whole project.
- **Day 7 only (null at creation):** `events_by_day7`, `comments_by_day7`, `commenters_by_day7`, `days_since_activity_day7`, `stage_at_day7`, `days_in_stage_day7`, `entered_active_by_day7`, `entered_review_by_day7`, `review_rounds_by_day7`.

## How as-of values are rebuilt

Priority, issue type, title length and description length come from the "from" value of the first change after the prediction point; if nothing changed later, the current value is the value then. Component and link counts are today's count with every later add undone. The assignee at the point comes from the assignee history. Workload and project history are running counts looked up at the point. Reporter experience counts the reporter's earlier tickets across all Apache projects.

## Verified against independent derivations

On a CASSANDRA and SPARK run, every reconstruction was compared with a separate forward replay of the changelog (start from the initial value, apply changes up to the point): priority, assignee, components and links all agreed on every checked row (47,950, 47,933 and 4,000 rows; 0 mismatches). A first assignee "mismatch" turned out to be the check ignoring unassign events (`arg_max` skips NULLs), not the SQL.

## What the features work found

- **Priority is changed after creation far more than expected.** The share of tickets whose priority at creation differs from the final priority is 79% in CASSANDRA, 29% in FLINK, 13% in SPARK and 10% in CAMEL (2% to 4% in AMBARI, HIVE and ARROW). Using the final priority would have leaked heavily.
- **Links and components also change** after creation: the creation-time link count differs from the final count for about 27% of tickets, and components for about 21% (smoke run).
- **Two leaks were caught and closed while building this:**
  1. A day-7 row requires the ticket to have reached day 7 inside the data, otherwise its state at day 7 is unknown.
  2. A ticket resolved before day 7 and reopened later is not open on day 7. Keeping it (because its final resolution is later) would leak the reopen. 1,091 such rows are dropped.
- **Missing values to expect:** `assignee_open` is empty when nobody is assigned (about 57% of creation rows). `peer_*` is empty for about 2% of rows (the first tickets of a peer group).

## Not yet done

Features that need text (beyond lengths) are out of v1, per the decision. The model session consumes this table; the time split and label come from `labels` (`split`, `train_eligible`, `is_late`).
