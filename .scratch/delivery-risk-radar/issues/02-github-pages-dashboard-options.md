# 02 - GitHub Pages dashboard options

Type: research
Status: resolved
Blocked by:

## Question

What are the realistic ways to ship an interactive dashboard on GitHub Pages (static hosting only) when the data and model outputs come from a Python/DuckDB pipeline? Compare at least: precomputed JSON/CSV plus a JS chart library, DuckDB-WASM querying Parquet in the browser, and a static-site tool such as Evidence or Observable Framework. For each: size limits on GitHub Pages, build and deploy flow (including GitHub Actions), how per-ticket explanations could be shown, and effort versus polish. End with a recommendation.

## Answer

Recommended: Observable Framework with Python data loaders, deployed through the documented GitHub Actions workflow (add setup-python). Precompute model scores and per-ticket explanations in the pipeline and ship as Parquet/JSON. Precomputed JSON plus a chart library is the simple fallback; DuckDB-WASM is optional and built into Framework; Evidence's current docs do not cover GitHub Pages. Pages limits: 1 GB site, 100 GB/month soft bandwidth, 10-minute deploy timeout; 100 MiB per committed file. Open items to spike: Range requests for Parquet on Pages, real data size.

Full findings: [research/02-github-pages-dashboard-options.md](../research/02-github-pages-dashboard-options.md)
