from __future__ import annotations

import math

from .attributes import place_attributes
from .model import (
    ERSpec,
    Edge,
    Layout,
    Node,
    Rect,
    Territory,
    attribute_size,
    centered_slot,
    compute_territory_circle_radius,
    dominant_side,
    effective_attribute_mode,
    entity_size,
    relationship_size,
)
from .ports import assign_ports
from .topology import choose_center, entity_adjacency, entity_weights


BEAM_WIDTH = 7
CANDIDATES_PER_ENTITY = 12
ORTHOGONAL_RELATION_BIAS = 0.35
TERRITORY_CLEARANCE_EPSILON = 1e-6
RELATIONSHIP_CENTER_PULL_MAX = 0.3
RELATIONSHIP_CENTER_PULL_DEADZONE = 80.0
RELATIONSHIP_CENTER_PULL_DISTANCE = 900.0
COMPACTION_MAX_ROUNDS = 4
COMPACTION_MIN_IMPROVEMENT = 0.996
HARD_METRIC_WEIGHTS = {
    "relationship_crossings": 50000,
    "relationship_obstacle_hits": 60000,
    "territory_overlaps": 100000,
    "attribute_out_of_territory": 100000,
    "relationship_crosses_territory": 80000,
    "node_overlaps": 40000,
}


def build_layout(spec: ERSpec) -> Layout:
    layout = Layout(spec=spec)
    positions, placement_order = entity_positions(spec)
    layout.placement_order = placement_order
    for entity_id, (x, y) in positions.items():
        entity = spec.entities[entity_id]
        width, height = entity_size(entity.label)
        layout.nodes[entity_id] = Node(entity_id, entity.label, "entity", x, y, width, height)
    rebuild_territories(layout)

    add_relationships(spec, layout)
    place_attributes(spec, layout)
    resolve_relationship_node_overlaps(layout)
    assign_ports(layout)
    compact_layout(layout)
    return layout


def entity_positions(spec: ERSpec) -> tuple[dict[str, tuple[float, float]], dict[str, int]]:
    return greedy_entity_positions(spec)


def compact_layout(layout: Layout) -> None:
    spec = layout.spec
    if has_complete_manual_layout(spec):
        return
    if len(spec.entities) >= 16:
        return
    movable = set(spec.entities) - manual_entity_ids(spec)
    if not movable or len(spec.entities) < 2:
        return

    adjacency = entity_adjacency(spec)
    best = evaluate_compaction_layout(layout, entity_node_positions(layout))
    if best is None:
        return
    best_layout = best[0]
    best_score = best[1]
    best_hard = best[2]
    best_stats = best[3]
    best_positions = entity_node_positions(best_layout)

    for _ in range(compaction_round_limit(spec)):
        improved = False
        for positions in compaction_candidates(spec, best_positions, movable, adjacency):
            resolved = resolve_circle_territory_positions(spec, positions)
            candidate = evaluate_compaction_layout(layout, resolved, max_pre_route_hard=best_hard)
            if candidate is None:
                continue
            candidate_layout, candidate_score, candidate_hard, candidate_stats = candidate
            if not accepts_compaction(spec, candidate_score, candidate_hard, candidate_stats, best_score, best_hard, best_stats):
                continue
            best_layout = candidate_layout
            best_score = candidate_score
            best_hard = candidate_hard
            best_stats = candidate_stats
            best_positions = entity_node_positions(best_layout)
            improved = True
        if not improved:
            break

    if best_layout is not layout and best_positions != entity_node_positions(layout):
        copy_layout_contents(layout, best_layout)


def has_complete_manual_layout(spec: ERSpec) -> bool:
    if not spec.entities:
        return False
    relationships_manual = all(has_relationship_position_override(spec, relationship.id) for relationship in spec.relationships)
    return all(has_entity_position_override(spec, entity_id) for entity_id in spec.entities) and relationships_manual


def manual_entity_ids(spec: ERSpec) -> set[str]:
    return {entity_id for entity_id in spec.entities if has_entity_position_override(spec, entity_id)}


def has_relationship_position_override(spec: ERSpec, relationship_id: str) -> bool:
    if relationship_id in spec.layout.relationship_positions:
        return True
    return any(
        relationship.id == relationship_id and relationship.layout.x is not None and relationship.layout.y is not None
        for relationship in spec.relationships
    )


def entity_node_positions(layout: Layout) -> dict[str, tuple[float, float]]:
    return {
        entity_id: (layout.nodes[entity_id].x, layout.nodes[entity_id].y)
        for entity_id in layout.spec.entities
        if entity_id in layout.nodes
    }


def evaluate_compaction_layout(
    source_layout: Layout,
    positions: dict[str, tuple[float, float]],
    max_pre_route_hard: float | None = None,
) -> tuple[Layout, float, float, dict[str, float | int]] | None:
    from .render_svg import tight_diagram_bounds
    from .router import route_all_edges
    from .stats import route_stats

    candidate = layout_from_entity_positions(source_layout, positions)
    pre_route_hard = pre_route_hard_metric_penalty(candidate)
    if max_pre_route_hard is not None and pre_route_hard > max_pre_route_hard:
        return None
    route_all_edges(candidate)
    stats = route_stats(candidate)
    bounds = tight_diagram_bounds(candidate, padding=0)
    area = max(1.0, bounds.width * bounds.height)
    hard = hard_metric_penalty(stats)
    score = (
        hard * 1_000_000
        + area * 0.018
        + float(stats["total_relationship_length"]) * 10
        + float(stats["max_relationship_length"]) * 24
        + float(stats["relationship_bends"]) * 180
        + float(stats["aspect_ratio_penalty"]) * 350
    )
    return candidate, score, hard, stats


def layout_from_entity_positions(source_layout: Layout, positions: dict[str, tuple[float, float]]) -> Layout:
    candidate = Layout(spec=source_layout.spec)
    candidate.debug_territory = source_layout.debug_territory
    candidate.placement_order = dict(source_layout.placement_order)
    populate_layout_from_entity_positions(candidate, positions)
    return candidate


def populate_layout_from_entity_positions(layout: Layout, positions: dict[str, tuple[float, float]]) -> None:
    layout.nodes.clear()
    layout.edges.clear()
    layout.paths.clear()
    layout.edge_labels.clear()
    layout.ports.clear()
    layout.route_kinds.clear()
    layout.territories.clear()
    for entity_id, entity in layout.spec.entities.items():
        x, y = positions[entity_id]
        width, height = entity_size(entity.label)
        layout.nodes[entity_id] = Node(entity_id, entity.label, "entity", x, y, width, height)
    rebuild_territories(layout)
    add_relationships(layout.spec, layout)
    place_attributes(layout.spec, layout)
    resolve_relationship_node_overlaps(layout)
    assign_ports(layout)


