# LEARN: how this replication works, and how to defend it

This file explains the choices behind the code, the traps found in the paper's artifacts, and what to say about them in an interview. The results are in [README.md](README.md).

## 1. What kind of study this is

*Redbench: Workload Synthesis From Cloud Traces* (Wehrstein et al., PVLDB 19, VLDB 2026) builds benchmark workloads that copy the **repetition**, **query mix** and **arrival times** of a real cloud trace (Redset, from Amazon Redshift) onto a public database (IMDb). It has two generators:

- **matching** maps each Redset query to an existing JOB/CEB benchmark query with a similar number of joins, and re-uses the same SQL whenever the Redset query repeats;
- **generation** writes new SQL for each Redset query: it maps Redset tables onto IMDb tables by scan size, then builds joins and filters to hit the same bytes read.

The authors published their code and the exact three workloads used in the paper (OSF project `fgny3`). That makes three levels of replication possible:

| Level | Question | Done here |
|---|---|---|
| **Analytic** | Do the paper's numbers follow from its own published artifacts? | yes: Table 4, Table 5, §5.2 recomputed from the OSF workloads and the Redset trace |
| **Generalization** | Do the paper's claims about Redset hold on the whole trace, not one cluster? | yes: query mix, skew, repetition of every May database |
| **Execution** | Do the workloads show the caching speedups of §6? | on DuckDB instead of the four unnamed commercial systems (see §6 below) |

Re-running the generators themselves (to test the "deterministic for a given seed" claim) was not done: see §7.

## 2. The metric everything rests on: repetition rates

Table 4 compares workloads with four numbers. For every SELECT, look back for an earlier SELECT with:

| | same key | still cache-valid |
|---|---|---|
| **QRR** | exact same query | not checked |
| **QRR_DML** | exact same query | no write to any table it reads since then |
| **SRR** | same set of tables (scanset) | not checked |
| **SRR_DML** | same set of tables | no write since then |

"Same query" is the Redset hash `fingerprint#num_scans#num_joins#(sorted table ids)` for the trace, and the SQL text for a generated workload. QRR_DML is exactly the share of SELECTs an ideal result cache with write invalidation would answer, which is why §6 uses it to predict caching speedups.

### Two implementations that must agree

`src/repetition.py` ports the authors' loop line for line. `sql/repetition.sql` computes the same thing set-based:

- `lag(i) OVER (PARTITION BY key ORDER BY i)` gives the previous occurrence of each SELECT;
- an **ASOF join** finds, for each table a SELECT reads, the last write to that table before it;
- the repeat survives DML when that last write is older than the previous occurrence.

The two give identical numbers on the paper's cluster and on random traces (`tests/test_repetition.py`). In an interview: *"I wrote the metric twice, once imperative and once relational, and the tests require them to agree to the last digit. That is how I trust a number I cannot check against anything else."*

### The authors' code has two definitions

| | `generator` (matching/gen_queries/query_generator.py) | `plot` (plots/plot_cluster_overview_plot.py) |
|---|---|---|
| What counts as a read | SELECT only | SELECT, plus INSERT/UPDATE/CTAS/ANALYZE that read tables |
| What invalidates | any non-SELECT | INSERT/UPDATE/DELETE/CTAS/COPY |
| Window | whole trace | **stops after row 1,001** by default (`stop_after_1k=True`) |

Table 4's generated rows match `generator`; its Redset row matches `plot` over the whole window slightly better (0.72/0.73/0.86/0.86 against the paper's 0.72/0.73/0.86/0.87). Both are within 0.015 of the paper everywhere. The Fig 5 code calls `plot` with the 1,000-row cut on by default: on cluster 186/8 that gives QRR ≈ 0.01, because the first 1,000 queries of that database are almost all INSERTs. `figures/first1k.png` shows that for most databases the first 1,000 queries say little about the month.

## 3. Traps found in the artifacts

- **The round-robin baseline is not repetition-free.** The text says it "exhibits no repetitions", but Table 4 gives it QRR 0.74. Both are right: the baseline is built to have as many *distinct* queries as Redset (`align_queries_with_num_distinct_in_redset`), so it repeats as often as Redset, but it interleaves a single-row INSERT/DELETE on a JOB table between repeats. Every repeat is invalidated: **QRR_DML = 0.00**. The text means "no cache-usable repetitions".
- **Matching collapses distinct queries.** Redset 186/8 has 6,405 distinct SELECTs; the matching workload uses only 415 distinct SQL texts (JOB/CEB has few queries per join count). That is why its QRR is 0.98 while Redset's is 0.73: matching is an *upper bound* on repetition, as the paper says in §6.
- **Generation repeats a bit more than Redset by text.** Keyed by the Redset hash it was built from, generation has QRR 0.743, Redset's exact value. Keyed by SQL text it has 0.803, because 6,405 Redset queries became 4,907 distinct SQL texts: different Redset queries can produce the same SQL. Table 4's 0.79 is between the two.
- **"May 2024" is nine days.** Cluster 186 database 8 only has queries from 4 to 13 May.
- **Cache hits must be restored.** Redset logs a result-cache hit as query type `other` with no fingerprint and no tables. Without restoring them from `cache_source_query_id` the paper's cluster would have 8,828 SELECTs instead of 24,881, and every repetition rate would collapse. `sql/redset_cluster.sql` does what the authors do (join on query id, instance, database and user).

## 4. Fleet claims: one cluster versus 400

The paper's §2 and §4 describe Redset as a whole (~50 % SELECTs, INSERT the largest DML type at ~20 %, most INSERTs are INSERT…SELECT, < 0.1 % of queries take ~25 % of CPU). `sql/fleet.sql` checks them on all 439 M non-aborted queries.

