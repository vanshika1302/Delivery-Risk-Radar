# 11 - Dashboard design

Type: prototype
Status: resolved
Blocked by:

## Question

What should the final dashboard look like and do? Make a rough prototype to react to, then decide: the views (for example overview of late rate by project and type, stage and bottleneck charts from the SQL phase, a searchable table of open tickets with risk scores, a ticket detail panel with top reasons and peer comparison, and a model-quality page with calibration and baselines), the interactions, how the day 0 and day 7 scores appear, how the snapshot date is shown ("as of January 2022"), and whether to adopt the research recommendation (Observable Framework with Python data loaders on GitHub Pages, with precomputed JSON as the fallback). No per-person views, per the leakage rules.

## Answer

Resolved on the owner's delegation ("go ahead with your inputs and use your judgement"), not from a live exchange. Reversible: re-open this ticket if the choices below do not feel right.

Prototype: `prototypes/dashboard-prototype.html` (three variants, invented example data, throwaway; open it and flip with the arrows or `?variant=A|B|C`). The repo has no commits, so it is not on a throwaway branch.

- **Chosen shape:** a hybrid of two variants. The **Analytics overview** is the landing page (project filter, late rate, median lead time, share of lead time by stage, what drives lateness across the model). A second page, **Open tickets**, is the **Triage queue** (ranked list with a detail panel showing the top 5 reasons and the peer-group comparison). The **Risk explorer** (age versus risk scatter) is dropped from v1 and kept as an optional later addition.
- **Pages:** Overview, Open tickets, Model quality (baselines, PR-AUC with intervals, calibration, precision at top 10%), and Method (definitions from the glossary, data scope, limits).
- **Prediction points:** one global toggle, "At creation" or "Day 7". The day 7 view lists only tickets at least 7 days old.
- **Snapshot honesty:** every page says the data is as of the January 2022 snapshot, and "open" means open at that date.
- **Explanations:** each reason shows direction, size and its reason theme, with the line "Reasons describe what the model associates with lateness, not what causes it."
- **No per-person views,** per the leakage rules.
- **Hosting:** adopt the research recommendation: Observable Framework with Python data loaders, deployed through GitHub Actions to GitHub Pages. The pipeline exports compact precomputed Parquet or JSON (scored tickets with top 5 reasons, stage statistics, model metrics). Because everything is precomputed and small, the browser never needs DuckDB-WASM or range requests, which removes the open Parquet range-request spike. Check at build time that the export stays well under the 1 GB Pages limit. Fallback: precomputed JSON with a plain chart library.
- Prototype caveats: the example numbers (including the model-check strip) are invented and show layout only.
