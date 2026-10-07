# Delivery Risk Radar

An analytics-first look at Jira data: predict which tickets will run late, and explain why. Portfolio project, built on public Apache Jira issue histories (The Public Jira Dataset, Zenodo 15719919, CC BY 4.0, snapshot to about January 2022).

Phases: data extraction -> SQL analysis (cycle time, bottlenecks) -> late-ticket prediction model -> static dashboard on GitHub Pages.

## Stack

Python 3.13, DuckDB, SQL, scikit-learn, Jupyter, pyarrow (Parquet), pymongo (only its `bson` decoder). Dashboard: Observable Framework with Python data loaders. Virtualenv is `.venv` (already activated); use `python -m pytest` for tests.

## Layout

- `etl/`: `extract.py` (stream the dataset's Apache collection to Parquet), `load.py` (Parquet to DuckDB; keeps every ticket but only the 8 modelling projects' changelog and comments, which keeps the file near 1 GB; `--all-projects` keeps everything), `transform.py` (scope and data quality, status stages, the late label; runs `sql/02` onward with parameters from `config/params.toml`), `run_pipeline.py`. Run as modules from the repo root, e.g. `python -m etl.run_pipeline`.
- `config/`: `params.toml` (projects, thresholds, split dates) and `stage_mapping.csv`. `docs/`: `adr/` and `data-audit.md` (read it before changing scope or labels).
- `sql/`: numbered SQL files (`05_analysis.sql` builds the analysis tables, `06_features.sql` builds the as-of features). `notebooks/`: Jupyter (`02_sql_analysis.ipynb`, with charts; findings in `docs/sql-analysis.md`). `tests/`: pytest. `prototypes/`: throwaway mock-ups.
- `data/raw/` and `data/processed/` are gitignored. The DuckDB file is `data/processed/radar.duckdb`.

## Where the thinking lives

- `GLOSSARY.md`: the canonical vocabulary (Ticket, Lead time, Late, Prediction point, Stage, and more). Use these terms; "ticket" in prose, "issue" only in raw-data names.
- `.scratch/delivery-risk-radar/map.md`: the planning map. Each decision lives in its ticket under `issues/`; research under `research/`. Read the relevant ticket before changing anything it decided.

## Decisions to respect

- **Late** = a delivered ticket (resolved Fixed or Done) whose lead time exceeds the P75 of its peer group (project and issue type, at least 30 tickets, with fallbacks). Thresholds come from the training period only. The label is binary.
- **Two prediction points**: at creation, and day 7 for tickets still open. Features are default-deny: allowed only if reconstructible as of the prediction point from the changelog. Never use resolution, resolution date, final status, the reopened flag, `updated`, fix versions, or anything after the prediction point.
- No per-person late rates or per-person views. Assignees are anonymised in the data; keep it that way.
- Splits are by time, never random.
- Never restore the dataset into MongoDB (it needs about 60 GB). The extraction streams it; the disk is small.
- Do not commit data. A small sample under `data/sample/` is the only exception.
- DuckDB memory and spill space are capped in `config/params.toml` (`[duckdb]`); the disk is small, so a heavy query should fail, not fill it.
