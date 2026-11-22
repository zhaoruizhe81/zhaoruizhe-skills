from __future__ import annotations

import math

from .model import (
    AttributeSpec,
    Edge,
    EntitySpec,
    Layout,
    Node,
    Rect,
    attribute_size,
    centered_slot,
    effective_attribute_mode,
    normalize_angle,
    node_radius,
)

COMPACT_SIDE_GAP = 36
COMPACT_STACK_GAP = 14


def place_attributes(spec, layout: Layout) -> None:
    relationship_angles = relationship_angles_by_entity(layout)
    relationship_nodes = [node for node in layout.nodes.values() if node.kind == "relationship"]
    layout_center = entity_centroid(layout)
    for entity_id, entity in spec.entities.items():
        attrs = visible_attributes(entity)
        if not attrs:
            continue
        entity_node = layout.nodes[entity_id]
        territory = layout.territories.get(entity_id)
        positions = attribute_positions(
            entity,
            entity_node,
            attrs,
            relationship_angles.get(entity_id, []),
            territory.attribute_rect if territory else None,
            len(spec.entities),
            layout_center,
            relationship_nodes,
            layout,
        )
        for attr, (x, y) in zip(attrs, positions):
            width, height = attribute_size(attr.label)
            node_id = f"attr:{entity_id}.{attr.id}"
            node = Node(
                node_id,
                attr.label,
                "attribute",
                x,
                y,
                width,
                height,
                owner=entity_id,
                key=attr.key,
                multivalued=attr.multivalued,
                derived=attr.derived,
            )
            layout.nodes[node_id] = node
            layout.edges.append(Edge(entity_id, node_id, "", "attribute-edge"))
    for rel in spec.relationships:
        if not rel.attributes:
            continue
        rel_node_id = f"rel:{rel.id}"
        rel_node = layout.nodes.get(rel_node_id)
        if rel_node is None:
            continue
        for i, attr in enumerate(rel.attributes):
            width, height = attribute_size(attr.label)
            widths = [attribute_size(a.label)[0] for a in rel.attributes]
            placed = place_relationship_attr(rel_node, attr, i, len(rel.attributes), widths)
            node_id = f"attr:{rel.id}.{attr.id}"
            node = Node(
                node_id,
                attr.label,
                "attribute",
                placed[0], placed[1],
                width, height,
                owner=rel_node_id,
                key=attr.key,
                multivalued=attr.multivalued,
                derived=attr.derived,
            )
            layout.nodes[node_id] = node
            layout.edges.append(Edge(rel_node_id, node_id, "", "attribute-edge"))


def place_relationship_attr(rel_node: Node, attr: AttributeSpec, index: int, total: int,
                            widths: list[int] | None = None) -> tuple[float, float]:
    offset_y = 72
    offset_x = -80
    if total == 1:
        positions = [(rel_node.x + offset_x, rel_node.y - offset_y)]
    elif total == 2:
        positions = [
            (rel_node.x + offset_x, rel_node.y - offset_y),
            (rel_node.x + offset_x, rel_node.y + offset_y),
        ]
    else:
        # 3 个及以上联系属性分多行排布在菱形下方（每行最多 2 个）：
        # 单行太宽会同时压到左右两侧实体的属性扇区
        offset_y_row = 88
        row_gap_y = 60
        gap = 14
        if widths is None:
            widths = [90] * total
        per_row = 2
        positions = []
        for i in range(total):
            row = i // per_row
            col = i % per_row
            row_widths = widths[row * per_row:(row + 1) * per_row]
            row_width = sum(row_widths) + gap * (len(row_widths) - 1)
            # 行左端钳制：不越过菱形中心左侧太远，避免压到左侧实体的属性扇区
            cursor = max(rel_node.x - row_width / 2 + 60, rel_node.x - 60)
            for j in range(col):
                cursor += row_widths[j] + gap
            y = rel_node.y + offset_y_row + row * row_gap_y
            positions.append((cursor + widths[i] / 2, y))
    return positions[index]


