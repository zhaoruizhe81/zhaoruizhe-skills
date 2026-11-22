---
name: er-svg-generator
description: Guide Chen-style ER diagram generation, rendering, debugging, and layout optimization. Use when Codex needs to create, render, debug, or validate ER 图 / 实体关系图 / Chen ER diagrams, requiring entity attributes to be included and rendered, especially for compact automatic layout, stale manual coordinate or attribute-side cleanup, space-aware attribute placement, diamond port alignment, relationship routing, SVG/PNG export, or hard layout metrics. The skill ships a complete, dependency-free renderer as the bundled `er/` package; a live renderer project directory, if present, remains the development source of truth.
---

# ER SVG Generator

## Purpose

Use this skill to generate, render, debug, and validate Chen-style ER diagrams end-to-end. The complete renderer ships with the skill as the `er/` package — pure Python standard library, no third-party dependencies (`model`, `parser`, `layout`, `attributes`, `ports`, `port_solver`, `router`, `post_layout`, `render_svg`, `export`, `png_export`, `stats`, `score`, `geometry`, `topology`, `cli`, plus a standalone `web_editor`).

Renderer priority:

1. If the current task sits inside a live renderer project (e.g. `/Users/zhaoruizhe/Desktop/project/P/ER图/er`, containing the same modules), edit and run that project directly — it is the development source of truth.
2. Otherwise use the bundled `er/` package from this skill directory (command below). It is self-contained and needs no installation.

## Quick Workflow

1. Inspect the local project first. Use `rg --files` and read the relevant modules before changing layout behavior.
2. Prepare or update an ER JSON input. For schema details, read `references/json-format.md` only when needed.
3. Before rendering, verify every entity has a non-empty `attributes` array and that attributes are not hidden. If attributes are missing, extract them from DDL/source material, infer concise core attributes when safe, or ask the user; do not produce a final ER diagram with attribute-less entities.
4. Before final rendering, prefer automatic layout. Remove or ignore `layout.positions.entities`, `layout.positions.relationships`, per-entity or per-relationship `layout.x`/`layout.y`, and stale `layout.attributes.side` hints unless the user explicitly asks to preserve manual placement. Treat coordinates and attribute sides from imported/exported JSON as draft hints; stale fixed layout data commonly makes the diagram sparse or places attributes on cramped sides.
5. Render with the bundled package: `cd` to this skill's directory (the one holding SKILL.md) and run:

```bash
cd <本技能目录>
python3 - <<'PY'
from er.cli import main
raise SystemExit(main([
    "er/demo_compact.json",      # 或你保存的 JSON 路径
    "-o", "er/output.svg",
    "--png-output", "er/output.png",
    "--auto-layout-clean",
    "--stats",
]))
PY
```

PNG export requires `rsvg-convert`（`brew install librsvg`）；没有它就去掉 `--png-output`，只交付 SVG。装机自检：渲染 `er/demo_compact.json`，预期 stats 显示 0 crossings / 0 overlaps，且 SVG、PNG 两个文件都生成。

6. Open or view the PNG directly after rendering. Prefer PNG when the user says it is easier to inspect.
7. Iterate on the algorithm only after checking hard metrics and the actual image.

Use `--debug-territory` when diagnosing spacing, invisible territory size, or why the middle of the graph looks empty.

## Attribute Placement

Compact attributes are placed by the project-local `attributes.py` algorithm. In automatic mode, it scores each side using real candidate ellipse rectangles, available outward space, nearby entity/relationship obstacles, internal attribute overlaps, canvas growth, and clamp/alignment penalties.

- Prefer `--auto-layout-clean` for final renders so stale `layout.attributes.side` hints do not force attributes onto cramped sides.
- Preserve `layout.attributes.side` only when the user explicitly asks for a fixed attribute direction or hand-tuned layout.
- If attributes overlap each other or sit on the cramped side of an entity, check whether the render used `--auto-layout-clean` before changing code.
- Relationship attributes are placed diagonally offset from the diamond (upper-left and lower-left). If relationship attributes overlap with entity attributes or the diamond itself, the offset parameters in `place_relationship_attr()` (in `attributes.py`) may need adjustment — increase `offset_x` to push further left or `offset_y` to increase vertical spacing.

