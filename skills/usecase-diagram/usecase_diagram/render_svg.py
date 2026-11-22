from __future__ import annotations

from html import escape
from math import atan2, cos, degrees, hypot, radians, sin
from pathlib import Path
from unicodedata import east_asian_width

from .icons import icon_href
from .layout import layout_diagram
from .model import ArrowHead, BoundaryShape, Diagram, Edge, LineStyle, Node, NodeKind, Point
from .router import Route, route_edges


def render_svg(diagram: Diagram, *, base_dir: Path | None = None) -> str:
    layout_diagram(diagram)
    routes = route_edges(diagram)
    default_association_arrow = diagram.layout.resolved_association_arrow()

    parts = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{_num(diagram.width or 640)}" '
            f'height="{_num(diagram.height or 360)}" viewBox="0 0 {_num(diagram.width or 640)} {_num(diagram.height or 360)}">'
        ),
        "<defs>",
        (
            '<marker id="openArrow" markerWidth="10" markerHeight="10" refX="10" refY="5" '
            'orient="auto" markerUnits="strokeWidth">'
            '<path d="M 0 0 L 10 5 L 0 10" fill="none" stroke="#111" stroke-width="1.4"/>'
            "</marker>"
        ),
        (
            '<marker id="triangleArrow" markerWidth="10" markerHeight="10" refX="10" refY="5" '
            'orient="auto" markerUnits="strokeWidth">'
            '<path d="M 0 0 L 10 5 L 0 10 Z" fill="#fff" stroke="#111" stroke-width="1.4"/>'
            "</marker>"
        ),
        "</defs>",
        '<rect x="0" y="0" width="100%" height="100%" fill="#fff"/>',
    ]

    for node in diagram.visible_nodes():
        if node.kind is NodeKind.BOUNDARY:
            parts.append(_render_boundary(node, diagram))

    for route in routes:
        parts.append(_render_edge(route, default_association_arrow=default_association_arrow))

    for node in diagram.visible_nodes():
        if node.kind is NodeKind.ACTOR:
            parts.append(_render_actor(node, base_dir=base_dir))
        elif node.kind is NodeKind.USECASE:
            parts.append(_render_usecase(node))

    parts.append("</svg>")
    return "\n".join(parts)


def _render_boundary(node: Node, diagram: Diagram) -> str:
    if _boundary_shape(node, diagram) is BoundaryShape.FRAME:
        return _render_frame_boundary(node)

    box = node.bbox()
    return "\n".join(
        [
            f'<g class="node boundary" data-id="{escape(node.id)}">',
            (
                f'<rect x="{_num(box.x)}" y="{_num(box.y)}" width="{_num(box.width)}" '
                f'height="{_num(box.height)}" fill="none" stroke="#111" stroke-width="1.2"/>'
            ),
            _text(node.label, box.x + 12, box.y + 18, anchor="start", size=13),
            "</g>",
        ]
    )


def _render_frame_boundary(node: Node) -> str:
    box = node.bbox()
    tab_height = 26.0
    tab_width = _boundary_tab_width(node.label, box.width)
    slant = min(18.0, tab_width * 0.22)
    tab_path = (
        f"M {_num(box.x)} {_num(box.y)} "
        f"L {_num(box.x + tab_width)} {_num(box.y)} "
        f"L {_num(box.x + tab_width - slant)} {_num(box.y + tab_height)} "
        f"L {_num(box.x)} {_num(box.y + tab_height)} Z"
    )
    return "\n".join(
        [
            f'<g class="node boundary boundary-frame" data-id="{escape(node.id)}">',
            (
                f'<rect x="{_num(box.x)}" y="{_num(box.y)}" width="{_num(box.width)}" '
                f'height="{_num(box.height)}" fill="none" stroke="#111" stroke-width="1.2"/>'
            ),
            (
                f'<path class="boundary-frame-tab" d="{tab_path}" fill="#fff" '
                'stroke="#111" stroke-width="1.2"/>'
            ),
            _text(node.label, box.x + 12, box.y + 16, anchor="start", size=13, middle=True),
            "</g>",
        ]
    )


def _boundary_shape(node: Node, diagram: Diagram) -> BoundaryShape:
    if node.shape is not None:
        return node.shape
    if diagram.layout.mode.value == "complex":
        return BoundaryShape.FRAME
    return BoundaryShape.BOX


