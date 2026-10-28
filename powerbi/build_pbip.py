"""Builds the Power BI dashboard of the replication as a Power BI Project (.pbip).

    python powerbi/build_pbip.py

1. Reads results/*.csv and writes tidy tables to powerbi/data/ (one CSV per Power BI table).
2. Writes Redbench.SemanticModel/ (TMDL: tables, Power Query, measures) and Redbench.Report/
   (PBIR: one JSON per page and visual) next to Redbench.pbip.

Open Redbench.pbip in Power BI Desktop and press Refresh. After the results change, rerun this
script (it only rewrites data/ and the project files) and Refresh again.
"""
from __future__ import annotations

import json
import os
import shutil
import uuid
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
RESULTS = HERE.parent / "results"
DATA = HERE / "data"
NAME = "Redbench"
NS = uuid.UUID("6f1d1c52-1f0e-4b7e-9a51-6c0d2f3a9b10")  # stable ids: rebuilds don't churn git


def uid(key: str) -> str:
    return str(uuid.uuid5(NS, key))


# ---------------------------------------------------------------- data

SERIES = {"redset": "Redset (trace)", "matching": "Redbench matching",
          "generation": "Redbench generation", "baseline_round_robin": "Round-robin baseline"}
METRICS = ["qrr_dml", "qrr", "srr_dml", "srr"]
METRIC_LABEL = {"qrr_dml": "QRR (DML-aware)", "qrr": "QRR", "srr_dml": "SRR (DML-aware)", "srr": "SRR"}
PAPER_T4 = {"redset": (.72, .73, .86, .87), "generation": (.73, .79, .95, .98),
            "matching": (.97, .98, .99, .99), "baseline_round_robin": (.00, .74, .36, .99)}
SOURCE_ORDER = {"Paper": 1, "Replication": 2, "Reference": 3}
VERDICT_ORDER = {"confirmed": 1, "close": 2, "not": 3, "n/a": 4}
GROUPS = {"Table 4": "Repetition (Table 4)", "§5.2": "Paper cluster (§5.2)", "Table 5": "String filters (Table 5)",
          "§4.1": "Query mix (§4)", "§4.3": "Query mix (§4)", "§2.1": "Skew (§2.1)"}


