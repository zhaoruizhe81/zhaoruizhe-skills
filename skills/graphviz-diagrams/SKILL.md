---
name: graphviz-diagrams
description: Create, edit, validate, and render Graphviz DOT/GV diagrams. Use when Codex needs to work with Graphviz, DOT language, `.dot` or `.gv` files, dependency graphs, architecture graphs, directed or undirected relationship diagrams, Chen-style ER diagrams, Chinese entity-attribute radial diagrams, flowcharts, state graphs, graph layout tuning, or rendering diagrams to PNG, SVG, or PDF with Graphviz.
---

# Graphviz Diagrams

## Quick Start

- Prefer producing editable `.dot` or `.gv` source first, then render an image when Graphviz is available.
- Before creating or revising a diagram, read the matching example file when one exists:
  - Chinese academic flowchart: `examples/flowchart-academic-login-cn.dot`
  - Classic Chen-style radial entity-attribute diagram: `examples/chen-er-radial-entity-cn.dot`
- Use the relevant example as the starting pattern for layout, shapes, font choices, spacing, and validation. If no example matches the request, state that no exact bundled example exists and proceed from the style defaults.
- Use `scripts/render_graphviz.py` to validate or render diagrams:

```sh
python3 scripts/render_graphviz.py path/to/diagram.dot --format png
python3 scripts/render_graphviz.py path/to/diagram.gv --layout neato --format svg --output path/to/diagram.svg
python3 scripts/render_graphviz.py path/to/diagram.dot --check-only
```

- Default to monochrome, high-contrast diagrams unless the user asks for color.
- Keep labels short. Move prose explanations outside the graph or into a small legend node.
- For large graphs, group, filter, or split the diagram before relying on Graphviz layout.

## Diagram Choices

- Use `digraph` and `->` for directed flows, dependencies, state transitions, pipelines, and architecture data flow.
- Use `graph` and `--` for undirected relationships, similarity maps, peer networks, and simple associations.
- Use `rankdir=LR` for process flows, dependency chains, and architecture diagrams that read left to right.
- Use `rankdir=TB` for hierarchy, organization, and tree-like diagrams.
- Use `subgraph cluster_name` only for meaningful groups such as modules, services, phases, or trust boundaries.
- Use layout engine `dot` for hierarchical graphs, `neato` or `fdp` for relationship maps, `sfdp` for larger undirected graphs, `twopi` for radial hierarchy, and `circo` for circular relationships.

## Style Defaults

Start from a simple base and adjust only when the task requires it:

```dot
digraph G {
  graph [
    rankdir=LR,
    bgcolor="white",
    pad=0.2,
    nodesep=0.45,
    ranksep=0.6
  ];
  node [
    shape=box,
    style="rounded",
    color="black",
    fontname="Arial",
    fontsize=12,
    margin="0.08,0.05"
  ];
  edge [
    color="black",
    fontname="Arial",
    fontsize=11,
    arrowsize=0.8
  ];

  A [label="Input"];
  B [label="Process"];
  C [label="Output"];
  A -> B -> C;
}
```

- For paper or report diagrams, prefer white background, black lines, readable spacing, and no decorative gradients.
- Avoid encoding essential meaning only through color; use labels, shapes, or line styles as well.
- Keep edge labels sparse. Too many labeled edges usually means the graph should be simplified.
- Use stable IDs in ASCII when possible, and put human text in `label`.

## Flowchart Example

Use this pattern when the user asks for a Chinese academic flowchart. Before drafting, read `examples/flowchart-academic-login-cn.dot` and follow it for layout, shapes, margins, manual line breaks, and retry edges. Use `digraph`, `rankdir=TB`, ellipse start/end nodes, parallelogram input/output nodes, diamond decision nodes, box processing/error nodes, and dashed back edges for retries. Keep Chinese labels short and use manual `\n` line breaks to avoid over-wide boxes.

