# 01 - Find public Apache Jira datasets

Type: research
Status: resolved
Blocked by:

## Question

Which public datasets of Apache Jira issues exist, and which fit this project? For each candidate, report: access method (URL, format, size), license, which Apache projects and date range, and whether it includes the fields we need: created and resolved dates, status-change history (changelog), priority, issue type, assignee, and any due-date or estimate fields. Also report whether pulling directly from the Apache Jira REST API is a viable alternative (rate limits, volume). End with a recommendation.

## Answer

Three public datasets include Apache Jira issues. The best fit is The Public Jira Dataset (Montgomery et al., Zenodo 10.5281/zenodo.5882881, CC BY 4.0, 5.8 GB MongoDB dump), which covers 657 Apache projects and about 1.01M issues up to about January 2022, with changelog, priority, type, assignee (pseudonymised) and created/resolved/due dates. TAWOS (about 640 MB MySQL dump, Apache 2.0) has only 3 Apache projects, and the 2015 Ortu dataset is old with no changelog found. The live Apache Jira REST API works anonymously (1.18M issues, 1,000 per page, CPU-based 429 rate limiting) and is viable for refreshing post-2022 data, but is slow for a bulk pull. Due dates are populated on under 1% of issues, so the "late" label will probably need a derived definition. Recommendation: use the Public Jira Dataset as the base and top up from the API.

Full findings: [research/01-apache-jira-datasets.md](../research/01-apache-jira-datasets.md)
