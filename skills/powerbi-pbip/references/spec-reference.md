# spec 全字段参考

生成器：`scripts/pbipgen.py`（纯标准库，Python 3.10+）。`python3 scripts/pbipgen.py <spec.json>`，
成功打印 `OK <输出目录绝对路径>`，任何硬约束不满足则向 stderr 打中文原因并 `SystemExit(1)`。

## 顶层字段

| 键 | 必填 | 类型 | 说明 |
|---|---|---|---|
| `name` | 是 | str | 项目名。产出 `<name>.pbip` / `<name>.Report/` / `<name>.SemanticModel/` |
| `out` | 是 | str | 输出目录，不存在则创建。相对路径相对**当前工作目录** |
| `table` | 是 | str | 唯一表的表名（TMDL `table <名>`） |
| `csv` | 是 | str | CSV 路径。**相对路径相对 spec 文件所在目录**解析，写入 TMDL 时转绝对路径 |
| `culture` | 否 | str | 模型 culture，默认 `en-US`；中文报表写 `zh-CN` |
| `columns` | 是 | list | 列定义，顺序即 CSV 列序 |
| `measures` | 否 | list | 度量值 |
| `page` | 是 | obj | 单页定义。`{name, display, width, height}` |
| `visuals` | 是 | list | 视觉对象，`z` 与 `tabOrder` 按数组顺序自增 |

`page` 默认画布 `1280 × 720`（16:9）。一页一套 spec；多页就生成多个 spec 指向同一个表（各自独立 PBIP），
或在生成后用 `pbir` 手改 `pages.json` 的 `pageOrder`。

## columns

| 键 | 必填 | 取值 | 说明 |
|---|---|---|---|
| `name` | 是 | str | 列名，须与 CSV 表头**完全一致** |
| `type` | 是 | `int64` \| `double` \| `string` \| `dateTime` | 映射到 M 的 `Int64.Type` / `type number` / `type text` / `type datetime`、TMDL 的 `dataType` |
| `format` | 否 | str | `formatString`，整数用 `0`、金额 `#,##0.00`、比率 `0.0%` |
| `summarize` | 否 | `none` \| `sum` \| `average` \| `count` \| `min` \| `max` | 默认 `none`。**维度列（年份、月份、类别）必须 `none`**，否则 Desktop 默认给 `Sum` |
| `hidden` | 否 | bool | 写 `isHidden` |

类型被显式钉在 M 里：partition 一定是
`Csv.Document(File.Contents("<abs csv>"),[Delimiter=",",Columns=N,Encoding=65001,QuoteStyle=QuoteStyle.Csv])`
→ `Table.PromoteHeaders` → `Table.TransformColumnTypes`。
只靠 TMDL 的 `dataType: double` **压不住** Power Query 的推断，数值列会退化成 String，后续 `SUM` 直接报
`函数 SUM 不能使用 String 类型的值`。`Encoding=65001` 是为了中文表头不乱码。

## measures

| 键 | 必填 | 说明 |
|---|---|---|
| `name` | 是 | 度量值名，后续在 visual 里用 `<table>[<name>]` 引用 |
| `dax` | 是 | DAX 表达式。**含换行时必须每行 3 个 tab 缩进**（生成器会给首行补；自己写就自己补） |
| `format` | 否 | `formatString`，比率用 `0.0%` |

多行 DAX 在 TMDL 里的正确形态：

```tmdl
	measure 营收增长率 =
			VAR y = MAX(Fin[年份])
			VAR cur = CALCULATE(SUM(Fin[营业收入]), Fin[年份] = y)
			VAR prev = CALCULATE(SUM(Fin[营业收入]), Fin[年份] = y - 1)
			RETURN DIVIDE(cur - prev, prev)
```

写成一行会因缩进丢失导致解析失败或语义错位。

### 已验证的 DAX 写法

- 求和：`SUM(Sales[销售额])`
- 比率：`DIVIDE(SUM(Fin[净利润]), SUM(Fin[营业收入]))`
- 派生根式：`DIVIDE(SUM(Fin[总资产]) - SUM(Fin[净资产]), SUM(Fin[总资产]))`
- 同比/环比（**不要用 `DATEADD` 配整数年份列**）：

```dax
VAR y = MAX(Fin[年份])
VAR cur = CALCULATE(SUM(Fin[营业收入]), Fin[年份] = y)
VAR prev = CALCULATE(SUM(Fin[营业收入]), Fin[年份] = y - 1)
RETURN DIVIDE(cur - prev, prev)
```

`DATEADD(Fin[年份], -1, YEAR)` 对 int64 年份列会报
`在对函数"DATEADD"的调用中指定的列不属于 DATE 类型`。

## visuals

每个视觉对象：`{name, type, x, y, w, h}` + 若干角色字段。

| 键 | 说明 |
|---|---|
| `name` | 视觉对象 id，同时是 `pages/<page>/visuals/<name>/visual.json` 的目录名 |
| `type` | 见下方类型别名表 |
| `x` / `y` / `w` / `h` | 画布像素坐标与尺寸（`w`/`h` 可省略，默认 300×200） |

### 角色字段

