"""Query and scanset repetition rates (QRR / SRR), the realism metric of Redbench Table 4.

A select "repeats" when an earlier select had the same key (exact: query hash or SQL text;
structural: the set of tables it reads). The DML-aware variant only counts the repeat if no
write touched any table of the scanset since that earlier select, i.e. a result cache could
still have answered it.

The authors' code has two definitions, and they differ (see LEARN.md):
  * `generator`: Redbench/matching/gen_queries/query_generator.py::_compute_repetition_ratio.
    Only selects count; every non-select invalidates its write table.
  * `plot`: Redbench/plots/plot_cluster_overview_plot.py::_compute_repetition_ratio.
    Selects AND insert/update/ctas/analyze that read tables count; only DML invalidates;
    by default the loop stops after row 1001 (`stop_after_1k`).
Both are ported here line for line on a normalized event list; `sql/repetition.sql` is an
independent window-function implementation of `generator`, and tests check they agree.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Sequence

import pandas as pd

READ_TYPES_PLOT = {"select", "analyze", "update", "insert", "ctas"}
WRITE_TYPES_PLOT = {"update", "insert", "delete", "ctas", "copy"}


@dataclass(frozen=True)
class Event:
    query_type: str
    key: object                 # exact-repetition identity
    scanset: tuple              # tables read (sorted), () if none
    write_table: object = None  # table written, None if none


def rate_generator(events: Sequence[Event], dml_aware: bool, scanset: bool) -> float:
    last_select, last_write = {}, {}
    rep = tot = 0
    for i, e in enumerate(events):
        if e.query_type == "select":
            tot += 1
            h = e.scanset if scanset else e.key
            if h in last_select:
                if all(last_write.get(t, -1) <= last_select[h] for t in e.scanset):
                    rep += 1
            last_select[h] = i
        elif e.write_table is not None and dml_aware:
            last_write[e.write_table] = i
    return rep / tot if tot else 0.0


def rate_plot(events: Sequence[Event], dml_aware: bool, scanset: bool,
              first_1k: bool = True) -> float:
    last_select, last_write = {}, {}
    rep = tot = 0
    for i, e in enumerate(events):
        if e.query_type in READ_TYPES_PLOT and e.scanset:
            tot += 1
            h = e.scanset if scanset else e.key
            if h in last_select:
                if not dml_aware or all(last_write.get(t, -1) <= last_select[h]
                                        for t in e.scanset):
                    rep += 1
            last_select[h] = i
        if dml_aware and e.query_type in WRITE_TYPES_PLOT and e.write_table is not None:
            last_write[e.write_table] = i
        if first_1k and i > 1000:
            break
    return rep / tot if tot else 0.0


def all_rates(events: Sequence[Event], definition: str = "generator", **kw) -> dict:
    f = rate_generator if definition == "generator" else rate_plot
    return {
        "qrr_dml": f(events, dml_aware=True, scanset=False, **kw),
        "qrr": f(events, dml_aware=False, scanset=False, **kw),
        "srr_dml": f(events, dml_aware=True, scanset=True, **kw),
        "srr": f(events, dml_aware=False, scanset=True, **kw),
    }


# ---------- building events from the three sources ----------

def _ids(s) -> tuple:
    if s is None or (isinstance(s, float) and pd.isna(s)) or s == "":
        return ()
    return tuple(sorted(int(x) for x in str(s).split(",")))


def _names(s) -> tuple:
    if s is None or (isinstance(s, float) and pd.isna(s)) or s == "":
        return ()
    return tuple(str(s).split(","))  # authors keep the generator's order, no sort


def redset_query_hash(fp, num_scans, num_joins, read_table_ids) -> str:
    """Same string as utils/load_and_preprocess_redset.py::query_hash."""
    h = f"{fp}#{int(num_scans)}#{int(num_joins)}"
    ids = _ids(read_table_ids)
    if ids:
        h += f"#{ids}"
    return h


def events_from_redset(df: pd.DataFrame) -> list[Event]:
    """df: Redset rows of one cluster/database, cache hits already restored, arrival order."""
    out = []
    for r in df.itertuples(index=False):
        w = r.write_table_ids
        out.append(Event(
            r.query_type,
            redset_query_hash(r.feature_fingerprint, r.num_scans, r.num_joins, r.read_table_ids),
            _ids(r.read_table_ids),
            None if w is None or (isinstance(w, float) and pd.isna(w)) else int(w),
        ))
    return out


def events_from_workload(df: pd.DataFrame) -> list[Event]:
    """A Redbench workload.csv (matching, generation or round-robin baseline)."""
    tables = df["join_tables"] if "join_tables" in df else df["read_tables"]
    out = []
    for qt, sql, tbl, w in zip(df["query_type"], df["sql"], tables, df["write_table"]):
        out.append(Event(qt, sql, _names(tbl), None if pd.isna(w) else w))
    return out


def rates_sql(events: Sequence[Event], con=None) -> dict:
    """`generator` rates computed by sql/repetition.sql (set-based, independent of the loop)."""
    import duckdb
    from pathlib import Path

    con = con or duckdb.connect()
    df = pd.DataFrame({
        "i": range(len(events)),
        "query_type": [e.query_type for e in events],
        "qkey": [str(e.key) for e in events],
        "scanset": [[str(t) for t in e.scanset] for e in events],
        "write_table": [None if e.write_table is None else str(e.write_table) for e in events],
    })
    con.register("events_df", df)
    con.execute("CREATE OR REPLACE TEMP TABLE events AS SELECT * FROM events_df")
    sql = (Path(__file__).resolve().parents[1] / "sql" / "repetition.sql").read_text()
    row = con.sql(sql.split("-- name: rates", 1)[1]).fetchone()
    return dict(zip(["qrr_dml", "qrr", "srr_dml", "srr"], row))
