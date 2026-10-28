"""Figures for README.md, drawn from results/*.csv only."""
from __future__ import annotations

import numpy as np
import pandas as pd
from matplotlib.ticker import PercentFormatter

from charts import BASELINE, INK, INK_2, MUTED, PALETTE, plt, save, style
from redset import ROOT

R, F = ROOT / "results", ROOT / "figures"
SERIES = [("redset", "Redset 186/8"), ("generation", "Redbench generation"),
          ("matching", "Redbench matching"), ("baseline_round_robin", "Round-robin baseline")]
PAPER4 = {"redset": (.72, .73, .86, .87), "generation": (.73, .79, .95, .98),
          "matching": (.97, .98, .99, .99), "baseline_round_robin": (.00, .74, .36, .99)}
METRICS = ["qrr_dml", "qrr", "srr_dml", "srr"]
LABELS = ["Exact repeat,\ncache still valid", "Exact repeat", "Same tables,\ncache still valid", "Same tables"]


def table4() -> None:
    t = pd.read_csv(R / "table4.csv").set_index("series")
    d = pd.read_csv(R / "table4_definitions.csv").set_index(["series", "definition"])
    t.loc["redset"] = d.loc[("redset", "plot_full"), METRICS]
    fig, ax = plt.subplots(figsize=(9.5, 4.6))
    x = np.arange(len(METRICS))
    w = 0.2
    for k, ((s, label), c) in enumerate(zip(SERIES, PALETTE)):
        xs = x + (k - 1.5) * w
        ax.bar(xs, t.loc[s, METRICS], width=w - 0.03, color=c, label=label, zorder=2)
        ax.scatter(xs, PAPER4[s], marker="_", s=180, color=INK, linewidths=2, zorder=3,
                   label="Paper (Table 4)" if k == 0 else None)
    ax.set_xticks(x, LABELS)
    ax.set_ylim(0, 1.05)
    ax.yaxis.set_major_formatter(PercentFormatter(1, decimals=0))
    ax.set_ylabel("Selects that repeat")
    ax.grid(axis="x", visible=False)
    ax.legend(ncol=5, loc="upper left", bbox_to_anchor=(0, -0.16), fontsize=9)
    ax.set_title("Table 4 reproduces from the published workloads")
    save(fig, F / "table4.png", "Redset (provisioned 186, db 8, May 2024); Redbench workloads on OSF (fgny3)",
         "Bars: recomputed. Black ticks: the paper's values.")


def fleet() -> None:
    c = pd.read_csv(R / "cluster_repetition.csv")
    c = c[c.selects >= 1000]
    if "error" in c:
        c = c[c.error.isna()]
    # Three clusters hold 50 databases each: one value per cluster (select-weighted) instead.
    k = (c.assign(w=c.gen_qrr_dml * c.selects).groupby(["variant", "instance_id"])
           .agg(w=("w", "sum"), selects=("selects", "sum")).reset_index())
    k["qrr_dml"] = k.w / k.selects
    fig, ax = plt.subplots(figsize=(8, 4.2))
    bins = np.linspace(0, 1, 21)
    ax.hist([k[k.variant == v].qrr_dml for v in ("provisioned", "serverless")], bins=bins, stacked=True,
            color=[PALETTE[0], PALETTE[1]], rwidth=0.9, zorder=2,
            label=[f"{v} ({(k.variant == v).sum()} clusters)" for v in ("provisioned", "serverless")])
    me = c[(c.instance_id == 186) & (c.database_id == 8) & (c.variant == "provisioned")].gen_qrr_dml
    if len(me):
        pct = (k.qrr_dml < me.iloc[0]).mean()
        ax.axvline(me.iloc[0], color=INK, lw=1.5, zorder=3)
        ax.annotate(f"paper's cluster 186/8\n(more repetitive than {pct:.0%})", (me.iloc[0], ax.get_ylim()[1] * 0.9),
                    xytext=(-6, 0), textcoords="offset points", ha="right", va="top", color=INK_2, fontsize=9)
    ax.xaxis.set_major_formatter(PercentFormatter(1, decimals=0))
    ax.set_xlabel("Selects a DML-invalidated result cache could answer (QRR_DML)")
    ax.set_ylabel("Clusters")
    ax.legend(loc="upper left")
    ax.set_title("The paper's cluster is a typical one")
    save(fig, F / "fleet_qrr.png", "Redset, May 2024, databases with at least 1,000 selects, grouped by cluster",
         "QRR_DML per cluster (select-weighted over its databases), whole month")

    fig, ax = plt.subplots(figsize=(5.6, 5))
    ax.plot([0, 1], [0, 1], color=BASELINE, lw=1, zorder=1)
    ax.scatter(c.gen_qrr_dml, c.plot1k_qrr_dml, s=16, color=PALETTE[0], alpha=0.7, zorder=2,
               edgecolors="none")
    ax.set_xlim(-0.02, 1.02), ax.set_ylim(-0.02, 1.02)
    for a in (ax.xaxis, ax.yaxis):
        a.set_major_formatter(PercentFormatter(1, decimals=0))
    ax.set_xlabel("QRR_DML, whole month")
    ax.set_ylabel("QRR_DML, first 1,002 queries (plot default)")
    ax.set_title("The first 1,000 queries are not the month")
    save(fig, F / "first1k.png", "Redset, May 2024, every database with at least 1,000 selects",
         "One dot per database; the diagonal is agreement")


