#!/usr/bin/env python3
"""pbipgen.py -- 纯 Python 生成 Power BI PBIP 工程（语义模型 + 报表页 + 视觉对象）。

不依赖 pbi-cli、不依赖 Windows、不需要连 Analysis Services。
生成的目录可以被 Power BI Desktop 直接打开，打开后点一次「立即刷新」即出图。

用法:
    python3 pbipgen.py spec.json [--out DIR]

spec 结构见 SPEC_EXAMPLE。
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
from pathlib import Path

# --- 常量：实测自 Power BI Desktop / pbi-cli v3.12.0 的编码表 -------------

# 聚合函数编号（PBIR Aggregation.Function）
AGG = {
    "sum": 0, "average": 1, "avg": 1, "distinctcount": 2, "distinct-count": 2,
    "min": 3, "max": 4, "count": 5, "median": 6,
    "standarddeviation": 7, "stdev": 7, "variance": 8, "var": 8,
}
AGG_LABEL = {
    0: ("Sum", "Sum of"), 1: ("Avg", "Average of"), 2: ("DistinctCount", "Distinct count of"),
    3: ("Min", "Min of"), 4: ("Max", "Max of"), 5: ("Count", "Count of"),
    6: ("Median", "Median of"), 7: ("StandardDeviation", "Standard deviation of"),
    8: ("Variance", "Variance of"),
}

# 视觉对象别名 -> PBIR visualType
VTYPE = {
    "bar": "barChart", "bar_chart": "barChart", "barchart": "barChart",
    "column": "columnChart", "column_chart": "columnChart", "columnchart": "columnChart",
    "clustered_column": "clusteredColumnChart", "clustered_bar": "clusteredBarChart",
    "stacked_bar": "stackedBarChart", "stacked_column": "stackedColumnChart",
    "line": "lineChart", "line_chart": "lineChart", "linechart": "lineChart",
    "area": "areaChart", "area_chart": "areaChart",
    "card": "card", "card_new": "cardVisual", "cardvisual": "cardVisual",
    "table": "tableEx", "tableex": "tableEx",
    "matrix": "pivotTable", "pivottable": "pivotTable", "pivot": "pivotTable",
    "donut": "donutChart", "donut_chart": "donutChart", "pie": "donutChart",
    "funnel": "funnelChart", "treemap": "treemap",
    "kpi": "kpi", "gauge": "gauge", "slicer": "slicer",
    "waterfall": "waterfallChart", "ribbon": "ribbonChart", "scatter": "scatterChart",
}

# 每种视觉对象的角色集合（缺一个 Desktop 就静默忽略，见坑 #2）
ROLES = {
    "barChart": ("Category", "Y", "Series"),
    "clusteredBarChart": ("Category", "Y", "Series"),
    "stackedBarChart": ("Category", "Y", "Series"),
    "columnChart": ("Category", "Y", "Series"),
    "clusteredColumnChart": ("Category", "Y", "Series"),
    "lineChart": ("Category", "Y", "Series"),
    "areaChart": ("Category", "Y", "Series"),
    "ribbonChart": ("Category", "Y", "Series"),
    "card": ("Values",),
    "cardVisual": ("Values",),
    "kpi": ("Indicator", "TrendLine", "Goal"),
    "gauge": ("Y", "MinValue", "MaxValue", "TargetValue"),
    "tableEx": ("Values",),
    "pivotTable": ("Rows", "Columns", "Values"),
    "donutChart": ("Category", "Y"),
    "funnelChart": ("Category", "Y"),
    "treemap": ("Category", "Values"),
    "waterfallChart": ("Category", "Y"),
    "scatterChart": ("X", "Y", "Series"),
    "slicer": ("Values",),
}

# 允许聚合的角色（类别/序列轴绝不能聚合，否则轴上会出现 Sum of 年份）
AGG_ROLES = {"Y", "Values", "X", "Indicator", "TargetValue",
             "MinValue", "MaxValue", "Tooltips", "TrendLine"}

# spec 里角色键 -> PBIR 角色名（视觉对象类型缺省时的通用映射）
ROLE_KEY = {
    "category": "Category", "y_field": "Y", "value": "Y", "measure": "Y",
    "series": "Series", "legend": "Series", "values": "Values", "field": "Values",
    "rows": "Rows", "columns": "Columns", "indicator": "Indicator",
    "trend": "TrendLine", "goal": "Goal", "x_field": "X",
    "target": "TargetValue", "min": "MinValue", "max": "MaxValue",
}

SCHEMA_VISUAL = ("https://developer.microsoft.com/json-schemas/fabric/item/report/"
                 "definition/visualContainer/2.7.0/schema.json")
SCHEMA_PAGE = ("https://developer.microsoft.com/json-schemas/fabric/item/report/"
               "definition/page/2.1.0/schema.json")
SCHEMA_PAGES = ("https://developer.microsoft.com/json-schemas/fabric/item/report/"
                "definition/pagesMetadata/1.0.0/schema.json")
SCHEMA_REPORT = ("https://developer.microsoft.com/json-schemas/fabric/item/report/"
                 "definition/report/1.2.0/schema.json")
SCHEMA_VERSION = ("https://developer.microsoft.com/json-schemas/fabric/item/report/"
                  "definition/versionMetadata/1.0.0/schema.json")
SCHEMA_PLATFORM = ("https://developer.microsoft.com/json-schemas/fabric/gitIntegration/"
                   "platformProperties/2.0.0/schema.json")

# TMDL dataType（不是 M 的 Int64.Type）
TMDL_TYPE = {"int64": "int64", "int": "int64", "double": "double", "decimal": "decimal",
             "number": "double", "text": "string", "string": "string",
             "date": "dateTime", "datetime": "dateTime", "bool": "boolean", "boolean": "boolean"}
M_TYPE = {"int64": "Int64.Type", "double": "type number", "decimal": "Currency.Type",
          "string": "type text", "dateTime": "type date", "boolean": "type logical"}


def w(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = obj if isinstance(obj, str) else json.dumps(obj, ensure_ascii=False, indent=2)
    path.write_text(text + ("" if text.endswith("\n") else "\n"), encoding="utf-8")


def tag() -> str:
    return str(uuid.uuid4())


# --- TMDL ----------------------------------------------------------------

def tmdl_table(spec: dict) -> str:
    t = spec["table"]
    csv_path = spec["csv"]
    cols = spec["columns"]
    lines = [f"table {t}", f"\tlineageTag: {tag()}", ""]

    for m in spec.get("measures", []):
        dax = m["dax"]
        if "\n" in dax:  # 多行 DAX 与 Desktop 保存的格式一致：= 后换行，每行 3 tab
            lines.append(f"\tmeasure {m['name']} =")
            if not dax.startswith("\t"):
                dax = "\t\t\t" + dax
            lines.append(dax)
        else:
            lines.append(f"\tmeasure {m['name']} = {dax}")
        if m.get("format"):
            lines.append(f"\t\tformatString: {m['format']}")
        if m.get("displayFolder"):
            lines.append(f"\t\tdisplayFolder: {m['displayFolder']}")
        lines.append(f"\t\tlineageTag: {tag()}")
        lines.append("")

    for c in cols:
        dt = TMDL_TYPE[c.get("type", "text").lower()]
        lines.append(f"\tcolumn {c['name']}")
        lines.append(f"\t\tdataType: {dt}")
        if c.get("format"):
            lines.append(f"\t\tformatString: {c['format']}")
        lines.append(f"\t\tsummarizeBy: {c.get('summarize', 'sum' if dt in ('int64', 'double', 'decimal') else 'none')}")
        lines.append(f"\t\tsourceColumn: {c['name']}")
        lines.append(f"\t\tlineageTag: {tag()}")
        lines.append("")

    # partition：显式 TransformColumnTypes，杜绝数值列退化成 String（坑 #3）
    pairs = ", ".join(f'{{"{c["name"]}", {M_TYPE[TMDL_TYPE[c.get("type", "text").lower()]]}}}' for c in cols)
    n = len(cols)
    body = [
        "\t\t\t\tlet",
        f'\t\t\t\t    Source = Csv.Document(File.Contents("{csv_path}"),'
        f'[Delimiter=",", Columns={n}, Encoding=65001, QuoteStyle=QuoteStyle.Csv]),',
        "\t\t\t\t    Promoted = Table.PromoteHeaders(Source, [PromoteAllScalars=true]),",
        f"\t\t\t\t    Typed = Table.TransformColumnTypes(Promoted, {{{pairs}}})",
        "\t\t\t\tin",
        "\t\t\t\t    Typed",
    ]
    lines.append(f"\tpartition {t} = m")
    lines.append("\t\tmode: import")
    lines.append("\t\tsource =")
    lines.extend(body)
    lines.append("")
    lines.append("\tannotation PBI_ResultType = Table")
    return "\n".join(lines) + "\n"


# --- PBIR visual ----------------------------------------------------------

def parse_ref(ref: str) -> tuple[str, str]:
    """'Fin[营业收入]' -> ('Fin', '营业收入')"""
    tb, _, col = ref.partition("[")
    return tb.strip(), col.rstrip("]").strip()


def make_projection(spec: dict, ref: str, agg: str | None, allow_agg: bool = True) -> dict:
    table, name = parse_ref(ref)
    is_measure = name in {m["name"] for m in spec.get("measures", [])}
    col_types = {c["name"]: TMDL_TYPE[c.get("type", "text").lower()] for c in spec["columns"]}

    if is_measure:
        return {"field": {"Measure": {"Expression": {"SourceRef": {"Entity": table}}, "Property": name}},
                "queryRef": f"{table}.{name}", "nativeQueryRef": name}

    base = {"Column": {"Expression": {"SourceRef": {"Entity": table}}, "Property": name}}
    fn = None
    if agg and agg.lower() not in ("none", ""):
        if not allow_agg:
            raise SystemExit(f"角色不支持聚合，但给了 agg={agg}：{ref}")
        fn = AGG.get(agg.lower())
        if fn is None:
            raise SystemExit(f"未知聚合 '{agg}'（{ref}）")
    elif allow_agg and col_types.get(name) in ("int64", "double", "decimal"):
        fn = AGG["sum"]  # Desktop 对数值列的隐式聚合

    if fn is None:
        return {"field": base, "queryRef": f"{table}.{name}", "nativeQueryRef": name, "active": True}

    prefix, label = AGG_LABEL[fn]
    return {"field": {"Aggregation": {"Expression": base, "Function": fn}},
            "queryRef": f"{prefix}({table}.{name})",
            "nativeQueryRef": f"{label} {name}"}


def tmdl_column_index(spec: dict) -> dict:
    idx = {}
    for c in spec["columns"]:
        idx[(spec["table"], c["name"])] = "column"
    for m in spec.get("measures", []):
        idx[(spec["table"], m["name"])] = "measure"
    return idx


def visual_json(spec: dict, v: dict, z: int) -> dict:
    vtype = VTYPE.get(str(v["type"]).lower().replace(" ", "_"), v["type"])
    if vtype not in ROLES:
        raise SystemExit(f"未支持的视觉对象类型: {v['type']} -> {vtype}")

    query_state: dict = {}
    idx = tmdl_column_index(spec)
    for key, role in ROLE_KEY.items():
        val = v.get(key)
        if not val:
            continue
        if role not in ROLES[vtype]:
            # 角色名错了 Desktop 会静默丢弃，这里直接拦住（坑 #2 的根治办法）
            raise SystemExit(
                f"视觉对象 '{v['name']}'（{vtype}）没有 '{role}' 角色，请改用 {ROLES[vtype]}")
        refs = val if isinstance(val, list) else [val]
        projections = []
        for r in refs:
            tb, name = parse_ref(r)
            if (tb, name) not in idx:
                raise SystemExit(f"字段不存在: {r}（不在表 {spec['table']} 的 TMDL 里）")
            allow = role in AGG_ROLES
            projections.append(make_projection(spec, r, v.get("agg") if allow else None, allow))
        query_state[role] = {"projections": projections}

    if not query_state:
        raise SystemExit(f"视觉对象 '{v['name']}' 没有任何字段绑定")

    return {
        "$schema": SCHEMA_VISUAL,
        "name": v["name"],
        "position": {
            "x": float(v.get("x", 0)), "y": float(v.get("y", 0)), "z": z,
            "height": float(v.get("h", 200)), "width": float(v.get("w", 400)),
            "tabOrder": z,
        },
        "visual": {
            "visualType": vtype,
            "query": {"queryState": query_state},
            "drillFilterOtherVisuals": True,
        },
    }


# --- 工程骨架 -------------------------------------------------------------

def build(spec: dict, out: Path) -> Path:
    name = spec["name"]
    out.mkdir(parents=True, exist_ok=True)
    rep = out / f"{name}.Report"
    sem = out / f"{name}.SemanticModel"

    w(out / f"{name}.pbip", {"version": "1.0", "artifacts": [{"report": {"path": f"{name}.Report"}}]})
    w(rep / ".platform", {"$schema": SCHEMA_PLATFORM,
                          "metadata": {"type": "Report", "displayName": name},
                          "config": {"version": "2.0", "logicalId": str(uuid.uuid4())}})
    w(rep / "definition.pbir", {"version": "4.0",
                                "datasetReference": {"byPath": {"path": f"../{name}.SemanticModel"}}})
    w(rep / "definition" / "report.json", {
        "$schema": SCHEMA_REPORT,
        "themeCollection": {"baseTheme": {"name": "CY24SU06",
                                          "reportVersionAtImport": "5.55",
                                          "type": "SharedResources"}},
        "layoutOptimization": "None",
        "settings": {"useStylableVisualContainerHeader": True,
                     "defaultDrillFilterOtherVisuals": True,
                     "allowChangeFilterTypes": True,
                     "useEnhancedTooltips": True,
                     "useDefaultAggregateDisplayName": True},
    })
    w(rep / "definition" / "version.json", {"$schema": SCHEMA_VERSION, "version": "2.0.0"})

    w(sem / ".platform", {"$schema": SCHEMA_PLATFORM,
                          "metadata": {"type": "SemanticModel", "displayName": name},
                          "config": {"version": "2.0", "logicalId": str(uuid.uuid4())}})
    w(sem / "definition.pbism", {"version": "4.1", "settings": {}})
    w(sem / "definition" / "model.tmdl",
      f"model Model\n\tculture: {spec.get('culture', 'en-US')}\n"
      "\tdefaultPowerBIDataSourceVersion: powerBI_V3\n")
    w(sem / "definition" / "tables" / f"{spec['table']}.tmdl", tmdl_table(spec))

    page = spec.get("page", {})
    pname = page.get("name", "p1")
    # pages.json 必须给出 pageOrder + activePageName，否则 Desktop 拒绝加载（坑 #19）
    w(rep / "definition" / "pages" / "pages.json", {
        "$schema": SCHEMA_PAGES, "pageOrder": [pname], "activePageName": pname})
    w(rep / "definition" / "pages" / pname / "page.json", {
        "$schema": SCHEMA_PAGE, "name": pname,
        "displayName": page.get("display", "Page 1"),
        "displayOption": "FitToPage",
        "height": page.get("height", 720), "width": page.get("width", 1280),
    })

    for z, v in enumerate(spec.get("visuals", [])):
        w(rep / "definition" / "pages" / pname / "visuals" / v["name"] / "visual.json",
          visual_json(spec, v, z))
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("spec")
    ap.add_argument("--out")
    a = ap.parse_args()
    spec_path = Path(a.spec).resolve()
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    if not os.path.isabs(spec["csv"]):
        # 相对路径按 spec 所在目录解析：TMDL 里必须写成绝对路径，Desktop 才找得到
        spec["csv"] = str((spec_path.parent / spec["csv"]).resolve())
    out = Path(a.out or spec.get("out") or spec["name"])
    build(spec, out)
    print(f"OK {out.resolve()}")


if __name__ == "__main__":
    main()
