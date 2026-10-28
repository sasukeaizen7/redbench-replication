"""Scorecard: every quantitative claim of the paper next to the replicated value.

Reads only results/*.csv (written by the other scripts) and writes results/scorecard.csv and
results/scorecard.md, which README.md quotes.

Verdicts: confirmed (same rounded value, or within the stated tolerance), close (same direction,
off by more than rounding), not (different conclusion), n/a (could not be measured here).
"""
from __future__ import annotations

import pandas as pd

from redset import ROOT

R = ROOT / "results"


def _csv(name: str) -> pd.DataFrame | None:
    p = R / f"{name}.csv"
    return pd.read_csv(p) if p.exists() else None


def verdict(paper: float, ours: float | None, tol: float) -> str:
    if ours is None or pd.isna(ours):
        return "n/a"
    return "confirmed" if abs(paper - ours) <= tol else "close" if abs(paper - ours) <= 3 * tol else "not"


def rows() -> list[dict]:
    out = []

    def add(section, claim, paper, ours, tol, fmt="{:.2f}", note="", force=None):
        out.append({"section": section, "claim": claim, "paper": fmt.format(paper),
                    "replication": "-" if ours is None or pd.isna(ours) else fmt.format(ours),
                    "verdict": force or verdict(paper, ours, tol), "note": note})

    t4 = _csv("table4")
    if t4 is not None:
        t4 = t4.set_index("series")
        paper4 = {"redset": (.72, .73, .86, .87), "generation": (.73, .79, .95, .98),
                  "matching": (.97, .98, .99, .99), "baseline_round_robin": (.00, .74, .36, .99)}
        # The Redset row fits the authors' plot definition over the full window better
        # (results/table4_definitions.csv); the generated rows fit the generator definition.
        d = _csv("table4_definitions").set_index(["series", "definition"])
        for s, vals in paper4.items():
            src = d.loc[("redset", "plot_full")] if s == "redset" else t4.loc[s]
            note = "plot definition, full window" if s == "redset" else ""
            for m, p in zip(["qrr_dml", "qrr", "srr_dml", "srr"], vals):
                # tolerance 0.01: the paper's 0.99 for a measured 0.999 shows its values are
                # sometimes truncated rather than rounded
                add("Table 4", f"{s}: {m.upper()}", p, src[m], 0.01, note=note)

    c = _csv("cluster_facts")
    if c is not None:
        c = c.iloc[0]
        add("§5.2", "Cluster 186/8: queries", 36_000, c.queries, 500, "{:,.0f}")
        add("§5.2", "Cluster 186/8: selects", 25_000, c.selects, 500, "{:,.0f}")
        add("§5.2", "Cluster 186/8: distinct selects", 6_400, c.distinct_selects, 50, "{:,.0f}")
        add("§5.2", "Cluster 186/8: DML", 11_000, c.dml, 500, "{:,.0f}")

    sf = _csv("string_filters")
    if sf is not None:
        sf = sf.set_index(["workload", "counting"])
        add("Table 5", "Matching: string filter share", .67, sf.loc[("matching", "instances"), "share_string"], .01, "{:.0%}")
        add("Table 5", "Generation: string filter share", .75, sf.loc[("generation", "distinct"), "share_string"], .01, "{:.0%}",
            "distinct queries; all instances give " + f"{sf.loc[('generation', 'instances'), 'share_string']:.0%}")

    mix = _csv("query_mix")
    if mix is not None:
        m = mix.set_index(["variant", "qtype"])
        for v in ("provisioned", "serverless"):
            add("§4.1", f"Selects among queries ({v})", .50, m.loc[(v, "select"), "share_all"], .02, "{:.0%}")
            add("§4.3", f"INSERTs among queries ({v})", .20, m.loc[(v, "insert"), "share_all"], .02, "{:.0%}")
            dml = m.loc[v].loc[["insert", "update", "delete"], "n"]
            out.append({"section": "§4.3", "claim": f"INSERT is the largest DML type ({v})", "paper": "insert",
                        "replication": f"{dml.idxmax()} ({dml.max() / m.loc[v, 'n'].sum():.0%} of queries)",
                        "verdict": "confirmed" if dml.idxmax() == "insert" else "not", "note": ""})
    ins = _csv("insert_select")
    if ins is not None:
        for r in ins.itertuples():
            out.append({"section": "§4.3", "claim": f"Most INSERTs are INSERT ... SELECT ({r.variant})",
                        "paper": "> 50%", "replication": f"{r.share_reading:.0%}",
                        "verdict": "confirmed" if r.share_reading > .5 else "not",
                        "note": "proxy: the INSERT reads a table"})
    sk = _csv("skew")
    if sk is not None:
        for r in sk.itertuples():
            # same direction, stronger: the top queries take even more than the paper says
            add("§2.1", f"CPU share of the top 0.1 % of queries ({r.variant})", .25, r.top01_cpu_share, .03, "{:.0%}",
                f"CPU proxy = execution time x nodes; top {r.top_cpu_query_share:.2%} of queries",
                force="close" if r.top01_cpu_share > .25 else None)

    ex = _csv("execution")
    if ex is not None:
        e = ex.set_index("workload")
        paper_lo = {"baseline_round_robin": 1.00, "generation": 1.10, "matching": 2.12}
        paper_hi = {"baseline_round_robin": 1.08, "generation": 2.00, "matching": 2.98}
        for w in paper_lo:
            if w in e.index:
                s = e.loc[w, "speedup"]
                lo, hi = paper_lo[w], paper_hi[w]
                out.append({"section": "§6 (Fig 8)", "claim": f"{w}: caching speedup",
                            "paper": f"{lo:.2f}-{hi:.2f}x", "replication": f"{s:.2f}x (DuckDB, simulated result cache)",
                            # above the range = same direction, stronger (DuckDB has no per-query overhead)
                            "verdict": "confirmed" if lo - .05 <= s <= hi + .05 else "close" if s > hi else "not",
                            "note": ""})
        if {"matching", "baseline_round_robin"} <= set(e.index):
            m, b = e.loc["matching", "speedup"], e.loc["baseline_round_robin", "speedup"]
            out.append({"section": "§6", "claim": "Caching helps matching, not the round-robin baseline",
                        "paper": "yes", "replication": f"{m:.2f}x vs {b:.2f}x",
                        "verdict": "confirmed" if m > 1.5 and b < 1.1 else "not", "note": ""})
    return out


def main() -> None:
    df = pd.DataFrame(rows())
    df.to_csv(R / "scorecard.csv", index=False)
    md = ["| § | Claim | Paper | Replication | Verdict |", "|---|---|---|---|---|"]
    md += [f"| {r.section} | {r.claim} | {r.paper} | {r.replication} | {r.verdict} |" for r in df.itertuples()]
    (R / "scorecard.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print(df.verdict.value_counts().to_dict())
    print("\n".join(md))


if __name__ == "__main__":
    main()