- **Streaming, not materializing.** A first version built a 441 M-row temp table and sorted it for `percent_rank`: it spilled 17 GB and nearly filled the disk. The final version is a view over the Parquet files and uses `approx_quantile` thresholds, so each query is one streaming pass (under 20 s each). `run_sql.py` caps DuckDB's spill at 6 GB.
- **No CPU column.** Redset has execution time and, for provisioned clusters, the number of nodes. The CPU proxy is `execution_ms × nodes`. Execution times are integers with many ties, so "the top 0.1 %" is in fact the top 0.07 % (the share is reported).
- **Count clusters, not databases.** Three clusters (13, 52, 97) have 50 databases each, all with QRR_DML between 4 % and 11 %. A histogram per database shows a spike that is really three customers; `figures/fleet_qrr.png` weights databases by their SELECTs within each cluster.
- **One database is missing.** Provisioned 96/0 (19.3 M queries in May) needed more than the 6 GB spill cap and is recorded with its error in `results/cluster_repetition.csv`.

## 5. Table 5: string filters

`src/filters.py` parses each SELECT with **sqlglot**, keeps every predicate that compares one column with literals (`=`, `IN`, `BETWEEN`, `LIKE`, `ILIKE`, `IS`, comparisons), resolves aliases to tables, and looks the column type up in the IMDb schema. Column-to-column comparisons are joins and are skipped. Generation writes to table copies (`title_1`), so the numeric suffix is stripped. The paper does not say whether it counts each executed query or each distinct one; both are reported. Matching fits per execution (69 % vs 67 %), generation per distinct query (76 % vs 75 %).

## 6. Execution on DuckDB instead of four commercial systems

The paper runs the workloads on four unnamed cloud warehouses (Systems A–D) with their caches on and off. Those are not available, so `src/execute.py`:

1. times every **distinct** statement of a workload on DuckDB over IMDb (the JOB snapshot from CWI, loaded with the authors' `schema.sql`/`load.sql`, because their prebuilt file on OSF could not be downloaded) (one warm-up, then one timed run; DML inside a transaction that is rolled back, so the data never changes);
2. replays the workload in arrival order with a **simulated result cache**: a SELECT costs 0 if the same SQL ran before and no statement wrote to one of its tables since (the QRR_DML rule), otherwise its measured time;
3. reports `speedup = runtime without cache / runtime with cache`;
4. `validate()` runs the first 2,000 statements for real with a Python dict as the cache, to check that simulated and real hits agree.

This tests the mechanism the paper credits for its speedups (repetition × cache), not the systems. It cannot reproduce predicate, scan or sub-result caching (Systems C and D).

Two things to know when reading the numbers:

- **A 60 s cap.** Each statement gets 60 s; a timer calls `interrupt()`. Some DuckDB operators do not check for interrupts often, so a few runs overshot (one baseline select ran 10,458 s, one DELETE 525 s). The simulation costs every statement at `min(time, 60 s)`, so a single outlier cannot decide a total. DML outliers are re-timed once by `src/retime.py`: the 525 s DELETE takes 0.011 s, so it was a stall of the machine, not of the query.
- **Why DuckDB shows more speedup than the paper for matching.** The ceiling is set by what the cache cannot skip: misses and DML. On DuckDB a single-row INSERT/DELETE takes ~5 ms and a JOB select ~0.2 s, so DML is a small share of the uncached run and hiding 97 % of selects removes most of the time. Cloud warehouses have a fixed per-statement overhead (compilation, commit, network) of tens to hundreds of milliseconds, which makes DML relatively expensive and caps the speedup lower. The paper's ranking holds (matching ≫ baseline ≈ 1), but the size of the effect depends on the system, which is what the paper's spread across Systems A–D also shows.

## 7. What was not done, and why

- **Re-running the generators.** The authors' generator code (`vendor/Redbench`) was cloned and read but not executed in this environment (running third-party code needs explicit approval here). `src/rerun_generators.py` is ready: it rebuilds the configs of the published workloads and calls the authors' entry points, then the "deterministic for a given trace, benchmark and seed" claim can be checked by diffing against `data/osf/`.
- **Fig 5 on generated workloads.** The paper's Fig 5 compares Redset with Redbench on 20 sampled clusters; that needs the generators too. The Redset side is measured for every database instead.
- **Systems A–D.** Not available; see §6.
- **Running the generation workload.** Its SQL reads and writes table copies (`title_0`, `person_info_1`, …) made by the authors' augmentation step (`db_augmented_x2`, 2.1 GB on OSF, not downloadable here). Building look-alike copies would time a different database, so only matching and the round-robin baseline are executed.

## 8. Questions to expect

- *Why trust a replication that mostly reuses the authors' workloads?* Because the numbers are recomputed from scratch with independent code (SQL and Python), from raw Redset and raw workload files. A mismatch would have shown up; three did (the generation row, the round-robin text, the 1,000-row cut).
- *Is cluster 186/8 representative?* Yes, as far as repetition goes. Its QRR_DML (0.74) sits just above the median cluster (0.66) and above 55 % of the 110 clusters measured. Counted per database instead, it would look far above the median (0.08), but only because three clusters contribute 150 near-identical databases.
- *Why does selects' share differ from the paper (31 % vs ~50 %)?* The paper's "about half" holds only after dropping COPY, ANALYZE, CTAS and VACUUM: among the four kept types SELECTs are 43 % (provisioned). Over all queries they are under a third, which matches the Redshift fleet analysis replicated in `../redset-replication` (30.5 %).