def hard_metric_penalty(stats: dict[str, float | int]) -> float:
    return sum(float(stats[key]) * weight for key, weight in HARD_METRIC_WEIGHTS.items())


def pre_route_hard_metric_penalty(layout: Layout) -> float:
    from .stats import attribute_out_of_territory_count, node_overlap_count, territory_overlap_count

    stats = {
        "relationship_crossings": 0,
        "relationship_obstacle_hits": 0,
        "territory_overlaps": territory_overlap_count(layout),
        "attribute_out_of_territory": attribute_out_of_territory_count(layout),
        "relationship_crosses_territory": 0,
        "node_overlaps": node_overlap_count(layout),
    }
    return hard_metric_penalty(stats)


def accepts_compaction(
    spec: ERSpec,
    candidate_score: float,
    candidate_hard: float,
    candidate_stats: dict[str, float | int],
    best_score: float,
    best_hard: float,
    best_stats: dict[str, float | int],
) -> bool:
    if candidate_hard > best_hard:
        return False
    if len(spec.entities) <= 8 and candidate_hard == best_hard == 0:
        if candidate_stats["total_relationship_length"] > best_stats["total_relationship_length"] + 0.5:
            return False
    if candidate_hard < best_hard:
        return True
    return candidate_score < best_score * COMPACTION_MIN_IMPROVEMENT


def copy_layout_contents(target: Layout, source: Layout) -> None:
    target.nodes = source.nodes
    target.edges = source.edges
    target.paths = source.paths
    target.edge_labels = source.edge_labels
    target.ports = source.ports
    target.route_kinds = source.route_kinds
    target.territories = source.territories
    target.debug_territory = source.debug_territory
    target.placement_order = source.placement_order


def compaction_candidates(
    spec: ERSpec,
    positions: dict[str, tuple[float, float]],
    movable: set[str],
    adjacency: dict[str, set[str]],
) -> list[dict[str, tuple[float, float]]]:
    center = compaction_center(positions, movable)
    candidates: list[dict[str, tuple[float, float]]] = []
    scale_values = (0.9, 0.82) if len(spec.entities) >= 16 else (0.9, 0.82, 0.74)
    axis_values = (0.86,) if len(spec.entities) >= 16 else (0.86, 0.76)
    pull_values = (0.22,) if len(spec.entities) >= 16 else (0.18, 0.3)
    neighbor_values = (0.28,) if len(spec.entities) >= 16 else (0.22, 0.36)
    for scale in scale_values:
        candidates.append(scale_positions(positions, movable, center, scale, scale))
    for scale in axis_values:
        candidates.append(scale_positions(positions, movable, center, scale, 1.0))
        candidates.append(scale_positions(positions, movable, center, 1.0, scale))
    for amount in pull_values:
        candidates.append(pull_positions(positions, movable, center, amount))
    for amount in neighbor_values:
        candidates.append(pull_to_neighbor_centroids(positions, movable, adjacency, amount, leaves_only=False))
        candidates.append(pull_to_neighbor_centroids(positions, movable, adjacency, amount, leaves_only=True))
    return unique_position_maps(candidates)


def compaction_round_limit(spec: ERSpec) -> int:
    return 3 if len(spec.entities) >= 16 else COMPACTION_MAX_ROUNDS


def compaction_center(positions: dict[str, tuple[float, float]], movable: set[str]) -> tuple[float, float]:
    fixed = [point for entity_id, point in positions.items() if entity_id not in movable]
    points = fixed or list(positions.values())
    return (
        sum(point[0] for point in points) / len(points),
        sum(point[1] for point in points) / len(points),
    )


def scale_positions(
    positions: dict[str, tuple[float, float]],
    movable: set[str],
    center: tuple[float, float],
    scale_x: float,
    scale_y: float,
) -> dict[str, tuple[float, float]]:
    result = dict(positions)
    for entity_id in movable:
        x, y = result[entity_id]
        result[entity_id] = (
            center[0] + (x - center[0]) * scale_x,
            center[1] + (y - center[1]) * scale_y,
        )
    return result


def pull_positions(
    positions: dict[str, tuple[float, float]],
    movable: set[str],
    target: tuple[float, float],
    amount: float,
) -> dict[str, tuple[float, float]]:
    result = dict(positions)
    for entity_id in movable:
        x, y = result[entity_id]
        result[entity_id] = (x * (1 - amount) + target[0] * amount, y * (1 - amount) + target[1] * amount)
    return result


def pull_to_neighbor_centroids(
    positions: dict[str, tuple[float, float]],
    movable: set[str],
    adjacency: dict[str, set[str]],
    amount: float,
    leaves_only: bool,
) -> dict[str, tuple[float, float]]:
    result = dict(positions)
    for entity_id in movable:
        neighbors = [neighbor for neighbor in adjacency.get(entity_id, set()) if neighbor in positions]
        if not neighbors or (leaves_only and len(neighbors) != 1):
            continue
        target = (
            sum(positions[neighbor][0] for neighbor in neighbors) / len(neighbors),
            sum(positions[neighbor][1] for neighbor in neighbors) / len(neighbors),
        )
        x, y = result[entity_id]
        result[entity_id] = (x * (1 - amount) + target[0] * amount, y * (1 - amount) + target[1] * amount)
    return result


def unique_position_maps(candidates: list[dict[str, tuple[float, float]]]) -> list[dict[str, tuple[float, float]]]:
    result: list[dict[str, tuple[float, float]]] = []
    seen: set[tuple[tuple[str, int, int], ...]] = set()
    for candidate in candidates:
        key = tuple(sorted((entity_id, round(point[0]), round(point[1])) for entity_id, point in candidate.items()))
        if key in seen:
            continue
        seen.add(key)
        result.append(candidate)
    return result


