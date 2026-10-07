# 12 - Repo layout and test strategy

Type: grilling
Status: resolved
Blocked by:

## Question

How is the repository laid out, and how is it tested? Decide: the contents of `etl/` (extract, transform, load, run_pipeline), `sql/`, `notebooks/`, `data/` (raw, interim, processed; all gitignored except the committed sample), where model code, explanation code and dashboard code live, how the pipeline is run end to end and made repeatable, what is tested (the label and peer-group logic, as-of reconstruction and leakage checks, the stage mapping, the extraction parser on the committed sample) and with what, how dependencies are pinned (including the new `pymongo` for BSON), and what the first build hand-off sessions are (extraction first, as in the original Step 1).

## Answer

Resolved on the owner's delegation ("go ahead with your inputs and use your judgement"), not from a live exchange. Reversible: re-open this ticket if the choices below do not feel right.

**Layout**
- `etl/`: `extract.py` (stream the dataset's zip entry, decompress, parse the archive framing, keep Apache documents and the chosen fields, write Parquet), `transform.py` (flatten into ticket, changelog and comment tables), `load.py` (Parquet into DuckDB), `run_pipeline.py` (runs all steps in order).
- `sql/`: numbered files, for example stage mapping, labels (peer groups, thresholds), day 0 features, day 7 features, and the analysis queries.
- `radar/`: a small Python package for the shared code: labels, as-of reconstruction, features, models, validation and explanations. SQL builds the tables, Python trains and explains.
- `notebooks/`: data audit, SQL analysis, modelling, explanations. They call `radar/` and read from DuckDB.
- `config/`: parameters in one file (percentile 0.75, minimum group size 30, prediction points, split rules) and one stage mapping table per project.
- `dashboard/`: the Observable Framework site and its Python data loaders.
- `data/`: `raw/`, `interim/` and `processed/` (including `radar.duckdb`) are gitignored. `data/sample/` is the small committed sample. `tests/`, `docs/adr/` and `prototypes/` complete the tree.

**Pipeline:** each step in `run_pipeline.py` can be run alone, skips work when its outputs exist, and reads its settings from the config file. Order: extract, transform, load, SQL tables, train, explain, export for the dashboard.

**Tests (pytest, fast, run on the committed sample)**
- Label logic: peer groups, fallbacks, delivered-only filter, final resolution for reopened tickets.
- As-of reconstruction, plus a leakage guard: features computed at a prediction point must not change when events after that point are removed, and no feature may use a never-use field.
- Stage mapping covers every status in the data, and unmapped statuses fail loudly.
- The extraction parser, run on a tiny archive fixture, and an end-to-end smoke test on the sample.
- SQL files run against in-memory DuckDB with small hand-made tables.

**Dependencies:** `pyproject.toml` with a lock file (uv, matching the project's existing setup), covering duckdb, pyarrow, pandas, scikit-learn, shap, pymongo (for the BSON decoder), matplotlib, jupyter and pytest. At build time, check whether SHAP supports the chosen boosting model.

**Build hand-off order, one session each**
1. Step 1: `CLAUDE.md`, `etl/extract.py` (streamed extraction), DuckDB load, row counts and column names. First run also verifies `priority` and the changelog item names on Apache documents, and lists the real statuses to finish the stage mapping.
2. Data audit, stage mapping, labels and chosen projects (from real counts).
3. SQL analysis (stages, bottlenecks, late rates).
4. Features, baselines, models and validation.
5. Explanations and the dashboard export.
6. Dashboard site, Actions deploy, and the Method page.
