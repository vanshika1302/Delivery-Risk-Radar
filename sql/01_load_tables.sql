-- Typed tables from the raw Parquet files written by etl/extract.py.
-- $RAW is replaced with the extraction folder. Dates arrive as the dataset's strings
-- (for example 2022-01-03T14:50:04.000+0000) and become naive UTC timestamps here.
--
-- A mongodump of a live database can write a document twice if it moves while the dump runs.
-- In the real Apache extraction this affects 17 tickets, each an exact copy with its changelog
-- rows doubled. Keep one copy of each ticket, and collapse identical child rows for those keys only.

CREATE OR REPLACE TEMP TABLE duplicate_keys AS
SELECT issue_key FROM read_parquet('$RAW/issues.parquet') GROUP BY issue_key HAVING count(*) > 1;

CREATE TABLE issues AS
SELECT * REPLACE (
    timezone('UTC', try_strptime(created, '%Y-%m-%dT%H:%M:%S.%g%z'))         AS created,
    timezone('UTC', try_strptime(updated, '%Y-%m-%dT%H:%M:%S.%g%z'))         AS updated,
    timezone('UTC', try_strptime(resolution_date, '%Y-%m-%dT%H:%M:%S.%g%z')) AS resolution_date,
    CAST(try_strptime(due_date, '%Y-%m-%d') AS DATE)                         AS due_date
)
FROM read_parquet('$RAW/issues.parquet')
QUALIFY row_number() OVER (PARTITION BY issue_key ORDER BY updated DESC NULLS LAST) = 1;

CREATE TABLE changelog AS
SELECT * REPLACE (
    timezone('UTC', try_strptime(created, '%Y-%m-%dT%H:%M:%S.%g%z')) AS created
)
FROM (SELECT * FROM read_parquet('$RAW/changelog.parquet') WHERE issue_key NOT IN (SELECT issue_key FROM duplicate_keys)
   UNION ALL
   SELECT DISTINCT * FROM read_parquet('$RAW/changelog.parquet') WHERE issue_key IN (SELECT issue_key FROM duplicate_keys));

CREATE TABLE comments AS
SELECT * REPLACE (
    timezone('UTC', try_strptime(created, '%Y-%m-%dT%H:%M:%S.%g%z')) AS created,
    timezone('UTC', try_strptime(updated, '%Y-%m-%dT%H:%M:%S.%g%z')) AS updated
)
FROM (SELECT * FROM read_parquet('$RAW/comments.parquet') WHERE issue_key NOT IN (SELECT issue_key FROM duplicate_keys)
   UNION ALL
   SELECT DISTINCT * FROM read_parquet('$RAW/comments.parquet') WHERE issue_key IN (SELECT issue_key FROM duplicate_keys));

-- Ticket text stays in issue_text.parquet (it is large, and v1 only needs lengths).
CREATE TABLE issue_text_stats AS
SELECT issue_key, any_value(length(summary)) AS summary_length, any_value(length(description)) AS description_length
FROM read_parquet('$RAW/issue_text.parquet')
GROUP BY issue_key;
