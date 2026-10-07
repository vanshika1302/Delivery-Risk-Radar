-- Descriptive analysis for the dashboard and the write-up. Delivered tickets only (Fixed, Done and equivalents),
-- after the scope and quality exclusions. "Late" here is labels.is_late_delivered_only, so open tickets do not distort rates.

CREATE OR REPLACE TABLE analysis_base AS
SELECT l.issue_key, l.project_key, l.issue_type, l.created, l.resolution_date, l.lead_days, l.is_late_delivered_only AS is_late,
       l.split, year(l.created) AS created_year,
       t.priority, (t.assignee IS NOT NULL) AS has_assignee,
       f.waiting_days, f.building_days, f.in_review_days, f.resolved_gap_days,
       f.cycle_days, f.wait_to_first_review_days, f.review_rounds, f.reopen_count,
       (f.first_review_at IS NOT NULL AND f.first_review_at < l.resolution_date) AS entered_review,
       (f.first_active_at IS NOT NULL AND f.first_active_at < l.resolution_date) AS entered_active,
       coalesce(len(i.components), 0) AS component_count, coalesce(i.link_count, 0) AS link_count, i.comment_count
FROM labels l
JOIN tickets t USING (issue_key)
JOIN ticket_flow f USING (issue_key)
JOIN issues i USING (issue_key)
WHERE l.label_status = 'labelled';

-- Lead time and late rate by project and issue type.
CREATE OR REPLACE TABLE analysis_lead_time AS
SELECT project_key, issue_type, count(*) AS tickets,
       round(median(lead_days), 1) AS median_days, round(quantile_cont(lead_days, 0.75), 1) AS p75_days,
       round(quantile_cont(lead_days, 0.90), 1) AS p90_days, round(100 * avg(is_late::int), 1) AS late_pct
FROM analysis_base GROUP BY ALL;

-- Where the time goes: share of total lead time in each stage, per project (sum over tickets, so long tickets weigh more).
CREATE OR REPLACE TABLE analysis_stage_share AS
SELECT project_key, count(*) AS tickets,
       round(100 * sum(waiting_days) / sum(lead_days), 1)   AS waiting_pct,
       round(100 * sum(building_days) / sum(lead_days), 1)  AS building_pct,
       round(100 * sum(in_review_days) / sum(lead_days), 1) AS in_review_pct,
       round(100 * sum(resolved_gap_days) / sum(lead_days), 1) AS resolved_gap_pct
FROM analysis_base GROUP BY project_key;

-- Review flow: how many tickets reach review, how long they wait for it, how much rework, and cycle time.
CREATE OR REPLACE TABLE analysis_review_flow AS
SELECT project_key, count(*) AS tickets,
       round(100 * avg(entered_active::int), 1) AS entered_active_pct,
       round(100 * avg(entered_review::int), 1) AS entered_review_pct,
       round(median(wait_to_first_review_days), 2) AS median_wait_to_review_days,
       round(quantile_cont(wait_to_first_review_days, 0.75), 2) AS p75_wait_to_review_days,
       round(median(cycle_days), 2) AS median_cycle_days,
       round(100 * avg((review_rounds > 0)::int), 1) AS any_rework_pct,
       round(avg(review_rounds) FILTER (WHERE entered_review), 2) AS mean_rounds_when_reviewed,
       round(100 * avg((reopen_count > 0)::int), 1) AS reopened_pct
FROM analysis_base GROUP BY project_key;

-- Late rate against a few things known early (and one known only late, review rounds, for contrast).
CREATE OR REPLACE TABLE analysis_late_by_factor AS
SELECT 'issue_type' AS factor, issue_type AS level, count(*) AS tickets, round(100 * avg(is_late::int), 1) AS late_pct FROM analysis_base GROUP BY issue_type HAVING count(*) >= 200
UNION ALL SELECT 'has_assignee_at_snapshot', CASE WHEN has_assignee THEN 'yes' ELSE 'no' END, count(*), round(100 * avg(is_late::int), 1) FROM analysis_base GROUP BY has_assignee
UNION ALL SELECT 'component_count_at_snapshot', CASE WHEN component_count >= 2 THEN '2+' ELSE component_count::varchar END, count(*), round(100 * avg(is_late::int), 1) FROM analysis_base GROUP BY 2
UNION ALL SELECT 'link_count_at_snapshot', CASE WHEN link_count >= 2 THEN '2+' ELSE link_count::varchar END, count(*), round(100 * avg(is_late::int), 1) FROM analysis_base GROUP BY 2
UNION ALL SELECT 'entered_review', CASE WHEN entered_review THEN 'yes' ELSE 'no' END, count(*), round(100 * avg(is_late::int), 1) FROM analysis_base GROUP BY entered_review
UNION ALL SELECT 'review_rounds (known late)', CASE WHEN review_rounds >= 2 THEN '2+' ELSE review_rounds::varchar END, count(*), round(100 * avg(is_late::int), 1) FROM analysis_base GROUP BY 2;

-- Trend: late rate and median lead time by creation year and project.
CREATE OR REPLACE TABLE analysis_trend AS
SELECT project_key, created_year, count(*) AS tickets, round(median(lead_days), 1) AS median_days, round(100 * avg(is_late::int), 1) AS late_pct
FROM analysis_base GROUP BY ALL;