def resolve_circle_territory_positions(spec: ERSpec, positions: dict[str, tuple[float, float]]) -> dict[str, tuple[float, float]]:
    fixed = set(spec.layout.entity_positions)
    for entity_id, entity in spec.entities.items():
        if entity.layout.x is not None and entity.layout.y is not None:
            fixed.add(entity_id)
    result = dict(positions)
    ids = list(result)
    for _ in range(80):
        moved = 0.0
        for index, left_id in enumerate(ids):
            for right_id in ids[index + 1 :]:
                lx, ly = result[left_id]
                rx, ry = result[right_id]
                dx, dy = rx - lx, ry - ly
                distance = math.hypot(dx, dy) or 0.01
                minimum = territory_radius(spec, left_id) + territory_radius(spec, right_id)
                if distance >= minimum:
                    continue
                push = (minimum - distance) / 2 + 0.5
                nx, ny = dx / distance, dy / distance
                if left_id in fixed and right_id in fixed:
                    continue
                if left_id in fixed:
                    result[right_id] = (rx + nx * push * 2, ry + ny * push * 2)
                elif right_id in fixed:
                    result[left_id] = (lx - nx * push * 2, ly - ny * push * 2)
                else:
                    result[left_id] = (lx - nx * push, ly - ny * push)
                    result[right_id] = (rx + nx * push, ry + ny * push)
                moved = max(moved, push)
        if moved < 0.5:
            break
    return result


def greedy_entity_positions(spec: ERSpec) -> tuple[dict[str, tuple[float, float]], dict[str, int]]:
    root = choose_center(spec)
    adjacency = entity_adjacency(spec)
    weights = entity_weights(spec)
    order = {entity_id: index for index, entity_id in enumerate(spec.entities)}
    beam_width = layout_beam_width(spec)
    candidate_limit = layout_candidates_per_entity(spec)
    root_position = entity_position_override(spec, root, 760.0, 600.0)
    beam: list[tuple[dict[str, tuple[float, float]], dict[str, int], set[str], float]] = [
        ({root: root_position}, {root: 1}, set(spec.entities) - {root}, 0.0)
    ]

    while any(unplaced for _, _, unplaced, _ in beam):
        expanded: list[tuple[dict[str, tuple[float, float]], dict[str, int], set[str], float]] = []
        for positions, placement_order, unplaced, _ in beam:
            if not unplaced:
                expanded.append((positions, placement_order, unplaced, partial_layout_score(spec, positions, adjacency)))
                continue
            entity_id = next_greedy_entity(spec, adjacency, weights, positions, unplaced, order)
            placed_neighbors = sorted(
                adjacency.get(entity_id, set()) & positions.keys(),
                key=lambda neighbor_id: (-weights[neighbor_id]["degree"], order[neighbor_id]),
            )
            candidates = candidate_points_for_entity(spec, entity_id, positions, placed_neighbors)
            scored_candidates = sorted(
                ((greedy_position_score(spec, entity_id, point, positions, placed_neighbors), point) for point in candidates),
                key=lambda item: item[0],
            )[:candidate_limit]

            for _, point in scored_candidates:
                next_positions = dict(positions)
                next_positions[entity_id] = point
                next_order = dict(placement_order)
                next_order[entity_id] = len(next_order) + 1
                next_unplaced = set(unplaced)
                next_unplaced.remove(entity_id)
                expanded.append((next_positions, next_order, next_unplaced, partial_layout_score(spec, next_positions, adjacency)))

        if not expanded:
            break
        expanded.sort(key=lambda state: state[3])
        cutoff = expanded[0][3] + 120000
        beam = [state for state in expanded if state[3] <= cutoff][:beam_width]

    best_positions: dict[str, tuple[float, float]] | None = None
    best_order: dict[str, int] | None = None
    best_score = float("inf")
    for positions, placement_order, _, _ in beam:
        resolved = resolve_circle_territory_positions(spec, positions)
        score = partial_layout_score(spec, resolved, adjacency)
        if score < best_score:
            best_score = score
            best_positions = resolved
            best_order = placement_order
    return best_positions or {}, best_order or {}


def layout_beam_width(spec: ERSpec) -> int:
    return 4 if len(spec.entities) >= 16 else BEAM_WIDTH


def layout_candidates_per_entity(spec: ERSpec) -> int:
    return 8 if len(spec.entities) >= 16 else CANDIDATES_PER_ENTITY


def candidate_points_for_entity(
    spec: ERSpec,
    entity_id: str,
    positions: dict[str, tuple[float, float]],
    placed_neighbors: list[str],
) -> list[tuple[float, float]]:
    if has_entity_position_override(spec, entity_id):
        return [entity_position_override(spec, entity_id, *fallback_tree_position(spec, positions, entity_id))]
    candidates = greedy_circle_candidates(spec, entity_id, positions, placed_neighbors)
    if not candidates:
        candidates = isolated_entity_candidates(spec, entity_id, positions)
    return candidates


def partial_layout_score(
    spec: ERSpec,
    positions: dict[str, tuple[float, float]],
    adjacency: dict[str, set[str]],
) -> float:
    score = 0.0
    max_related_distance = 0.0
    items = list(positions.items())
    for index, (left_id, left_point) in enumerate(items):
        left_radius = territory_radius(spec, left_id)
        for right_id, right_point in items[index + 1 :]:
            right_radius = territory_radius(spec, right_id)
            distance = math.dist(left_point, right_point)
            clearance = distance - left_radius - right_radius
            if clearance < -TERRITORY_CLEARANCE_EPSILON:
                score += abs(clearance) * 100000
            elif right_id in adjacency.get(left_id, set()):
                clearance = max(0.0, clearance)
                score += clearance * 14 + distance * 3.0
                score += relationship_axis_penalty(left_point, right_point) * ORTHOGONAL_RELATION_BIAS
                max_related_distance = max(max_related_distance, distance)
            else:
                clearance = max(0.0, clearance)
                score += clearance * 0.15
    score += max_related_distance * 4
    for entity_id, point in positions.items():
        if not adjacency.get(entity_id):
            score += isolated_zone_penalty(spec, entity_id, point, positions)
    score += placed_canvas_penalty(positions) * 2
    return score


def next_greedy_entity(
    spec: ERSpec,
    adjacency: dict[str, set[str]],
    weights: dict[str, dict[str, float]],
    positions: dict[str, tuple[float, float]],
    unplaced: set[str],
    order: dict[str, int],
) -> str:
    return min(
        unplaced,
        key=lambda entity_id: (
            -len(adjacency.get(entity_id, set()) & positions.keys()),
            -weights[entity_id]["degree"],
            -weights[entity_id]["topology"],
            -(spec.entities[entity_id].layout.priority or 0),
            spec.entities[entity_id].layout.order if spec.entities[entity_id].layout.order is not None else 999,
            order[entity_id],
        ),
    )


def has_entity_position_override(spec: ERSpec, entity_id: str) -> bool:
    entity = spec.entities[entity_id]
    return entity_id in spec.layout.entity_positions or (entity.layout.x is not None and entity.layout.y is not None)


