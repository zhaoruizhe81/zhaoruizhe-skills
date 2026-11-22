from __future__ import annotations

import html

from .model import (
    FONT_STACK,
    Layout,
    Node,
    Rect,
    compute_territory_circle_radius,
    text_width,
)
from .router import route_all_edges


def render_svg(layout: Layout, title: str | None = None) -> str:
    if not routes_available(layout):
        route_all_edges(layout)
    bounds = diagram_bounds(layout)
    parts = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{fmt(bounds.left)} {fmt(bounds.top)} {fmt(bounds.width)} {fmt(bounds.height)}" width="{fmt(bounds.width)}" height="{fmt(bounds.height)}" role="img">',
    ]
    if title:
        parts.append(f"<title>{escape(title)}</title>")
    parts.append(svg_style())
    parts.append(f'<rect class="page-bg" x="{fmt(bounds.left)}" y="{fmt(bounds.top)}" width="{fmt(bounds.width)}" height="{fmt(bounds.height)}"/>')
    if layout.debug_territory:
        parts.append(render_territories(layout))
    parts.append('<g class="edges">')
    for edge in layout.edges:
        path = layout.paths[(edge.source, edge.target, edge.label)]
        parts.append(f'<path class="{edge.class_name}" d="{path_data(path)}"/>')
    for label, x, y in layout.edge_labels:
        parts.append(f'<text class="edge-label" x="{fmt(x)}" y="{fmt(y)}">{escape(label)}</text>')
    parts.append("</g>")
    parts.append('<g class="nodes">')
    for node in layout.nodes.values():
        parts.append(render_node(node))
    parts.append("</g>")
    parts.append("</svg>")
    return "\n".join(parts) + "\n"


def routes_available(layout: Layout) -> bool:
    expected = {(edge.source, edge.target, edge.label) for edge in layout.edges}
    return bool(expected) and expected.issubset(layout.paths)


def diagram_bounds(layout: Layout) -> Rect:
    return tight_diagram_bounds(layout, padding=4)


def tight_diagram_bounds(layout: Layout, padding: float) -> Rect:
    rects = [node_visual_bounds(node) for node in layout.nodes.values()]
    rects.extend(path_bounds(path) for path in layout.paths.values() if path)
    rects.extend(edge_label_bounds(label, x, y) for label, x, y in layout.edge_labels)
    if layout.debug_territory:
        rects.extend(debug_territory_bounds(layout))
    if not rects:
        return Rect(-padding, -padding, padding, padding)
    min_x = min(rect.left for rect in rects) - padding
    min_y = min(rect.top for rect in rects) - padding
    max_x = max(rect.right for rect in rects) + padding
    max_y = max(rect.bottom for rect in rects) + padding
    return Rect(min_x, min_y, max_x, max_y)


def node_visual_bounds(node: Node) -> Rect:
    if node.kind == "attribute":
        return node.rect.inflate(2)
    return node.rect.inflate(3)


def path_bounds(path: list[tuple[float, float]]) -> Rect:
    xs = [point[0] for point in path]
    ys = [point[1] for point in path]
    return Rect(min(xs), min(ys), max(xs), max(ys)).inflate(3)


def edge_label_bounds(label: str, x: float, y: float) -> Rect:
    width = text_width(label, 12) + 10
    height = 18
    return Rect(x - width / 2, y - height / 2, x + width / 2, y + height / 2)


def debug_territory_bounds(layout: Layout) -> list[Rect]:
    rects: list[Rect] = []
    for territory in layout.territories.values():
        outer = territory.outer_rect
        attr = territory.attribute_rect
        outer_radius = compute_territory_circle_radius(len(layout.spec.entities), outer.width, outer.height)
        attr_radius = compute_territory_circle_radius(len(layout.spec.entities), attr.width, attr.height)
        rects.append(circle_bounds(outer.center[0], outer.center[1], outer_radius).inflate(1))
        rects.append(circle_bounds(attr.center[0], attr.center[1], attr_radius).inflate(1))
        if territory.entity_id in layout.placement_order:
            order = layout.placement_order[territory.entity_id]
            entity_label = layout.nodes.get(territory.entity_id).label if territory.entity_id in layout.nodes else territory.entity_id
            label_y = outer.center[1] - outer_radius - 18
            rects.append(placement_label_bounds(f"#{order} {entity_label}", outer.center[0], label_y))
    return rects


def circle_bounds(cx: float, cy: float, radius: float) -> Rect:
    return Rect(cx - radius, cy - radius, cx + radius, cy + radius)


def placement_label_bounds(label: str, x: float, y: float) -> Rect:
    width = text_width(label, 15) + 12
    height = 22
    return Rect(x - width / 2, y - height / 2, x + width / 2, y + height / 2)


