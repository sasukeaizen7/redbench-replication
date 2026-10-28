"""Fig 5: repetition rates of every Redset database with enough selects in May 2024.

The paper plots 20 randomly sampled clusters. Here every provisioned and serverless database
with at least 1,000 selects in the window is measured, so the paper's cluster 186/8 and the 20
can be placed in the fleet distribution. Two definitions (see src/repetition.py):
  * generator: sql/repetition.sql over the whole window;
  * plot_first1k: the authors' plot default, which stops after row 1001.
"""
from __future__ import annotations

import sys
import time

import duckdb
import pandas as pd

from redset import PROVISIONED, SERVERLESS, ROOT
from repetition import all_rates, events_from_redset

MIN_SELECTS = 1000
WINDOW = dict(start="2024-05-01 00:00:00", end="2024-06-01 00:00:00")

EVENTS_SQL = """
CREATE OR REPLACE TEMP TABLE events AS
SELECT row_number() OVER (ORDER BY arrival_timestamp, query_id) - 1 AS i,
       query_type,
       feature_fingerprint || '#' || num_scans || '#' || num_joins
         || coalesce('#' || list_sort(string_split(read_table_ids, ',')::INT[])::VARCHAR, '') AS qkey,
       coalesce(list_sort(string_split(read_table_ids, ',')::INT[])::VARCHAR[], []) AS scanset,
       write_table_ids AS write_table
FROM trace
"""


def measure(con, variant, path, instance, database) -> dict:
    sql = (ROOT / "sql" / "redset_cluster.sql").read_text().format(
        path=path.as_posix(), instance=instance, database=database, **WINDOW)
    con.execute(sql)
    con.execute(EVENTS_SQL)
    n, n_sel = con.sql("SELECT count(*), count(*) FILTER (WHERE query_type = 'select') FROM events").fetchone()
    rep = (ROOT / "sql" / "repetition.sql").read_text().split("-- name: rates", 1)[1]
    gen = dict(zip(["qrr_dml", "qrr", "srr_dml", "srr"], con.sql(rep).fetchone()))
    head = con.sql("SELECT * FROM trace ORDER BY arrival_timestamp, query_id LIMIT 1002").df()
    plot = all_rates(events_from_redset(head), "plot", first_1k=True)
    return {"variant": variant, "instance_id": instance, "database_id": database,
            "queries": n, "selects": n_sel,
            **{f"gen_{k}": v for k, v in gen.items()},
            **{f"plot1k_{k}": v for k, v in plot.items()}}


def main() -> None:
    con = duckdb.connect()
    con.execute("SET temp_directory = 'data/tmp'; SET max_temp_directory_size = '6GB'; SET memory_limit = '12GB'")
    out = ROOT / "results" / "cluster_repetition.csv"
    done = pd.read_csv(out) if out.exists() else pd.DataFrame(columns=["variant", "instance_id", "database_id"])
    seen = set(zip(done.variant, done.instance_id, done.database_id))
    rows = done.to_dict("records")
    for variant, path in (("provisioned", PROVISIONED), ("serverless", SERVERLESS)):
        dbs = pd.read_csv(ROOT / "data" / "redset" / f"may_dbs_{variant}.csv")
        dbs = dbs[dbs.sel >= MIN_SELECTS].sort_values("n")
        for r in dbs.itertuples():
            if (variant, r.instance_id, r.database_id) in seen:
                continue
            t = time.time()
            try:
                rows.append(measure(con, variant, path, r.instance_id, r.database_id))
            except duckdb.Error as e:                         # e.g. spill cap hit on the largest dbs
                rows.append({"variant": variant, "instance_id": r.instance_id,
                             "database_id": r.database_id, "queries": r.n, "error": str(e)[:200]})
            pd.DataFrame(rows).to_csv(out, index=False)   # resumable
            print(f"{variant} {r.instance_id}/{r.database_id} n={r.n} {time.time() - t:.1f}s", flush=True)


if __name__ == "__main__":
    sys.exit(main())
