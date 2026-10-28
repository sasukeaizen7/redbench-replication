-- Repetition rates as set-based SQL: an independent check of src/repetition.py::rate_generator.
-- Input: events(i BIGINT, query_type VARCHAR, qkey VARCHAR, scanset VARCHAR[], write_table VARCHAR),
-- one row per query in arrival order (i = position).
--
-- A select repeats when an earlier select had the same key (lag over the key). It still repeats
-- with DML awareness when, for every table it reads, the last write to that table before it
-- (ASOF join) happened before the earlier select.

-- name: rates
WITH sel AS (
    SELECT i, scanset,
           lag(i) OVER (PARTITION BY qkey ORDER BY i)                    AS prev_q,
           lag(i) OVER (PARTITION BY scanset ORDER BY i)                 AS prev_s
    FROM events WHERE query_type = 'select'
),
writes AS (
    SELECT i, write_table AS t FROM events
    WHERE query_type <> 'select' AND write_table IS NOT NULL
),
reads AS (SELECT i, unnest(scanset) AS t FROM sel),
last_write AS (                         -- last write to each read table before the select
    SELECT r.i, max(w.i) AS lw_i_per_table, r.t
    FROM reads r ASOF LEFT JOIN writes w ON r.t = w.t AND r.i > w.i
    GROUP BY r.i, r.t
),
last_any AS (                           -- latest of those over the scanset
    SELECT i, max(lw_i_per_table) AS lw FROM last_write GROUP BY i
)
SELECT
    avg(CASE WHEN prev_q IS NOT NULL AND coalesce(lw, -1) <= prev_q THEN 1 ELSE 0 END) AS qrr_dml,
    avg(CASE WHEN prev_q IS NOT NULL THEN 1 ELSE 0 END)                                AS qrr,
    avg(CASE WHEN prev_s IS NOT NULL AND coalesce(lw, -1) <= prev_s THEN 1 ELSE 0 END) AS srr_dml,
    avg(CASE WHEN prev_s IS NOT NULL THEN 1 ELSE 0 END)                                AS srr
FROM sel LEFT JOIN last_any USING (i);
