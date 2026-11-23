---
name: powerbi-pbip
description: 用 JSON spec 代码生成可用的 Power BI 报表（PBIP：TMDL 语义模型 + PBIR 布局），产出后打开即有图表、无需手动拖拽。当任务要求"批量/可复现地生成 Power BI 报表""pbip / pbir / tmdl 手写""Power BI 自动化出图""把 CSV 一键变成看板"时使用。附带生成器、不变量校验器与两个已实测示例。
metadata:
  short-description: JSON spec → 可直接打开的 Power BI PBIP 报表
  tags: [PowerBI, PBIP, PBIR, TMDL, 报表生成, 数据可视化]
---

# Power BI PBIP 代码生成

Power BI 的报表工程（PBIP）本来就是纯文本：**TMDL** 描述语义模型，**PBIR JSON** 描述画布与视觉对象。
所以报表可以被"写"出来，而不是拖出来。本 skill 提供一条已验证的落地路径：写一个 JSON spec → 跑生成器 → 打开 Desktop → 点一次刷新 → 全部图表有数。

## 什么时候用

- 需要**可复现、可 review、可批量**地出报表，而不是每次手工拖字段
- 手上是 CSV/导出表，要快速变成多视觉对象的看板
- 要在 CI / 无 Desktop 的机器上**生产**报表文件（渲染仍需要 Desktop）
- 已有 PBIP 报错打不开、字段消失、图表空白，要定位是结构问题还是数据问题

不适合：需要 DirectQuery / 实时连接、需要复杂关系模型（多表 + 日期表）、需要精细主题与条件格式的场景 —— 见文末"边界"。

## 核心链路

```bash
# 1. 写 spec（照抄 examples 里最接近的一份，改字段名）
#    2. 生成
python3 scripts/pbipgen.py examples/sales/spec.json
#    OK /abs/path/build/sales

# 3. 校验不变量（页面/类型/角色，坏了直接非零退出）
python3 scripts/check.py build/sales/SalesDemo

# 4. 在装了 Power BI Desktop 的机器上打开 <name>.pbip
#    5. 点一次「立即刷新」 —— 这一步不可省，Desktop 打开时不会自动灌数据
```

生成 + 校验可以跑在 macOS / Linux；**打开与刷新必须 Windows + Desktop**。

## spec 结构

```json
{
  "name": "SalesDemo",
  "out": "build/sales",
  "table": "Sales",
  "csv": "data/sales.csv",
  "culture": "zh-CN",
  "columns": [{"name": "月份", "type": "int64", "format": "0", "summarize": "none"},
              {"name": "销售额", "type": "double", "format": "#,##0.0", "summarize": "sum"}],
  "measures": [{"name": "销售额合计", "dax": "SUM(Sales[销售额])", "format": "#,##0.0"}],
  "page": {"name": "p1", "display": "销售看板", "width": 1280, "height": 720},
  "visuals": [
    {"name": "c1", "type": "card", "x": 40, "y": 12, "w": 200, "h": 105, "values": "Sales[销售额合计]"},
    {"name": "v1", "type": "column_chart", "x": 40, "y": 136, "w": 580, "h": 300,
     "category": "Sales[月份]", "y_field": "Sales[销售额]", "series": "Sales[产品]"}
  ]
}
```

字段全表见 `references/spec-reference.md`。三个最容易踩的点：

- `csv` 写相对路径时**相对 spec 所在目录**解析，并写成绝对路径塞进 TMDL —— CSV 必须存在于**渲染那台机器**上。
- 值角色叫 `y_field`，不叫 `y`（`y` 是画布坐标）。
- 多行 DAX 要用 `\n` + 每行 3 个 tab 缩进，TMDL 对缩进敏感。

## 角色映射（决定了图表对不对）

| spec key | PBIR 角色 | 适用 |
|---|---|---|
| `category` | `Category` | 柱/折线/环/漏斗/瀑布的轴 |
| `y_field` / `value` / `measure` | `Y` | 数值轴 |
| `series` / `legend` | `Series` | 分组图例 |
| `values` / `field` | `Values` | card / table / matrix |
| `rows` / `columns` | `Rows` / `Columns` | matrix / pivot |
| `x_field` | `X` | 散点 |

