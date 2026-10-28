"""§6 substitute: what a result cache saves on each workload, measured on DuckDB over IMDb.

The paper runs the workloads on four commercial warehouses. Here every distinct statement of a
workload is timed on DuckDB (one warm-up, then RUNS timed runs, median; DML inside a transaction
that is rolled back, so the database never changes), and a result cache is simulated over the
workload in arrival order:

  * a SELECT is a hit when the same SQL ran before and no statement wrote to any table it reads
    since then (exactly the DML-aware QRR keyed by SQL text); a hit costs 0;
  * everything else costs its measured time.

speedup = total time without cache / total time with cache. `validate()` runs a slice of the
workload for real, with a Python dict as the cache, to check the simulation.
"""
from __future__ import annotations

import statistics
import sys
import threading
import time

import duckdb
import pandas as pd

from redset import ROOT
from repetition import events_from_workload

DB = ROOT / "data" / "imdb" / "imdb.duckdb"
RUNS = 1   # after one warm-up; 3 runs would take ~3 h for the 6,392 baseline selects
TIMEOUT_S = 60


def _timed(con, sql: str, write: bool) -> float:
    timer = threading.Timer(TIMEOUT_S, con.interrupt)
    timer.start()
    t = time.perf_counter()
    try:
        if write:
            con.execute("BEGIN")
            con.execute(sql)        # DELETE ...; INSERT ...: DuckDB runs every statement of the string
            con.execute("ROLLBACK")
        else:
            con.execute(sql).fetchall()
    except duckdb.InterruptException:          # timeout: costed at the cap
        if write:
            con.execute("ROLLBACK")
        return float("nan")
    except duckdb.Error:                       # rejected by DuckDB (e.g. a key conflict): -1, costed 0
        if write:
            con.execute("ROLLBACK")
        return -1.0
    finally:
        timer.cancel()
    return time.perf_counter() - t


def time_distinct(name: str) -> pd.DataFrame:
    """Median runtime of each distinct statement; resumable (results/exec_<name>.csv)."""
    out = ROOT / "results" / f"exec_{name}.csv"
    w = pd.read_csv(ROOT / "data" / "osf" / name / "workload.csv", low_memory=False)
    stmts = w.drop_duplicates("sql")[["sql", "query_type"]]
    done = pd.read_csv(out) if out.exists() else pd.DataFrame(columns=["sql", "query_type", "seconds"])
    seen = set(done.sql)
    rows = done.to_dict("records")
    con = duckdb.connect(str(DB))
    con.execute("SET threads = 8")
    for k, (sql, qt) in enumerate(stmts.itertuples(index=False)):
        if sql in seen:
            continue
        write = qt != "select"
        first = _timed(con, sql, write)                       # warm-up
        times = [first] if first != first or first < 0 else [_timed(con, sql, write) for _ in range(RUNS)]
        rows.append({"sql": sql, "query_type": qt, "seconds": statistics.median(times)})
        if k % 50 == 0:
            pd.DataFrame(rows).to_csv(out, index=False)
            print(f"{name}: {len(rows)}/{len(stmts)}", flush=True)
    pd.DataFrame(rows).to_csv(out, index=False)
    return pd.DataFrame(rows)


def cache_hits(w: pd.DataFrame) -> list[bool]:
    """Per row: would a DML-invalidated result cache answer it?"""
    last_select, last_write, hits = {}, {}, []
    for i, e in enumerate(events_from_workload(w)):
        hit = False
        if e.query_type == "select":
            j = last_select.get(e.key)
            hit = j is not None and all(last_write.get(t, -1) <= j for t in e.scanset)
            last_select[e.key] = i
        elif e.write_table is not None:
            last_write[e.write_table] = i
        hits.append(hit)
    return hits


def simulate(name: str) -> dict:
    w = pd.read_csv(ROOT / "data" / "osf" / name / "workload.csv", low_memory=False)
    t = pd.read_csv(ROOT / "results" / f"exec_{name}.csv").set_index("sql")["seconds"]
    w["seconds"] = w["sql"].map(t)
    w["hit"] = cache_hits(w)
    # interrupt() does not stop every operator in time, so a few runs overshoot the cap: cap them too
    timed_out = w["seconds"].isna() | (w["seconds"] > TIMEOUT_S)
    rejected = w["seconds"] < 0
    w["seconds"] = w["seconds"].fillna(TIMEOUT_S).clip(0, TIMEOUT_S)  # timeout = the cap, rejected = 0
    sel = w.query_type == "select"
    no_cache = w.seconds.sum()
    with_cache = w.seconds[~w.hit].sum()
    return {
        "workload": name, "statements": len(w), "distinct": w.sql.nunique(),
        "timed_out_rows": int(timed_out.sum()), "rejected_rows": int(rejected.sum()),
        "hit_share_selects": w.hit[sel].mean(),
        "runtime_no_cache_s": no_cache, "runtime_cache_s": with_cache,
        "speedup": no_cache / with_cache,
        "select_speedup": w.seconds[sel].sum() / w.seconds[sel & ~w.hit].sum(),
        "dml_share_no_cache": w.seconds[~sel].sum() / no_cache,
    }


def validate(name: str, n: int = 2000) -> dict:
    """Run the first n statements for real with a dict cache; compare with the simulation."""
    w = pd.read_csv(ROOT / "data" / "osf" / name / "workload.csv", low_memory=False).head(n)
    hits = cache_hits(w)
    con = duckdb.connect(str(DB))
    con.execute("SET threads = 8")
    cache, real_hits, failed, capped = {}, [], 0, 0
    ev = events_from_workload(w)
    con.execute("BEGIN")                                     # rolled back at the end
    t = time.perf_counter()
    for e in ev:
        if e.query_type == "select":
            hit = e.key in cache
            real_hits.append(hit)
            if not hit:
                timer = threading.Timer(TIMEOUT_S, con.interrupt)
                timer.start()
                try:
                    cache[e.key] = (con.execute(e.key).fetchall(), set(e.scanset))
                except duckdb.InterruptException:   # same cap as the timing run; not cached
                    capped += 1
                    con.execute("ROLLBACK")
                    con.execute("BEGIN")
                finally:
                    timer.cancel()
        else:
            real_hits.append(False)
            try:
                con.execute(e.key)
            except duckdb.Error:          # a rejected DML aborts the transaction: start a new one
                failed += 1
                con.execute("ROLLBACK")
                con.execute("BEGIN")
            cache = {k: v for k, v in cache.items() if e.write_table not in v[1]}
    elapsed = time.perf_counter() - t
    con.execute("ROLLBACK")
    times = pd.read_csv(ROOT / "results" / f"exec_{name}.csv").set_index("sql")["seconds"]
    times = times.fillna(TIMEOUT_S).clip(0, TIMEOUT_S)
    sim = sum(times.get(e.key, 0) for e, h in zip(ev, hits) if not h)
    return {"workload": name, "rows": n, "hits_agree": real_hits == hits, "failed_dml": failed,
            "timed_out": capped,
            "real_cached_run_s": elapsed, "simulated_cached_run_s": sim}


if __name__ == "__main__":
    for name in sys.argv[1:]:
        time_distinct(name)
