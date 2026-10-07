-- Scope and data quality. One row per ticket in the chosen projects, with the reason it is excluded (if any).
-- Parameters ($NAME) come from config/params.toml; see etl/transform.py.

CREATE OR REPLACE TABLE tickets AS
WITH base AS (
    SELECT issue_key, project_key, issue_type, priority, status, resolution, created, resolution_date, assignee, reporter
    FROM issues
    WHERE project_key IN $PROJECTS
      AND coalesce(issue_type, '') NOT IN $EXCLUDED_TYPES
),
delivered AS (
    SELECT issue_key FROM base WHERE resolution IN $DELIVERED AND resolution_date IS NOT NULL
),
-- A person resolving many delivered tickets within one minute is a bulk cleanup, not delivery.
bulk AS (
    SELECT DISTINCT issue_key FROM (
        SELECT c.issue_key,
               count(*) OVER (PARTITION BY b.project_key, c.author, date_trunc('minute', c.created)) AS n
        FROM changelog c
        JOIN base b USING (issue_key)
        JOIN delivered d USING (issue_key)
        WHERE c.field = 'resolution' AND c.to_string IS NOT NULL
    ) WHERE n >= $BULK_MIN
),
flags AS (
    SELECT b.*,
           (b.resolution_date IS NOT NULL)                                          AS is_resolved,
           (d.issue_key IS NOT NULL)                                                AS is_delivered,
           date_diff('second', b.created, b.resolution_date) / 86400.0              AS lead_days,
           (b.created < TIMESTAMP '$MIN_CREATED')                                   AS bad_created,
           (b.resolution_date < b.created)                                          AS negative_lead,
           (d.issue_key IS NOT NULL
              AND date_diff('second', b.created, b.resolution_date) < $TOO_FAST_HOURS * 3600) AS too_fast,
           (bulk.issue_key IS NOT NULL)                                             AS bulk_closed
    FROM base b
    LEFT JOIN delivered d USING (issue_key)
    LEFT JOIN bulk USING (issue_key)
)
SELECT *,
       CASE WHEN bad_created THEN 'bad_created'
            WHEN negative_lead THEN 'negative_lead'
            WHEN bulk_closed THEN 'bulk_closed'
            WHEN too_fast THEN 'too_fast' END AS exclusion_reason
FROM flags;
