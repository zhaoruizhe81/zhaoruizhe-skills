# Use Case Diagram Renderer

This project renders UML use case diagrams from JSON to SVG or high-resolution PNG.

## Install

```bash
python3 -m pip install -r requirements.txt
```

## Run

```bash
python3 -m usecase_diagram examples/simple.json -o examples/simple.svg
python3 -m usecase_diagram examples/with_boundary.json -o examples/with_boundary.svg
python3 -m usecase_diagram examples/simple.json -o examples/simple.png
python3 -m usecase_diagram examples/simple.json -o examples/simple-4x.png --scale 4
python3 -m usecase_diagram examples/simple.json -o examples/simple-2400w.png --png-width 2400
python3 -m usecase_diagram examples/admin_straight.json -o examples/admin_straight.png --png-width 2600
python3 -m usecase_diagram examples/admin_icon_actor.json -o examples/admin_icon_actor.png --png-width 1600
python3 -m usecase_diagram examples/library_complex.json -o examples/library_complex.svg
python3 -m usecase_diagram examples/library_complex.json -o examples/library_complex.png --png-width 2400
```

PNG output automatically trims the white margin around rendered content. When
`--png-width` or `--png-height` is provided, the cropped image is resized back to
the requested dimension.

## JSON Shape

```json
{
  "actors": [{"id": "user", "label": "User", "icon": "assets/user.png"}],
  "usecases": [{"id": "login", "label": "Log in"}],
  "boundaries": [{"id": "system", "label": "System"}],
  "edges": [
    {"source": "user", "target": "login", "type": "association", "arrow": "open"}
  ]
}
```

Complex diagrams are opt-in so existing JSON keeps the original simple layout:

```json
{
  "layout": {
    "mode": "complex",
    "associationArrow": "open"
  },
  "actors": [
    {"id": "member", "label": "会员"},
    {"id": "admin", "label": "管理员", "side": "right"}
  ],
  "boundaries": [
    {"id": "system", "label": "图书管理系统"}
  ],
  "usecases": [
    {"id": "login", "label": "登录", "boundary": "system"},
    {"id": "borrow", "label": "借书", "boundary": "system"},
    {"id": "search", "label": "信息查询", "boundary": "system"}
  ],
  "edges": [
    {"source": "member", "target": "login"},
    {"source": "admin", "target": "login"},
    {"source": "borrow", "target": "search", "type": "include", "label": "<<包含>>"}
  ]
}
```

In complex mode, actors are placed outside the system boundary. Actor `side`
can be `left`, `right`, or `auto`; auto actors are split across the left and
right sides. Boundaries default to a UML-style frame tab in complex mode and
can be forced with `"shape": "box"` or `"shape": "frame"`. Association edges
default to open arrowheads in complex mode unless `"associationArrow": "none"`
is set.

Actor icons are optional. If `icon` is omitted, the renderer uses the default
stick figure. Relative icon paths are resolved from the JSON file directory.
PNG export supports PNG, JPG, WebP, and GIF icons. SVG export supports raster
icons and SVG icons.

Supported edge types:

- `association`: solid line; add `"arrow": "open"` when actor links should look like the reference image
- `include`: dashed line, open arrow, `<<include>>`
- `extend`: dashed line, open arrow, `<<extend>>`
- `generalization`: solid line, hollow triangle arrow

Routes are straight by default, matching common thesis use case diagrams. Set
`"route": "orthogonal"` on an edge only when a line must avoid nodes with
right-angle bends. In complex mode, default routes first try a straight line
and automatically switch to an orthogonal route when another node blocks the
line.

## Modules

- `usecase_diagram/model.py`: node, actor, use case, boundary, edge, line style, and arrow entities
- `usecase_diagram/icons.py`: custom actor icon loading and embedding
- `usecase_diagram/layout.py`: simple and complex automatic layout
- `usecase_diagram/router.py`: straight routing by default, with optional or complex-mode automatic orthogonal routing
- `usecase_diagram/render_svg.py`: SVG rendering for stick actors, use case ovals, boundaries, line styles, and arrows
- `usecase_diagram/png.py`: high-resolution PNG export through Pillow
- `usecase_diagram/cli.py`: command line entry point
