"""Table 4 and the cluster facts of §5.2, on Redset 186/8 and the three published workloads.

results/table4.csv             the authors' `generator` definition (the one that matches Table 4)
results/table4_definitions.csv every definition x series, to show which one the paper used
results/cluster_facts.csv      size of the paper's cluster and what the generators preserve
"""
from __future__ import annotations

import pandas as pd

from redset import ROOT, load_cluster
from repetition import Event, all_rates, events_from_redset, events_from_workload, redset_query_hash

WORKLOADS = ["matching", "generation", "baseline_round_robin"]


def main() -> None:
    trace = load_cluster(ROOT / "data" / "redset" / "c186_db8.parquet")
    series = {"redset": events_from_redset(trace)}
    workloads = {}
    for w in WORKLOADS:
        workloads[w] = pd.read_csv(ROOT / "data" / "osf" / w / "workload.csv", low_memory=False)
        series[w] = events_from_workload(workloads[w])
    # generation keyed by the Redset hash it was built from, not by its SQL text
    g = workloads["generation"]
    series["generation_by_redset_hash"] = [Event(e.query_type, k, e.scanset, e.write_table)
                                           for e, k in zip(series["generation"], g["exact_repetition_hash"])]

    pd.DataFrame([{"series": s, **all_rates(ev, "generator")} for s, ev in series.items()]) \
        .to_csv(ROOT / "results" / "table4.csv", index=False)

    defs = []
    for s, ev in series.items():
        for d, kw in [("generator", {}), ("plot_full", {"first_1k": False}), ("plot_first1k", {"first_1k": True})]:
            defs.append({"series": s, "definition": d, **all_rates(ev, d.split("_")[0], **kw)})
    pd.DataFrame(defs).to_csv(ROOT / "results" / "table4_definitions.csv", index=False)

    sel = trace[trace.query_type == "select"]
    facts = {
        "first_arrival": trace.arrival_timestamp.min(), "last_arrival": trace.arrival_timestamp.max(),
        "queries": len(trace), "selects": len(sel), "dml": len(trace) - len(sel),
        "cache_hits_restored": int((sel.was_cached == 1).sum()),
        "distinct_selects": len({redset_query_hash(*r) for r in zip(
            sel.feature_fingerprint, sel.num_scans, sel.num_joins, sel.read_table_ids)}),
        "distinct_select_fingerprints": sel.feature_fingerprint.nunique(),
    }
    ts = trace.arrival_timestamp.values
    for w, df in workloads.items():
        facts[f"{w}_distinct_select_sql"] = df.loc[df.query_type == "select", "sql"].nunique()
        same_len = len(df) == len(trace)
        facts[f"{w}_same_arrival_times"] = same_len and bool((pd.to_datetime(df.arrival_timestamp).values == ts).all())
        facts[f"{w}_same_query_types"] = same_len and bool((df.query_type.values == trace.query_type.values).all())
    pd.DataFrame([facts]).to_csv(ROOT / "results" / "cluster_facts.csv", index=False)
    print(pd.read_csv(ROOT / "results" / "table4.csv").round(3).to_string())
    print(pd.Series(facts).to_string())


if __name__ == "__main__":
    main()