def visible_attributes(entity: EntitySpec) -> list[AttributeSpec]:
    if entity.layout.attributes_mode == "hidden":
        return []
    if entity.layout.attributes_mode == "keys_only":
        return [attr for attr in entity.attributes if attr.key]
    return entity.attributes


def relationship_angles_by_entity(layout: Layout) -> dict[str, list[float]]:
    result: dict[str, list[float]] = {}
    for edge in layout.edges:
        if edge.class_name != "relationship-edge":
            continue
        source = layout.nodes[edge.source]
        target = layout.nodes[edge.target]
        if source.kind == "entity":
            result.setdefault(source.id, []).append(normalize_angle(math.atan2(target.y - source.y, target.x - source.x)))
        if target.kind == "entity":
            result.setdefault(target.id, []).append(normalize_angle(math.atan2(source.y - target.y, source.x - target.x)))
    return result


def attribute_positions(
    entity: EntitySpec,
    entity_node: Node,
    attrs: list[AttributeSpec],
    avoid_angles: list[float],
    attribute_rect: Rect | None,
    entity_count: int,
    layout_center: tuple[float, float],
    relationship_nodes: list[Node],
    layout: Layout,
) -> list[tuple[float, float]]:
    mode = effective_attribute_mode(entity_count, len(attrs), entity.layout.attributes_mode)
    if mode == "compact":
        side = entity.layout.attributes_side or best_compact_side(
            entity_node,
            attrs,
            avoid_angles,
            layout_center,
            attribute_rect,
            relationship_nodes,
            layout,
        )
        return compact_positions(entity_node, attrs, side, attribute_rect)
    return radial_positions(entity_node, attrs, avoid_angles, entity.layout.attributes_side, attribute_rect)


def entity_centroid(layout: Layout) -> tuple[float, float]:
    entities = [node for node in layout.nodes.values() if node.kind == "entity"]
    if not entities:
        return 0.0, 0.0
    return (
        sum(node.x for node in entities) / len(entities),
        sum(node.y for node in entities) / len(entities),
    )


def compact_positions(
    entity_node: Node,
    attrs: list[AttributeSpec],
    side: str,
    attribute_rect: Rect | None,
) -> list[tuple[float, float]]:
    positions: list[tuple[float, float]] = []
    sizes = [attribute_size(attr.label) for attr in attrs]
    horizontal_gap = max((size[0] for size in sizes), default=84) + COMPACT_STACK_GAP
    vertical_gap = max((size[1] for size in sizes), default=42) + COMPACT_STACK_GAP
    for index, attr in enumerate(attrs):
        width, height = sizes[index]
        slot = centered_slot(index, len(attrs))
        if side == "top":
            x = entity_node.x + slot * horizontal_gap
            y = entity_node.rect.top - COMPACT_SIDE_GAP - height / 2
        elif side == "bottom":
            x = entity_node.x + slot * horizontal_gap
            y = entity_node.rect.bottom + COMPACT_SIDE_GAP + height / 2
        elif side == "left":
            x = entity_node.rect.left - COMPACT_SIDE_GAP - width / 2
            y = entity_node.y + slot * vertical_gap
        else:
            x = entity_node.rect.right + COMPACT_SIDE_GAP + width / 2
            y = entity_node.y + slot * vertical_gap
        positions.append(clamp_to_attribute_rect(x, y, width, height, attribute_rect))
    return positions


def radial_positions(
    entity_node: Node,
    attrs: list[AttributeSpec],
    avoid_angles: list[float],
    preferred_side: str | None,
    attribute_rect: Rect | None,
) -> list[tuple[float, float]]:
    max_attr_radius = max((math.hypot(*attribute_size(attr.label)) / 2 for attr in attrs), default=32)
    base_ring = node_radius(entity_node) + max_attr_radius + 58
    min_chord = max_attr_radius * 2 + 22
    count_ring = min_chord / (2 * math.sin(math.pi / max(len(attrs), 2)))
    ring = max(base_ring, count_ring)
    angles = free_angles(len(attrs), avoid_angles, preferred_side)
    positions: list[tuple[float, float]] = []
    for attr, angle in zip(attrs, angles):
        width, height = attribute_size(attr.label)
        x = entity_node.x + math.cos(angle) * ring
        y = entity_node.y + math.sin(angle) * ring
        positions.append(clamp_to_attribute_rect(x, y, width, height, attribute_rect))
    return positions


