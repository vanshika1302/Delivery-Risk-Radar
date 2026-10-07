-- Status history turned into stages. Stage mapping: config/stage_mapping.csv (Waiting, Building, In review, Done).
-- A ticket's first status is not in the changelog; it is the "from" of its first change (or its current status if it never changed).

CREATE OR REPLACE TABLE stage_map AS
SELECT lower(trim(status)) AS status_key, stage FROM read_csv('$STAGE_CSV', header = true);

CREATE OR REPLACE TABLE status_intervals AS
WITH events AS (
    SELECT c.issue_key, c.created AS event_at, c.from_string AS from_status, c.to_string AS to_status,
           row_number() OVER (PARTITION BY c.issue_key ORDER BY c.created, try_cast(c.history_id AS BIGINT)) AS seq
    FROM changelog c
    JOIN tickets t USING (issue_key)
    WHERE c.field = 'status' AND t.exclusion_reason IS NULL
),
starts AS (
    SELECT t.issue_key, coalesce(e.from_status, t.status) AS status, t.created AS start_at, 0 AS seq
    FROM tickets t
    LEFT JOIN events e ON e.issue_key = t.issue_key AND e.seq = 1
    WHERE t.exclusion_reason IS NULL
    UNION ALL
    SELECT issue_key, to_status, event_at, seq FROM events
),
segments AS (
    SELECT issue_key, status, start_at,
           lead(start_at) OVER (PARTITION BY issue_key ORDER BY start_at, seq) AS next_start,
           row_number() OVER (PARTITION BY issue_key ORDER BY start_at, seq)   AS ord
    FROM starts
),
capped AS (
    -- Time is measured up to the final resolution, or the snapshot for tickets still open.
    SELECT s.issue_key, s.status, s.start_at, s.ord,
           least(coalesce(s.next_start, TIMESTAMP '$SNAPSHOT'), coalesce(t.resolution_date, TIMESTAMP '$SNAPSHOT')) AS end_at
    FROM segments s JOIN tickets t USING (issue_key)
)
SELECT c.issue_key, c.ord, c.status, coalesce(m.stage, 'Unmapped') AS stage, c.start_at, c.end_at,
       date_diff('second', c.start_at, c.end_at) / 86400.0 AS days,
       lag(coalesce(m.stage, 'Unmapped')) OVER (PARTITION BY c.issue_key ORDER BY c.ord) AS prev_stage
FROM capped c
LEFT JOIN stage_map m ON lower(trim(c.status)) = m.status_key
WHERE c.end_at > c.start_at;

CREATE OR REPLACE TABLE ticket_stages AS
SELECT t.issue_key,
       coalesce(sum(i.days) FILTER (WHERE i.stage = 'Waiting'), 0)   AS waiting_days,
       coalesce(sum(i.days) FILTER (WHERE i.stage = 'Building'), 0)  AS building_days,
       coalesce(sum(i.days) FILTER (WHERE i.stage = 'In review'), 0) AS in_review_days,
       coalesce(sum(i.days) FILTER (WHERE i.stage = 'Done'), 0)      AS resolved_gap_days,
       min(i.start_at) FILTER (WHERE i.stage IN ('Building', 'In review')) AS first_active_at,
       min(i.start_at) FILTER (WHERE i.stage = 'In review')                AS first_review_at,
       count(*) FILTER (WHERE i.stage = 'Waiting' AND i.prev_stage = 'In review') AS review_rounds,
       count(*) FILTER (WHERE lower(i.status) = 'reopened')                       AS reopen_count
FROM tickets t
LEFT JOIN status_intervals i USING (issue_key)
WHERE t.exclusion_reason IS NULL
GROUP BY t.issue_key;

-- Cycle time and wait to first review, for resolved tickets. Empty when the ticket never entered the stage.
CREATE OR REPLACE VIEW ticket_flow AS
SELECT t.issue_key, t.project_key, t.issue_type, t.is_delivered, t.lead_days, s.*  EXCLUDE (issue_key),
       CASE WHEN t.is_resolved AND s.first_active_at < t.resolution_date
            THEN date_diff('second', s.first_active_at, t.resolution_date) / 86400.0 END AS cycle_days,
       CASE WHEN t.is_resolved AND s.first_review_at < t.resolution_date
            THEN date_diff('second', t.created, s.first_review_at) / 86400.0 END         AS wait_to_first_review_days
FROM tickets t JOIN ticket_stages s USING (issue_key);