| spec key | PBIR 角色 | 说明 |
|---|---|---|
| `category` | `Category` | 轴/分组维度，**不加聚合**，投影带 `"active": true` |
| `y_field` / `value` / `measure` | `Y` | 数值轴，列自动套 `Sum of`，度量值原样 |
| `series` / `legend` | `Series` | 分组图例 |
| `values` / `field` | `Values` | card / table / matrix |
| `rows` | `Rows` | matrix 行 |
| `columns` | `Columns` | matrix 列 |
| `x_field` | `X` | 散点 X 轴 |
| `indicator` | `Indicator` | kpi |
| `goal` | `TargetValue` | kpi / gauge |
| `min_value` / `max_value` | `MinValue` / `MaxValue` | gauge |

值可以是单个字符串，也可以是字符串数组（同一角色挂多个字段）。
字段引用一律 `<table>[<列或度量>]`，生成器会去 TMDL 索引里核对，不存在即报错。

### 视觉类型别名（34 个键 → 15 个 PBIR 类型）

| PBIR 类型 | 可用 spec `type` |
|---|---|
| `card` | `card` |
| `cardVisual` | `card_new`, `cardvisual` |
| `barChart` | `bar`, `bar_chart`, `barchart` |
| `clusteredBarChart` | `clustered_bar` |
| `columnChart` | `column_chart`, `column_chart`, `columnchart`, `column` |
| `clusteredColumnChart` | `clustered_column` |
| `stackedBarChart` | `stacked_bar` |
| `stackedColumnChart` | `stacked_column` |
| `lineChart` | `line`, `line_chart`, `linechart` |
| `areaChart` | `area`, `area_chart` |
| `donutChart` | `donut`, `donut_chart`, `pie` |
| `pivotTable` | `matrix`, `pivot`, `pivottable` |
| `tableEx` | `table`, `tableex` |
| `treemap` | `treemap` |
| `funnelChart` | `funnel` |
| `waterfallChart` | `waterfall` |
| `ribbonChart` | `ribbon` |
| `scatterChart` | `scatter` |
| `gauge` | `gauge` |
| `kpi` | `kpi` |
| `slicer` | `slicer` |

### 各类型的角色集合（绑错就非零退出）

| 类型 | 合法角色 |
|---|---|
| `card` / `cardVisual` / `kpi` | `Values`, `Indicator`, `TargetValue`, `TrendLine` |
| `barChart` / `columnChart` / 各 stacked / clustered | `Category`, `Y`, `Series`, `Tooltips` |
| `lineChart` / `areaChart` | `Category`, `Y`, `Series`, `Tooltips` |
| `donutChart` / `pie` / `funnel` / `treemap` / `ribbon` / `waterfall` | `Category`, `Y`, `Series`（部分仅 `Category`+`Y`） |
| `pivotTable` | `Rows`, `Columns`, `Values` |
| `tableEx` | `Values` |
| `scatterChart` | `X`, `Y`, `Series`, `Size` |
| `gauge` | `Y`, `MinValue`, `MaxValue`, `TargetValue` |
| `slicer` | `Values`(`Field`) |

精确集合以 `scripts/pbipgen.py` 里的 `ROLES` 常量为唯一真相，本表是它的可读镜像。

## 聚合

`y_field` / `values` 里挂的是**列**时，生成器加隐式聚合；挂的是**度量值**时原样。显式指定用
`aggregation` 键或在字段后缀上写。

| 函数 | `AGGREGATE_FUNCTIONS` 值 | 标题前缀 |
|---|---|---|
| `sum` | 0 | `Sum of` |
| `average` / `avg` | 1 | `Average of` |
| `distinctcount` / `distinct-count` | 2 | `Distinct count of` |
| `min` | 3 | `Min of` |
| `max` | 4 | `Max of` |
| `count` | 5 | `Count of` |
| `median` | 6 | `Median of` |
| `standarddeviation` / `stdev` | 7 | `Standard deviation of` |
| `variance` / `var` | 8 | `Variance of` |

## 产出文件树

```
<out>/<name>.pbip
<out>/<name>.Report/.platform
<out>/<name>.Report/definition.pbir
<out>/<name>.Report/definition/report.json
<out>/<name>.Report/definition/version.json
<out>/<name>.Report/definition/pages/pages.json
<out>/<name>.Report/definition/pages/<page>/page.json
<out>/<name>.Report/definition/pages/<page>/visuals/<v>/visual.json
<out>/<name>.SemanticModel/.platform
<out>/<name>.SemanticModel/definition.pbism
<out>/<name>.SemanticModel/definition/model.tmdl
<out>/<name>.SemanticModel/definition/tables/<table>.tmdl
```

打开的是 `<name>.pbip`。只把 `.Report` 或 `.SemanticModel` 单独拷走会重新触发"找不到数据集"。

## 版本锚点

`definition.pbir` 写 `version: 4.0` + `datasetReference.byPath.path = "../<name>.SemanticModel"`，
`definition.pbism` 写 `version: 4.1`，`report.json` 用 schema `report/1.2.0` 与 baseTheme `CY24SU06`，
`visual.json` 用 `visualContainer/2.7.0`，`page.json` 用 `page/2.1.0`，`pages.json` 用 `pagesMetadata/1.0.0`。
这些是 Power BI Desktop 5.55 实测可读的组合，改版本号前先在 Desktop 里试开。