def build_data() -> dict[str, pd.DataFrame]:
    r = lambda n: pd.read_csv(RESULTS / f"{n}.csv")
    t = {}

    sc = r("scorecard")
    sc.insert(0, "id", range(1, len(sc) + 1))
    sc["topic"] = sc["section"].map(GROUPS).fillna(sc["section"])
    sc["verdict_order"] = sc["verdict"].map(VERDICT_ORDER).fillna(9).astype(int)
    sc["note"] = sc["note"].fillna("")
    t["claims"] = sc

    # Redset row: the definition the scorecard uses (plot, full window); generated rows: generator.
    d = r("table4_definitions")
    t4 = r("table4").set_index("series")
    rows = []
    for s, label in SERIES.items():
        rep = d[(d.series == "redset") & (d.definition == "plot_full")].iloc[0] if s == "redset" else t4.loc[s]
        for m, p in zip(METRICS, PAPER_T4[s]):
            rows += [dict(series=label, series_order=list(SERIES).index(s) + 1, metric=METRIC_LABEL[m],
                          metric_order=METRICS.index(m) + 1, source=src, value=v)
                     for src, v in (("Paper", p), ("Replication", float(rep[m])))]
    t["repetition"] = pd.DataFrame(rows)

    defs = {"generator": "Generator stats (full)", "plot_full": "Plot code (full)", "plot_first1k": "Plot code (first 1k rows)"}
    rows = []
    for x in d[d.series.isin(SERIES)].itertuples():
        for m in METRICS:
            rows.append(dict(series=SERIES[x.series], definition=defs[x.definition],
                             definition_order=list(defs).index(x.definition) + 1,
                             metric=METRIC_LABEL[m], metric_order=METRICS.index(m) + 1, value=getattr(x, m)))
    t["definitions"] = pd.DataFrame(rows)

    mix = r("query_mix")
    mix = mix[["variant", "qtype", "n", "share_all"]].rename(columns={"share_all": "share"})
    paper = pd.DataFrame([dict(variant="Paper", qtype="select", n=None, share=.50),
                          dict(variant="Paper", qtype="insert", n=None, share=.20)])
    mix = pd.concat([paper, mix], ignore_index=True)
    mix["variant_order"] = mix["variant"].map({"Paper": 1, "provisioned": 2, "serverless": 3})
    order = mix[mix.variant == "provisioned"].sort_values("share", ascending=False)["qtype"].tolist()
    mix["qtype_order"] = mix["qtype"].map({q: i + 1 for i, q in enumerate(order)}).fillna(99).astype(int)
    t["query_mix"] = mix

    sk = r("skew")
    rows = [dict(label="Paper (Redset)", source="Paper", value=.25)]
    rows += [dict(label=f"Redset {v.variant}", source="Replication", value=v.top01_cpu_share) for v in sk.itertuples()]
    t["skew"] = pd.DataFrame(rows)

    sf = r("string_filters")
    sf = sf[sf.workload.isin(["matching", "generation", "baseline_round_robin"])]
    rows = [dict(label="Redbench matching", source="Paper", value=.67),
            dict(label="Redbench generation", source="Paper", value=.75),
            dict(label="Snowflake (Szlang et al.)", source="Reference", value=.58),
            dict(label="TPC-DS", source="Reference", value=.22)]
    rows += [dict(label=SERIES[x.workload], source="Replication", value=x.share_string)
             for x in sf[sf.counting == "instances"].itertuples()]
    t["strings"] = pd.DataFrame(rows)

    cl = r("cluster_repetition")
    cl = cl[(cl.selects >= 1000) & cl.gen_qrr_dml.notna()].copy()
    cl["cluster"] = cl.variant.str[0].str.upper() + " " + cl.instance_id.astype(str) + "/" + cl.database_id.astype(str)
    paper = (cl.variant == "provisioned") & (cl.instance_id == 186) & (cl.database_id == 8)
    cl["highlight"] = paper.map({True: "Paper cluster 186/8", False: "Other clusters"})
    cl = cl.rename(columns={f"gen_{m}": m for m in METRICS} | {"plot1k_qrr_dml": "qrr_dml_first1k"})
    cl[["queries", "selects"]] = cl[["queries", "selects"]].fillna(0).astype("int64")
    t["clusters"] = cl[["cluster", "variant", "highlight", "queries", "selects", *METRICS, "qrr_dml_first1k"]]

    for df in t.values():
        if "source" in df:
            df["source_order"] = df["source"].map(SOURCE_ORDER)
    return t


# ---------------------------------------------------------------- semantic model (TMDL)

M_TYPE = {"string": "type text", "double": "type number", "int64": "Int64.Type"}

# Measures per table: name -> (DAX, format string)
MEASURES = {
    "claims": {"Claims": ("COUNTROWS(claims)", "0"),
               "Confirmed": ('CALCULATE(COUNTROWS(claims), claims[verdict] = "confirmed") + 0', "0"),
               "Close": ('CALCULATE(COUNTROWS(claims), claims[verdict] = "close") + 0', "0"),
               "Not confirmed": ('CALCULATE(COUNTROWS(claims), claims[verdict] = "not") + 0', "0"),
               "Confirmed share": ("DIVIDE([Confirmed], [Claims])", "0%")},
    "repetition": {"Rate": ("SUM(repetition[value])", "0.00")},
    "definitions": {"Definition rate": ("SUM(definitions[value])", "0.00")},
    "query_mix": {"Share of queries": ("SUM(query_mix[share])", "0%")},
    "skew": {"CPU share of top 0.1%": ("SUM(skew[value])", "0%")},
    "strings": {"String filter share": ("SUM(strings[value])", "0%")},
    # CLUSTERS is a reserved word in DAX: the table name must be quoted.
    "clusters": {"Clusters": ("COUNTROWS('clusters')", "0"),
                 "Avg QRR (DML-aware)": ("AVERAGE('clusters'[qrr_dml])", "0.00"),
                 "Avg SRR (DML-aware)": ("AVERAGE('clusters'[srr_dml])", "0.00"),
                 "Total selects": ("SUM('clusters'[selects])", "#,0")},
}
SORT_BY = {"verdict": "verdict_order", "source": "source_order", "series": "series_order",
           "metric": "metric_order", "definition": "definition_order", "variant": "variant_order",
           "qtype": "qtype_order"}