def free_angles(count: int, avoid_angles: list[float], preferred_side: str | None) -> list[float]:
    if count <= 0:
        return []
    if not avoid_angles or count >= 8:
        start = side_angle(preferred_side) if preferred_side else -math.pi / 2
        step = math.pi * 2 / count
        return [normalize_angle(start + step * index) for index in range(count)]
    segments = free_segments(avoid_angles, gap=0.55)
    preferred = side_angle(preferred_side) if preferred_side else None
    if preferred is not None:
        segments.sort(key=lambda seg: angle_distance(preferred, (seg[0] + seg[1]) / 2), reverse=False)
    total = sum(end - start for start, end in segments) or math.pi * 2
    allocations = [max(0, round(count * (end - start) / total)) for start, end in segments]
    while sum(allocations) < count:
        idx = max(range(len(segments)), key=lambda i: segments[i][1] - segments[i][0])
        allocations[idx] += 1
    while sum(allocations) > count:
        for idx in range(len(allocations) - 1, -1, -1):
            if allocations[idx] > 0:
                allocations[idx] -= 1
                break
    result: list[float] = []
    for (start, end), amount in zip(segments, allocations):
        if amount <= 0:
            continue
        step = (end - start) / amount
        for i in range(amount):
            result.append(normalize_angle(start + step * (i + 0.5)))
    return result[:count]


def free_segments(avoid_angles: list[float], gap: float) -> list[tuple[float, float]]:
    angles = sorted(normalize_angle(angle) for angle in avoid_angles)
    if not angles:
        return [(0, math.pi * 2)]
    segments: list[tuple[float, float]] = []
    total = math.pi * 2
    for index, angle in enumerate(angles):
        next_angle = angles[(index + 1) % len(angles)]
        if index == len(angles) - 1:
            next_angle += total
        start = angle + gap / 2
        end = next_angle - gap / 2
        if end > start:
            segments.append((start, end))
    return segments or [(0, total)]


def clamp_to_attribute_rect(
    x: float,
    y: float,
    width: float,
    height: float,
    attribute_rect: Rect | None,
) -> tuple[float, float]:
    if attribute_rect is None:
        return x, y
    min_x = attribute_rect.left + width / 2
    max_x = attribute_rect.right - width / 2
    min_y = attribute_rect.top + height / 2
    max_y = attribute_rect.bottom - height / 2
    if min_x > max_x:
        cx = (attribute_rect.left + attribute_rect.right) / 2
    else:
        cx = max(min_x, min(max_x, x))
    if min_y > max_y:
        cy = (attribute_rect.top + attribute_rect.bottom) / 2
    else:
        cy = max(min_y, min(max_y, y))
    return cx, cy


def best_side_from_avoid(avoid_angles: list[float]) -> str:
    sides = ["top", "right", "bottom", "left"]
    return max(sides, key=lambda side: min((angle_distance(side_angle(side), angle) for angle in avoid_angles), default=999))


def best_compact_side(
    entity_node: Node,
    attrs: list[AttributeSpec],
    avoid_angles: list[float],
    layout_center: tuple[float, float],
    attribute_rect: Rect | None,
    relationship_nodes: list[Node],
    layout: Layout,
) -> str:
    sides = fitting_compact_sides(entity_node, attrs, attribute_rect)
    inward = unit_vector(layout_center[0] - entity_node.x, layout_center[1] - entity_node.y)
    return max(
        sides,
        key=lambda side: (
            compact_side_score(side, entity_node, attrs, avoid_angles, inward, attribute_rect, relationship_nodes, layout),
            -abs(side_angle(side)),
        ),
    )


