-- Features as of each prediction point. Two points per ticket: at creation, and at day 7 for tickets still open then.
-- Every value is rebuilt from the changelog as it stood at the prediction point T. A current (final) value is used only
-- when the changelog shows no change after T. Allowlist: nothing here may look at resolution, resolution date, final status,
-- `updated`, fix versions, or anything that happened after T.

CREATE OR REPLACE TABLE priority_rank AS
SELECT lower(trim(priority)) AS priority_key, rank FROM read_csv('$PRIORITY_CSV', header = true);

-- Every ticket of the chosen projects (any type): the base for workload counts.
CREATE OR REPLACE TEMP TABLE scope_issues AS
SELECT issue_key, project_key, assignee, created, resolution_date
FROM issues
WHERE project_key IN $PROJECTS AND created >= TIMESTAMP '$MIN_CREATED'
  AND (resolution_date IS NULL OR resolution_date >= created);

CREATE OR REPLACE TEMP TABLE points AS
SELECT t.issue_key, t.project_key, t.issue_type, t.priority AS priority_now, 'creation' AS point, t.created AS t_at
FROM tickets t JOIN labels l USING (issue_key)
WHERE t.exclusion_reason IS NULL AND l.label_status IN ('labelled', 'open_known_late', 'open_unlabelled')
UNION ALL
SELECT t.issue_key, t.project_key, t.issue_type, t.priority, 'day7', t.created + INTERVAL $POINT_DAYS DAY
FROM tickets t JOIN labels l USING (issue_key)
WHERE t.exclusion_reason IS NULL AND l.label_status IN ('labelled', 'open_known_late', 'open_unlabelled')
  AND (t.resolution_date IS NULL OR t.resolution_date > t.created + INTERVAL $POINT_DAYS DAY);

-- Changelog rows for the fields we rewind (old text is reduced to its length).
CREATE OR REPLACE TEMP TABLE cl AS
SELECT c.issue_key, c.history_id, c.created, lower(c.field) AS field, c.from_string, c.to_string, length(c.from_string) AS from_len
FROM changelog c
WHERE c.issue_key IN (SELECT issue_key FROM points)
  AND lower(c.field) IN ('component', 'link', 'description', 'summary', 'priority', 'issuetype', 'issue type');

-- The first change after T carries the value the field had at T (its "from").
CREATE OR REPLACE TEMP TABLE first_after AS
SELECT p.issue_key, p.point,
       CASE WHEN c.field IN ('issuetype', 'issue type') THEN 'type' ELSE c.field END AS field,
       c.from_string, c.from_len
FROM points p JOIN cl c ON c.issue_key = p.issue_key AND c.created > p.t_at
WHERE c.field IN ('priority', 'issuetype', 'issue type', 'summary', 'description')
QUALIFY row_number() OVER (PARTITION BY p.issue_key, p.point,
        CASE WHEN c.field IN ('issuetype', 'issue type') THEN 'type' ELSE c.field END
        ORDER BY c.created, try_cast(c.history_id AS BIGINT)) = 1;

-- Components and links are counted back from today's count by undoing each add (+1) and remove (-1) after T.
CREATE OR REPLACE TEMP TABLE net_after AS
SELECT p.issue_key, p.point,
       sum(CASE WHEN c.field = 'component' THEN (c.to_string IS NOT NULL)::int - (c.from_string IS NOT NULL)::int ELSE 0 END) AS component_net,
       sum(CASE WHEN c.field = 'link'      THEN (c.to_string IS NOT NULL)::int - (c.from_string IS NOT NULL)::int ELSE 0 END) AS link_net
FROM points p JOIN cl c ON c.issue_key = p.issue_key AND c.created > p.t_at
WHERE c.field IN ('component', 'link')
GROUP BY p.issue_key, p.point;

-- Who held each ticket, and when (assignee history as spans).
CREATE OR REPLACE TEMP TABLE assignee_spans AS
WITH ev AS (
    SELECT c.issue_key, greatest(c.created, s.created) AS event_at, c.from_value, c.to_value,
           row_number() OVER (PARTITION BY c.issue_key ORDER BY c.created, try_cast(c.history_id AS BIGINT)) AS seq
    FROM changelog c JOIN scope_issues s USING (issue_key)
    WHERE lower(c.field) = 'assignee'
),
starts AS (
    SELECT s.issue_key, s.created AS start_at, 0 AS seq,
           CASE WHEN e.issue_key IS NULL THEN s.assignee ELSE e.from_value END AS assignee
    FROM scope_issues s LEFT JOIN ev e ON e.issue_key = s.issue_key AND e.seq = 1
    UNION ALL
    SELECT issue_key, event_at, seq, to_value FROM ev
)
SELECT issue_key, assignee, start_at,
       coalesce(lead(start_at) OVER (PARTITION BY issue_key ORDER BY start_at, seq), TIMESTAMP '2100-01-01') AS end_at
