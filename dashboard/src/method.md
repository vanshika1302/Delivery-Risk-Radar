---
title: Method
---

```js
const meta = FileAttachment("data/meta.json").json();
const q = FileAttachment("data/model_quality.json").json();
```

# How this was built

<p class="lede">Every number on this site comes from a public Jira snapshot, a fixed definition of "late", and a model tested on tickets it had not seen.</p>

## The data

- **Source:** The Public Jira Dataset (Montgomery et al., 2022; Zenodo, CC BY 4.0). Its Apache collection holds about 1.01 million tickets with full change history. The snapshot ends in early January 2022, so everything here is as of ${meta.snapshot}.
- **Scope:** the eight largest software-delivery projects after setting aside operations requests (INFRA) and a legacy import (FLEX): ${meta.projects.join(", ")}. Epics and sub-tasks are left out because they are not comparable with ordinary tickets.
- **Cleaning:** tickets with impossible dates are dropped (289 early SPARK tickets are dated the year 0010; 18 resolved before they were created). So are tickets resolved in under an hour, which are most likely filed after the fix was committed (25% of AMBARI's delivered tickets and 18% of CAMEL's, under 7% elsewhere), and 320 tickets resolved in bulk by one person. The one-hour rule is a deliberate design choice and it narrows what AMBARI and CAMEL results describe.

## What "late" means

- **Lead time** is the days from creation to final resolution. A ticket that was reopened counts to its last resolution.
- **Peer group:** tickets in the same project and of the same type. With fewer than 30 delivered tickets, the group widens to the project, then to the issue type.
- **Late:** a delivered ticket (resolved as Fixed, Done, Implemented, Resolved or Delivered) whose lead time is above the ${Math.round(meta.late_percentile * 100)}th percentile of its peer group. The thresholds come only from tickets finished before ${meta.train_cutoff}, so no label sees the future.
- **Open tickets:** a ticket still open that is already older than its threshold counts as late. A younger open ticket has no label yet. Leaving open tickets out would make recent years look better than they are, because the slowest tickets are not finished yet.

## Two moments of prediction

The model scores a ticket **when it is filed** and again **on day 7** if it is still open. Each score uses only what was known at that moment. Fields that change (priority, type, components, links, assignee) are rebuilt from the change history as they stood then, never the final value: in CASSANDRA, 79% of tickets have their priority changed after filing, so using the final value would have leaked the future. Anything known only after the moment, such as the resolution, is never used.

## The model

Gradient boosting (scikit-learn), compared with a logistic regression and two baselines, trained on ${meta.points.creation.n_train.toLocaleString("en-US")} tickets filed before ${meta.train_cutoff} (${meta.points.day7.n_train.toLocaleString("en-US")} for the day-7 model) and tested on ${meta.points.creation.n_test.toLocaleString("en-US")} filed from ${meta.test_window[0]} to ${meta.test_window[1]}. The split is by time, never random. Hyperparameters were chosen by validating on the next year in a rolling fashion, and probabilities were calibrated on the last validation year. Nothing was tuned on the test period.

## The reasons

Each ticket's reasons are exact SHAP values from the boosting model, grouped into four themes: **Ownership**, **Scope**, **Workload** and **History**. A check requires the values to add up to the model's own output. Rankings stay stable when the model is refit on resampled or earlier data (rank correlation 0.94 to 0.99).

## What this cannot tell you

- It describes what the model associates with a ticket running slow, not what causes it.
- Late means slower than comparable tickets, not later than a promised date.
- It covers eight large projects over a fixed period, and ends in January 2022.
- The test sample at the bottom of "Model quality" is random, not hand-picked, so some of the tickets are explained poorly. That is the point of looking.
- Nothing here is about individuals. Assignees and reporters are anonymised in the source, and the model only uses counts such as how many tickets a reporter had filed.

## The code

The project is a Python and SQL pipeline (DuckDB, scikit-learn, SHAP) that extracts the dataset, builds the label and features, trains the models and exports the small files this site reads. The site itself is static and computes nothing in your browser beyond drawing charts.
