# 08 - Sample real Apache data

Type: task
Status: resolved
Blocked by:

## Question

Nobody has seen real Apache ticket data yet, and the SQL analysis and features depend on it. Pull a small sample (about 3 projects, a few thousand tickets, with changelog) from the live Apache Jira REST API and report: which status names and transitions appear per project, whether `priority` and the changelog item names are populated, which issue types and resolution values exist, how often there is no in-progress status, and how often a ticket was resolved with no status change. Keep requests few and polite to avoid HTTP 429. Do not commit the raw sample. Report findings in `research/08-apache-sample-findings.md`.

## Answer

Pulled 4,743 resolved tickets with changelog (KAFKA 1,600, HDFS 1,600, CASSANDRA 1,543; four created-year windows each; 12 requests, no 429s). Status vocabularies differ per project (Cassandra has ~16 statuses); `priority` is always populated but uses two schemes; changelog `field`/`fromString`/`toString` are always populated; no changelog truncation seen. "In Progress" is rarely used (never entered in 87-96% of tickets), the real flow is Open -> Patch Available -> Resolved; no resolved ticket lacked a status change; lead-time medians are 13-38 days with P90 of 412-1069 days. Details: [research/08-apache-sample-findings.md](../research/08-apache-sample-findings.md).