def dtype(s: pd.Series) -> str:
    if pd.api.types.is_integer_dtype(s):
        return "int64"
    if pd.api.types.is_float_dtype(s):
        return "double"
    return "string"


def table_tmdl(name: str, df: pd.DataFrame) -> str:
    types = {c: dtype(df[c]) for c in df.columns}
    out = [f"table {name}", f"\tlineageTag: {uid('t/' + name)}", ""]
    for m, (dax, fmt) in MEASURES.get(name, {}).items():
        mname = f"'{m}'" if not m.isidentifier() else m
        out += [f"\tmeasure {mname} = {dax}", f"\t\tformatString: {fmt}",
                f"\t\tlineageTag: {uid(f'm/{name}/{m}')}", ""]
    for c, ty in types.items():
        out += [f"\tcolumn {c}", f"\t\tdataType: {ty}", f"\t\tlineageTag: {uid(f'c/{name}/{c}')}",
                f"\t\tsummarizeBy: none", f"\t\tsourceColumn: {c}"]
        if ty == "double":
            out.append("\t\tformatString: 0.00")
        elif ty == "int64" and c != "id" and not c.endswith("_order"):
            out.append("\t\tformatString: #,0")
        if c in SORT_BY and SORT_BY[c] in types:
            out.append(f"\t\tsortByColumn: {SORT_BY[c]}")
        if c.endswith("_order") or c == "id":
            out.append("\t\tisHidden")
        out.append("")
    cols = ", ".join(f'{{"{c}", {M_TYPE[ty]}}}' for c, ty in types.items())
    m = [
        "let",
        f'    Source = Csv.Document(File.Contents(DataFolder & "{name}.csv"), [Delimiter = ",", Encoding = 65001, QuoteStyle = QuoteStyle.Csv]),',
        "    Headers = Table.PromoteHeaders(Source, [PromoteAllScalars = true]),",
        f'    Typed = Table.TransformColumnTypes(Headers, {{{cols}}}, "en-US")',
        "in",
        "    Typed",
    ]
    out += [f"\tpartition {name} = m", "\t\tmode: import", "\t\tsource ="]
    out += ["\t\t\t\t" + line for line in m]
    out += ["", "\tannotation PBI_ResultType = Table", ""]
    return "\n".join(out)


def write_model(tables: dict[str, pd.DataFrame]) -> None:
    sm = HERE / f"{NAME}.SemanticModel"
    shutil.rmtree(sm, ignore_errors=True)
    (sm / "definition" / "tables").mkdir(parents=True)
    _json(sm / "definition.pbism", {"version": "4.2", "settings": {}})
    _json(sm / ".platform", _platform("SemanticModel"))
    (sm / "definition" / "database.tmdl").write_text("database\n\tcompatibilityLevel: 1600\n\n", encoding="utf-8")
    order = ["DataFolder", *tables]
    model = ["model Model", "\tculture: en-US", "\tdefaultPowerBIDataSourceVersion: powerBI_V3",
             "\tsourceQueryCulture: en-US", "\tdataAccessOptions", "\t\tlegacyRedirects",
             "\t\treturnErrorValuesAsNull", "",
             f"annotation PBI_QueryOrder = {json.dumps(order)}", ""]
    model += [f"ref table {t}" for t in tables]
    (sm / "definition" / "model.tmdl").write_text("\n".join(model) + "\n", encoding="utf-8")
    folder = str(DATA) + "\\"
    expr = [f'expression DataFolder = "{folder}" meta [IsParameterQuery = true, Type = "Text", IsParameterQueryRequired = true]',
            f"\tlineageTag: {uid('e/DataFolder')}", "", "\tannotation PBI_ResultType = Text", ""]
    (sm / "definition" / "expressions.tmdl").write_text("\n".join(expr), encoding="utf-8")
    for name, df in tables.items():
        (sm / "definition" / "tables" / f"{name}.tmdl").write_text(table_tmdl(name, df), encoding="utf-8")


