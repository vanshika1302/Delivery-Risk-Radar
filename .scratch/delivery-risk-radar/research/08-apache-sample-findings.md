# 08 - Apache sample findings

Sample pulled from the anonymous Apache Jira REST API (`/jira/rest/api/2/search`, `expand=changelog`, 12 requests total, no 429s). Raw JSON is kept outside the repo (session scratchpad) and not committed.

## Sample design

JQL: `project = X AND resolution is not EMPTY AND created in <year> ORDER BY created ASC`, `maxResults=400`, four created-year windows per project. Total 4,743 tickets.

| Project | Windows (created year) | Tickets |
|---|---|---|
| KAFKA | 2012, 2015, 2018, 2021 | 1,600 |
| HDFS | 2010, 2013, 2016, 2019 | 1,600 |
| CASSANDRA | 2010, 2013, 2016, 2019 | 1,543 (2019 window had only 343) |

Bias to know about: each window is the first 400 resolved tickets created in that year (ASC), so it covers roughly the early part of each year, not a random sample. Only resolved tickets are included (by design), so unresolved tickets are not represented. Fields requested: created, resolutiondate, status, resolution, priority, issuetype, assignee, reporter, project, components, fixVersions, duedate.

Note: Python's urllib failed TLS verification on this machine (no local CA bundle); `curl` was used for fetching instead.

## Status names and transitions (from changelog `status` items)

`fromString` and `toString` were populated on every status item (0 nulls in 11,041 items). Current `status` of sampled tickets is only Resolved or Closed (Cassandra: 1 ticket still `Open` with a resolution set).

**KAFKA** statuses: Open, In Progress, Patch Available, Resolved, Closed, Reopened. Top transitions:
Open->Resolved 1013, Patch Available->Resolved 499, Open->Patch Available 453, Resolved->Closed 202, Open->In Progress 165, In Progress->Patch Available 107, In Progress->Resolved 104, Resolved->Reopened 50, Patch Available->In Progress 49, Reopened->Resolved 34.

**HDFS** statuses: Open, In Progress, Patch Available, Resolved, Closed, Reopened. Top transitions:
Open->Patch Available 1457, Patch Available->Resolved 1116, Open->Resolved 521, Resolved->Closed 444, Patch Available->Open 433, Resolved->Reopened 80, In Progress->Patch Available 75, Open->In Progress 61, Reopened->Patch Available 45, Reopened->Resolved 34.

**CASSANDRA** statuses (richest workflow): Open, Triage Needed, Triage, In Progress, Patch Available, Review In Progress, Changes Suggested, Change Requested, Ready to Commit, Awaiting Feedback, Testing, Needs Committer, Needs Reviewer, Resolved, Reopened, Closed. Top transitions:
Open->Patch Available 821, Open->Resolved 644, Patch Available->Resolved 578, Ready to Commit->Resolved 273, Patch Available->Review In Progress 209, Triage Needed->Open 193, Review In Progress->Ready to Commit 178, In Progress->Patch Available 167, Open->In Progress 152, Patch Available->Open 118, Resolved->Reopened 102.

Status vocabularies differ per project, so a status-category mapping must be per project (or mapped via the Jira status category, which was not fetched).

## Priority and changelog field names

- `priority` is populated on 100% of tickets, but the vocabulary differs: KAFKA and HDFS use Blocker/Critical/Major/Minor/Trivial; CASSANDRA (newer scheme) uses Urgent/High/Normal/Low (Normal 889, Low 581, Urgent 68, High 5).
- Changelog item `field` is always populated (`field`, `fieldtype`, `fromString`, `toString` present). Common items: status, resolution, assignee, priority, Fix Version, Component, Attachment, Link, RemoteIssueLink, description, summary, labels, issuetype. Project-specific custom fields appear by display name (Cassandra: Workflow, Severity, Authors, Reviewers, Complexity, Bug Category...; HDFS: Hadoop Flags, Target Version/s, Release Note). Both `Labels`/`labels` and `Parent`/`Parent Issue` variants appear, so field-name matching should be case-insensitive and list-based.
- `priority` changelog items exist for 171 (KAFKA), 142 (HDFS), 1,411 (CASSANDRA) events, so priority changes over time are rare outside Cassandra.
- Other fields: assignee null in 28% (KAFKA 450/1600, HDFS 228/1600 = 14%, CASSANDRA 430/1543 = 28%); components empty 43% / 30% / 55%; fixVersions empty 42% / 28% / 34%; duedate set on only 4-8 tickets per project (unusable).