def greedy_circle_candidates(
    spec: ERSpec,
    entity_id: str,
    positions: dict[str, tuple[float, float]],
    placed_neighbors: list[str],
) -> list[tuple[float, float]]:
    if not placed_neighbors:
        return []
    candidates: list[tuple[float, float]] = []
    anchors = placed_neighbors[:4]
    relevant = relevant_circle_ids(spec, entity_id, positions, anchors, limit=4)
    if len(relevant) >= 2:
        for left_index, left_id in enumerate(relevant):
            for right_id in relevant[left_index + 1 :]:
                candidates.extend(two_circle_candidates(spec, entity_id, left_id, right_id, positions))
        candidates.extend(multi_circle_projection_candidates(spec, entity_id, relevant, positions))
    for anchor_id in anchors[:3]:
        candidates.extend(one_circle_candidates(spec, entity_id, anchor_id, positions))
    if len(spec.entities) < 16:
        candidates.extend(inward_clearance_candidates(spec, entity_id, positions, anchors))
    return unique_points(candidates)


def isolated_entity_candidates(
    spec: ERSpec,
    entity_id: str,
    positions: dict[str, tuple[float, float]],
) -> list[tuple[float, float]]:
    if not positions:
        return [fallback_tree_position(spec, positions, entity_id)]

    candidate_radius = territory_radius(spec, entity_id)
    placed = list(positions.items())
    min_x = min(point[0] - territory_radius(spec, placed_id) for placed_id, point in placed)
    max_x = max(point[0] + territory_radius(spec, placed_id) for placed_id, point in placed)
    min_y = min(point[1] - territory_radius(spec, placed_id) for placed_id, point in placed)
    max_y = max(point[1] + territory_radius(spec, placed_id) for placed_id, point in placed)
    center = ((min_x + max_x) / 2, (min_y + max_y) / 2)
    gap = max(36.0, spec.layout.territory_port_lane)
    left = min_x - candidate_radius - gap
    right = max_x + candidate_radius + gap
    top = min_y - candidate_radius - gap
    bottom = max_y + candidate_radius + gap

    zone = spec.entities[entity_id].layout.zone
    zone_direction = normalized_zone_vector(zone)
    candidates = []
    if zone_direction != (0.0, 0.0):
        candidates.append(isolated_ray_candidate(spec, entity_id, positions, zone_direction, gap))
    for direction in ((1, 0), (0, 1), (-1, 0), (0, -1), (1, 1), (-1, 1), (1, -1), (-1, -1)):
        unit = unit_vector(*direction)
        if unit != zone_direction:
            candidates.append(isolated_ray_candidate(spec, entity_id, positions, unit, gap))
    by_zone = {
        "left": [(left, center[1]), (left, top), (left, bottom)],
        "far_left": [(left, center[1]), (left, top), (left, bottom)],
        "right": [(right, center[1]), (right, top), (right, bottom)],
        "far_right": [(right, center[1]), (right, top), (right, bottom)],
        "top": [(center[0], top), (left, top), (right, top)],
        "bottom": [(center[0], bottom), (left, bottom), (right, bottom)],
        "lower_left": [(left, bottom), (left, center[1]), (center[0], bottom)],
        "lower_right": [(right, bottom), (right, center[1]), (center[0], bottom)],
    }
    candidates.extend(by_zone.get(zone or "", []))
    candidates.extend(
        [
            (right, center[1]),
            (right, bottom),
            (center[0], bottom),
            (left, bottom),
            (left, center[1]),
            (left, top),
            (center[0], top),
            (right, top),
            fallback_tree_position(spec, positions, entity_id),
        ]
    )
    return unique_points(candidates)


def isolated_ray_candidate(
    spec: ERSpec,
    entity_id: str,
    positions: dict[str, tuple[float, float]],
    direction: tuple[float, float],
    gap: float,
) -> tuple[float, float]:
    center = placed_centroid(positions)
    candidate_radius = territory_radius(spec, entity_id)

    def clear_at(distance: float) -> bool:
        point = (center[0] + direction[0] * distance, center[1] + direction[1] * distance)
        return all(
            math.dist(point, other_point) >= candidate_radius + territory_radius(spec, other_id) + gap
            for other_id, other_point in positions.items()
        )

    high = max(spec.layout.spacing_x, spec.layout.spacing_y, candidate_radius + gap)
    for _ in range(16):
        if clear_at(high):
            break
        high *= 1.35
    low = 0.0
    for _ in range(48):
        mid = (low + high) / 2
        if clear_at(mid):
            high = mid
        else:
            low = mid
    return center[0] + direction[0] * high, center[1] + direction[1] * high


def relevant_circle_ids(
    spec: ERSpec,
    entity_id: str,
    positions: dict[str, tuple[float, float]],
    anchors: list[str],
    limit: int,
) -> list[str]:
    result: list[str] = []
    for anchor_id in anchors:
        if anchor_id in positions and anchor_id not in result:
            result.append(anchor_id)
        if len(result) >= limit:
            return result
    if anchors:
        focus = (
            sum(positions[anchor_id][0] for anchor_id in anchors) / len(anchors),
            sum(positions[anchor_id][1] for anchor_id in anchors) / len(anchors),
        )
    else:
        focus = placed_centroid(positions)
    blockers = [
        other_id
        for other_id in positions
        if other_id != entity_id and other_id not in result
    ]
    blockers.sort(
        key=lambda other_id: (
            math.dist(focus, positions[other_id]) - territory_radius(spec, other_id),
            -len(spec.entities[other_id].layout.near),
            other_id,
        )
    )
    for blocker_id in blockers:
        result.append(blocker_id)
        if len(result) >= limit:
            break
    return result


def one_circle_candidates(
    spec: ERSpec,
    entity_id: str,
    anchor_id: str,
    positions: dict[str, tuple[float, float]],
) -> list[tuple[float, float]]:
    anchor = positions[anchor_id]
    radius = entity_circle_distance(spec, entity_id, anchor_id)
    centroid = placed_centroid(positions)
    directions = [
        normalized_zone_vector(spec.entities[entity_id].layout.zone),
        unit_vector(anchor[0] - centroid[0], anchor[1] - centroid[1]),
        (1.0, 0.0),
        (-1.0, 0.0),
        (0.0, -1.0),
        (0.0, 1.0),
        unit_vector(1, 1),
        unit_vector(-1, 1),
        unit_vector(1, -1),
        unit_vector(-1, -1),
    ]
    return [(anchor[0] + dx * radius, anchor[1] + dy * radius) for dx, dy in directions if (dx, dy) != (0.0, 0.0)]


