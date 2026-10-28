"""Time the workloads on DuckDB, simulate the result cache, validate the simulation.

results/exec_<workload>.csv   median time of every distinct statement
results/execution.csv         speedup and hit share per workload
results/execution_check.csv   simulated vs real cached run on the first 2,000 statements
"""
from __future__ import annotations

import sys

import pandas as pd

from execute import simulate, time_distinct, validate
from redset import ROOT
from retime import retime

WORKLOADS = ["matching", "baseline_round_robin"]   # generation needs the augmented IMDb copies


def main(names: list[str]) -> None:
    for n in names:
        time_distinct(n)
        retime(n)          # one more run for DML that stalled
    pd.DataFrame([simulate(n) for n in names]).to_csv(ROOT / "results" / "execution.csv", index=False)
    pd.DataFrame([validate(n) for n in names]).to_csv(ROOT / "results" / "execution_check.csv", index=False)
    print(pd.read_csv(ROOT / "results" / "execution.csv").to_string())
    print(pd.read_csv(ROOT / "results" / "execution_check.csv").to_string())


if __name__ == "__main__":
    main(sys.argv[1:] or WORKLOADS)
