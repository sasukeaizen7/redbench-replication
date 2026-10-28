"""Re-run the authors' generators (vendor/Redbench) with the configs of the published workloads.

    python src/rerun_generators.py matching            # needs no database: JOB/CEB stats come from the SQL text
    python src/rerun_generators.py generation          # needs the IMDb support database (data/imdb/)

The output goes to data/rerun/<strategy>/ and is compared with data/osf/<strategy>/workload.csv
by src/determinism.py. The vendor code shells out to `rm -rf` and `tar` with paths relative to the
repository root, so it runs with vendor/Redbench as the working directory.

`hillmapper` (only used by the 'scanset' matching method; the paper uses 'join') has no Windows
wheel: an empty stand-in module is put on the path.
"""
from __future__ import annotations

import json
import os
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VENDOR = ROOT / "vendor" / "Redbench"
REDSET = "D:/da/redset-replication/data/provisioned/full.parquet"  # path must say 'provisioned'
OUT = ROOT / "data" / "rerun"


def _prepare() -> None:
    sys.modules.setdefault("hillmapper", types.ModuleType("hillmapper"))
    sys.path[:0] = [str(VENDOR / "src" / "redbench"), str(VENDOR / "src")]
    os.chdir(VENDOR)


def _config(strategy: str) -> Path:
    """The published used_config.json, minus the authors' machine-specific paths."""
    cfg = json.loads((ROOT / "data" / "osf" / strategy / "used_config.json").read_text())
    for k in ("output_dir", "wl_dir", "stats_db_filepath", "redset_path", "cluster_id",
              "database_id", "redset_dataset"):
        cfg.pop(k, None)
    if strategy == "matching" and isinstance(cfg["support_benchmarks"], dict):
        cfg["support_benchmarks"] = [cfg["support_benchmarks"]]
    if strategy == "generation":
        cfg["raw_database_tables"] = str(ROOT / "data" / "imdb" / "raw")
    path = OUT / f"{strategy}_config.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cfg, indent=2))
    return path


def main(strategy: str) -> None:
    config = _config(strategy)
    out = OUT / strategy
    _prepare()
    if strategy == "matching":
        # setup_db() only checks that the IMDb file exists; matching never opens it.
        marker = out / "tmp_generation" / "imdb" / "db_original.duckdb"
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.touch()
        from redbench.matching.run import generate_workload
    else:
        from redbench.generation.run import generate_workload
    generate_workload(str(out), REDSET, 186, 8, str(config), overwrite_existing=True)


if __name__ == "__main__":
    main(sys.argv[1])