**柱/折线图的图例角色是 `Series`，不是 `Legend`。** 写 `Legend` 时 Desktop 静默忽略，图例不出现、多个系列还会被合并成一个总和 —— 看起来像"数据错了"，其实是角色名错了。生成器对视觉对象类型做角色白名单校验，不符直接退出，从根上堵掉这类静默失败。

## 生成器的硬约束（会主动失败，不会产出"看起来正常"的坏文件）

1. 角色不在该视觉对象的角色集合里 → 非零退出
2. `Table[Field]` 不在 TMDL 的列/度量索引里 → 非零退出
3. `pages.json` 永远带 `pageOrder` + `activePageName`（缺了 Desktop 拒绝加载，弹「报表没有页面」且点"继续"无效）

`scripts/check_reject.py` 就是拿一个故意绑错角色的 spec 来验证第 1 条确实生效。

## Desktop 侧注意事项

- **首次打开必定是空图 + 黄条「某些表包含不完整数据或没有数据」**，这是正常状态，不是生成失败。点「立即刷新」，等 45–90 秒（会出现"正在加载数据"对话框）后全部出数。
- 想**修改 PBIR 文件前必须先关掉 Desktop**，否则 Desktop 退出时会用内存态回写、覆盖你的改动。
- 想看真实报错原文：去 **DAX 查询视图**跑 `EVALUATE ...`，或翻 `msmdsrv.log`。图表上的"请参阅详细信息"往往点不开。

## 验收判据（不要只看"命令返回 0"）

1. 生成器 `OK <path>`，`check.py` 打印每个项目的视觉对象数量且退出码 0
2. 打开 PBIP **不弹任何错误对话框**，页标签显示你在 spec 里写的 `display`
3. 刷新后**用数据对账**，不是用眼睛看：
   - 卡片值 = 明细求和（如 `192.92 = 25.62+32.18+39.75+44.31+51.06`）
   - 比率类 = 手算复核（净利率 `9.53/192.92 = 4.94%`，资产负债率 `1 − 183.58/481.26 = 61.85%`）
   - 带 `Series` 的图表：标题应自动变成「… (按X和Y)」且图例出现多个系列 —— 标题里没有"和Y"就是分组没生效

## 故障速查

| 现象 | 原因 | 处理 |
|---|---|---|
| 打开就弹「报表没有页面 / 找不到 ActivePageN」 | `pages.json` 的 `pageOrder` 为空 | 生成器已强制写入；手改过就补回去 |
| 图表全空、黄条提示数据不完整 | 导入模型未加载 | 点一次「立即刷新」 |
| 图例不出现、系列被加总 | 用了 `Legend` 角色 | 改成 `Series` |
| `SUM 不能使用 String 类型的值` | 分区没显式定型 | partition 必须 `Csv.Document` → `PromoteHeaders` → `TransformColumnTypes` |
| 轴显示 `Sum of 年份` | 类别轴被隐式聚合 | 类别角色不给聚合、投影加 `"active": true` |
| 指标错位、多行 DAX 解析异常 | TMDL 缩进 / 换行不对 | `measure X =` 单独一行，DAX 每行 3 tab |
| 报表字段"消失" | 结构名写错（不是数据问题） | 先核对角色名与 TMDL 字段名 |
| Desktop 里改了没保存 | 生成顺序反了 | 先关 Desktop，再生成/改文件 |

完整 26 条实战坑（含远程自动化、PDF 裁剪、打包编码）见 `references/pbip-quirks.md`。

## 边界

- 单表一份 spec；多表关系、日期表、计算组未覆盖
- 仅 Import 模式（`Csv.Document`），无 DirectQuery
- 只输出 `formatString`，配色/标题/条件格式由 Desktop 默认值补齐
- 刷新那一击无法从文件格式跳过，是 Desktop 行为，不是生成器缺口

## 参考文件

- `references/spec-reference.md` — spec 全字段、视觉类型与角色集合、聚合函数表
- `references/pbip-quirks.md` — 26 条实测坑（表现 → 原因 → 避法），含远程 Windows 自动化与交付环节
- `examples/finance/spec.json` — 5 视觉对象（3 卡片 + 条形 + 折线），已实测出数
- `examples/sales/spec.json` — 8 视觉对象（卡片/柱/线/环/矩阵/表），已实测出数
- 独立版本与更新：<https://github.com/zhaoruizhe81/pbipgen>
