# 04 - Data scope

Type: grilling
Status: resolved
Blocked by: 01

## Question

First confirm the source: the dataset research recommends The Public Jira Dataset (5.8 GB MongoDB dump, about 15 GB restored, data to about Jan 2022) with an optional live-API top-up. Decide whether to adopt it, and how a MongoDB dump gets into DuckDB without making the project hard to reproduce (restore locally, or extract only the Apache subset). Then: which slice of the dataset do we use? Decide: which Apache projects (one deep project versus several), the date window, which issue types (bugs only versus all), and how to handle tickets with missing history, never-resolved tickets, and obvious outliers (bulk-closed, auto-generated). Weigh the trade-off between generalisation across projects and a clean, explainable story for a portfolio.

## Answer

- **Source:** The Public Jira Dataset (Zenodo 15719919, CC BY 4.0), Apache collection only, snapshot ending about January 2022. No live-API top-up in v1.
- **Loading:** one streamed extraction pass. The script downloads the zip entry, decompresses it on the fly (zip deflate, then gzip, then mongodump archive framing), keeps only Apache documents, and writes Parquet. No MongoDB, and nothing large on disk. Costs a 5.8 GB download and a long decompress of about 60 GB. Can use `pymongo`'s BSON decoder (one new dependency).
- **Kept fields:** structured fields (key, project, type, status, resolution, priority, dates, assignee, reporter, changelog), comment counts and timestamps without bodies, and title and description text in a separate optional Parquet file. Comment bodies are dropped.
- **Projects:** a handful of large, varied projects (about 5-8), taken as the top N by delivered ticket count with some workflow variety. The list is chosen from real counts in the SQL phase.
- **Issue types:** everything except Epics and Sub-tasks. Confirm the exact list against the real values.
- **Date window:** everything available, with a data-quality check. Add a floor only if early years prove unstable, and record why.
- **Outliers:** rule-based filters: lead time under 1 hour, and bulk-closure clusters (many tickets resolved by the same person in the same minute). Long lead times are kept. Report how many tickets each rule removes. Thresholds are set from the observed distribution.
- **Missing history:** keep those tickets for the label with a flag. Which features may use history is settled in the prediction point ticket.
- **Git:** the script, the download checksum and expected-output notes, plus a small committed sample (a few hundred tickets from one project). Raw and extracted data are gitignored.
- **Unconfirmed, to check in the first extraction run:** `priority` and the changelog item names on Apache documents (the sample inspected was not from Apache). Findings: [research/04-public-jira-dataset-structure.md](../research/04-public-jira-dataset-structure.md)
