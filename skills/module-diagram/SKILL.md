---
name: module-diagram
description: Generate, revise, and debug thesis-style function module diagrams, WBS tree diagrams, and Chinese 论文模块图/功能模块图 from JSON module trees, text module lists, or screenshot references. Use when Codex needs automatic SVG/PNG output with multi-level layout, vertical leaf labels, and orthogonal parent-child bus connectors aligned to the middle child node.
---

# Module Diagram

## Quick Start

Use the bundled script:

```bash
python3 <skill-dir>/scripts/draw_module_diagram.py \
  --config module_config.json \
  --output output/module_diagram.svg \
  --png output/module_diagram.png
```

The script exports SVG by default. PNG export uses `cairosvg` when available and falls back to `rsvg-convert`.

## Input Format

Create or update a JSON tree where every node is either a string leaf or an object with `label` and `children`:

```json
{
  "label": "大学生科技竞赛管理系统",
  "children": [
    {
      "label": "用户",
      "children": ["团队管理", "注册登录", "竞赛列表"]
    }
  ]
}
```

Use nested `children` for 4-level or 5-level diagrams. The script supports arbitrary depth, but very large trees should be split for thesis readability.

## Workflow

1. Convert the user’s module list, existing JSON, or screenshot labels into the JSON tree format.
2. Run `scripts/draw_module_diagram.py` from this skill instead of rewriting drawing code.
3. Prefer SVG for editable/vector output; also generate PNG when the user wants a preview or Word-friendly raster image.
4. For Chinese thesis figures, keep labels short, group by role or subsystem, and split overly wide diagrams rather than shrinking text.

## Layout Rules

- Root and intermediate nodes are horizontal rectangular boxes.
- Leaf nodes are vertical boxes with one Chinese character per line.
- Leaf nodes at the same depth share one height based on the longest leaf label in that depth.
- Connectors are orthogonal: parent bottom center -> horizontal bus -> child top centers.
- Parent connector anchors align to the middle child; if the child count is even, align to the average of the two middle child centers.
- The same anchor and bus routing rule is applied recursively at every level.

## Validation

After changing the script or generating a diagram:

```bash
python3 -m py_compile <skill-dir>/scripts/draw_module_diagram.py
python3 <skill-dir>/scripts/draw_module_diagram.py --config module_config.json --output output/module_diagram.svg --png output/module_diagram.png
```

When debugging alignment, inspect the SVG line coordinates. For odd child counts, the parent vertical line x-coordinate should equal the middle child vertical line x-coordinate.
