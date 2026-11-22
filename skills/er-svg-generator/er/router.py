from __future__ import annotations

import heapq
import math

from .geometry import crossing_count, path_obstacle_hits, simplify_path
from .model import GRID, Edge, Layout, Node, Port, Rect, euclidean_path_length, manhattan_path_length, path_segments, turn_count
from .port_solver import solve_relationship_route


def route_all_edges(layout: Layout) -> None:
    layout.paths.clear()
    layout.edge_labels.clear()
    layout.ports.clear()
    layout.route_kinds.clear()
    used_segments: list[tuple[tuple[float, float], tuple[float, float]]] = []
    relationship_edges = sorted(
        [edge for edge in layout.edges if edge.class_name == "relationship-edge"],
        key=lambda edge: euclidean_between(layout.nodes[edge.source], layout.nodes[edge.target]),
        reverse=False,
    )
    for edge in relationship_edges:
        path, kind = route_relationship_edge(layout, edge, used_segments)
        key = edge_key(edge)
        layout.paths[key] = path
        layout.route_kinds[key] = kind
        used_segments.extend(path_segments(path))
    if len(relationship_edges) <= 32:
        optimize_relationship_routes(layout, relationship_edges)
    for edge in relationship_edges:
        label = edge_display_label(edge)
        if label:
            layout.edge_labels.append(
                (label, *relationship_label_position(layout, edge, layout.paths[edge_key(edge)]))
            )
    for edge in [edge for edge in layout.edges if edge.class_name == "attribute-edge"]:
        path = route_attribute_edge(layout, edge)
        key = edge_key(edge)
        layout.paths[key] = path
        layout.route_kinds[key] = "attribute"


def route_relationship_edge(
    layout: Layout,
    edge: Edge,
    used_segments: list[tuple[tuple[float, float], tuple[float, float]]],
) -> tuple[list[tuple[float, float]], str]:
    excluded = relationship_edge_exclusions(layout, edge)
    obstacles = obstacle_rects(layout, excluded, margin=10)
    direct_path = direct_relationship_path(layout, edge)
    if not path_obstacle_hits(direct_path, obstacles) and not crossing_count(direct_path, used_segments):
        return direct_path, "direct"
    path, kind, source_port, target_port = solve_relationship_route(
        layout,
        edge,
        used_segments,
        obstacles,
        relationship_candidates,
        lambda source_port, target_port: astar_route(source_port, target_port, obstacles, layout),
    )
    if path_obstacle_hits(path, obstacles):
        astar_path = astar_route(source_port, target_port, obstacles, layout)
        if astar_path and not path_obstacle_hits(astar_path, obstacles):
            return astar_path, "astar"
    return path, kind


def relationship_edge_exclusions(layout: Layout, edge: Edge) -> set[str]:
    excluded = {edge.source, edge.target}
    if edge.class_name == "relationship-edge":
        excluded.update(
            other_edge.source
            for other_edge in layout.edges
            if other_edge.class_name == "relationship-edge" and other_edge.target == edge.target
        )
    return excluded


def direct_relationship_path(layout: Layout, edge: Edge) -> list[tuple[float, float]]:
    source = layout.nodes[edge.source]
    target = layout.nodes[edge.target]
    target_anchor = relationship_cardinal_anchor(target, edge.target_side or dominant_side(target, source))
    source_anchor = node_boundary(source, target_anchor[0] - source.x, target_anchor[1] - source.y)
    return [source_anchor, target_anchor]


def relationship_cardinal_anchor(node: Node, side: str) -> tuple[float, float]:
    rect = node.rect
    if side == "top":
        return node.x, rect.top
    if side == "bottom":
        return node.x, rect.bottom
    if side == "left":
        return rect.left, node.y
    return rect.right, node.y


def optimize_relationship_routes(layout: Layout, relationship_edges: list[Edge]) -> None:
    for _ in range(1):
        changed = False
        for edge in relationship_edges:
            key = edge_key(edge)
            obstacles = obstacle_rects(layout, {edge.source, edge.target}, margin=10)
            other_segments = [
                segment
                for other in relationship_edges
                if other is not edge
                for segment in path_segments(layout.paths.get(edge_key(other), []))
            ]
            current = layout.paths[key]
            current_score = global_route_score(current, obstacles, other_segments)
            best_path, best_kind = route_relationship_edge(layout, edge, other_segments)
            best_score = global_route_score(best_path, obstacles, other_segments)
            if best_score + 1e-6 < current_score:
                layout.paths[key] = best_path
                layout.route_kinds[key] = best_kind
                changed = True
        if not changed:
            break


