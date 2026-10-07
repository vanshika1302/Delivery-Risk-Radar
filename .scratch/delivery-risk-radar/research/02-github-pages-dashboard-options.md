# Research 02: Shipping an interactive dashboard on GitHub Pages

Question: realistic ways to ship an interactive dashboard on static-only GitHub Pages when data and model outputs come from a Python/DuckDB pipeline. Date researched: 2026-10-05.

## Constraints common to all options (GitHub Pages)

- Published site must not exceed 1 GB; source repo recommended limit is 1 GB; soft bandwidth limit 100 GB/month; deployments time out after 10 minutes; soft limit of 10 builds/hour (waived with custom GitHub Actions workflows). Source: GitHub Docs, "GitHub Pages limits" https://docs.github.com/en/pages/getting-started-with-github-pages/github-pages-limits
- Git warns on files over 50 MiB and GitHub blocks files over 100 MiB (Git LFS otherwise). Source: https://docs.github.com/en/repositories/working-with-files/managing-large-files/about-large-files-on-github . This applies to anything committed; files generated inside a Actions build and uploaded as a Pages artifact are not committed, so the repo limit does not apply to them, but the 1 GB site limit does.
- Custom workflow deploys use `actions/configure-pages`, `actions/upload-pages-artifact`, `actions/deploy-pages`; artifact must be a gzipped tar under 10 GB, no symlinks/hardlinks; job needs `pages: write` and `id-token: write` and the `github-pages` environment. Source: https://docs.github.com/en/pages/getting-started-with-github-pages/using-custom-workflows-with-github-pages
- Pages is static only: no server-side query or inference at request time. All model scoring must happen in the pipeline.

## Option A: Precomputed JSON/CSV + a JS chart library

- Flow: Python/DuckDB pipeline writes aggregates and per-ticket rows to JSON/CSV (or small Parquet); hand-written HTML/JS (Plot, Chart.js, D3, Vega-Lite, etc.) fetches and renders them. Actions workflow: run pipeline (setup-python, install, run), copy output into `site/`, then configure-pages / upload-pages-artifact / deploy-pages (pattern above). Alternatively commit outputs and let Pages serve them.
- Size: bounded by the 1 GB site limit; practically keep each file well under 50 MiB (git warning) if committed. Split per-ticket data into chunked/sharded files (e.g. one JSON per project or per prediction snapshot) so the browser loads only what it needs.
- Per-ticket explanations: precompute them in Python (e.g. top-N feature contributions or SHAP values, plain-text reason strings) into a per-ticket JSON; the UI is a searchable table with a detail drawer rendering a contribution bar chart. Fully under our control, no runtime compute.
- Effort vs polish: lowest tooling risk, smallest bundle, but all layout/filter/table UI is hand-built; polish depends on front-end effort.

## Option B: DuckDB-WASM querying Parquet in the browser

- What it is: full DuckDB engine in the browser via WebAssembly; supports Parquet with partial reads (metadata-only answers, row-group skipping on filters), so querying large remote Parquet is practical. Remote files are registered lazily with `db.registerFileURL(name, url, DuckDBDataProtocol.HTTP, false)` and are subject to browser CORS rules. Installed via npm (`@duckdb/duckdb-wasm`) or jsDelivr bundles. Sources: https://duckdb.org/docs/current/clients/wasm/overview.html , https://duckdb.org/docs/current/clients/wasm/data_ingestion.html
- Limits: single-threaded by default (multithreading experimental); WebAssembly memory capped at 4 GB and browsers may be stricter (same overview page). The docs do not state range-request requirements or file-size thresholds; whether GitHub Pages serves HTTP Range requests correctly was NOT verified from an official source and should be tested in a spike.
- Same-origin Parquet on Pages avoids CORS issues. Size limits same as above (Parquet is compact; 1 GB site cap, 100 MiB per committed file).
- Build/deploy: same as A (pipeline writes `.parquet`; static JS app + wasm bundles deployed). Extra: ship the wasm/worker bundles (self-host or CDN).
- Per-ticket explanations: store explanation columns (feature contributions, reason text) in the Parquet; user can filter/sort/search with arbitrary SQL and drill into one ticket with a `WHERE ticket_id = ...` query. Enables ad-hoc slicing without pre-aggregating every view.
- Effort vs polish: highest engineering complexity (async init, worker, Arrow-to-chart plumbing), heavier initial download; payoff is flexible exploration. Overkill when the dataset is small enough to ship as JSON.

