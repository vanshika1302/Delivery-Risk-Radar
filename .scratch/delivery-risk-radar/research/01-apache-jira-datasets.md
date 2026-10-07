# 01 - Public Apache Jira datasets and API viability

Researched 2026-10-05 (live checks 2026-10-06 UTC). Question: issues/01-find-public-apache-jira-datasets.md

## Summary

Three public datasets include Apache Jira issues. For a late-ticket predictor, **The Public Jira Dataset** (Montgomery et al., Zenodo, CC BY 4.0) is the best fit. It covers 657 Apache projects (about 1.01M issues) with the full changelog, priority, type, assignee (anonymised), created/resolved/due dates and estimate fields. TAWOS is a cleaner, SQL-based alternative, but it has only 3 Apache projects. The Ortu 2015 dataset is old and has no changelog. The live Apache Jira REST API is viable as a top-up (anonymous access works, 1,000 issues per page, rate limited), but it is slow and fragile for a bulk pull.

## Candidates

### 1. The Public Jira Dataset (Montgomery, Lueders, Maalej; Univ. Hamburg)
- Paper: MSR 2022, https://arxiv.org/abs/2201.08368 (live, HTTP 200).
- Access: Zenodo concept DOI https://doi.org/10.5281/zenodo.5882881, which redirects to the latest record https://zenodo.org/records/15719919 (verified through the Zenodo API: published 2025-06-23, open access). File: `2025-06-23 ThePublicJiraDataset.zip`, 5,813,135,238 bytes (about 5.8 GB). Contents: MongoDB dump, download scripts, interpretation scripts, qualitative analyses.
- The original January 2022 version (record 5901804) is access-restricted because it contained personal data. Use the latest version.
- Format: MongoDB dump. The paper says about 15 GB sits in MongoDB once restored.
- License: CC BY 4.0 (Zenodo metadata).
- Scope: 16 public Jira instances, 1,822 projects, 2.7M issues, 32M changes, 9M comments, 1M links. Apache is the largest instance: 1,014,926 issues across 657 projects and about 10.5M changes (paper). Initial download May 2021, updated January 2022. Therefore Apache issues end around January 2022, so there is a gap to today (see API section).
- Anonymisation: assignee, creator, reporter and comment/changelog authors are replaced with UUID4 masks (Zenodo description). Assignee identity is preserved as a stable pseudonym, which is enough for per-person features.
- Fields (paper schema section): created, updated, resolutiondate, duedate; status, priority, resolution, fixVersions; creator, reporter, assignee; full changelog. Issue type is a standard Jira field. Time-estimate fields are standard Jira fields but their population rate is not documented (see Live API check below).

### 2. TAWOS (Tawosi, Al-Subaihin, Moussa, Sarro; UCL)
- Paper: MSR 2022, https://arxiv.org/abs/2202.00979 (live). Repo: https://github.com/SOLAR-group/TAWOS (live, HTTP 200).
- Access: the repo has the schema script and ERD. Data is on UCL's figshare, https://doi.org/10.5522/04/21308124. The figshare API shows `TAWOS.sql.zip`, 637,550,449 bytes (about 640 MB), plus a README.
- Format: MySQL 8.0.22 dump (relational).
- License: Apache 2.0 (figshare metadata and repo `Licence.txt`), with terms of use limiting it to research use and asking users not to re-identify people.
- Scope: v1.1 has 458,232 issues from 39 projects in 12 Jira repositories. The paper's original version had 508,963 issues in 44 projects across 13 repositories, collected October 2020. **Only 3 Apache projects**: Mesos, MXNet, Usergrid. The rest are Atlassian, Appcelerator, Spring, MongoDB and others (README table).
- Fields (paper and README): created/resolved dates (UTC), type, status, priority, assignee, reporter, due dates, story points with estimate date, Change_Log table with previous/new values, sprints, versions, comments. Resolution time is derived.
- Pros: relational, small, includes sprints and story points (useful for estimate-vs-actual features), PII scrubbed. Cons: few Apache projects, data frozen at October 2020.

### 3. JIRA Social Repository (Ortu et al., PROMISE 2015)
- Repo: https://github.com/marcoortu/jira-social-repository (live, HTTP 200). Paper: PROMISE 2015.
- Access: split tar.gz parts in the GitHub repo, or a Dropbox link, which expand to SQL files. The repo license is Apache 2.0.
- Scope: Apache, Spring, JBoss, Codehaus. More than 1K projects, 700K+ issues, 2M+ comments. The Apache subset figure given in the README (3,516 tasks) looks inconsistent with that total, so treat it with caution.
- Focus: developer comments, sentiment and emotion. I did not find a changelog in the descriptions I read, and the data is from about 2015. Verdict: too old and thin for this project.

