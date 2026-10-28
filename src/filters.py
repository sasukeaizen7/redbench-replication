"""Table 5: what share of filter predicates hit string columns.

A filter predicate is a comparison between one column and literals (=, <>, <, <=, >, >=,
IN, BETWEEN, LIKE / ILIKE, IS NULL). Column-to-column comparisons are joins and are not counted.
Each predicate's column type comes from the IMDb schema the workloads run on
(vendor/Redbench/src/redbench/matching/benchmarks/imdb/schema.sql). Generation workloads write to
copies of the tables named `<table>_<n>`; the suffix is stripped to find the schema table.
"""
from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

import pandas as pd
import sqlglot
from sqlglot import exp

from redset import ROOT

SCHEMA = ROOT / "vendor/Redbench/src/redbench/matching/benchmarks/imdb/schema.sql"
PREDICATES = (exp.EQ, exp.NEQ, exp.LT, exp.LTE, exp.GT, exp.GTE, exp.In, exp.Between,
              exp.Like, exp.ILike, exp.Is)


def load_schema(path: Path = SCHEMA) -> dict[str, dict[str, str]]:
    """{table: {column: 'string' | 'numeric' | 'other'}} from CREATE TABLE statements."""
    out: dict[str, dict[str, str]] = {}
    for table, body in re.findall(r"CREATE TABLE (\w+) \((.*?)\);", path.read_text(), re.S):
        cols = {}
        for line in body.splitlines():
            m = re.match(r"\s*(\w+)\s+([a-z ]+)", line)
            if not m or line.strip().startswith("--"):
                continue
            t = m.group(2)
            cols[m.group(1)] = ("string" if "char" in t or "text" in t else
                                "numeric" if any(k in t for k in ("int", "numeric", "double", "real", "float")) else
                                "other")
        out[table] = cols
    return out


def base_table(name: str, schema: dict) -> str:
    if name in schema:
        return name
    return re.sub(r"_\d+$", "", name)


@lru_cache(maxsize=None)
def predicate_types(sql: str) -> tuple[str, ...]:
    """Column type of every filter predicate of one SELECT."""
    schema = _SCHEMA
    tree = sqlglot.parse_one(sql, read="duckdb")
    alias = {}
    for t in tree.find_all(exp.Table):
        alias[t.alias_or_name] = base_table(t.name, schema)
    tables = set(alias.values())
    types = []
    for p in tree.find_all(*PREDICATES):
        cols = list(p.find_all(exp.Column))
        if len(cols) != 1:                 # a join (two columns) or an expression without a column
            continue
        c = cols[0]
        tbl = alias.get(c.table) if c.table else next(
            (t for t in tables if c.name in schema.get(t, {})), None)
        types.append(schema.get(tbl, {}).get(c.name, "unknown"))
    return tuple(types)


_SCHEMA = load_schema()


def string_share(workload: pd.DataFrame) -> dict:
    """Shares over all executed selects (each instance counts) and over distinct SQL."""
    sel = workload.loc[workload["query_type"] == "select", "sql"]
    rows = []
    for distinct, series in (("instances", sel), ("distinct", sel.drop_duplicates())):
        counts: dict[str, int] = {}
        for sql in series:
            for t in predicate_types(sql):
                counts[t] = counts.get(t, 0) + 1
        total = sum(counts.values())
        rows.append({"counting": distinct, "predicates": total,
                     **{f"share_{k}": v / total for k, v in sorted(counts.items())}})
    return rows