FROM starts;

-- Open tickets per assignee, and per project, over time (a running count; look up the latest value at or before T).
CREATE OR REPLACE TEMP TABLE assignee_load AS
SELECT assignee, ts, sum(d) OVER (PARTITION BY assignee ORDER BY ts RANGE BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS open_n
FROM (
    SELECT a.assignee, greatest(a.start_at, s.created) AS ts, 1 AS d
    FROM assignee_spans a JOIN scope_issues s USING (issue_key)
    WHERE a.assignee IS NOT NULL AND least(a.end_at, coalesce(s.resolution_date, TIMESTAMP '2100-01-01')) > greatest(a.start_at, s.created)
    UNION ALL
    SELECT a.assignee, least(a.end_at, coalesce(s.resolution_date, TIMESTAMP '2100-01-01')), -1
    FROM assignee_spans a JOIN scope_issues s USING (issue_key)
    WHERE a.assignee IS NOT NULL AND least(a.end_at, coalesce(s.resolution_date, TIMESTAMP '2100-01-01')) > greatest(a.start_at, s.created)
      AND least(a.end_at, coalesce(s.resolution_date, TIMESTAMP '2100-01-01')) < TIMESTAMP '2100-01-01'
);

CREATE OR REPLACE TEMP TABLE project_load AS
SELECT project_key, ts, sum(d) OVER (PARTITION BY project_key ORDER BY ts RANGE BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS open_n
FROM (SELECT project_key, created AS ts, 1 AS d FROM scope_issues
      UNION ALL SELECT project_key, resolution_date, -1 FROM scope_issues WHERE resolution_date IS NOT NULL);

-- How many tickets the reporter had filed before this one (any Apache project).
CREATE OR REPLACE TEMP TABLE reporter_prior AS
SELECT issue_key,
       count(*) OVER (PARTITION BY reporter ORDER BY created, issue_key ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING) AS prior_n
FROM issues WHERE reporter IS NOT NULL;

-- Recent history of the peer group (and of the project): over the last N delivered tickets resolved before T.
CREATE OR REPLACE TEMP TABLE peer_hist AS
SELECT project_key, issue_type, resolution_date,
       count(*) OVER w AS n, quantile_cont(lead_days, 0.5) OVER w AS median_lead_days, avg(is_late_delivered_only::int) OVER w AS late_rate
FROM labels WHERE label_status = 'labelled'
WINDOW w AS (PARTITION BY project_key, issue_type ORDER BY resolution_date, issue_key ROWS BETWEEN $PEER_PRECEDING PRECEDING AND CURRENT ROW);

CREATE OR REPLACE TEMP TABLE project_hist AS
SELECT project_key, resolution_date,
       count(*) OVER w AS n, quantile_cont(lead_days, 0.5) OVER w AS median_lead_days, avg(is_late_delivered_only::int) OVER w AS late_rate
FROM labels WHERE label_status = 'labelled'
WINDOW w AS (PARTITION BY project_key ORDER BY resolution_date, issue_key ROWS BETWEEN $PEER_PRECEDING PRECEDING AND CURRENT ROW);

-- Day 7 only: activity up to T.
CREATE OR REPLACE TEMP TABLE day7_activity AS
WITH hist AS (
    SELECT p.issue_key, count(DISTINCT c.history_id) AS events_n, max(c.created) AS last_event
    FROM points p JOIN changelog c ON c.issue_key = p.issue_key AND c.created <= p.t_at
    WHERE p.point = 'day7' GROUP BY p.issue_key
),
com AS (
    SELECT p.issue_key, count(*) AS comments_n, count(DISTINCT c.author) AS commenters_n, max(c.created) AS last_comment
    FROM points p JOIN comments c ON c.issue_key = p.issue_key AND c.created <= p.t_at
    WHERE p.point = 'day7' GROUP BY p.issue_key
)
SELECT p.issue_key, coalesce(h.events_n, 0) AS events_by_t, coalesce(c.comments_n, 0) AS comments_by_t, coalesce(c.commenters_n, 0) AS commenters_by_t,
       date_diff('second', greatest(t.created, coalesce(h.last_event, t.created), coalesce(c.last_comment, t.created)), p.t_at) / 86400.0 AS days_since_activity
FROM points p JOIN tickets t USING (issue_key)
LEFT JOIN hist h USING (issue_key) LEFT JOIN com c USING (issue_key)
WHERE p.point = 'day7';

CREATE OR REPLACE TEMP TABLE day7_stage AS
SELECT p.issue_key,
       any_value(i.stage) FILTER (WHERE i.start_at <= p.t_at AND i.end_at > p.t_at) AS stage_at_t,
       date_diff('second', any_value(i.start_at) FILTER (WHERE i.start_at <= p.t_at AND i.end_at > p.t_at), p.t_at) / 86400.0 AS days_in_stage,
       bool_or(i.stage IN ('Building', 'In review') AND i.start_at <= p.t_at) AS entered_active_by_t,
       bool_or(i.stage = 'In review' AND i.start_at <= p.t_at) AS entered_review_by_t,
       count(*) FILTER (WHERE i.stage = 'Waiting' AND i.prev_stage = 'In review' AND i.start_at <= p.t_at) AS review_rounds_by_t
FROM points p JOIN status_intervals i ON i.issue_key = p.issue_key
WHERE p.point = 'day7'
GROUP BY p.issue_key, p.t_at;

CREATE OR REPLACE TABLE features AS
WITH base AS (
    SELECT p.issue_key, p.point, p.t_at, p.project_key,
           CASE WHEN p.project_key IN $JIRA_REVIEW_PROJECTS THEN 'jira_review' ELSE 'github_review' END AS workflow_family,
           coalesce(ft.from_string, p.issue_type) AS issue_type_t,
           coalesce(fp.from_string, p.priority_now) AS priority_t,
           greatest(coalesce(len(i.components), 0) - coalesce(n.component_net, 0), 0) AS component_count,
           greatest(coalesce(i.link_count, 0) - coalesce(n.link_net, 0), 0) AS link_count,
           CASE WHEN fs.issue_key IS NOT NULL THEN coalesce(fs.from_len, 0) ELSE coalesce(x.summary_length, 0) END AS title_length,
           CASE WHEN fd.issue_key IS NOT NULL THEN coalesce(fd.from_len, 0) ELSE coalesce(x.description_length, 0) END AS description_length
    FROM points p
    JOIN issues i USING (issue_key)
    LEFT JOIN issue_text_stats x USING (issue_key)
    LEFT JOIN net_after n ON n.issue_key = p.issue_key AND n.point = p.point
    LEFT JOIN first_after ft ON ft.issue_key = p.issue_key AND ft.point = p.point AND ft.field = 'type'
    LEFT JOIN first_after fp ON fp.issue_key = p.issue_key AND fp.point = p.point AND fp.field = 'priority'
    LEFT JOIN first_after fs ON fs.issue_key = p.issue_key AND fs.point = p.point AND fs.field = 'summary'
    LEFT JOIN first_after fd ON fd.issue_key = p.issue_key AND fd.point = p.point AND fd.field = 'description'
)
SELECT b.issue_key, b.point, b.t_at, b.project_key, b.workflow_family, b.issue_type_t AS issue_type,
       pr.rank AS priority_rank, b.component_count, b.link_count, b.title_length, b.description_length,
       greatest(pl.open_n - 1, 0) AS project_open,
       CASE WHEN sp.assignee IS NOT NULL THEN greatest(al.open_n - 1, 0) END AS assignee_open,
       (sp.assignee IS NOT NULL) AS has_assignee,
       rp.prior_n AS reporter_prior_tickets, (coalesce(rp.prior_n, 0) = 0) AS reporter_first_time,
       ph.n AS peer_n, ph.median_lead_days AS peer_median_lead_days, ph.late_rate AS peer_late_rate,
       jh.median_lead_days AS project_median_lead_days, jh.late_rate AS project_late_rate,
       d.events_by_t AS events_by_day7, d.comments_by_t AS comments_by_day7, d.commenters_by_t AS commenters_by_day7,
       d.days_since_activity AS days_since_activity_day7,
       s.stage_at_t AS stage_at_day7, s.days_in_stage AS days_in_stage_day7,
       s.entered_active_by_t AS entered_active_by_day7, s.entered_review_by_t AS entered_review_by_day7,
       s.review_rounds_by_t AS review_rounds_by_day7
FROM base b
LEFT JOIN priority_rank pr ON pr.priority_key = lower(trim(b.priority_t))
ASOF LEFT JOIN assignee_spans sp ON sp.issue_key = b.issue_key AND b.t_at >= sp.start_at
ASOF LEFT JOIN assignee_load al ON al.assignee = sp.assignee AND b.t_at >= al.ts
ASOF LEFT JOIN project_load pl ON pl.project_key = b.project_key AND b.t_at >= pl.ts
LEFT JOIN reporter_prior rp ON rp.issue_key = b.issue_key
ASOF LEFT JOIN peer_hist ph ON ph.project_key = b.project_key AND ph.issue_type = b.issue_type_t AND b.t_at > ph.resolution_date
ASOF LEFT JOIN project_hist jh ON jh.project_key = b.project_key AND b.t_at > jh.resolution_date
LEFT JOIN day7_activity d ON d.issue_key = b.issue_key AND b.point = 'day7'
LEFT JOIN day7_stage s ON s.issue_key = b.issue_key AND b.point = 'day7';
