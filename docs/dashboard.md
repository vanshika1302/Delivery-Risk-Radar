# The dashboard

A static site built with [Observable Framework](https://observablehq.com/framework/). It computes nothing at run time beyond drawing charts: every number comes from the small JSON files in `dashboard/src/data/`, written by `python -m radar.export` and committed. That is deliberate. A GitHub build cannot rerun the 5.8 GB extraction, and the files are about 4 MB.

## Pages

| Page | What it shows |
|---|---|
| Overview | where the time goes (by stage, grouped by where review happens), waiting for a first review, why delivered-only late rates mislead, what the model relies on |
| Open tickets | the 715 tickets open at the snapshot and not yet late, ranked by risk, scored at filing or on day 7, with the top reasons for the selected ticket |
| Model quality | the model against baselines (with intervals), calibration, every project against its own base rate, how risk moves with five signals, and a backtest explorer over a sample of test tickets |
| Method | the data, the cleaning, the definition of late, the prediction points, the model and its limits |

The layout follows the throwaway prototype in `prototypes/dashboard-prototype.html` (the analytics overview as the landing page, a triage queue for open tickets, plus quality and method pages).

## Run it locally

```bash
cd dashboard
npm ci
npm run dev      # live preview
npm run build    # static copy in dashboard/dist
```

Needs Node 18 or newer. Light and dark mode follow the viewer's setting; the layout works at phone width.

## Refresh the data

After retraining: `python -m radar.train && python -m radar.report && python -m radar.export`, then commit the changed files in `dashboard/src/data/` and `docs/`.

## Publishing (not done)

`.github/workflows/deploy-dashboard.yml` builds the site and deploys it to GitHub Pages. It is **manual only** (`workflow_dispatch`) on purpose:

1. **A Pages site is public even when the repository is private.** The dashboard shows ticket keys, reasons and model results for public Apache tickets, and no personal data, but publishing is still the owner's decision.
2. GitHub Pages for a private repository needs a paid plan (Pro, Team or Enterprise). On a free account, make the repository public first or use another static host.
3. To publish: in the repository settings, set Pages "Source" to "GitHub Actions", then run the workflow from the Actions tab. The site appears at `https://<user>.github.io/Delivery-Risk-Radar/`.

The build output is plain static files, so any static host works (Netlify, Cloudflare Pages, an S3 bucket): upload `dashboard/dist`.

## How the page was checked

Each page was built and loaded in headless Chrome with light and dark mode forced, at desktop width and at 400 px: no render errors, no console errors, no horizontal overflow, and every chart drawn from the real data.
