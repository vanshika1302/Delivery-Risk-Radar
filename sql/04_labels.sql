-- The "late" label. Late = a delivered ticket whose lead time exceeds the percentile of its peer group.
-- Thresholds use only tickets created AND resolved before the training cutoff, so no label sees the future.
-- Peer group: project and issue type; with fewer than $MIN_GROUP delivered tickets, fall back to the project, then the issue type.

CREATE OR REPLACE TABLE peer_thresholds AS
WITH pool AS (
    SELECT project_key, issue_type, lead_days FROM tickets
    WHERE is_delivered AND exclusion_reason IS NULL
      AND created < TIMESTAMP '$TRAIN_CUTOFF' AND resolution_date < TIMESTAMP '$TRAIN_CUTOFF'
)
SELECT 'project_type' AS level, project_key, issue_type, count(*) AS n, quantile_cont(lead_days, $PERCENTILE) AS threshold_days FROM pool GROUP BY project_key, issue_type
UNION ALL
SELECT 'project', project_key, NULL, count(*), quantile_cont(lead_days, $PERCENTILE) FROM pool GROUP BY project_key
UNION ALL
SELECT 'type', NULL, issue_type, count(*), quantile_cont(lead_days, $PERCENTILE) FROM pool GROUP BY issue_type;

CREATE OR REPLACE TABLE labels AS
WITH picked AS (
    SELECT t.*,
           date_diff('second', t.created, coalesce(t.resolution_date, TIMESTAMP '$SNAPSHOT')) / 86400.0 AS age_days,
           CASE WHEN pt.n >= $MIN_GROUP THEN 'project_type' WHEN p.n >= $MIN_GROUP THEN 'project' WHEN ty.n >= $MIN_GROUP THEN 'type' END AS threshold_level,
           CASE WHEN pt.n >= $MIN_GROUP THEN pt.threshold_days WHEN p.n >= $MIN_GROUP THEN p.threshold_days WHEN ty.n >= $MIN_GROUP THEN ty.threshold_days END AS threshold_days
    FROM tickets t
    LEFT JOIN peer_thresholds pt ON pt.level = 'project_type' AND pt.project_key = t.project_key AND pt.issue_type = t.issue_type
    LEFT JOIN peer_thresholds p  ON p.level  = 'project'      AND p.project_key  = t.project_key
    LEFT JOIN peer_thresholds ty ON ty.level = 'type'         AND ty.issue_type  = t.issue_type
),
labelled AS (
    SELECT *,
           CASE WHEN exclusion_reason IS NOT NULL THEN 'excluded:' || exclusion_reason
                WHEN is_resolved AND NOT is_delivered THEN 'not_delivered'
                WHEN threshold_days IS NULL THEN 'no_threshold'
                WHEN is_delivered THEN 'labelled'
                WHEN age_days > threshold_days THEN 'open_known_late'
                ELSE 'open_unlabelled' END AS label_status
    FROM picked
)
SELECT issue_key, project_key, issue_type, created, resolution_date, is_resolved, is_delivered, lead_days, age_days,
       threshold_level, threshold_days, label_status,
       CASE label_status WHEN 'labelled' THEN lead_days > threshold_days WHEN 'open_known_late' THEN TRUE END AS is_late,
       -- Variant for comparison: delivered tickets only. Open tickets already past their threshold (mostly stale backlog) are left out.
       CASE label_status WHEN 'labelled' THEN lead_days > threshold_days END AS is_late_delivered_only,
       CASE WHEN created < TIMESTAMP '$TRAIN_CUTOFF' THEN 'train'
            WHEN created < TIMESTAMP '$TEST_START' THEN 'gap'
            WHEN created < TIMESTAMP '$TEST_END' THEN 'test'
            ELSE 'after' END AS split,
       -- In training, a ticket is usable only if its label was already known at the cutoff:
       -- resolved before it, or already older than its threshold.
       (created < TIMESTAMP '$TRAIN_CUTOFF' AND label_status IN ('labelled', 'open_known_late')
         AND (resolution_date < TIMESTAMP '$TRAIN_CUTOFF'
              OR date_diff('second', created, TIMESTAMP '$TRAIN_CUTOFF') / 86400.0 > threshold_days)) AS train_eligible
FROM labelled;