def two_circle_candidates(
    spec: ERSpec,
    entity_id: str,
    left_id: str,
    right_id: str,
    positions: dict[str, tuple[float, float]],
) -> list[tuple[float, float]]:
    left = positions[left_id]
    right = positions[right_id]
    left_radius = entity_circle_distance(spec, entity_id, left_id)
    right_radius = entity_circle_distance(spec, entity_id, right_id)
    intersections = circle_intersections(left, left_radius, right, right_radius)
    if intersections:
        return intersections
    return closest_two_circle_points(left, left_radius, right, right_radius)


def multi_circle_projection_candidates(
    spec: ERSpec,
    entity_id: str,
    anchors: list[str],
    positions: dict[str, tuple[float, float]],
) -> list[tuple[float, float]]:
    point = (
        sum(positions[anchor_id][0] for anchor_id in anchors) / len(anchors),
        sum(positions[anchor_id][1] for anchor_id in anchors) / len(anchors),
    )
    candidates = [point]
    for _ in range(18):
        px, py = point
        for anchor_id in anchors:
            ax, ay = positions[anchor_id]
            desired = entity_circle_distance(spec, entity_id, anchor_id)
            dx, dy = px - ax, py - ay
            distance = math.hypot(dx, dy) or 1.0
            correction = (desired - distance) / len(anchors) * 0.42
            px += dx / distance * correction
            py += dy / distance * correction
        point = (px, py)
    candidates.append(point)
    return candidates


def inward_clearance_candidates(
    spec: ERSpec,
    entity_id: str,
    positions: dict[str, tuple[float, float]],
    anchors: list[str],
) -> list[tuple[float, float]]:
    if not anchors:
        return []
    focus = (
        sum(positions[anchor_id][0] for anchor_id in anchors) / len(anchors),
        sum(positions[anchor_id][1] for anchor_id in anchors) / len(anchors),
    )
    centroid = placed_centroid(positions)
    candidate_radius = territory_radius(spec, entity_id)
    candidates: list[tuple[float, float]] = []
    for target in (focus, centroid):
        dx, dy = target[0] - focus[0], target[1] - focus[1]
        direction = unit_vector(dx, dy)
        if direction == (0.0, 0.0):
            continue
        low, high = 0.0, max(spec.layout.spacing_x, spec.layout.spacing_y)
        for _ in range(16):
            point = (focus[0] + direction[0] * high, focus[1] + direction[1] * high)
            if all(
                math.dist(point, other_point) >= candidate_radius + territory_radius(spec, other_id)
                for other_id, other_point in positions.items()
            ):
                break
            high *= 1.35
        for _ in range(36):
            mid = (low + high) / 2
            point = (focus[0] + direction[0] * mid, focus[1] + direction[1] * mid)
            if all(
                math.dist(point, other_point) >= candidate_radius + territory_radius(spec, other_id)
                for other_id, other_point in positions.items()
            ):
                high = mid
            else:
                low = mid
        candidates.append((focus[0] + direction[0] * high, focus[1] + direction[1] * high))
    return candidates


def greedy_position_score(
    spec: ERSpec,
    entity_id: str,
    point: tuple[float, float],
    positions: dict[str, tuple[float, float]],
    placed_neighbors: list[str],
) -> float:
    score = 0.0
    candidate_radius = territory_radius(spec, entity_id)
    for other_id, other_point in positions.items():
        clearance = math.dist(point, other_point) - (candidate_radius + territory_radius(spec, other_id))
        if clearance < -TERRITORY_CLEARANCE_EPSILON:
            score += abs(clearance) * 1200
        else:
            clearance = max(0.0, clearance)
            score += clearance * 1.6
    for anchor_id in placed_neighbors:
        desired = entity_circle_distance(spec, entity_id, anchor_id)
        distance = math.dist(point, positions[anchor_id])
        score += abs(distance - desired) * 18
        score += distance * 0.8
        score += relationship_axis_penalty(point, positions[anchor_id]) * ORTHOGONAL_RELATION_BIAS
    if len(placed_neighbors) < 2 and len(positions) < 2:
        score += zone_penalty(spec, entity_id, point, positions)
    elif not placed_neighbors:
        score += isolated_zone_penalty(spec, entity_id, point, positions)
    else:
        score += zone_penalty(spec, entity_id, point, positions) * 0.02
    score += canvas_growth_penalty(point, positions)
    return score


def zone_penalty(
    spec: ERSpec,
    entity_id: str,
    point: tuple[float, float],
    positions: dict[str, tuple[float, float]],
) -> float:
    direction = normalized_zone_vector(spec.entities[entity_id].layout.zone)
    if direction == (0.0, 0.0) or not positions:
        return 0.0
    center = placed_centroid(positions)
    dx, dy = unit_vector(point[0] - center[0], point[1] - center[1])
    alignment = dx * direction[0] + dy * direction[1]
    return max(0.0, -alignment) * 260


def isolated_zone_penalty(
    spec: ERSpec,
    entity_id: str,
    point: tuple[float, float],
    positions: dict[str, tuple[float, float]],
) -> float:
    direction = normalized_zone_vector(spec.entities[entity_id].layout.zone)
    if direction == (0.0, 0.0) or len(positions) < 2:
        return 0.0
    other_positions = {other_id: other_point for other_id, other_point in positions.items() if other_id != entity_id}
    if not other_positions:
        return 0.0
    center = placed_centroid(other_positions)
    dx, dy = unit_vector(point[0] - center[0], point[1] - center[1])
    alignment = dx * direction[0] + dy * direction[1]
    return max(0.0, 1.0 - alignment) * 8000


def canvas_growth_penalty(point: tuple[float, float], positions: dict[str, tuple[float, float]]) -> float:
    xs = [item[0] for item in positions.values()] + [point[0]]
    ys = [item[1] for item in positions.values()] + [point[1]]
    width = max(xs) - min(xs)
    height = max(ys) - min(ys)
    if len(positions) < 2 or min(width, height) < 120:
        return (width + height) * 0.16
    return abs(width / max(height, 1) - 1.6) * 140 + (width + height) * 0.16


def placed_canvas_penalty(positions: dict[str, tuple[float, float]]) -> float:
    if len(positions) < 2:
        return 0.0
    xs = [point[0] for point in positions.values()]
    ys = [point[1] for point in positions.values()]
    width = max(xs) - min(xs)
    height = max(ys) - min(ys)
    if len(positions) < 3 or min(width, height) < 120:
        return (width + height) * 0.16
    return abs(width / max(height, 1) - 1.6) * 140 + (width + height) * 0.16


def relationship_axis_penalty(first: tuple[float, float], second: tuple[float, float]) -> float:
    return min(abs(first[0] - second[0]), abs(first[1] - second[1]))


def entity_circle_distance(spec: ERSpec, first_id: str, second_id: str) -> float:
    return territory_radius(spec, first_id) + territory_radius(spec, second_id)


