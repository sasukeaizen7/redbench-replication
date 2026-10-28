"""Build the IMDb database the workloads run on: data/imdb/imdb.duckdb.

The authors' prebuilt file (OSF) kept failing to download (connection resets, then 403), so the
database is built the way their own commented-out `_setup_db_from_cwi` did: the JOB snapshot of
IMDb from CWI (data/imdb/raw/*.csv) loaded with the repository's schema.sql and load.sql.
"""
from __future__ import annotations

import re
import time

import duckdb

from redset import ROOT

SRC = ROOT / "vendor/Redbench/src/redbench/matching/benchmarks/imdb"
RAW = ROOT / "data" / "imdb" / "raw"
DB = ROOT / "data" / "imdb" / "imdb.duckdb"


def main() -> None:
    DB.unlink(missing_ok=True)
    con = duckdb.connect(str(DB))
    con.execute((SRC / "schema.sql").read_text())
    for stmt in filter(str.strip, (SRC / "load.sql").read_text().split(";")):
        stmt = re.sub(r"'([^']+\.csv)'", lambda m: f"'{(RAW / m.group(1)).as_posix()}'", stmt)
        t = time.time()
        con.execute(stmt)
        print(stmt.split()[1], f"{time.time() - t:.1f}s", flush=True)
    con.execute("CHECKPOINT")
    for (t, n) in con.sql("SELECT table_name, estimated_size FROM duckdb_tables() ORDER BY 1").fetchall():
        print(f"{t:20} {n:>12,}")


if __name__ == "__main__":
    main()