# ---------------------------------------------------------------- report (PBIR)

SCHEMA = "https://developer.microsoft.com/json-schemas/fabric/item/report/definition"
COLORS = {"Paper": "#6B7785", "Replication": "#1F6FB2", "Reference": "#E08A2E",
          "confirmed": "#2E7D5B", "close": "#D9A21B", "not": "#C2453D", "n/a": "#9AA1AA"}


def lit(v) -> dict:
    if isinstance(v, bool):
        s = "true" if v else "false"
    elif isinstance(v, (int, float)):
        s = f"{v}D"
    else:
        s = "'" + str(v).replace("'", "''") + "'"
    return {"expr": {"Literal": {"Value": s}}}


def col(table: str, column: str) -> dict:
    return {"Column": {"Expression": {"SourceRef": {"Entity": table}}, "Property": column}}


def meas(table: str, measure: str) -> dict:
    return {"Measure": {"Expression": {"SourceRef": {"Entity": table}}, "Property": measure}}


def proj(field: dict) -> dict:
    kind = "Column" if "Column" in field else "Measure"
    t, p = field[kind]["Expression"]["SourceRef"]["Entity"], field[kind]["Property"]
    return {"field": field, "queryRef": f"{t}.{p}", "nativeQueryRef": p}


def title(text: str) -> dict:
    return {"title": [{"properties": {"show": lit(True), "text": lit(text)}}]}


def in_filter(table: str, column: str, values: list[str]) -> dict:
    return {"filters": [{
        "name": uid(f"f/{table}/{column}/{values}")[:20].replace("-", ""),
        "field": col(table, column), "type": "Categorical",
        "filter": {"Version": 2, "From": [{"Name": "t", "Entity": table, "Type": 0}],
                   "Where": [{"Condition": {"In": {
                       "Expressions": [{"Column": {"Expression": {"SourceRef": {"Source": "t"}}, "Property": column}}],
                       "Values": [[{"Literal": {"Value": f"'{v}'"}}] for v in values]}}}]},
        "howCreated": "User"}]}


def color_points(table: str, column: str, colors: dict) -> list:
    return [{"properties": {"fill": {"solid": {"color": lit(c)}}},
             "selector": {"data": [{"scopeId": {"Comparison": {
                 "ComparisonKind": 0, "Left": col(table, column), "Right": {"Literal": {"Value": f"'{v}'"}}}}}]}}
            for v, c in colors.items()]


