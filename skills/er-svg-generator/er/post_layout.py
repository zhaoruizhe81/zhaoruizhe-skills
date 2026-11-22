from __future__ import annotations

import math

from .attributes import place_attributes
from .layout import compact_layout, rebuild_territories
from .model import Layout, node_radius
from .ports import assign_ports


def apply_post_layout(layout: Layout, mode: str) -> None:
    if mode == "none":
        return
    if mode in {"align", "align-arrange"}:
        align_core(layout)
        rebuild_territories(layout)
    if mode in {"arrange", "align-arrange"}:
        arrange_relationship_midpoints(layout)
        remove_attributes(layout)
        rebuild_territories(layout)
        place_attributes(layout.spec, layout)
    layout.paths.clear()
    layout.edge_labels.clear()
    layout.route_kinds.clear()
    assign_ports(layout)
    compact_layout(layout)


def align_core(layout: Layout) -> None:
    entities = [node for node in layout.nodes.values() if node.kind == "entity"]
    if len(entities) < 2:
        return
    entities.sort(key=lambda node: (-relationship_degree(layout, node.id), node.x, node.y))
    start_x = min(node.x for node in entities)
    y = sum(node.y for node in entities) / len(entities)
    for index, node in enumerate(entities):
        node.x = start_x + index * 190
        node.y = y
    arrange_relationship_midpoints(layout)


def arrange_relationship_midpoints(layout: Layout) -> None:
    rel_entities: dict[str, list[str]] = {}
    for edge in layout.edges:
        if edge.class_name != "relationship-edge":
            continue
        rel_entities.setdefault(edge.target, []).append(edge.source)
    grouped: dict[tuple[str, ...], list[str]] = {}
    for rel_id, entities in rel_entities.items():
        key = tuple(sorted(entities))
        grouped.setdefault(key, []).append(rel_id)
    for rel_ids in grouped.values():
        rel_ids.sort()
        offset_mid = (len(rel_ids) - 1) / 2
        entities = rel_entities[rel_ids[0]]
        if len(entities) < 2:
            continue
        a = layout.nodes[entities[0]]
        b = layout.nodes[entities[1]]
        dx, dy = b.x - a.x, b.y - a.y
        dist = math.hypot(dx, dy) or 1
        px, py = -dy / dist, dx / dist
        for index, rel_id in enumerate(rel_ids):
            rel = layout.nodes[rel_id]
            old_mid_x = (a.x + b.x) / 2
            old_mid_y = (a.y + b.y) / 2
            current_offset = (rel.x - old_mid_x) * px + (rel.y - old_mid_y) * py
            auto_offset = (index - offset_mid) * (node_radius(rel) * 2 + 14)
            offset = current_offset if abs(current_offset) > 1 else auto_offset
            rel.x = old_mid_x + px * offset
            rel.y = old_mid_y + py * offset
            push_relationship_out_of_territories(layout, rel, set(rel_entities[rel_id]), (px, py))


def remove_attributes(layout: Layout) -> None:
    attr_ids = {node_id for node_id, node in layout.nodes.items() if node.kind == "attribute"}
    for node_id in attr_ids:
        del layout.nodes[node_id]
    layout.edges = [edge for edge in layout.edges if edge.source not in attr_ids and edge.target not in attr_ids and edge.class_name != "attribute-edge"]


def push_relationship_out_of_territories(layout: Layout, rel, participants: set[str], normal: tuple[float, float]) -> None:
    nx, ny = normal
    if abs(nx) < 1e-9 and abs(ny) < 1e-9:
        nx, ny = 0, 1
    base_x, base_y = rel.x, rel.y
    for step in range(8):
        for sign in ([1, -1] if step else [1]):
            rel.x = base_x + nx * sign * step * 60
            rel.y = base_y + ny * sign * step * 60
            if not relationship_intersects_foreign_territory(layout, rel, participants):
                return
    rel.x, rel.y = base_x, base_y


def relationship_intersects_foreign_territory(layout: Layout, rel, participants: set[str]) -> bool:
    rel_rect = rel.rect.inflate(8)
    for entity_id, territory in layout.territories.items():
        if entity_id in participants:
            continue
        if rel_rect.intersects(territory.outer_rect):
            return True
    return False


def resolve_overlaps(layout: Layout) -> None:
    nodes = list(layout.nodes.values())
    for _ in range(140):
        moved = 0.0
        for index, left in enumerate(nodes):
            for right in nodes[index + 1 :]:
                dx, dy = right.x - left.x, right.y - left.y
                dist = math.hypot(dx, dy) or 0.01
                minimum = node_radius(left) + node_radius(right) + 8
                if dist >= minimum:
                    continue
                push = (minimum - dist) / 2
                nx, ny = dx / dist, dy / dist
                left.x -= nx * push
                left.y -= ny * push
                right.x += nx * push
                right.y += ny * push
                moved = max(moved, push)
        if moved < 0.3:
            break


def relationship_degree(layout: Layout, entity_id: str) -> int:
    return sum(1 for edge in layout.edges if edge.class_name == "relationship-edge" and edge.source == entity_id)