def _render_actor(node: Node, *, base_dir: Path | None = None) -> str:
    if node.icon:
        return _render_actor_icon(node, base_dir=base_dir)

    box = node.bbox()
    cx = box.center.x
    top = box.top + 8
    head_cy = top + 10
    body_top = head_cy + 10
    body_bottom = body_top + 30
    arm_y = body_top + 12
    leg_bottom = body_bottom + 24
    return "\n".join(
        [
            f'<g class="node actor" data-id="{escape(node.id)}">',
            f'<circle cx="{_num(cx)}" cy="{_num(head_cy)}" r="10" fill="#fff" stroke="#111" stroke-width="1.4"/>',
            f'<line x1="{_num(cx)}" y1="{_num(body_top)}" x2="{_num(cx)}" y2="{_num(body_bottom)}" stroke="#111" stroke-width="1.4"/>',
            f'<line x1="{_num(cx - 20)}" y1="{_num(arm_y)}" x2="{_num(cx + 20)}" y2="{_num(arm_y)}" stroke="#111" stroke-width="1.4"/>',
            f'<line x1="{_num(cx)}" y1="{_num(body_bottom)}" x2="{_num(cx - 16)}" y2="{_num(leg_bottom)}" stroke="#111" stroke-width="1.4"/>',
            f'<line x1="{_num(cx)}" y1="{_num(body_bottom)}" x2="{_num(cx + 16)}" y2="{_num(leg_bottom)}" stroke="#111" stroke-width="1.4"/>',
            _text(node.label, cx, box.bottom - 4, anchor="middle", size=13),
            "</g>",
        ]
    )


def _render_actor_icon(node: Node, *, base_dir: Path | None = None) -> str:
    box = node.bbox()
    image_box = _actor_icon_box(node)
    href = icon_href(node.icon or "", base_dir)
    return "\n".join(
        [
            f'<g class="node actor actor-icon" data-id="{escape(node.id)}">',
            (
                f'<image href="{escape(href, quote=True)}" x="{_num(image_box.x)}" '
                f'y="{_num(image_box.y)}" width="{_num(image_box.width)}" '
                f'height="{_num(image_box.height)}" preserveAspectRatio="xMidYMid meet"/>'
            ),
            _text(node.label, box.center.x, box.bottom - 4, anchor="middle", size=13),
            "</g>",
        ]
    )


def _actor_icon_box(node: Node) -> "IconBox":
    box = node.bbox()
    padding_x = min(10.0, box.width * 0.14)
    top_padding = 6.0
    label_space = 28.0
    return IconBox(
        x=box.x + padding_x,
        y=box.y + top_padding,
        width=max(1.0, box.width - padding_x * 2),
        height=max(1.0, box.height - top_padding - label_space),
    )


class IconBox:
    def __init__(self, *, x: float, y: float, width: float, height: float) -> None:
        self.x = x
        self.y = y
        self.width = width
        self.height = height


def _render_usecase(node: Node) -> str:
    box = node.bbox()
    return "\n".join(
        [
            f'<g class="node usecase" data-id="{escape(node.id)}">',
            (
                f'<ellipse cx="{_num(box.center.x)}" cy="{_num(box.center.y)}" '
                f'rx="{_num(box.width / 2)}" ry="{_num(box.height / 2)}" '
                'fill="#fff" stroke="#111" stroke-width="1.4"/>'
            ),
            _text(node.label, box.center.x, box.center.y, anchor="middle", size=13, middle=True),
            "</g>",
        ]
    )


def _render_edge(route: Route, *, default_association_arrow: ArrowHead) -> str:
    edge = route.edge
    attrs = [
        f'points="{_points(route.points)}"',
        'fill="none"',
        'stroke="#111"',
        'stroke-width="1.35"',
    ]
    if edge.resolved_style() is LineStyle.DASHED:
        attrs.append('stroke-dasharray="6 4"')

    marker = _marker(edge, default_association_arrow)
    if marker:
        attrs.append(f'marker-end="{marker}"')

    label = edge.resolved_label()
    label_part = ""
    if label:
        label_point, label_angle = _path_midpoint_with_angle(route.points)
        label_x, label_y = _offset_label_point(label_point, label_angle, 6)
        transform = f' transform="rotate({_num(label_angle)} {_num(label_x)} {_num(label_y)})"'
        label_part = "\n".join(
            [
                f'<g class="edge-label" data-angle="{_num(label_angle)}"{transform}>',
                _label_mask(label, label_x, label_y, size=12),
                _text(label, label_x, label_y, anchor="middle", size=12, middle=True),
                "</g>",
            ]
        )

    return "\n".join(
        [
            f'<g class="edge {escape(edge.type.value)}" data-id="{escape(edge.id or "")}">',
            f"<polyline {' '.join(attrs)}/>",
            label_part,
            "</g>",
        ]
    )