class Page:
    def __init__(self, key: str, display: str):
        self.key, self.display, self.visuals = key, display, []

    def add(self, kind: str, x, y, w, h, roles=None, objects=None, container=None, sort=None, filters=None):
        name = f"{self.key}_{len(self.visuals) + 1:02d}"
        v = {"visualType": kind}
        if roles:
            v["query"] = {"queryState": {r: {"projections": [proj(f) for f in fs]} for r, fs in roles.items()}}
            if sort:
                v["query"]["sortDefinition"] = {"sort": [{"field": f, "direction": d} for f, d in sort],
                                                 "isDefaultSort": False}
        if objects:
            v["objects"] = objects
        if container:
            v["visualContainerObjects"] = container
        v["drillFilterOtherVisuals"] = True
        doc = {"$schema": f"{SCHEMA}/visualContainer/1.4.0/schema.json", "name": name,
               "position": {"x": x, "y": y, "z": len(self.visuals) * 1000, "height": h, "width": w,
                            "tabOrder": len(self.visuals) * 1000},
               "visual": v}
        if filters:
            doc["filterConfig"] = filters
        self.visuals.append(doc)

    def text(self, x, y, w, h, runs: list[tuple[str, dict]]):
        paragraphs = [{"textRuns": [{"value": t, "textStyle": s}]} for t, s in runs]
        self.add("textbox", x, y, w, h, objects={"general": [{"properties": {"paragraphs": paragraphs}}]})

    def header(self, title_text: str, subtitle: str):
        self.text(16, 8, 1248, 64, [(title_text, {"fontWeight": "bold", "fontSize": "20pt"}),
                                    (subtitle, {"fontSize": "11pt", "color": "#5B6470"})])


def no_category_label() -> dict:
    return {"categoryLabels": [{"properties": {"show": lit(False)}}]}


def legend_bottom() -> dict:
    return {"legend": [{"properties": {"show": lit(True), "position": lit("Bottom")}}]}


def labels(fmt_units=None) -> dict:
    return {"labels": [{"properties": {"show": lit(True)}}]}


def series_colors(table: str, column: str, values: list[str]) -> dict:
    return {"dataPoint": color_points(table, column, {v: COLORS[v] for v in values})}


