-- One Redset cluster/database as Redbench sees it (utils/load_and_preprocess_redset.py).
-- {path}, {instance}, {database}, {start}, {end} are filled in by src/redset.py.
--
--   * aborted queries dropped;
--   * result-cache hits (query_type 'other', no features) take every column of the select
--     that produced the cached result, except their own arrival time / id / was_cached;
--   * only select / insert / delete / update are kept (copy, analyze, ctas off, as in the paper);
--   * rows missing the scan size or their read/write tables are dropped.
CREATE OR REPLACE TABLE trace AS
WITH raw AS (
    SELECT * FROM read_parquet('{path}')
    WHERE instance_id = {instance} AND database_id = {database}
      AND was_aborted = 0
      AND arrival_timestamp BETWEEN TIMESTAMP '{start}' AND TIMESTAMP '{end}'
),
original AS (SELECT * FROM raw WHERE was_cached = 0),
cached AS (
    SELECT o.* REPLACE (c.arrival_timestamp AS arrival_timestamp, c.query_id AS query_id,
                        c.was_cached AS was_cached)
    FROM raw c
    JOIN original o
      ON c.cache_source_query_id = o.query_id AND c.instance_id = o.instance_id
     AND c.database_id = o.database_id AND c.user_id = o.user_id
    WHERE c.was_cached = 1
)
SELECT * FROM (SELECT * FROM original UNION ALL SELECT * FROM cached)
WHERE query_type IN ('select', 'insert', 'delete', 'update')
  AND mbytes_scanned IS NOT NULL
  AND (query_type NOT IN ('select', 'update') OR read_table_ids IS NOT NULL)
  AND (query_type NOT IN ('insert', 'update', 'delete') OR write_table_ids IS NOT NULL)
ORDER BY arrival_timestamp, query_id;
