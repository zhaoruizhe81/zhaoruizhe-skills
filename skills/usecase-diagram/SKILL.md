---
name: usecase-diagram
description: Render UML use case diagrams (用例图) from JSON to SVG or high-resolution PNG with the bundled pure-Python renderer — actors (stick figure or custom icon image), use case ellipses, system boundaries, association/include/extend edges, opt-in complex layout, auto-trimmed PNG with scale or exact width/height control. Use when the user asks for 用例图 / use case diagram / UML 用例 / actor 与用例关系图 / 参与者用例图. Do NOT use for ER 图 (use er-svg-generator), flowcharts (use flowchart-json-renderer), or editable class/sequence/architecture diagrams (use drawio-skill).
allowed-tools: [Bash, Read, Write, Glob, Grep]
keywords: usecase, 用例图, UML, diagram, svg, png, renderer, actor, boundary, 参与者, 系统边界
---

# Use Case Diagram Generator

## Purpose

Bundled `usecase_diagram/` package renders UML use case diagrams from JSON to SVG or high-resolution PNG. Pure Python, single dependency: **pillow**（仅 PNG 需要；SVG 用任何 Python 3 都能出）。支持：参与者火柴人/自定义图标、用例椭圆、系统边界框、association/include/extend 关系边、复杂布局模式、PNG 自动裁白边 + 倍数/精确宽高输出。

## Quick Workflow

1. Draft JSON per the schema below（id 用 snake_case，label 中英文皆可）。
2. `cd` to this skill's directory (the one holding SKILL.md) and run:

```bash
cd <本技能目录>
python3 -m usecase_diagram examples/simple.json -o output.svg
# PNG：自动裁白边，默认 3x 放大
python3 -m usecase_diagram examples/simple.json -o output.png
# 高清定制
python3 -m usecase_diagram examples/library_complex.json -o output.png --png-width 2400
python3 -m usecase_diagram examples/simple.json -o output-4x.png --scale 4
```

3. Open the PNG and inspect. Layout is automatic — no manual coordinates to maintain. Iterate on the JSON only.

装机自检：渲染 `examples/simple.json`，exit 0 且 SVG、PNG 都生成。

## JSON Schema

```json
{
  "title": "Repair order use cases",
  "actors":   [{"id": "student", "label": "Student", "icon": "admin_icon.png"}],
  "usecases": [{"id": "login", "label": "Log in"}],
  "boundaries": [{"id": "system", "label": "System"}],
  "edges": [
    {"source": "student", "target": "login"},
    {"source": "login", "target": "core", "type": "include", "arrow": "open"}
  ],
  "layout": {"mode": "complex", "associationArrow": "open"}
}
```

- `icon` 路径**相对 JSON 文件所在目录**解析（`examples/admin_icon.png` 是现成素材；不给 icon 则画默认火柴人）
- `boundaries` = 系统边界矩形，可多个
- `edges.type`：association（默认，省略即可）/ include / extend；`arrow`：open（开放箭头，include/extend 的 UML 规范画法）/ filled / none
- `layout.mode: "complex"` 是给密集图的 opt-in 开关——存量简单 JSON 不写它就保持原有简单布局，不会因升级而变样

## CLI

```bash
python3 -m usecase_diagram <input.json 或 -> -o <out.svg|out.png> [--format auto|svg|png] [--scale 3] [--png-width N] [--png-height N]
```

- 输出格式默认按扩展名推断；`-` 从 stdin 读 JSON
- PNG 默认 3x 并自动裁掉白边；`--png-width/--png-height` 指定最终像素尺寸（裁剪后再缩放到该尺寸）

## Dependencies

- SVG：零依赖
- PNG：`pillow`（`python3 -m pip install pillow`）

## Boundary（和邻居技能的分工）

- ER 图 / 实体关系图 → `er-svg-generator`
- 流程图 → `flowchart-json-renderer`
- 可编辑类图/时序图/架构图 → `drawio-skill`