def build_pages() -> list[Page]:
    pages = []

    p = Page("scorecard", "Scorecard")
    p.header("Redbench (VLDB 2026): does the paper hold up?",
             "Every number the paper states next to the value recomputed from the public Redset trace "
             "and the workloads the authors published.")
    for i, m in enumerate(["Claims", "Confirmed", "Close", "Not confirmed"]):
        p.add("card", 16 + i * 316, 84, 300, 110, roles={"Values": [meas("claims", m)]},
              objects=no_category_label(), container=title(m))
    p.add("donutChart", 16, 210, 380, 494,
          roles={"Category": [col("claims", "verdict")], "Y": [meas("claims", "Claims")]},
          objects={"dataPoint": color_points("claims", "verdict", {k: COLORS[k] for k in VERDICT_ORDER}),
                   **legend_bottom()},
          container=title("Verdicts"), sort=[(col("claims", "verdict"), "Ascending")])
    p.add("slicer", 412, 210, 852, 64, roles={"Values": [col("claims", "topic")]},
          objects={"data": [{"properties": {"mode": lit("Basic")}}],
                   "general": [{"properties": {"orientation": lit(1)}}]},
          container=title("Topic"))
    p.add("tableEx", 412, 284, 852, 420,
          roles={"Values": [col("claims", c) for c in ["section", "claim", "paper", "replication", "verdict", "note"]]},
          container=title("Claims"))
    pages.append(p)

    p = Page("repetition", "Repetition (Table 4)")
    p.header("Table 4: how often queries repeat",
             "QRR: share of selects identical to an earlier one. SRR: same set of tables read. "
             "DML-aware: only if no write touched those tables in between (a result cache could answer).")
    for i, s in enumerate(SERIES.values()):
        x, y = 16 + (i % 2) * 632, 84 + (i // 2) * 316
        p.add("clusteredColumnChart", x, y, 616, 300,
              roles={"Category": [col("repetition", "metric")], "Series": [col("repetition", "source")],
                     "Y": [meas("repetition", "Rate")]},
              objects={**series_colors("repetition", "source", ["Paper", "Replication"]), **legend_bottom(),
                       **labels(), "valueAxis": [{"properties": {"start": lit(0), "end": lit(1)}}]},
              container=title(s), filters=in_filter("repetition", "series", [s]),
              sort=[(col("repetition", "metric"), "Ascending")])
    pages.append(p)

    p = Page("definitions", "Metric definitions")
    p.header("Same metric, three implementations in the authors' code",
             "The generator's statistics and the plotting code count repeats differently, and the plot code "
             "stops after row 1,001 by default. On the paper's cluster that alone turns QRR 0.72 into 0.01.")
    for i, s in enumerate(["Redset (trace)", "Redbench generation"]):
        p.add("clusteredColumnChart", 16 + i * 632, 84, 616, 420,
              roles={"Category": [col("definitions", "metric")], "Series": [col("definitions", "definition")],
                     "Y": [meas("definitions", "Definition rate")]},
              objects={**legend_bottom(), **labels(),
                       "valueAxis": [{"properties": {"start": lit(0), "end": lit(1)}}]},
              container=title(s), filters=in_filter("definitions", "series", [s]),
              sort=[(col("definitions", "metric"), "Ascending")])
    p.add("pivotTable", 16, 520, 1248, 184,
          roles={"Rows": [col("definitions", "series"), col("definitions", "definition")],
                 "Columns": [col("definitions", "metric")], "Values": [meas("definitions", "Definition rate")]},
          container=title("All series"))
    pages.append(p)

    p = Page("fleet", "Fleet")
    p.header("What Redset looks like across the fleet",
             "Query mix over all 441 M queries (March-May 2024), CPU skew, and the share of filters on strings.")
    p.add("clusteredBarChart", 16, 84, 616, 620,
          roles={"Category": [col("query_mix", "qtype")], "Series": [col("query_mix", "variant")],
                 "Y": [meas("query_mix", "Share of queries")]},
          objects={**legend_bottom(), **labels(),
                   "dataPoint": color_points("query_mix", "variant",
                                             {"Paper": COLORS["Paper"], "provisioned": COLORS["Replication"],
                                              "serverless": COLORS["Reference"]})},
          container=title("Query types (share of all queries)"), sort=[(col("query_mix", "qtype"), "Ascending")])
    p.add("clusteredColumnChart", 648, 84, 616, 300,
          roles={"Category": [col("skew", "label")], "Series": [col("skew", "source")],
                 "Y": [meas("skew", "CPU share of top 0.1%")]},
          objects={**series_colors("skew", "source", ["Paper", "Replication"]), **legend_bottom(), **labels()},
          container=title("CPU time used by the top 0.1 % of queries (Redset has no CPU column: exec time x nodes)"))
    p.add("clusteredColumnChart", 648, 400, 616, 304,
          roles={"Category": [col("strings", "label")], "Series": [col("strings", "source")],
                 "Y": [meas("strings", "String filter share")]},
          objects={**series_colors("strings", "source", ["Paper", "Replication", "Reference"]),
                   **legend_bottom(), **labels()},
          container=title("Filters on string columns (Table 5)"))
    pages.append(p)

    p = Page("clusters", "Clusters")
    p.header("Is the paper's cluster typical?",
             "Repetition rates of every Redset database with at least 1,000 selects in May 2024 "
             "(generator definition). The paper's cluster 186/8 is highlighted.")
    for i, m in enumerate(["Clusters", "Avg QRR (DML-aware)", "Avg SRR (DML-aware)"]):
        p.add("card", 16 + i * 216, 84, 200, 110, roles={"Values": [meas("clusters", m)]},
              objects=no_category_label(), container=title(m))
    p.add("scatterChart", 16, 210, 632, 494,
          roles={"Category": [col("clusters", "cluster")], "Series": [col("clusters", "highlight")],
                 "X": [meas("clusters", "Avg SRR (DML-aware)")], "Y": [meas("clusters", "Avg QRR (DML-aware)")],
                 "Size": [meas("clusters", "Total selects")]},
          objects={**legend_bottom(),
                   "dataPoint": color_points("clusters", "highlight",
                                             {"Paper cluster 186/8": COLORS["not"], "Other clusters": COLORS["Replication"]})},
          container=title("QRR vs SRR per database (bubble size: selects)"))
    p.add("tableEx", 664, 84, 600, 620,
          roles={"Values": [col("clusters", c) for c in ["cluster", "selects", "qrr_dml", "qrr", "srr_dml", "srr", "qrr_dml_first1k"]]},
          container=title("Databases (qrr_dml_first1k: the plot code's default)"),
          sort=[(col("clusters", "selects"), "Descending")])
    pages.append(p)
    return pages


def write_report(pages: list[Page]) -> None:
    rp = HERE / f"{NAME}.Report"
    shutil.rmtree(rp, ignore_errors=True)
    d = rp / "definition"
    (d / "pages").mkdir(parents=True)
    _json(rp / ".platform", _platform("Report"))
    _json(rp / "definition.pbir", {"version": "4.0", "datasetReference": {"byPath": {"path": f"../{NAME}.SemanticModel"}}})
    _json(d / "version.json", {"$schema": f"{SCHEMA}/versionMetadata/1.0.0/schema.json", "version": "2.0.0"})
    _json(d / "report.json", {
        "$schema": f"{SCHEMA}/report/1.2.0/schema.json",
        "themeCollection": {"baseTheme": {"name": "CY24SU10", "reportVersionAtImport": "5.59", "type": "SharedResources"}},
        "layoutOptimization": "None",
        "resourcePackages": [{"name": "SharedResources", "type": "SharedResources",
                              "items": [{"name": "CY24SU10", "path": "BaseThemes/CY24SU10.json", "type": "BaseTheme"}]}],
    })
    theme = rp / "StaticResources" / "SharedResources" / "BaseThemes" / "CY24SU10.json"
    theme.parent.mkdir(parents=True)
    _json(theme, {"name": "CY24SU10",
                  "dataColors": ["#1F6FB2", "#E08A2E", "#6B7785", "#2E7D5B", "#C2453D", "#D9A21B", "#7B5EA7", "#3AA0A8"],
                  "background": "#FFFFFF", "foreground": "#1E2329", "tableAccent": "#1F6FB2"})
    _json(d / "pages" / "pages.json", {"$schema": f"{SCHEMA}/pagesMetadata/1.0.0/schema.json",
                                       "pageOrder": [p.key for p in pages],
                                       "activePageName": os.environ.get("PBI_ACTIVE_PAGE", pages[0].key)})
    for p in pages:
        pd_ = d / "pages" / p.key
        (pd_ / "visuals").mkdir(parents=True)
        _json(pd_ / "page.json", {"$schema": f"{SCHEMA}/page/1.3.0/schema.json", "name": p.key,
                                  "displayName": p.display, "displayOption": "FitToPage",
                                  "height": 720, "width": 1280})
        for v in p.visuals:
            (pd_ / "visuals" / v["name"]).mkdir()
            _json(pd_ / "visuals" / v["name"] / "visual.json", v)


def _platform(kind: str) -> dict:
    return {"$schema": "https://developer.microsoft.com/json-schemas/fabric/gitIntegration/platformProperties/2.0.0/schema.json",
            "metadata": {"type": kind, "displayName": NAME},
            "config": {"version": "2.0", "logicalId": uid("platform/" + kind)}}


def _json(path: Path, obj) -> None:
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main() -> None:
    tables = build_data()
    DATA.mkdir(exist_ok=True)
    for name, df in tables.items():
        df.to_csv(DATA / f"{name}.csv", index=False)
    write_model(tables)
    write_report(build_pages())
    _json(HERE / f"{NAME}.pbip", {
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/pbip/pbipProperties/1.0.0/schema.json",
        "version": "1.0", "artifacts": [{"report": {"path": f"{NAME}.Report"}}],
        "settings": {"enableAutoRecovery": True}})
    for name, df in tables.items():
        print(f"{name:12s} {len(df):5d} rows")
    print(f"wrote {HERE / (NAME + '.pbip')}")


if __name__ == "__main__":
    main()