def fitting_compact_sides(
    entity_node: Node,
    attrs: list[AttributeSpec],
    attribute_rect: Rect | None,
) -> list[str]:
    sides = ["top", "right", "bottom", "left"]
    if attribute_rect is None:
        return sides
    result = []
    for side in sides:
        rects = compact_attribute_rects(entity_node, attrs, side, attribute_rect)
        internal_overlaps, _ = compact_side_internal_overlap_penalty(rects)
        if side_alignment_penalty(side, entity_node, rects) == 0 and internal_overlaps == 0:
            result.append(side)
    return result or sides


def compact_side_score(
    side: str,
    entity_node: Node,
    attrs: list[AttributeSpec],
    avoid_angles: list[float],
    inward: tuple[float, float],
    attribute_rect: Rect | None,
    relationship_nodes: list[Node],
    layout: Layout,
) -> float:
    angle = side_angle(side)
    relationship_clearance = min((angle_distance(angle, avoid) for avoid in avoid_angles), default=math.pi)
    side_vec = (math.cos(angle), math.sin(angle))
    inward_score = side_vec[0] * inward[0] + side_vec[1] * inward[1]
    rects = compact_attribute_rects(entity_node, attrs, side, attribute_rect)
    group_rect = union_rects(rects)
    obstacles = compact_side_obstacles(layout, entity_node)
    internal_overlap_count, internal_overlap_depth = compact_side_internal_overlap_penalty(rects)
    overlap_count, overlap_depth = compact_side_node_overlap_penalty(rects, obstacles)
    nearest_clearance = nearest_rect_clearance(group_rect, obstacles)
    outward_clearance = directional_clearance(side, group_rect, obstacles)
    growth_penalty = canvas_growth_penalty(layout, group_rect)
    alignment_penalty = side_alignment_penalty(side, entity_node, rects)
    relationship_overlap_penalty = compact_side_relationship_overlaps(entity_node, attrs, side, attribute_rect, relationship_nodes)
    return (
        relationship_clearance * 1.7
        + min(nearest_clearance, 260) / 70
        + min(outward_clearance, 320) / 80
        + inward_score * 0.3
        - internal_overlap_count * 180
        - internal_overlap_depth * 5
        - overlap_count * 160
        - overlap_depth * 5
        - relationship_overlap_penalty * 80
        - growth_penalty / 140
        - alignment_penalty * 120
    )


def compact_side_internal_overlap_penalty(rects: list[Rect]) -> tuple[int, float]:
    count = 0
    depth = 0.0
    for index, rect in enumerate(rects):
        inflated = rect.inflate(2)
        for other in rects[index + 1 :]:
            distance = rect_distance(inflated, other.inflate(2))
            if distance < 0:
                count += 1
                depth += -distance
    return count, depth


def compact_attribute_rects(
    entity_node: Node,
    attrs: list[AttributeSpec],
    side: str,
    attribute_rect: Rect | None,
) -> list[Rect]:
    positions = compact_positions(entity_node, attrs, side, attribute_rect)
    rects: list[Rect] = []
    for attr, (x, y) in zip(attrs, positions):
        width, height = attribute_size(attr.label)
        rects.append(Rect(x - width / 2, y - height / 2, x + width / 2, y + height / 2))
    return rects


def compact_side_obstacles(layout: Layout, entity_node: Node) -> list[Rect]:
    obstacles: list[Rect] = []
    for node in layout.nodes.values():
        if node.id == entity_node.id:
            continue
        if node.kind == "attribute" and node.owner == entity_node.id:
            continue
        margin = 16 if node.kind == "relationship" else 8
        obstacles.append(node.rect.inflate(margin))
    return obstacles


def compact_side_node_overlap_penalty(rects: list[Rect], obstacles: list[Rect]) -> tuple[int, float]:
    count = 0
    depth = 0.0
    for rect in rects:
        inflated = rect.inflate(8)
        for obstacle in obstacles:
            distance = rect_distance(inflated, obstacle)
            if distance < 0:
                count += 1
                depth += -distance
    return count, depth


def nearest_rect_clearance(rect: Rect, obstacles: list[Rect]) -> float:
    if not obstacles:
        return 260.0
    return max(0.0, min(rect_distance(rect, obstacle) for obstacle in obstacles))


