"""Load one Redset cluster/database the way Redbench does (sql/redset_cluster.sql)."""
from __future__ import annotations

from pathlib import Path

import duckdb
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
REDSET = Path("D:/da/redset-replication/data")  # the 17.7 GB trace downloaded for redset-replication
PROVISIONED = REDSET / "provisioned" / "full.parquet"
SERVERLESS = REDSET / "serverless" / "full.parquet"

# The paper's cluster (footnote 2) and window (used_config.json of the published workloads).
PAPER_CLUSTER = dict(instance=186, database=8, start="2024-05-01 00:00:00", end="2024-06-01 00:00:00")


def load_cluster(path: Path = PROVISIONED, con: duckdb.DuckDBPyConnection | None = None,
                 **cluster) -> pd.DataFrame:
    c = {**PAPER_CLUSTER, **cluster}
    con = con or duckdb.connect()
    sql = (ROOT / "sql" / "redset_cluster.sql").read_text().format(path=Path(path).as_posix(), **c)
    con.execute(sql)
    return con.sql("SELECT * FROM trace").df()
