"""Run a SQL file split on `-- name: <id>` markers; save each result to results/<id>.csv.

Names starting with `_` are setup steps and are not saved (same contract as redset-replication).
"""
from __future__ import annotations

import re
import sys
import time
from pathlib import Path

import duckdb

from redset import PROVISIONED, SERVERLESS, ROOT

RESULTS = ROOT / "results"


def run_file(path: Path, con: duckdb.DuckDBPyConnection | None = None, **params) -> None:
    con = con or duckdb.connect()
    con.execute("SET temp_directory = 'data/tmp'; SET max_temp_directory_size = '6GB'; "
                "SET preserve_insertion_order = false")
    params = {"provisioned": PROVISIONED.as_posix(), "serverless": SERVERLESS.as_posix(), **params}
    text = path.read_text().format(**params)
    RESULTS.mkdir(exist_ok=True)
    for name, sql in re.findall(r"-- name: (\S+)\n(.*?)(?=\n-- name: |\Z)", text, re.S):
        t = time.time()
        if name.startswith("_"):
            con.execute(sql)
        else:
            df = con.sql(sql).df()
            df.to_csv(RESULTS / f"{name}.csv", index=False)
        print(f"{path.name}:{name} {time.time() - t:.1f}s", flush=True)


if __name__ == "__main__":
    for p in sys.argv[1:]:
        run_file(ROOT / p)