def directional_clearance(side: str, rect: Rect, obstacles: list[Rect]) -> float:
    distances: list[float] = []
    for obstacle in obstacles:
        if side == "top" and intervals_overlap(rect.left, rect.right, obstacle.left, obstacle.right) and obstacle.bottom <= rect.top:
            distances.append(rect.top - obstacle.bottom)
        elif side == "bottom" and intervals_overlap(rect.left, rect.right, obstacle.left, obstacle.right) and obstacle.top >= rect.bottom:
            distances.append(obstacle.top - rect.bottom)
        elif side == "left" and intervals_overlap(rect.top, rect.bottom, obstacle.top, obstacle.bottom) and obstacle.right <= rect.left:
            distances.append(rect.left - obstacle.right)
        elif side == "right" and intervals_overlap(rect.top, rect.bottom, obstacle.top, obstacle.bottom) and obstacle.left >= rect.right:
            distances.append(obstacle.left - rect.right)
    return min(distances) if distances else 260.0


def canvas_growth_penalty(layout: Layout, candidate: Rect) -> float:
    base_rects = [node.rect for node in layout.nodes.values()]
    if not base_rects:
        return 0.0
    base = union_rects(base_rects)
    expanded = union_rects([base, candidate])
    return max(0.0, expanded.width - base.width) + max(0.0, expanded.height - base.height)


def side_alignment_penalty(side: str, entity_node: Node, rects: list[Rect]) -> int:
    count = 0
    for rect in rects:
        if side == "top" and rect.bottom > entity_node.rect.top - 4:
            count += 1
        elif side == "bottom" and rect.top < entity_node.rect.bottom + 4:
            count += 1
        elif side == "left" and rect.right > entity_node.rect.left - 4:
            count += 1
        elif side == "right" and rect.left < entity_node.rect.right + 4:
            count += 1
    return count


def union_rects(rects: list[Rect]) -> Rect:
    return Rect(
        min(rect.left for rect in rects),
        min(rect.top for rect in rects),
        max(rect.right for rect in rects),
        max(rect.bottom for rect in rects),
    )


def rect_distance(left: Rect, right: Rect) -> float:
    dx = max(right.left - left.right, left.left - right.right, 0)
    dy = max(right.top - left.bottom, left.top - right.bottom, 0)
    if dx or dy:
        return math.hypot(dx, dy)
    x_overlap = min(left.right, right.right) - max(left.left, right.left)
    y_overlap = min(left.bottom, right.bottom) - max(left.top, right.top)
    return -min(x_overlap, y_overlap)


def intervals_overlap(left_start: float, left_end: float, right_start: float, right_end: float) -> bool:
    return not (left_end < right_start or left_start > right_end)


def compact_side_relationship_overlaps(
    entity_node: Node,
    attrs: list[AttributeSpec],
    side: str,
    attribute_rect: Rect | None,
    relationship_nodes: list[Node],
) -> int:
    positions = compact_positions(entity_node, attrs, side, attribute_rect)
    count = 0
    for attr, (x, y) in zip(attrs, positions):
        width, height = attribute_size(attr.label)
        attr_rect = Rect(x - width / 2, y - height / 2, x + width / 2, y + height / 2)
        for rel_node in relationship_nodes:
            if attr_rect.inflate(8).intersects(rel_node.rect.inflate(8)):
                count += 1
    return count


def side_angle(side: str | None) -> float:
    return {"right": 0, "bottom": math.pi / 2, "left": math.pi, "top": -math.pi / 2}.get(side or "top", -math.pi / 2)


def angle_to_side(angle: float) -> str:
    c = math.cos(angle)
    s = math.sin(angle)
    if abs(c) >= abs(s):
        return "right" if c >= 0 else "left"
    return "bottom" if s >= 0 else "top"


def angle_distance(left: float, right: float) -> float:
    diff = abs(normalize_angle(left) - normalize_angle(right))
    return min(diff, math.pi * 2 - diff)


def unit_vector(dx: float, dy: float) -> tuple[float, float]:
    length = math.hypot(dx, dy)
    if length < 1e-6:
        return 0.0, 0.0
    return dx / length, dy / length
