from __future__ import annotations

from .model import Layout, Node, Port, VALID_SIDES, centered_slot, clamp, dominant_side


DEFAULT_PORT_OFFSET = 34


def assign_ports(layout: Layout) -> None:
    layout.ports.clear()
    grouped: dict[tuple[str, str], list] = {}
    for edge in layout.edges:
        if edge.class_name != "relationship-edge":
            continue
        grouped.setdefault((edge.source, edge.source_side or "auto"), []).append(edge)
        grouped.setdefault((edge.target, edge.target_side or "auto"), []).append(edge)

    for (node_id, side), edges in grouped.items():
        if side not in VALID_SIDES:
            continue
        if side in {"top", "bottom"}:
            edges.sort(key=lambda edge: other_node(layout, edge, node_id).x)
        else:
            edges.sort(key=lambda edge: other_node(layout, edge, node_id).y)
        for index, edge in enumerate(edges):
            slot = centered_slot(index, len(edges))
            port = make_port(layout.nodes[node_id], side, slot, offset=DEFAULT_PORT_OFFSET)
            layout.ports[(edge.source, edge.target, edge.label, node_id)] = port


def other_node(layout: Layout, edge, node_id: str) -> Node:
    return layout.nodes[edge.target if edge.source == node_id else edge.source]


def edge_port(layout: Layout, edge, node_id: str, offset: float = DEFAULT_PORT_OFFSET) -> Port:
    existing = layout.ports.get((edge.source, edge.target, edge.label, node_id))
    if existing is not None and offset == DEFAULT_PORT_OFFSET:
        return existing
    side = edge.source_side if node_id == edge.source else edge.target_side
    if side not in VALID_SIDES:
        node = layout.nodes[node_id]
        other = other_node(layout, edge, node_id)
        side = dominant_side(node, other)
    slot = existing.slot if existing is not None else 0
    return make_port(layout.nodes[node_id], side, slot, offset)


def make_port(node: Node, side: str, slot: float, offset: float) -> Port:
    if node.kind == "relationship":
        return make_diamond_port(node, side, slot, offset)
    rect = node.rect
    horizontal_step = min(34, max(20, rect.width / 4))
    vertical_step = min(30, max(16, rect.height / 3))
    if side == "top":
        x = clamp(node.x + slot * horizontal_step, rect.left + 10, rect.right - 10)
        return Port(node.id, side, slot, (x, rect.top), (x, rect.top - offset), (0, -1))
    if side == "bottom":
        x = clamp(node.x + slot * horizontal_step, rect.left + 10, rect.right - 10)
        return Port(node.id, side, slot, (x, rect.bottom), (x, rect.bottom + offset), (0, 1))
    if side == "left":
        y = clamp(node.y + slot * vertical_step, rect.top + 8, rect.bottom - 8)
        return Port(node.id, side, slot, (rect.left, y), (rect.left - offset, y), (-1, 0))
    y = clamp(node.y + slot * vertical_step, rect.top + 8, rect.bottom - 8)
    return Port(node.id, side, slot, (rect.right, y), (rect.right + offset, y), (1, 0))


def make_diamond_port(node: Node, side: str, slot: float, offset: float) -> Port:
    rect = node.rect
    rx = node.width / 2
    ry = node.height / 2
    horizontal_step = min(30, max(18, rect.width / 5))
    vertical_step = min(26, max(14, rect.height / 4))
    if side in {"top", "bottom"}:
        dx = clamp(slot * horizontal_step, -rx + 8, rx - 8)
        y_offset = ry * (1 - abs(dx) / rx)
        y = node.y - y_offset if side == "top" else node.y + y_offset
        direction = (0, -1) if side == "top" else (0, 1)
        return Port(node.id, side, slot, (node.x + dx, y), (node.x + dx, y + direction[1] * offset), direction)
    dy = clamp(slot * vertical_step, -ry + 8, ry - 8)
    x_offset = rx * (1 - abs(dy) / ry)
    x = node.x - x_offset if side == "left" else node.x + x_offset
    direction = (-1, 0) if side == "left" else (1, 0)
    return Port(node.id, side, slot, (x, node.y + dy), (x + direction[0] * offset, node.y + dy), direction)
