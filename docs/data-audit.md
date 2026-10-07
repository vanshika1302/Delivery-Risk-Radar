# Data audit (Apache extraction, snapshot 2022-01-05)

Source: The Public Jira Dataset, Apache collection, extracted by `etl/extract.py` (1,014,926 documents, 1,014,909 tickets after removing 17 that the dump wrote twice). Parameters and choices below live in `config/params.toml` and `config/stage_mapping.csv`.

## What the audit found

| Finding | What we did |
|---|---|
| 646 projects (the paper reports 657); keys match names | Nothing. Noted. |
| 289 SPARK tickets are dated the year 0010 (early import) | Excluded (`bad_created`, created before 2001). |
| 18 tickets resolved before they were created (old imports) | Excluded (`negative_lead`). |
| 60 tickets have a resolution date but no resolution | Treated as not delivered. |
| Delivered resolutions go beyond Fixed and Done: Implemented, Resolved, Delivered mean the same | Added to `delivered_resolutions`. Later, Abandoned, Auto Closed, Staged and similar stay out. |
| Priority has at least 16 values across several schemes (Blocker..Trivial, Urgent/High/Normal/Low, P0..P4, "Not a Priority"); 12,612 tickets have none | Feature work must rank priority within each project's scheme. Not touched yet. |
| 51 distinct status names, 8 used widely | Mapped to four stages in `config/stage_mapping.csv`. All statuses in the chosen projects map. |
| The first status is not in the changelog | Taken from the "from" of the first change, or the current status if it never changed. |
| Delivered tickets resolved in under 1 hour: 25% of AMBARI, 18% of CAMEL, under 7% elsewhere | Excluded (`too_fast`, 10,845 tickets). See "Review these". |
| 320 delivered tickets resolved in bulk (10 or more by one person in one minute) | Excluded (`bulk_closed`). |

## Chosen projects (8)

AMBARI, SPARK, HBASE, CAMEL, HIVE, FLINK, ARROW, CASSANDRA: the top 8 by delivered ticket count, after excluding INFRA (operations requests) and FLEX (legacy import, 90% bugs). Four use Patch Available (AMBARI, HBASE, HIVE, CASSANDRA) and four are pull-request based, so both workflows are represented. Project P75 lead times range from about 6 days (AMBARI) to 49 days (FLINK).

## Split (parameters, not yet a modelling decision)

Training cutoff 2019-01-01, two months of gap, test window 2019-03-01 to 2021-10-01. `etl.transform` checks the test window stays at least 90% labelable (it is 99.8%).

## Review these

1. **Open tickets past their threshold raise the late rate, and they should stay in the label.** Among delivered tickets the late rate is 22.6% to 26.5%, as a P75 definition implies. Counting open tickets already past their threshold lifts it to 36% in training and 43% in test, because 13% (train) and 26% (test) of labelled tickets are open ones with a median age of 3.5 years (HIVE: 34%). The SQL analysis settled the question this raised: the delivered-only rate falls for recent cohorts (26% for tickets created in 2019, 18% for 2021) because slow tickets are not delivered yet, while the inclusive rate stays at 41% to 45%. Delivered-only is therefore biased for recent tickets, so keep `labels.is_late` as the target. Use `is_late_delivered_only` only for older cohorts or as a robustness check. The inclusive rate itself drifts up over time (about 27% for 2007 to 2011 creations, about 43% since 2018) because more tickets stay open; evaluate on the time-split test set and watch for that drift.
2. **Design choice, kept: the 1-hour rule.** Delivered tickets resolved in under 1 hour are excluded (`too_fast`, 10,845 tickets), which removes 25% of AMBARI's delivered tickets and 18% of CAMEL's (under 7% elsewhere). The rule stays at 1 hour by decision of the project owner. The reasoning: a ticket created and resolved within the hour is most likely filed after the fix is committed, so there was nothing to predict, and including it would teach the model that "late" is rare for these projects. The cost is real and should be stated wherever results are shown: AMBARI and CAMEL are modelled on a narrower set of tickets, and their P75 thresholds are higher than they would be with these tickets in. The threshold is `scope.too_fast_hours` in `config/params.toml`; a lower cutoff (for example 5 minutes) is the alternative if this is revisited.
3. **Stage mapping judgement calls.** Reopened, Accepted, Assigned and Needs Reviewer map to Waiting; Testing and Verified map to In review. Open to change in the CSV.
4. **The earlier three-project sample was biased.** Its lead times (P75 100 to 280 days) were far longer than the full data (P75 6 to 49 days in the chosen projects), because it took early-year, resolved-only tickets.
