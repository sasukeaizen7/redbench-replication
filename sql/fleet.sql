-- Fleet-level Redset claims of the Redbench paper (§2.1, §4.1, §4.3).
-- {provisioned} and {serverless} are the full Redset Parquet files. Whole trace (March-May 2024).
--
-- Redset has no CPU-time column. The CPU proxy is execution time x nodes for provisioned clusters
-- (cluster_size) and execution time alone for serverless; the claim is checked on both.
-- Result-cache hits are logged as query_type 'other' with was_cached = 1: they count as selects.

-- name: _q
CREATE OR REPLACE TEMP VIEW q AS  -- a view: streamed from Parquet, never materialized
SELECT 'provisioned' AS variant,
       CASE WHEN was_cached = 1 THEN 'select' ELSE query_type END AS qtype,
       was_cached, execution_duration_ms AS exec_ms,
       execution_duration_ms * coalesce(cluster_size, 1) AS cpu_proxy,
       read_table_ids IS NOT NULL AND read_table_ids <> '' AS reads
FROM read_parquet('{provisioned}') WHERE was_aborted = 0
UNION ALL
SELECT 'serverless',
       CASE WHEN was_cached = 1 THEN 'select' ELSE query_type END,
       was_cached, execution_duration_ms, execution_duration_ms,
       read_table_ids IS NOT NULL AND read_table_ids <> ''
FROM read_parquet('{serverless}') WHERE was_aborted = 0;

-- name: query_mix
-- Share of each query type, over all types and over the four types Redbench keeps.
SELECT variant, qtype, count(*) AS n,
       count(*) / sum(count(*)) OVER (PARTITION BY variant) AS share_all,
       CASE WHEN qtype IN ('select', 'insert', 'update', 'delete')
            THEN count(*) / sum(count(*) FILTER (WHERE qtype IN ('select', 'insert', 'update', 'delete')))
                            OVER (PARTITION BY variant) END AS share_4types
FROM q GROUP BY variant, qtype ORDER BY variant, n DESC;

-- name: insert_select
-- INSERTs that read a table (INSERT ... SELECT) versus plain INSERT ... VALUES.
SELECT variant, count(*) AS inserts, avg(reads::INT) AS share_reading
FROM q WHERE qtype = 'insert' GROUP BY ALL ORDER BY variant;

-- name: skew
-- Share of total time taken by the most expensive 0.1 % (and 1 %) of queries. Thresholds come
-- from approximate quantiles (a streaming pass instead of sorting 441 M rows).
WITH thr AS (
    SELECT variant,
           approx_quantile(cpu_proxy, 0.999) AS cpu_999, approx_quantile(cpu_proxy, 0.99) AS cpu_99,
           approx_quantile(exec_ms, 0.999) AS exec_999
    FROM q WHERE exec_ms IS NOT NULL GROUP BY variant
)
SELECT variant,
       avg((q.cpu_proxy > cpu_999)::INT)                                      AS top_cpu_query_share,
       sum(cpu_proxy) FILTER (WHERE q.cpu_proxy > cpu_999) / sum(cpu_proxy)   AS top01_cpu_share,
       sum(exec_ms) FILTER (WHERE q.exec_ms > exec_999) / sum(exec_ms)        AS top01_exec_share,
       sum(cpu_proxy) FILTER (WHERE q.cpu_proxy > cpu_99) / sum(cpu_proxy)    AS top1_cpu_share
FROM q JOIN thr USING (variant) WHERE exec_ms IS NOT NULL
GROUP BY variant ORDER BY variant;