def query_mix() -> None:
    m = pd.read_csv(R / "query_mix.csv")
    types = ["select", "insert", "delete", "update", "copy", "analyze", "ctas", "other"]
    fig, ax = plt.subplots(figsize=(8.5, 4.2))
    y = np.arange(len(types))
    for k, (v, col) in enumerate((("provisioned", PALETTE[0]), ("serverless", PALETTE[1]))):
        s = m[m.variant == v].set_index("qtype").share_all.reindex(types).fillna(0)
        ax.barh(y + (k - 0.5) * 0.38, s, height=0.34, color=col, label=v, zorder=2)
    ax.axvline(0.5, color=INK, lw=1.2, ls="--", zorder=3)
    ax.annotate("paper: about 50 % selects", (0.5, -0.6), xytext=(4, 0), textcoords="offset points",
                color=INK_2, fontsize=9, va="center")
    ax.set_yticks(y, types)
    ax.invert_yaxis()
    ax.xaxis.set_major_formatter(PercentFormatter(1, decimals=0))
    ax.grid(axis="y", visible=False)
    ax.legend(loc="lower right")
    ax.set_title("Selects are under a third of Redset's queries")
    save(fig, F / "query_mix.png", "Redset, March-May 2024, non-aborted queries; cache hits counted as selects",
         "Share of queries by type")


def execution() -> None:
    p = R / "execution.csv"
    if not p.exists():
        return
    e = pd.read_csv(p).set_index("workload")
    paper = {"baseline_round_robin": (1.00, 1.08), "generation": (1.10, 2.00), "matching": (2.12, 2.98)}
    names = [s for s, _ in SERIES[1:] if s in e.index]
    fig, ax = plt.subplots(figsize=(8, 3.2))
    y = np.arange(len(names))
    for k, n in enumerate(names):
        lo, hi = paper[n]
        ax.plot([lo, hi], [k, k], color=INK, lw=6, solid_capstyle="butt", zorder=2,
                label="Paper, range over 4 commercial systems" if k == 0 else None)
        ax.annotate(f"paper {lo:.2f}-{hi:.2f}x", (lo, k), xytext=(0, -15), textcoords="offset points",
                    ha="left", va="center", color=INK_2, fontsize=9)
        s = e.loc[n, "speedup"]
        ax.scatter([s], [k], s=90, color=PALETTE[0], edgecolors="white", linewidths=2, zorder=3,
                   label="DuckDB + simulated result cache" if k == 0 else None)
        ax.annotate(f"DuckDB {s:.2f}x", (s, k), xytext=(0, 15), textcoords="offset points",
                    ha="center" if s > 1.5 else "left", va="center", color=INK, fontsize=10)
    ax.set_xscale("log")
    ax.set_xticks([1, 2, 5, 10, 20], ["1x", "2x", "5x", "10x", "20x"])
    ax.minorticks_off()
    ax.set_xlim(0.9, max(30, e.speedup.max() * 1.6))
    ax.set_ylim(len(names) - 0.4, -0.6)
    ax.set_yticks(y, [dict(SERIES)[n] for n in names])
    ax.set_xlabel("Speedup from caching (runtime without / with, log scale)")
    ax.grid(axis="y", visible=False)
    ax.legend(loc="lower right", fontsize=9)
    ax.set_title("Caching pays off only on workloads that repeat")
    save(fig, F / "execution.png", "Published Redbench workloads run on DuckDB 1.5.6 over IMDb",
         "Each distinct statement timed once after a warm-up; cache simulated in arrival order")


if __name__ == "__main__":
    style()
    table4()
    query_mix()
    if (R / "cluster_repetition.csv").exists():
        fleet()
    execution()