def global_route_score(
    path: list[tuple[float, float]],
    obstacles: list[Rect],
    other_segments: list[tuple[tuple[float, float], tuple[float, float]]],
) -> float:
    return (
        path_obstacle_hits(path, obstacles) * 1000
        + crossing_count(path, other_segments) * 1000
        + manhattan_path_length(path)
        + turn_count(path) * 30
    )


def relationship_candidates(source: Port, target: Port) -> list[tuple[list[tuple[float, float]], str]]:
    s = source.anchor
    t = target.anchor
    so = source.outside
    to = target.outside
    candidates: list[tuple[list[tuple[float, float]], str]] = []
    candidates.append((simplify_path([s, so, to, t]), "straight"))
    candidates.append((simplify_path([s, so, (to[0], so[1]), to, t]), "l"))
    candidates.append((simplify_path([s, so, (so[0], to[1]), to, t]), "l"))
    mid_x = (so[0] + to[0]) / 2
    mid_y = (so[1] + to[1]) / 2
    candidates.append((simplify_path([s, so, (mid_x, so[1]), (mid_x, to[1]), to, t]), "z"))
    candidates.append((simplify_path([s, so, (so[0], mid_y), (to[0], mid_y), to, t]), "z"))
    for offset in (88, -88, 160, -160):
        x = so[0] + offset
        candidates.append((simplify_path([s, so, (x, so[1]), (x, to[1]), to, t]), "u"))
        y = so[1] + offset
        candidates.append((simplify_path([s, so, (so[0], y), (to[0], y), to, t]), "u"))
    min_x, max_x = sorted((so[0], to[0]))
    min_y, max_y = sorted((so[1], to[1]))
    for x in (min_x - 180, max_x + 180):
        candidates.append((simplify_path([s, so, (x, so[1]), (x, to[1]), to, t]), "u"))
    for y in (min_y - 180, max_y + 180):
        candidates.append((simplify_path([s, so, (so[0], y), (to[0], y), to, t]), "u"))
    return candidates


def route_attribute_edge(layout: Layout, edge: Edge) -> list[tuple[float, float]]:
    source = layout.nodes[edge.source]
    target = layout.nodes[edge.target]
    dx = target.x - source.x
    dy = target.y - source.y
    return [node_boundary(source, dx, dy), node_boundary(target, -dx, -dy)]


def node_boundary(node: Node, dx: float, dy: float) -> tuple[float, float]:
    if node.kind == "relationship":
        return diamond_boundary(node, dx, dy)
    if node.kind == "attribute":
        return ellipse_boundary(node, dx, dy)
    return rect_boundary(node.rect, dx, dy)


def rect_boundary(rect, dx: float, dy: float) -> tuple[float, float]:
    if dx == 0 and dy == 0:
        return rect.center
    cx, cy = rect.center
    scale_x = (rect.width / 2) / abs(dx) if dx else float("inf")
    scale_y = (rect.height / 2) / abs(dy) if dy else float("inf")
    scale = min(scale_x, scale_y)
    return cx + dx * scale, cy + dy * scale


def ellipse_boundary(node: Node, dx: float, dy: float) -> tuple[float, float]:
    if dx == 0 and dy == 0:
        return node.x, node.y
    rx, ry = node.width / 2, node.height / 2
    scale = 1 / math.sqrt((dx * dx) / (rx * rx) + (dy * dy) / (ry * ry))
    return node.x + dx * scale, node.y + dy * scale


def diamond_boundary(node: Node, dx: float, dy: float) -> tuple[float, float]:
    if dx == 0 and dy == 0:
        return node.x, node.y
    rx, ry = node.width / 2, node.height / 2
    scale = 1 / ((abs(dx) / rx) + (abs(dy) / ry))
    return node.x + dx * scale, node.y + dy * scale