def circle_intersections(
    first: tuple[float, float],
    first_radius: float,
    second: tuple[float, float],
    second_radius: float,
) -> list[tuple[float, float]]:
    dx = second[0] - first[0]
    dy = second[1] - first[1]
    distance = math.hypot(dx, dy)
    if distance < 1e-6:
        return []
    if distance > first_radius + second_radius or distance < abs(first_radius - second_radius):
        return []
    along = (first_radius**2 - second_radius**2 + distance**2) / (2 * distance)
    height_sq = first_radius**2 - along**2
    if height_sq < -1e-6:
        return []
    height = math.sqrt(max(0.0, height_sq))
    ux, uy = dx / distance, dy / distance
    base_x = first[0] + along * ux
    base_y = first[1] + along * uy
    px, py = -uy * height, ux * height
    if height < 1e-6:
        return [(base_x, base_y)]
    return [(base_x + px, base_y + py), (base_x - px, base_y - py)]


def closest_two_circle_points(
    first: tuple[float, float],
    first_radius: float,
    second: tuple[float, float],
    second_radius: float,
) -> list[tuple[float, float]]:
    dx = second[0] - first[0]
    dy = second[1] - first[1]
    direction = unit_vector(dx, dy)
    if direction == (0.0, 0.0):
        return []
    return [
        (first[0] + direction[0] * first_radius, first[1] + direction[1] * first_radius),
        (second[0] - direction[0] * second_radius, second[1] - direction[1] * second_radius),
    ]


def placed_centroid(positions: dict[str, tuple[float, float]]) -> tuple[float, float]:
    return (
        sum(point[0] for point in positions.values()) / len(positions),
        sum(point[1] for point in positions.values()) / len(positions),
    )


def normalized_zone_vector(zone: str | None) -> tuple[float, float]:
    dx, dy = {
        "left": (-1, 0),
        "far_left": (-1, 0),
        "right": (1, 0),
        "far_right": (1, 0),
        "top": (0, -1),
        "bottom": (0, 1),
        "lower_left": (-1, 1),
        "lower_right": (1, 1),
    }.get(zone or "", (0, 0))
    return unit_vector(dx, dy)


def unit_vector(dx: float, dy: float) -> tuple[float, float]:
    length = math.hypot(dx, dy)
    if length < 1e-6:
        return (0.0, 0.0)
    return dx / length, dy / length


def unique_points(points: list[tuple[float, float]]) -> list[tuple[float, float]]:
    result: list[tuple[float, float]] = []
    seen: set[tuple[int, int]] = set()
    for x, y in points:
        key = (round(x), round(y))
        if key in seen:
            continue
        seen.add(key)
        result.append((x, y))
    return result


def fallback_tree_position(spec: ERSpec, positions: dict[str, tuple[float, float]], entity_id: str) -> tuple[float, float]:
    index = len(positions)
    radius = 420 + index * 40
    angle = index * (math.pi * 2 / 7)
    return 760 + math.cos(angle) * radius, 600 + math.sin(angle) * radius


def entity_position_override(spec: ERSpec, entity_id: str, x: float, y: float) -> tuple[float, float]:
    entity = spec.entities[entity_id]
    if entity_id in spec.layout.entity_positions:
        return spec.layout.entity_positions[entity_id]
    if entity.layout.x is not None and entity.layout.y is not None:
        return entity.layout.x, entity.layout.y
    return x, y


_territory_radius_cache: dict[tuple[id, str], float] = {}


def territory_radius(spec: ERSpec, entity_id: str) -> float:
    cache_key = (id(spec), entity_id)
    cached = _territory_radius_cache.get(cache_key)
    if cached is not None:
        return cached
    width, height = estimate_territory_size(spec, entity_id)
    result = compute_territory_circle_radius(len(spec.entities), width, height)
    _territory_radius_cache[cache_key] = result
    return result


def clear_territory_cache() -> None:
    _territory_radius_cache.clear()


def estimate_territory_size(spec: ERSpec, entity_id: str) -> tuple[float, float]:
    entity = spec.entities[entity_id]
    width, height = entity_size(entity.label)
    visible_attrs = [attr for attr in entity.attributes if entity.layout.attributes_mode != "hidden" and (entity.layout.attributes_mode != "keys_only" or attr.key)]
    port_lane = spec.layout.territory_port_lane
    padding = spec.layout.territory_attribute_padding
    if not visible_attrs:
        simple_port_lane = min(port_lane, 24.0)
        simple_padding = min(padding, 14.0)
        return width + simple_port_lane * 2 + simple_padding * 2, height + simple_port_lane * 2 + simple_padding * 2
    attr_sizes = [attribute_size(attr.label) for attr in visible_attrs]
    max_attr_w = max(size[0] for size in attr_sizes)
    max_attr_h = max(size[1] for size in attr_sizes)
    count = len(visible_attrs)
    mode = effective_attribute_mode(len(spec.entities), count, entity.layout.attributes_mode)
    if mode == "compact":
        horizontal_w = max(width, count * (max_attr_w + 14))
        horizontal_h = height + max_attr_h + port_lane + padding * 3 + 14
        vertical_w = width + max_attr_w + port_lane + padding * 3 + 14
        vertical_h = max(height, count * (max_attr_h + 14))
        if entity.layout.attributes_side in {"left", "right"}:
            total_w, total_h = vertical_w, vertical_h
        elif entity.layout.attributes_side in {"top", "bottom"}:
            total_w, total_h = horizontal_w, horizontal_h
        else:
            horizontal_radius = compute_territory_circle_radius(len(spec.entities), horizontal_w, horizontal_h)
            vertical_radius = compute_territory_circle_radius(len(spec.entities), vertical_w, vertical_h)
            if vertical_radius <= horizontal_radius:
                total_w, total_h = vertical_w, vertical_h
            else:
                total_w, total_h = horizontal_w, horizontal_h
    else:
        per_side = max(1, math.ceil(count / 4))
        total_w = max(width + 2 * (max_attr_w + port_lane + padding), per_side * (max_attr_w + 20))
        total_h = max(height + 2 * (max_attr_h + port_lane + padding), per_side * (max_attr_h + 20))
    return total_w + padding * 2, total_h + padding * 2


