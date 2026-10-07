# Map: Delivery Risk Radar

Label: wayfinder:map

## Destination

A **build-ready spec** for Delivery Risk Radar (predict which Apache Jira tickets will run late, and explain why), detailed enough that each phase (extraction, SQL analysis, model, dashboard) can be handed to a separate build session. Planning only: no build happens inside this map.

## Notes

- Domain: software delivery analytics on public Apache Jira issue histories.
- Stack: Python, DuckDB, SQL, scikit-learn, Jupyter; final dashboard on GitHub Pages (static hosting, no backend).
- Phases: data extraction -> SQL analysis (cycle time, bottlenecks) -> late-ticket prediction model -> dashboard.
- Audience: both analyst and data-science roles; SQL findings and the model are equal showpieces, and the explanations are the dashboard's selling point.
- Vocabulary lives in `GLOSSARY.md` at the repo root (created lazily when the first term resolves). ADRs under `docs/adr/` only for hard-to-reverse, surprising, trade-off decisions.
- Plan, don't do. Exception: a single AFK `task` ticket may fetch a small data sample if a decision needs real data.
- The earlier Step 1 request (CLAUDE.md, `etl/extract.py`, DuckDB load) is a post-map hand-off, not part of this map.
- Tickets live in `issues/`. Research findings land in `research/`.

## Decisions so far

<!-- one line per resolved ticket: [title](link): gist -->

- [Define "late"](issues/03-define-late.md): late = delivered ticket whose lead time (created to final resolution, calendar days) is above its peer group's P75 (project and issue type, min 30 tickets with fallbacks), thresholds from the training period only, binary label.
- [Dashboard design](issues/11-dashboard-design.md): resolved on delegation; hybrid of the analytics overview (landing) and the triage queue (open tickets), plus model quality and method pages; global day 0 or day 7 toggle; snapshot date on every page; Observable Framework with precomputed exports on GitHub Pages. Prototype at `prototypes/dashboard-prototype.html`.
- [Repo layout and test strategy](issues/12-repo-layout-and-tests.md): resolved on delegation; `etl/`, `sql/`, `radar/` package, `notebooks/`, `config/`, `dashboard/`, gitignored data with a committed sample; pytest with a leakage guard; uv lock file; six build sessions starting with extraction.
- [Cycle time and status stages](issues/09-cycle-time-and-status-stages.md): cycle time starts at first entry into an active stage (Building or In review) from a per-project status mapping; four stages; loop time summed and review rounds counted; SQL reports stage share of lead time, wait to first review and review rounds as percentiles.
- [Explainability](issues/10-explainability.md): SHAP per ticket (top 5 plain-English reasons plus peer comparison), grouped into reason themes; global importance and per-project drivers; precomputed JSON for the static page; explanations checked for stability and described as associations, not causes.
- [Model and validation](issues/07-model-and-validation.md): logistic regression baseline plus gradient boosting main model, two models (creation and day 7) pooled across projects, label-aware time split, PR-AUC primary with calibration and precision at top 10%, no resampling, success means beating both baselines with bootstrap intervals.
- [Feature set](issues/06-feature-set.md): allowlisted features: type, project, within-scheme priority rank, component and link counts, title and description lengths, project and assignee workload, peer-group recent lead time and late rate, a first-time versus experienced reporter bucket; day 7 adds assignment, changelog events, comments, distinct commenters and days since last activity. Stage-based features wait on the status stages ticket.
- [Sample real Apache data](issues/08-sample-real-apache-data.md): 4,743 resolved tickets from KAFKA, HDFS and CASSANDRA via the live API. Status vocabularies differ per project (Cassandra has about 16); 87-96% of tickets never enter a status named "In Progress"; priority is populated but uses two schemes; no changelog truncation; lead times are heavy-tailed (P90 is 30-40x the median). Sample is resolved-only and skews to early-year tickets.
- [Prediction point and leakage rules](issues/05-prediction-point-and-leakage.md): two prediction points (creation and day 7), as-of values rebuilt from the changelog, default-deny allowlist, time split on prediction time, workload allowed but no per-person history or views.
- [Data scope](issues/04-data-scope.md): Public Jira Dataset, Apache only, snapshot to ~Jan 2022; one streamed extraction pass to Parquet (no MongoDB, disk too small for a restore); a handful of large projects, all types except Epic and Sub-task, rule-based outlier filters; script, checksum and a small sample in git, data local.
- [Find public Apache Jira datasets](issues/01-find-public-apache-jira-datasets.md): research recommends The Public Jira Dataset (Zenodo, CC BY 4.0, 5.8 GB MongoDB dump, 657 Apache projects, ~1.01M issues to ~Jan 2022, with changelog) as the base. Due dates exist on under 1% of issues, so "late" needs a derived definition. Adopted in Data scope.
- [GitHub Pages dashboard options](issues/02-github-pages-dashboard-options.md): research recommends Observable Framework with Python data loaders deployed via GitHub Actions, serving precomputed scores and explanations (JSON/Parquet); precomputed JSON plus a chart library is the fallback. Not yet confirmed by you. Spikes still open: Parquet range requests on Pages, real data size.

## Not yet specified


## Out of scope

- Live Jira integration or any server-side backend (dashboard is static).
- Deep learning or LLM-based prediction.
- Forecasting for private or company Jira instances.