## Field comparison

| Field | Public Jira Dataset | TAWOS | Ortu 2015 |
|---|---|---|---|
| Apache projects | 657 | 3 | many (Apache subset, 2015) |
| Created / resolved dates | yes | yes | likely, not confirmed |
| Changelog | yes (about 10.5M Apache changes) | yes | not found |
| Priority | yes | yes | not confirmed |
| Issue type | yes | yes | not confirmed |
| Assignee | yes (pseudonymised) | yes | not confirmed |
| Due date | field exists, sparse | yes, sparse | not confirmed |
| Estimates | Jira estimate fields, sparse | story points plus estimate date | no |
| End of data | about Jan 2022 | Oct 2020 | about 2015 |
| Size | 5.8 GB zip, about 15 GB restored | about 640 MB zip | multi-part tar.gz |
| License | CC BY 4.0 | Apache 2.0 plus research terms | Apache 2.0 |

"Not confirmed" means I did not verify it from a primary source.

## Live Apache Jira REST API check

Base URL https://issues.apache.org/jira (ASF Jira, Jira Server 8.20.10 per `/rest/api/2/serverInfo`). Queries below were run anonymously.

- Anonymous access works. The search endpoint returns counts without a login.
- Volume today: 1,179,430 issues in total (`created>2000-01-01`) across 674 projects (`/rest/api/2/project`). Kafka alone has 19,931. This is about 165K more than the dataset's 2022 snapshot, so a newer slice is available.
- Fields confirmed on KAFKA-1 with `expand=changelog`: created, resolutiondate, duedate, priority, issuetype, assignee, status, timeoriginalestimate, timeestimate, timespent, fixVersions, components. The changelog came back with 15 history entries.
- Sparsity of planning fields across all of ASF Jira: `duedate is not EMPTY` = 8,771 issues; `timeoriginalestimate is not EMPTY` = 22,799. Resolved issues with a due date = 7,528. Against about 1.18M issues, due dates are present on under 1%. **A "late versus due date" label cannot be built from due dates on most issues**, so lateness will likely need a different definition, such as resolution time exceeding a per-project quantile or fixVersion release dates.
- Page size: a request for maxResults=1000 returned 1,000 issues; maxResults=5000 also returned only 1,000, so 1,000 is the server cap.
- Rate limiting: ASF Infra states Jira was among the first services rate-limited (January 2019). Limits are based on CPU time, and a breach returns HTTP 429 with a text explanation, generally unblocking within about two minutes. Limits apply across IP ranges, and bots should check for 429 and slow down (https://infra.apache.org/blog/rate-limiting-on-apache-services.html). A global ban policy also exists (https://infra.apache.org/infra-ban.html). No numeric request limit is published. Atlassian's generic Server/Data Center behaviour is a 429 plus a Retry-After header (https://confluence.atlassian.com/adminjiraserver/adjusting-your-code-for-rate-limiting-987143384.html).
- Viability: pulling about 1.2M issues with changelogs means at least 1,200 search pages, and the changelog expansion makes each call heavy. Feasible with throttling, retries and resumable per-project JQL slices, but expect hours to days. The Montgomery dataset's download scripts already implement this.
- Not checked: whether `expand=changelog` on search results truncates long histories. A single issue's changelog should be fetched separately if so.

## Recommendation

1. Use The Public Jira Dataset (Zenodo 15719919) as the base. It is the only candidate with broad Apache coverage plus the full changelog, it is CC BY 4.0, and it has about 1M Apache issues. Budget about 6 GB download and about 15 GB disk, and restore only what is needed (filter to the Apache collection, or a handful of large projects).
2. Do not download it yet. Decide first the size and project subset needed.
3. Use the live REST API only to refresh data after January 2022 for chosen projects, throttled, using the dataset's own scripts as the starting point.
4. Optionally use TAWOS (about 640 MB, SQL) for a quick prototype on Mesos, MXNet and Usergrid, or as a source of story-point features.
5. Plan the "late" label early: due dates are under 1% populated, so lateness probably has to be derived.

## Sources
- https://arxiv.org/abs/2201.08368 and https://ar5iv.labs.arxiv.org/html/2201.08368
- https://zenodo.org/records/15719919 (Zenodo API metadata), https://doi.org/10.5281/zenodo.5882881
- https://arxiv.org/abs/2202.00979, https://github.com/SOLAR-group/TAWOS, https://doi.org/10.5522/04/21308124 (figshare API)
- https://github.com/marcoortu/jira-social-repository
- https://infra.apache.org/blog/rate-limiting-on-apache-services.html
- https://issues.apache.org/jira/rest/api/2/ (live queries)