def _marker(edge: Edge, default_association_arrow: ArrowHead) -> str | None:
    arrow = edge.resolved_arrow(default_association_arrow)
    if arrow is ArrowHead.OPEN:
        return "url(#openArrow)"
    if arrow is ArrowHead.TRIANGLE:
        return "url(#triangleArrow)"
    return None


def _text(
    label: str,
    x: float,
    y: float,
    *,
    anchor: str,
    size: int,
    middle: bool = False,
) -> str:
    lines = label.splitlines() or [label]
    dominant = ' dominant-baseline="middle"' if middle and len(lines) == 1 else ""
    if len(lines) == 1:
        return (
            f'<text x="{_num(x)}" y="{_num(y)}" text-anchor="{anchor}" '
            f'font-family="PingFang SC, Songti SC, Arial Unicode MS, Arial, Helvetica, sans-serif" '
            f'font-size="{size}" fill="#111"{dominant}>'
            f"{escape(lines[0])}</text>"
        )

    line_height = size + 3
    start_y = y - line_height * (len(lines) - 1) / 2
    spans = [
        (
            f'<tspan x="{_num(x)}" dy="{_num(0 if index == 0 else line_height)}">'
            f"{escape(line)}</tspan>"
        )
        for index, line in enumerate(lines)
    ]
    return (
        f'<text x="{_num(x)}" y="{_num(start_y)}" text-anchor="{anchor}" '
        f'font-family="PingFang SC, Songti SC, Arial Unicode MS, Arial, Helvetica, sans-serif" '
        f'font-size="{size}" fill="#111">'
        + "".join(spans)
        + "</text>"
    )


def _label_mask(label: str, x: float, y: float, *, size: int) -> str:
    width, height = _label_size(label, size)
    return (
        f'<rect class="edge-label-mask" x="{_num(x - width / 2)}" '
        f'y="{_num(y - height / 2)}" width="{_num(width)}" height="{_num(height)}" '
        'fill="#fff" stroke="none"/>'
    )


def _label_size(label: str, size: int) -> tuple[float, float]:
    lines = label.splitlines() or [label]
    max_units = max((_visual_units(line) for line in lines), default=1.0)
    width = max_units * size * 0.62 + 18
    height = len(lines) * (size + 4) + 6
    return width, height


def _boundary_tab_width(label: str, boundary_width: float) -> float:
    desired = _visual_units(label) * 8.0 + 34.0
    maximum = max(70.0, boundary_width - 24.0)
    return min(max(90.0, desired), maximum)


def _visual_units(text: str) -> float:
    total = 0.0
    for char in text:
        total += 2.0 if east_asian_width(char) in {"F", "W"} else 1.0
    return total


def _path_midpoint_with_angle(points: list[Point]) -> tuple[Point, float]:
    if len(points) == 1:
        return points[0], 0.0

    lengths: list[float] = []
    total = 0.0
    for start, end in zip(points, points[1:]):
        length = hypot(start.x - end.x, start.y - end.y)
        lengths.append(length)
        total += length

    halfway = total / 2
    walked = 0.0
    for (start, end), length in zip(zip(points, points[1:]), lengths):
        if walked + length >= halfway:
            ratio = 0 if length == 0 else (halfway - walked) / length
            point = Point(
                start.x + (end.x - start.x) * ratio,
                start.y + (end.y - start.y) * ratio,
            )
            return point, _readable_angle(start, end)
        walked += length
    return points[-1], _readable_angle(points[-2], points[-1])


def _readable_angle(start: Point, end: Point) -> float:
    angle = degrees(atan2(end.y - start.y, end.x - start.x))
    if angle > 90:
        angle -= 180
    elif angle <= -90:
        angle += 180
    return angle


def _offset_label_point(point: Point, angle: float, distance: float) -> tuple[float, float]:
    angle_radians = radians(angle)
    return (
        point.x + distance * sin(angle_radians),
        point.y - distance * cos(angle_radians),
    )


def _points(points: list[Point]) -> str:
    return " ".join(f"{_num(point.x)},{_num(point.y)}" for point in points)


def _num(value: float) -> str:
    if abs(value - round(value)) < 0.001:
        return str(int(round(value)))
    return f"{value:.2f}".rstrip("0").rstrip(".")