def svg_style() -> str:
    return f"""<defs>
<style><![CDATA[
.page-bg {{ fill: #fff; }}
.entity, .relationship, .attribute {{ fill: #fff; stroke: #000; stroke-width: 1.35; }}
.attribute.derived {{ stroke-dasharray: 5 4; }}
.relationship-edge, .attribute-edge {{ fill: none; stroke: #000; stroke-width: 1.15; stroke-linejoin: round; stroke-linecap: square; }}
.attribute-edge {{ stroke-width: 1.05; }}
.node-label {{ font-family: {FONT_STACK}; font-size: 15px; fill: #000; text-anchor: middle; dominant-baseline: central; }}
.entity-label {{ font-size: 16px; font-weight: 600; }}
.attribute-label {{ font-size: 14px; }}
.key-label {{ text-decoration: underline; }}
.edge-label {{ font-family: {FONT_STACK}; font-size: 12px; fill: #000; text-anchor: middle; dominant-baseline: central; paint-order: stroke; stroke: #fff; stroke-width: 4px; stroke-linejoin: round; }}
.territory {{ fill: none; stroke: #9ca3af; stroke-width: 1; stroke-dasharray: 8 5; }}
.attribute-territory {{ fill: none; stroke: #d1d5db; stroke-width: 1; stroke-dasharray: 4 4; }}
.placement-label {{ font-family: {FONT_STACK}; font-size: 15px; font-weight: 600; fill: #d00000; text-anchor: middle; dominant-baseline: central; paint-order: stroke; stroke: #fff; stroke-width: 4px; stroke-linejoin: round; }}
]]></style>
</defs>"""


def render_territories(layout: Layout) -> str:
    parts = ['<g class="territories">']
    for territory in layout.territories.values():
        outer = territory.outer_rect
        attr = territory.attribute_rect
        outer_radius = compute_territory_circle_radius(len(layout.spec.entities), outer.width, outer.height)
        attr_radius = compute_territory_circle_radius(len(layout.spec.entities), attr.width, attr.height)
        parts.append(
            f'<circle class="territory" cx="{fmt(outer.center[0])}" cy="{fmt(outer.center[1])}" r="{fmt(outer_radius)}"/>'
        )
        parts.append(
            f'<circle class="attribute-territory" cx="{fmt(attr.center[0])}" cy="{fmt(attr.center[1])}" r="{fmt(attr_radius)}"/>'
        )
        if territory.entity_id in layout.placement_order:
            order = layout.placement_order[territory.entity_id]
            label_y = outer.center[1] - outer_radius - 18
            entity_label = layout.nodes.get(territory.entity_id).label if territory.entity_id in layout.nodes else territory.entity_id
            parts.append(
                f'<text class="placement-label" x="{fmt(outer.center[0])}" y="{fmt(label_y)}">#{order} {escape(entity_label)}</text>'
            )
    parts.append("</g>")
    return "\n".join(parts)


def render_node(node: Node) -> str:
    if node.kind == "entity":
        rect = node.rect
        return "\n".join([
            f'<g id="{escape_id(node.id)}">',
            f'<rect class="entity" x="{fmt(rect.left)}" y="{fmt(rect.top)}" width="{fmt(node.width)}" height="{fmt(node.height)}"/>',
            f'<text class="node-label entity-label" x="{fmt(node.x)}" y="{fmt(node.y)}">{escape(node.label)}</text>',
            "</g>",
        ])
    if node.kind == "relationship":
        rect = node.rect
        points = [(node.x, rect.top), (rect.right, node.y), (node.x, rect.bottom), (rect.left, node.y)]
        return "\n".join([
            f'<g id="{escape_id(node.id)}">',
            f'<polygon class="relationship" points="{points_attr(points)}"/>',
            f'<text class="node-label" x="{fmt(node.x)}" y="{fmt(node.y)}">{escape(node.label)}</text>',
            "</g>",
        ])
    classes = ["attribute"]
    if node.derived:
        classes.append("derived")
    label_classes = ["node-label", "attribute-label"]
    if node.key:
        label_classes.append("key-label")
    rx, ry = node.width / 2, node.height / 2
    ellipses = [f'<ellipse class="{" ".join(classes)}" cx="{fmt(node.x)}" cy="{fmt(node.y)}" rx="{fmt(rx)}" ry="{fmt(ry)}"/>']
    if node.multivalued:
        ellipses.append(f'<ellipse class="{" ".join(classes)}" cx="{fmt(node.x)}" cy="{fmt(node.y)}" rx="{fmt(rx - 5)}" ry="{fmt(ry - 4)}"/>')
    return "\n".join([
        f'<g id="{escape_id(node.id)}">',
        *ellipses,
        f'<text class="{" ".join(label_classes)}" x="{fmt(node.x)}" y="{fmt(node.y)}">{escape(node.label)}</text>',
        "</g>",
    ])


def path_data(path: list[tuple[float, float]]) -> str:
    if not path:
        return ""
    first, *rest = path
    data = [f"M {fmt(first[0])} {fmt(first[1])}"]
    data.extend(f"L {fmt(x)} {fmt(y)}" for x, y in rest)
    return " ".join(data)


def points_attr(points: list[tuple[float, float]]) -> str:
    return " ".join(f"{fmt(x)},{fmt(y)}" for x, y in points)


def fmt(value: float) -> str:
    if abs(value - round(value)) < 0.001:
        return str(int(round(value)))
    return f"{value:.2f}".rstrip("0").rstrip(".")


def escape(value: str) -> str:
    return html.escape(value, quote=False)


def escape_id(value: str) -> str:
    return "".join(ch if ch.isalnum() or ch in {"_", "-", ":"} else "_" for ch in value)
