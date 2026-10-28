"""Re-time statements whose first measurement looks like a stall (over 10x the median of their type).

One DELETE of the matching workload took 525 s against ~4 ms for the others: re-measure such
outliers once more and keep the faster run. Timeouts (NaN) are left as they are.
"""
from __future__ import annotations

import sys

import duckdb
import pandas as pd

from execute import DB, _timed
from redset import ROOT


def retime(name: str, factor: float = 10, floor_s: float = 5) -> None:
    out = ROOT / "results" / f"exec_{name}.csv"
    d = pd.read_csv(out)
    med = d.groupby("query_type").seconds.transform("median")
    sus = d.index[(d.seconds > factor * med) & (d.seconds > floor_s) & (d.query_type != "select")]
    if not len(sus):
        return
    con = duckdb.connect(str(DB))
    con.execute("SET threads = 8")
    for i in sus:
        t = _timed(con, d.at[i, "sql"], True)
        print(f"{name}: {d.at[i, 'query_type']} {d.at[i, 'seconds']:.1f}s -> {t:.3f}s", flush=True)
        if t == t and t >= 0:
            d.at[i, "seconds"] = min(d.at[i, "seconds"], t)
    d.to_csv(out, index=False)


if __name__ == "__main__":
    for n in sys.argv[1:] or ["matching", "baseline_round_robin"]:
        retime(n)
