---
name: flowchart-json-renderer
description: Generate simple black-and-white flowcharts from JSON using a bundled Python renderer. Use when Codex needs to create or edit 流程图 / flowchart outputs as SVG and PNG, especially diagrams made from rectangles, diamonds, capsule start/end nodes, explicit ports, Chinese labels, and 90-degree orthogonal connector lines without Graphviz/DOT layout.
---

# Flowchart JSON Renderer

Use this skill to turn a JSON flowchart definition into editable SVG and PNG files. The bundled renderer computes geometry itself; do not use Graphviz, DOT, Mermaid, or PlantUML for this workflow unless the user explicitly asks for a different backend.

## Workflow

1. Create or edit a JSON file with `nodes` and `edges`.
2. Use only these node types unless the user requests an extension:
   - `terminal`: capsule start/end node
   - `rect`: process rectangle
   - `diamond`: decision diamond
3. Put human-readable text in `text`; use `\n` for manual Chinese line breaks.
4. Use edge labels such as `是` and `否` for decision branches.
5. Render with the bundled script:

```sh
python3 scripts/flowchart.py input.json -o output.png
```

The script writes both `output.svg` and `output.png`. PNG export requires local `rsvg-convert`.
The renderer uses deterministic node placement plus a grid-cost orthogonal router. Node interiors are blocked, node padding, existing lines, labels, and retry lanes contribute routing costs, and final SVG paths are simplified into horizontal/vertical polylines.
Multiple forward branches from the same bottom port and multiple branches merging into the same top port use shared horizontal bus lines so branch/merge diagrams do not form stepped split points.
Multiple branches merging into the same side port use a shared vertical bus line. For right-side validation/error boxes that all end at the same terminal, prefer `from_port: "e"`, `to_port: "e"`, and `route_hint: "right"` so the error boxes connect from their right edges into one shared right-side line.
When a decision node branches from its `e` or `w` side into a rectangular prompt/process node on the same horizontal band, the renderer resolves a vertical target port (`n` or `s`) to the nearest side port (`w` or `e`). When the target rectangle is lower, keep the top entry and prefer a short right-angle elbow over a distant side lane.
When rectangular result nodes merge into the left or right side of a terminal node, do not create bottom-exit jogs before the long merge line. If a result rectangle is left of the terminal and targets `end.w`, exit from the rectangle's `w` side; if it is right of the terminal and targets `end.e`, exit from `e`. The renderer also resolves `from_port: "s"` to that outer side in this geometry.
The SVG viewBox must preserve safety padding on every side, even when that requires negative top/left values; do not clamp the viewBox to `0` if doing so would make branch lines touch the image edge.

## JSON Shape

```json
{
  "direction": "TB",
  "nodes": [
    {"id": "start", "type": "terminal", "text": "开始"},
    {"id": "login", "type": "rect", "text": "登录"},
    {"id": "check", "type": "diamond", "text": "是否正确输入\n用户名和密码"},
    {"id": "end", "type": "terminal", "text": "结束"}
  ],
  "edges": [
    {"from": "start", "to": "login"},
    {"from": "login", "to": "check"},
    {"from": "check", "to": "end", "label": "是"}
  ]
}
```

Supported fields:

- Root: `title` optional; `direction` must be `TB`.
- Nodes: `id`, `type`, `text`, optional `width`, optional `height`, optional fixed center coordinates `x` / `y`.
- Edges: `from`, `to`, optional `label`, optional `from_port`, optional `to_port`, optional `route_hint`.
- Ports: `n`, `e`, `s`, `w`, `c`.
- Root routing/layout options: optional `grid_size`, `node_gap`, `margin_x`, `margin_top`, `margin_bottom`, `lane_clearance`, `lane_gap`, `side_stub`, `port_stub`, `node_pad`, `label_pad`.
- Root typography/theme options: optional `node_font_size`, `label_font_size`, `title_font_size`, `font`, `theme` (`white` or `black`).
- Root stroke options: optional `node_stroke_width`, `edge_stroke_width`, `arrow_size`; defaults use a thinner report-style line.

Default routing:

- Forward flow uses `s -> n`.
- Backward or retry flow uses `e -> e` and routes around the right side.
- Explicit `e` / `w` ports use short outside stubs before routing, so diamond side ports connect at the left/right tips without entering from the wrong direction.
- Side branches from a decision to a horizontally aligned rectangular node enter the rectangle from the nearest side. If the rectangle is below the decision, keep the `n` target and let the renderer use a short right-angle elbow into the top edge.
- Result rectangles that merge into terminal side ports should exit from their outer side. Example: `{"from":"show_warning","from_port":"w","to":"end","to_port":"w","route_hint":"left"}` for a left result, and `{"from":"show_normal","from_port":"e","to":"end","to_port":"e","route_hint":"right"}` for a right result. If the JSON still uses `from_port: "s"` in this geometry, the renderer resolves it to the outer side.
- If several right-side validation/error branches flow to the same end node, make their outbound edges `e -> e` with `route_hint: "right"`; do not use `s -> e` unless the user specifically wants bottom exits from those boxes.
- Side branches and retry edges use side lanes when they skip over intermediate nodes.
- `route_hint` can be `left` or `right` when an edge should prefer a specific side.
- Multiple backward edges get separate right-side lanes.
- All connector segments are horizontal or vertical.

## Examples

Copy examples when a quick starting point is useful:

```sh
cp assets/examples/login.json ./login.json
cp assets/examples/stress_complex.json ./stress_complex.json
cp assets/examples/diamond_ports_test.json ./diamond_ports_test.json
cp assets/examples/double_diamond_ports_example.json ./double_diamond_ports_example.json
cp assets/examples/personal_center_flow.json ./personal_center_flow.json
cp assets/examples/personal_center_flow_black.json ./personal_center_flow_black.json
cp assets/examples/branch_merge_flow.json ./branch_merge_flow.json
```

Use `login.json` for a small Chinese login flow. Use `stress_complex.json` to pressure-test long workflows with many retry branches.
Use `diamond_ports_test.json` when checking explicit left/right ports on decision diamonds.
Use `double_diamond_ports_example.json` when checking multiple decision diamonds with side-port branches and retry edges.
Use `personal_center_flow.json` when checking compact vertical flowcharts with the default white theme.
Use `personal_center_flow_black.json` when checking the optional black theme.
Use `branch_merge_flow.json` when checking fixed-position left/right branches that merge back into one process.

## Validation

After rendering, run:

```sh
python3 -m py_compile scripts/flowchart.py
file output.svg output.png
```

Use `--debug-grid` when investigating path choices:

```sh
python3 scripts/flowchart.py input.json -o output.png --debug-grid
```

For important diagrams, inspect the PNG visually and confirm:

- labels do not overlap nodes or lines
- branch labels use the requested wording, such as `是` / `否`
- side validation/error boxes exit from the side edge when they merge into a shared side bus
- branch and merge lines keep visible padding from the image edges, especially the top edge
- retry/backward connectors remain on the right side
- all connectors are 90-degree orthogonal lines