def astar_route(source: Port, target: Port, obstacles: list[Rect], layout: Layout) -> list[tuple[float, float]] | None:
    start = snap_point(source.outside)
    end = snap_point(target.outside)
    bounds = routing_bounds(layout, [start, end])
    if blocked(start, obstacles) or blocked(end, obstacles):
        return None
    directions = [(1, 0), (-1, 0), (0, 1), (0, -1)]
    start_state = (start[0], start[1], source.direction)
    heap = [(heuristic(start, end), 0, 0, start_state)]
    best = {start_state: 0}
    came: dict[tuple[int, int, tuple[int, int]], tuple[int, int, tuple[int, int]]] = {}
    counter = 0
    while heap and counter < 60000:
        _, _, cost, state = heapq.heappop(heap)
        x, y, previous_direction = state
        if (x, y) == end:
            path = reconstruct(state, came)
            return simplify_path([source.anchor, source.outside, *path[1:-1], target.outside, target.anchor])
        for direction in directions:
            nx, ny = x + direction[0] * GRID, y + direction[1] * GRID
            if not bounds.contains(nx, ny) or blocked((nx, ny), obstacles):
                continue
            next_state = (nx, ny, direction)
            turn_penalty = 0 if direction == previous_direction else 24
            new_cost = cost + GRID + turn_penalty
            if new_cost >= best.get(next_state, float("inf")):
                continue
            best[next_state] = new_cost
            came[next_state] = state
            counter += 1
            heapq.heappush(heap, (new_cost + heuristic((nx, ny), end), counter, new_cost, next_state))
    return None


def reconstruct(state, came) -> list[tuple[float, float]]:
    states = [state]
    while state in came:
        state = came[state]
        states.append(state)
    states.reverse()
    return [(x, y) for x, y, _ in states]


def snap_point(point: tuple[float, float]) -> tuple[int, int]:
    return round(point[0] / GRID) * GRID, round(point[1] / GRID) * GRID


def routing_bounds(layout: Layout, extra: list[tuple[float, float]]) -> Rect:
    rects = [node.rect for node in layout.nodes.values()]
    min_x = min([rect.left for rect in rects] + [p[0] for p in extra]) - 120
    max_x = max([rect.right for rect in rects] + [p[0] for p in extra]) + 120
    min_y = min([rect.top for rect in rects] + [p[1] for p in extra]) - 120
    max_y = max([rect.bottom for rect in rects] + [p[1] for p in extra]) + 120
    return Rect(min_x, min_y, max_x, max_y)


def blocked(point: tuple[int, int], obstacles: list[Rect]) -> bool:
    return any(obstacle.contains(*point) for obstacle in obstacles)


def heuristic(left: tuple[int, int], right: tuple[int, int]) -> float:
    return abs(left[0] - right[0]) + abs(left[1] - right[1])


def obstacle_rects(layout: Layout, excluded: set[str], margin: float) -> list[Rect]:
    obstacles: list[Rect] = []
    for entity_id, territory in layout.territories.items():
        if entity_id not in excluded:
            obstacles.append(territory.outer_rect.inflate(margin))
    for node_id, node in layout.nodes.items():
        if node_id in excluded or node.kind in {"entity", "attribute"}:
            continue
        obstacles.append(node.rect.inflate(margin))
    return obstacles



def edge_display_label(edge: Edge) -> str:
    return edge.display_label if edge.display_label is not None else edge.label


def relationship_label_position(layout: Layout, edge: Edge, path: list[tuple[float, float]]) -> tuple[float, float]:
    if not path:
        node = layout.nodes[edge.target]
        return node.x, node.y

    relationship_node = layout.nodes[edge.target]
    anchor = path[-1]
    dx = anchor[0] - relationship_node.x
    dy = anchor[1] - relationship_node.y
    distance = math.hypot(dx, dy)
    if distance < 1e-6 and len(path) >= 2:
        dx = path[-2][0] - anchor[0]
        dy = path[-2][1] - anchor[1]
        distance = math.hypot(dx, dy)
    if distance < 1e-6:
        return anchor[0], anchor[1] - 16

    ux = dx / distance
    uy = dy / distance
    x = anchor[0] + ux * 20
    y = anchor[1] + uy * 20
    if abs(ux) >= abs(uy):
        y -= 13
    else:
        x += 13
    return x, y


def edge_key(edge: Edge) -> tuple[str, str, str]:
    return edge.source, edge.target, edge.label


def euclidean_between(left: Node, right: Node) -> float:
    return math.hypot(left.x - right.x, left.y - right.y)