```dot
digraph AcademicLoginFlowchart {
  graph [rankdir=TB, dpi=300];

  node [
    fontname="SimSun",
    shape=box,
    style=solid,
    color=black,
    fontcolor=black,
    margin="0.2,0.1"
  ];
  edge [
    fontname="SimSun",
    color=black,
    fontcolor=black,
    fontsize=10
  ];

  Start [shape=ellipse, label="开始"];
  Input [shape=parallelogram, label="输入账号\n和密码"];
  CheckFormat [shape=diamond, label="格式是否\n有效?"];
  FormatError [shape=box, label="提示输入\n格式错误"];
  VerifyUser [shape=box, label="系统查询\n并验证凭据"];
  CheckAuth [shape=diamond, label="验证是否\n通过?"];
  AuthError [shape=box, label="提示账号或\n密码错误"];
  CreateSession [shape=box, label="创建会话\n并授权"];
  End [shape=ellipse, label="结束"];

  Start -> Input;
  Input -> CheckFormat;

  CheckFormat -> VerifyUser [label=" 是"];
  CheckFormat -> FormatError [label=" 否"];
  FormatError -> Input [style=dashed];

  VerifyUser -> CheckAuth;

  CheckAuth -> CreateSession [label=" 是"];
  CheckAuth -> AuthError [label=" 否"];
  AuthError -> Input [style=dashed];

  CreateSession -> End;
}
```

## Chinese Labels

- DOT source may contain Chinese labels directly when saved as UTF-8.
- Set a local Chinese font when rendering Chinese text, for example:

```dot
graph [fontname="PingFang SC"];
node [fontname="PingFang SC"];
edge [fontname="PingFang SC"];
```

- On macOS, common choices include `PingFang SC`, `Songti SC`, and `Heiti SC`.
- If Chinese text renders as boxes or missing glyphs, switch the `fontname` explicitly before changing the diagram structure.

## Chen ER Radial Example

Use this as the default pattern when the user asks for a classic Chen-style local entity-attribute diagram. Before drafting, read `examples/chen-er-radial-entity-cn.dot` and follow it for fixed radial placement, ellipse-only entity/attribute shapes, and line style conventions. Keep the central entity and attributes as ellipses, place attributes around the entity in all directions, underline key attributes, use `peripheries=2` for multivalued attributes, and use dashed ellipses for derived attributes. Render this fixed-position pattern with `--layout neato`.

```dot
graph ChenER_Radial_Student_CN {
  graph [
    layout=neato,
    bgcolor="white",
    outputorder=edgesfirst,
    overlap=false,
    splines=line,
    pad=0.25,
    fontname="PingFang SC"
  ];

  node [
    shape=ellipse,
    fontname="PingFang SC",
    color=black,
    fillcolor=white,
    fontcolor=black,
    style=filled,
    margin="0.10,0.05"
  ];
  edge [
    color=black,
    penwidth=1.1
  ];

  Student [
    label="学生",
    style="filled,bold",
    fontsize=16,
    width=1.25,
    height=0.65,
    pos="0,0!",
    pin=true
  ];

  StudentID [label=<<U>学号</U>>, pos="0,2.55!", pin=true];
  Name [label="姓名", pos="1.80,1.80!", pin=true];
  Gender [label="性别", pos="2.55,0!", pin=true];
  Phone [label="联系方式", peripheries=2, pos="1.80,-1.80!", pin=true];
  Email [label="邮箱", pos="0,-2.55!", pin=true];
  Age [label="年龄", style="filled,dashed", pos="-1.80,-1.80!", pin=true];
  EnrollmentDate [label="入学日期", pos="-2.55,0!", pin=true];
  Major [label="专业", pos="-1.80,1.80!", pin=true];

  Student -- StudentID;
  Student -- Name;
  Student -- Gender;
  Student -- Phone;
  Student -- Email;
  Student -- Age;
  Student -- EnrollmentDate;
  Student -- Major;
}
```

## Oversize Control

- If a graph has more than about 30 nodes or many crossing edges, first reduce scope, cluster related nodes, or create multiple diagrams.
- For dense dependency graphs, show only the selected component, direct neighbors, and important external boundaries.
- For architecture diagrams, prefer 5-9 main nodes per view and use clusters for domains instead of drawing every class or function.
- For workflow diagrams, split overview and detail views when labels or edge crossings make the rendered result hard to read.

## Validation

- Always validate DOT syntax before final delivery when Graphviz is available:

```sh
python3 scripts/render_graphviz.py path/to/diagram.dot --check-only
```

- When rendering, inspect failures for Graphviz syntax messages. Common issues are missing semicolons, unquoted labels with spaces, mismatched braces, or using `->` inside `graph` instead of `digraph`.
- If Graphviz is unavailable, still deliver the editable DOT source and explain that rendering could not be verified locally.

## Resource

- `scripts/render_graphviz.py`: validate and render `.dot` or `.gv` files to `png`, `svg`, or `pdf` using a selected Graphviz layout engine.
- `examples/flowchart-academic-login-cn.dot`: required starting example for Chinese academic flowcharts.
- `examples/chen-er-radial-entity-cn.dot`: required starting example for classic Chen-style radial entity-attribute diagrams.