## Compact Layout Debugging

When the user complains that the diagram is too loose, hollow in the middle, or not compact:

- Check fixed layout hints first. If the input JSON has `layout.positions`, node-level `layout.x`/`layout.y`, or stale `layout.attributes.side`, render with `--auto-layout-clean` before changing the algorithm.
- Check territory sizing first. Over-conservative circular territory estimates can reserve empty corner space and push entities apart.
- Check early layout scoring. Avoid letting target aspect ratio dominate while only one or two entities have been placed.
- Check attribute placement separately from entity placement. Space-aware attribute scoring can fix cramped attributes without changing entity positions.
- Treat near-zero negative clearances as floating-point noise, not real overlap.
- Add only a mild orthogonal relationship bias. Too much axis preference can stretch side entities far away.
- Keep dense diagrams more conservative than small and medium diagrams.
- Validate with both stats and the rendered PNG before saying the layout is fixed.

When the user says relationship lines do not connect to the diamond correctly:

- Route relationship edges from entity boundaries to diamond cardinal anchors.
- Ensure diamond ports lie on the diamond edge, not on the bounding rectangle.
- Exclude participant entities from their own relationship routing obstacles.
- Re-render small zoomed PNGs around the relationship if visual alignment is in doubt.

## Input Handling

- If the user provides JSON, save it next to the renderer you will run (bundled mode: this skill's `er/` directory; project mode: the active project).
- If provided JSON contains fixed coordinates or old `layout.attributes.side` hints, default to `--auto-layout-clean` for final PNG/SVG output. Preserve manual coordinates and attribute sides only when the user asks to keep the current structure, exact positions, or a hand-tuned layout.
- If the user provides SQL DDL or a natural-language schema, convert it into the JSON format in `references/json-format.md`.
- Keep entity and relationship ids in `snake_case`; labels can be Chinese or English.
- Entity attributes are mandatory in Chen ER output. Every entity must include at least one rendered attribute, preferably its key plus 2-5 core business attributes. If the source has many columns, keep the ER diagram concise by choosing representative attributes or splitting the diagram; do not use empty attributes, `hidden`, or `keys_only` as a shortcut for final output unless the user explicitly overrides this requirement.
- Relationship attributes are supported for M:N and other relationship types. Add an `attributes` array to the relationship object (same format as entity attributes) to render attribute ellipses connected to the diamond. This is required for M:N relationships that produce business data — the attributes must be drawn on the relationship (diamond), not omitted. Attribute options (`key`, `multivalued`, `derived`) work the same as entity attributes.
- Relationship participant `role` values are semantic metadata; rendered relationship edge labels should show only cardinality values such as `1`, `N`, `M`, or `0..1`.

## Output and Validation

Return the PNG/SVG paths and summarize the important `--stats` lines. Treat these as hard quality checks:

```text
relationship_crossings: 0
relationship_obstacle_hits: 0
territory_overlaps: 0
attribute_out_of_territory: 0
relationship_crosses_territory: 0
node_overlaps: 0
```

If any hard metric is nonzero, report it clearly and preserve the generated debug output for inspection. Do not claim the layout is clean until these metrics are zero.

When diagnosing excessive whitespace or cramped attributes, compare the fixed-hint render against an `--auto-layout-clean` render. Report the SVG `viewBox`, entity span, total relationship length, max relationship length, and whether `node_overlaps` comes from attributes when those explain the visible issue.

## Skill Storage Rule

The bundled `er/` package IS the renderer — keep it complete and up to date with the live project (this is intentional, not an accident). Hygiene rules that still apply:

- Never commit `__pycache__`, `.DS_Store`, or generated outputs (`output.svg`, `output.png`, `*.pyc`) — delete them after test renders.
- When the live project's modules change meaningfully, refresh the bundled copies in `er/` so the skill stays self-sufficient.
- Keep lightweight references (`references/json-format.md`) and example JSONs in the skill.