## Option C: Static-site tools

### C1. Observable Framework (open source, static output)

- Build produces a static `dist`; docs state it can be hosted on any static host and give a GitHub Pages + Actions guide: workflow with triggers on push to main, daily cron, and manual dispatch; steps checkout, setup-node (22), `npm ci`, `npm run build`, configure-pages, upload-pages-artifact (path `dist`), deploy-pages. Source: https://github.com/observablehq/framework/blob/main/docs/deploying.md (rendered at https://observablehq.com/framework/deploying).
- Data loaders are polyglot, include built-in Python (`.py`, run with `python3`; venv/uv supported) and can invoke DuckDB; they run at build and emit static snapshots (CSV, JSON, Parquet, etc.); a loader runs only if its output is referenced by a page; outputs are cached; a non-zero exit fails the build. The docs show an Actions step caching `src/.observablehq/cache`. Source: https://github.com/observablehq/framework/blob/main/docs/data-loaders.md
- DuckDB-WASM is built in (`sql` code blocks, `DuckDBClient`) and loads Parquet/CSV/JSON/Arrow `FileAttachment`s, so Option B comes almost free. Source: https://github.com/observablehq/framework/blob/main/docs/lib/duckdb.md
- Python must be installed in the Actions job in addition to Node (add setup-python; the doc's sample only sets up Node).
- Per-ticket explanations: a Python loader emits the explanations file; a page uses Inputs.table / search input plus Observable Plot for a contribution chart in a detail view. Dynamic pages per ticket are possible but thousands of pages is heavy; a single page with a selector is more practical (my inference, not stated in docs).
- Size: same Pages limits; Framework copies only referenced files into `dist`.
- Effort vs polish: moderate effort, good default look, reactive inputs, Markdown authoring; JS-centric.

### C2. Evidence

- Current official docs (checked 2026-10-05) position Evidence around Evidence Studio (hosted) and self-hosting as a Docker server (`evidence serve`) that must use direct connectors; the self-host guide lists Vercel, Render, Fly.io, Railway and contains no GitHub Pages guide. Sources: https://docs.evidence.dev/self-host/index.md , https://docs.evidence.dev/llms.txt . The repo README mentions "self-host the generated static site" without detail. I found no current official GitHub Pages instructions; older versions of Evidence did document static builds, but I could not confirm that from current primary sources.
- Conclusion: Evidence is a poor fit for GitHub Pages right now; verifying that a static export still works would be a spike with unknown risk. SQL-and-markdown authoring is attractive but the hosting story has moved away from static hosting.

## Comparison

| | A: JSON + chart lib | B: DuckDB-WASM | C1: Observable Framework | C2: Evidence |
|---|---|---|---|---|
| Pages fit | Excellent | Good (verify Range) | Excellent, documented | Not documented |
| Python pipeline | Plain step in Actions | Plain step | Native Python loaders | Needs connector |
| Per-ticket explanations | Precomputed JSON, custom drawer | Parquet columns + SQL | Loader output + table/plot | n/a |
| Effort | Low-medium (UI by hand) | High | Medium | Unknown |
| Polish | Depends on you | Depends on you | High out of the box | High if it works |

## Recommendation

Use Observable Framework with Python data loaders (Option C1), deployed via the documented Actions workflow plus a setup-python step. It gives the best polish per hour, the pipeline stays in Python/DuckDB, the output is plain static files, and DuckDB-WASM is available later if we want in-browser slicing without changing stack. Precompute all model scores and per-ticket explanations (top feature contributions, reason text) in the pipeline and ship them as Parquet/JSON; keep the dashboard to aggregates plus one searchable ticket table with a detail panel. Fallback if Node tooling is unwanted: Option A with Observable Plot or Vega-Lite on hand-written HTML. Skip Evidence for Pages. Open items to test in a spike: Range-request behaviour of Pages for Parquet, real data size versus the 1 GB cap, and total Actions build time versus the 10-minute deploy timeout (applies to the deployment step, not the build).