def rebuild_territories(layout: Layout) -> None:
    layout.territories.clear()
    for entity_id in layout.spec.entities:
        if entity_id not in layout.nodes:
            continue
        entity_node = layout.nodes[entity_id]
        entity = layout.spec.entities[entity_id]
        visible_attrs = [
            attr
            for attr in entity.attributes
            if entity.layout.attributes_mode != "hidden" and (entity.layout.attributes_mode != "keys_only" or attr.key)
        ]
        attr_mode = effective_attribute_mode(len(layout.spec.entities), len(visible_attrs), entity.layout.attributes_mode)
        width, height = estimate_territory_size(layout.spec, entity_id)
        outer = Rect(entity_node.x - width / 2, entity_node.y - height / 2, entity_node.x + width / 2, entity_node.y + height / 2)
        port_lane = layout.spec.layout.territory_port_lane
        attribute_inset = min(port_lane, 12) if attr_mode == "compact" else port_lane
        attribute_rect = outer.inflate(-attribute_inset)
        layout.territories[entity_id] = Territory(
            entity_id=entity_id,
            entity_rect=entity_node.rect,
            attribute_rect=attribute_rect,
            port_lane_rect=entity_node.rect.inflate(port_lane),
            outer_rect=outer,
            safe_gap=layout.spec.layout.territory_safe_gap,
        )


def add_relationships(spec: ERSpec, layout: Layout) -> None:
    circle_obstacles = [
        (entity_id, territory.outer_rect.center, compute_territory_circle_radius(len(layout.spec.entities), territory.outer_rect.width, territory.outer_rect.height))
        for entity_id, territory in layout.territories.items()
    ]
    node_obstacles: list[Rect] = [
        node.rect.inflate(12)
        for node in layout.nodes.values()
        if node.kind == "entity"
    ]
    side_offsets = relationship_side_offsets(spec, layout)
    grouped_pairs: dict[tuple[str, ...], list] = {}
    for relationship in spec.relationships:
        key = tuple(sorted(part.entity for part in relationship.participants))
        grouped_pairs.setdefault(key, []).append(relationship)

    pair_offsets: dict[str, tuple[float, float]] = {}
    for relationships in grouped_pairs.values():
        relationships.sort(key=lambda rel: (rel.layout.order if rel.layout.order is not None else 0, rel.id))
        mid = (len(relationships) - 1) / 2
        for index, rel in enumerate(relationships):
            pair_offsets[rel.id] = (index - mid, len(relationships))

    for relationship in sorted(spec.relationships, key=lambda rel: rel.layout.order if rel.layout.order is not None else 0):
        width, height = relationship_size(relationship.label)
        x, y = relationship_position(spec, layout, relationship, pair_offsets.get(relationship.id, (0, 1))[0], side_offsets.get(relationship.id, (0, 0)))
        participant_ids = [participant.entity for participant in relationship.participants]
        manual_position = (
            relationship.id in spec.layout.relationship_positions
            or (relationship.layout.x is not None and relationship.layout.y is not None)
        )
        if not manual_position:
            x, y = find_free_position(
                x,
                y,
                width,
                height,
                circle_obstacles,
                node_obstacles,
                relationship_gap_candidates(layout, participant_ids),
                allowed_circle_ids=set(participant_ids),
            )
        node_id = f"rel:{relationship.id}"
        layout.nodes[node_id] = Node(node_id, relationship.label, "relationship", x, y, width, height)
        node_obstacles.append(layout.nodes[node_id].rect.inflate(20))
        for participant in relationship.participants:
            entity_node = layout.nodes[participant.entity]
            rel_node = layout.nodes[node_id]
            source_side = effective_participant_side(entity_node, rel_node, participant.side)
            target_side = dominant_side(rel_node, entity_node)
            label = participant_label(participant.role, participant.cardinality)
            layout.edges.append(
                Edge(
                    participant.entity,
                    node_id,
                    label,
                    "relationship-edge",
                    source_side,
                    target_side,
                    display_label=participant.cardinality.strip(),
                )
            )


def resolve_relationship_node_overlaps(layout: Layout) -> None:
    relationship_nodes = [node for node in layout.nodes.values() if node.kind == "relationship"]
    if not relationship_nodes:
        return
    manual_relationships = set(layout.spec.layout.relationship_positions)
    for relationship in layout.spec.relationships:
        if relationship.layout.x is not None and relationship.layout.y is not None:
            manual_relationships.add(relationship.id)
    for _ in range(24):
        moved = 0.0
        for rel in relationship_nodes:
            rel_key = rel.id.removeprefix("rel:")
            if rel_key in manual_relationships:
                continue
            for other in layout.nodes.values():
                if other.id == rel.id or other.kind == "relationship":
                    continue
                if other.kind == "entity" and other.id in relationship_participants(layout, rel.id):
                    continue
                if not rel.rect.inflate(8).intersects(other.rect.inflate(8)):
                    continue
                dx, dy = rel.x - other.x, rel.y - other.y
                nx, ny = unit_vector(dx, dy)
                if (nx, ny) == (0.0, 0.0):
                    nx, ny = 0.0, -1.0
                push = overlap_push_distance(rel.rect.inflate(8), other.rect.inflate(8))
                rel.x += nx * push
                rel.y += ny * push
                moved = max(moved, push)
        if moved < 0.5:
            break


def relationship_participants(layout: Layout, relationship_node_id: str) -> set[str]:
    return {
        edge.source
        for edge in layout.edges
        if edge.class_name == "relationship-edge" and edge.target == relationship_node_id
    }


def overlap_push_distance(first: Rect, second: Rect) -> float:
    x_overlap = min(first.right, second.right) - max(first.left, second.left)
    y_overlap = min(first.bottom, second.bottom) - max(first.top, second.top)
    return max(8.0, min(x_overlap, y_overlap) + 8.0)


def effective_participant_side(entity_node: Node, rel_node: Node, hinted_side: str | None) -> str:
    actual = dominant_side(entity_node, rel_node)
    if hinted_side is None:
        return actual
    if hinted_side == actual:
        return hinted_side
    dx = rel_node.x - entity_node.x
    dy = rel_node.y - entity_node.y
    if hinted_side in {"left", "right"} and abs(dy) > abs(dx) * 0.75:
        return actual
    if hinted_side in {"top", "bottom"} and abs(dx) > abs(dy) * 0.75:
        return actual
    return hinted_side