## Issue types

- KAFKA: Bug 829, Improvement 410, Sub-task 213, Task 68, New Feature 51, Test 28, Wish 1.
- HDFS: Bug 763, Improvement 372, Sub-task 357, New Feature 49, Test 33, Task 21, Wish 5.
- CASSANDRA: Bug 920, Improvement 451, New Feature 82, Task 57, Sub-task 33.

## Resolution values

Fixed dominates: KAFKA 1134 (71%), HDFS 1223 (76%), CASSANDRA 1024 (66%). Non-delivery resolutions are substantial: Duplicate (166 / 177 / 155), Won't Fix (96 / 65 / 95), Not A Problem (45 / 47 / 98), Invalid (31 / 46 / 62), Cannot Reproduce (27 / 12 / 59), Not A Bug, Later, Incomplete, Abandoned, Auto Closed (KAFKA 35), Information Provided, Won't Do, Workaround, Pending Closed, Delivered, Feedback Received, plus "completed" synonyms Implemented and Done. Lead-time features need a resolution filter (Fixed/Implemented/Done/Delivered vs the rest).

## Share with no in-progress-like status

Share of tickets whose changelog never enters a given status:

| Project | Never "In Progress" | Never In Progress / Patch Available / any review status |
|---|---|---|
| KAFKA | 87.2% | 62.4% |
| HDFS | 95.7% | 30.6% |
| CASSANDRA | 89.7% | 42.3% |

`In Progress` is rarely used; the Apache workflow mostly goes Open -> Patch Available -> Resolved. "Patch Available" (and Cassandra's review states) is the real work-in-flight signal. For KAFKA, 62% of tickets have neither, so a work-start timestamp is often unavailable (many go straight Open->Resolved, 1013 times).

## Resolved with no status change

0% in all three projects: every sampled ticket has at least one `status` item in its changelog (the resolve transition itself). This is expected because tickets were filtered to resolved ones and Jira records the transition. The meaningful variant is "only one status change (Open->Resolved, no intermediate state)", which is the dominant path for many tickets (Open->Resolved is the top or second transition in all projects; counts above are transitions, not distinct tickets). The one Cassandra ticket with status Open and a resolution set shows data inconsistencies can exist.

## Changelog truncation

0 tickets truncated in all three projects: `len(histories) == changelog.total` for every ticket at `maxResults=400`. No evidence of truncation in this sample; still worth asserting in the loader since very long histories on other projects may differ (not observed).

## Lead time (created -> resolutiondate, all resolutions, days)

| Project | n | Median | P75 | P90 | Resolved < 1 day |
|---|---|---|---|---|---|
| KAFKA | 1,600 | 37.6 | 279.4 | 1069.1 | 189 (12%) |
| HDFS | 1,600 | 13.2 | 106.9 | 498.0 | 289 (18%) |
| CASSANDRA | 1,543 | 12.6 | 97.8 | 412.1 | 352 (23%) |

No negative lead times. Distributions are heavily right-skewed (P90 is 30-40x the median), so use percentiles or log scale, not means. Includes Duplicate/Won't Fix etc.; Fixed-only numbers were not separately computed.

## Implications

- Per-project status mapping is required; do not assume "In Progress" exists.
- Prefer "first Patch Available / review state" as a work-start proxy, with fallback to created.
- Normalise priority per project (two different schemes).
- Filter on resolution before computing delivery lead time.
- Sample is biased toward early-in-year tickets and resolved only.