def relationship_side_offsets(spec: ERSpec, layout: Layout) -> dict[str, tuple[float, float]]:
    grouped: dict[tuple[str, str], list] = {}
    for relationship in spec.relationships:
        participants = [layout.nodes[part.entity] for part in relationship.participants]
        if not participants:
            continue
        center = (
            sum(node.x for node in participants) / len(participants),
            sum(node.y for node in participants) / len(participants),
        )
        for participant in relationship.participants:
            pseudo_rel = Node("_rel_center", "", "relationship", center[0], center[1], 1, 1)
            side = effective_participant_side(layout.nodes[participant.entity], pseudo_rel, participant.side)
            grouped.setdefault((participant.entity, side), []).append(relationship)
    offsets: dict[str, tuple[float, float]] = {}
    for (entity_id, side), relationships in grouped.items():
        relationships.sort(key=lambda rel: (rel.layout.order if rel.layout.order is not None else 0, rel.id))
        for index, relationship in enumerate(relationships):
            slot = centered_slot(index, len(relationships))
            dx, dy = offsets.get(relationship.id, (0.0, 0.0))
            amount = slot * 108
            if side in {"top", "bottom"}:
                dx += amount
            else:
                dy += amount
            offsets[relationship.id] = (dx, dy)
    return offsets


def relationship_position(spec: ERSpec, layout: Layout, relationship, pair_offset: float, side_offset: tuple[float, float]) -> tuple[float, float]:
    if relationship.id in spec.layout.relationship_positions:
        return spec.layout.relationship_positions[relationship.id]
    if relationship.layout.x is not None and relationship.layout.y is not None:
        return relationship.layout.x, relationship.layout.y
    participants = [layout.nodes[part.entity] for part in relationship.participants]
    x = sum(node.x for node in participants) / len(participants)
    y = sum(node.y for node in participants) / len(participants)
    if len(participants) == 2:
        a, b = participants
        dx, dy = b.x - a.x, b.y - a.y
        dist = math.hypot(dx, dy) or 1
        px, py = -dy / dist, dx / dist
        offset = pair_offset * 62
        x += px * offset
        y += py * offset
    x += side_offset[0]
    y += side_offset[1]
    if relationship.layout.side is None:
        x, y = pull_relationship_toward_center(layout, x, y)
    side = relationship.layout.side
    if side == "top":
        y -= 66
    elif side == "bottom":
        y += 66
    elif side == "left":
        x -= 66
    elif side == "right":
        x += 66
    return x, y


def pull_relationship_toward_center(layout: Layout, x: float, y: float) -> tuple[float, float]:
    center = entity_layout_centroid(layout)
    distance = math.hypot(x - center[0], y - center[1])
    if distance <= RELATIONSHIP_CENTER_PULL_DEADZONE:
        return x, y
    amount = min(
        RELATIONSHIP_CENTER_PULL_MAX,
        (distance - RELATIONSHIP_CENTER_PULL_DEADZONE) / RELATIONSHIP_CENTER_PULL_DISTANCE,
    )
    return (
        x * (1 - amount) + center[0] * amount,
        y * (1 - amount) + center[1] * amount,
    )


def entity_layout_centroid(layout: Layout) -> tuple[float, float]:
    entities = [node for node in layout.nodes.values() if node.kind == "entity"]
    if not entities:
        return 0.0, 0.0
    return (
        sum(node.x for node in entities) / len(entities),
        sum(node.y for node in entities) / len(entities),
    )


def participant_label(role: str, cardinality: str) -> str:
    if role and cardinality:
        return f"{role} {cardinality}"
    return role or cardinality


def find_free_position(
    x: float,
    y: float,
    width: float,
    height: float,
    circle_obstacles: list[tuple[str, tuple[float, float], float]],
    node_obstacles: list[Rect],
    preferred_candidates: list[tuple[float, float]] | None = None,
    allowed_circle_ids: set[str] | None = None,
) -> tuple[float, float]:
    best = (x, y)
    clearance_radius = max(width, height) / 2 + 4
    base_candidates = [best]
    if preferred_candidates:
        base_candidates = [best, *preferred_candidates]
    for cx, cy in base_candidates:
        rect = Rect(cx - width / 2, cy - height / 2, cx + width / 2, cy + height / 2).inflate(12)
        if not any(rect.intersects(obstacle) for obstacle in node_obstacles) and not point_hits_circles((cx, cy), clearance_radius, circle_obstacles, allowed_circle_ids or set()):
            return cx, cy
    for ring in range(8):
        step = ring * 28
        candidates = [(x, y)] if ring == 0 else [
            (x + step, y),
            (x - step, y),
            (x, y + step),
            (x, y - step),
            (x + step, y + step),
            (x - step, y + step),
            (x + step, y - step),
            (x - step, y - step),
        ]
        for cx, cy in candidates:
            rect = Rect(cx - width / 2, cy - height / 2, cx + width / 2, cy + height / 2).inflate(12)
            if not any(rect.intersects(obstacle) for obstacle in node_obstacles) and not point_hits_circles((cx, cy), clearance_radius, circle_obstacles, allowed_circle_ids or set()):
                return cx, cy
    return best


def relationship_gap_candidates(layout: Layout, participant_ids: list[str]) -> list[tuple[float, float]]:
    if len(participant_ids) < 2:
        return []
    nodes = [layout.nodes[entity_id] for entity_id in participant_ids if entity_id in layout.nodes]
    if len(nodes) < 2:
        return []
    center = (sum(node.x for node in nodes) / len(nodes), sum(node.y for node in nodes) / len(nodes))
    candidates = [center]
    if len(nodes) == 2:
        left, right = nodes
        dx, dy = right.x - left.x, right.y - left.y
        distance = math.hypot(dx, dy) or 1.0
        ux, uy = dx / distance, dy / distance
        px, py = -uy, ux
        left_radius = layout_territory_circle_radius(layout, left.id)
        right_radius = layout_territory_circle_radius(layout, right.id)
        gap = max(0.0, distance - left_radius - right_radius)
        gap_center = (left.x + ux * (left_radius + gap / 2), left.y + uy * (left_radius + gap / 2))
        candidates.extend([
            gap_center,
            (gap_center[0] + px * 28, gap_center[1] + py * 28),
            (gap_center[0] - px * 28, gap_center[1] - py * 28),
            (left.x + ux * distance * 0.46, left.y + uy * distance * 0.46),
            (left.x + ux * distance * 0.54, left.y + uy * distance * 0.54),
        ])
    return candidates


def layout_territory_circle_radius(layout: Layout, entity_id: str) -> float:
    territory = layout.territories.get(entity_id)
    if territory is None:
        return 0.0
    rect = territory.outer_rect
    return compute_territory_circle_radius(len(layout.spec.entities), rect.width, rect.height)


def point_hits_circles(
    point: tuple[float, float],
    clearance_radius: float,
    circle_obstacles: list[tuple[str, tuple[float, float], float]],
    allowed_circle_ids: set[str],
) -> bool:
    return any(
        entity_id not in allowed_circle_ids and math.dist(point, center) <= radius + clearance_radius
        for entity_id, center, radius in circle_obstacles
    )
