from __future__ import annotations

from dataclasses import dataclass
from heapq import heappop, heappush
from math import atan2, cos, inf, radians, sin

from .geometry import ellipse_boundary_point, segment_intersects_ellipse
from .model import Diagram, Edge, EdgeType, LayoutMode, Node, NodeKind, Point, Rect, RouteMode


@dataclass(frozen=True)
class RouteOptions:
    node_margin: float = 18.0
    duplicate_spacing: float = 10.0
    outer_padding: float = 56.0
    ellipse_margin: float = 6.0


@dataclass(frozen=True)
class Route:
    edge: Edge
    points: list[Point]


def route_edges(diagram: Diagram, options: RouteOptions | None = None) -> list[Route]:
    options = options or RouteOptions()
    groups: dict[tuple[str, str], list[Edge]] = {}
    for edge in diagram.edges:
        groups.setdefault((edge.source, edge.target), []).append(edge)

    routes: list[Route] = []
    seen: dict[tuple[str, str], int] = {}
    for edge in diagram.edges:
        group_key = (edge.source, edge.target)
        index = seen.get(group_key, 0)
        seen[group_key] = index + 1
        routes.append(
            Route(
                edge=edge,
                points=route_edge(
                    edge,
                    diagram.nodes,
                    index,
                    len(groups[group_key]),
                    options,
                    auto_route=False,
                    optimize_ports=diagram.layout.mode is LayoutMode.COMPLEX,
                ),
            )
        )
    return routes


def route_edge(
    edge: Edge,
    nodes: dict[str, Node],
    duplicate_index: int = 0,
    duplicate_total: int = 1,
    options: RouteOptions | None = None,
    *,
    auto_route: bool = False,
    optimize_ports: bool = False,
) -> list[Point]:
    options = options or RouteOptions()
    source = nodes[edge.source]
    target = nodes[edge.target]
    source_side, target_side = _choose_sides(source, target)
    duplicate_offset = (duplicate_index - (duplicate_total - 1) / 2) * options.duplicate_spacing
    start, goal = _connection_points(
        source,
        target,
        nodes,
        source_side,
        target_side,
        duplicate_offset,
        options,
        optimize_straight=edge.resolved_route() is RouteMode.STRAIGHT and optimize_ports,
    )
    obstacles = [
        node.bbox().inflate(options.node_margin)
        for node in nodes.values()
        if node.kind is not NodeKind.BOUNDARY and node.id not in {source.id, target.id}
    ]

    if edge.resolved_route() is RouteMode.STRAIGHT and not auto_route:
        return [start, goal]

    if edge.resolved_route() is RouteMode.STRAIGHT and _segment_is_clear(start, goal, obstacles):
        return [start, goal]

    direct = _simple_route(start, goal, obstacles)
    if direct is not None:
        return _compress(direct)

    return _compress(_astar_route(start, goal, obstacles, nodes.values(), options))


def _choose_sides(source: Node, target: Node) -> tuple[str, str]:
    source_center = source.bbox().center
    target_center = target.bbox().center
    dx = target_center.x - source_center.x
    dy = target_center.y - source_center.y

    if abs(dx) > 8:
        return ("right", "left") if dx >= 0 else ("left", "right")
    return ("bottom", "top") if dy >= 0 else ("top", "bottom")


def _port_offset(side: str, offset: float) -> float:
    if side in {"left", "right", "top", "bottom"}:
        return offset
    return 0.0


def _connection_points(
    source: Node,
    target: Node,
    nodes: dict[str, Node],
    source_side: str,
    target_side: str,
    duplicate_offset: float,
    options: RouteOptions,
    *,
    optimize_straight: bool,
) -> tuple[Point, Point]:
    source_center = source.bbox().center
    target_center = target.bbox().center
    natural_start = _connection_point(source, target_center, source_side, duplicate_offset)
    natural_goal = _connection_point(target, source_center, target_side, duplicate_offset)
    if not optimize_straight:
        return natural_start, natural_goal

    best_key = (10**9, 0.0, 0.0)
    best_points = (natural_start, natural_goal)
    for start in _candidate_points(source, target_center, source_side, duplicate_offset):
        for goal in _candidate_points(target, source_center, target_side, duplicate_offset):
            collisions = len(
                route_usecase_collisions(
                    Edge(source.id, target.id),
                    [start, goal],
                    nodes,
                    padding=options.ellipse_margin,
                )
            )
            port_shift = _manhattan(start, natural_start) + _manhattan(goal, natural_goal)
            line_length = _manhattan(start, goal)
            score_key = (collisions, port_shift, line_length)
            if score_key < best_key:
                best_key = score_key
                best_points = (start, goal)
    return best_points


def _connection_point(node: Node, other_center: Point, side: str, offset: float) -> Point:
    if node.kind is NodeKind.USECASE:
        return _offset_usecase_point(node, other_center, offset, angle_offset=0.0)
    return node.port(side, _port_offset(side, offset))


def _candidate_points(
    node: Node,
    other_center: Point,
    side: str,
    duplicate_offset: float,
) -> list[Point]:
    if node.kind is NodeKind.USECASE:
        return _unique_points(
            [
                _offset_usecase_point(node, other_center, duplicate_offset, angle_offset=angle)
                for angle in (0, -12, 12, -24, 24, -36, 36, -54, 54)
            ]
        )

    if node.kind is NodeKind.ACTOR:
        box = node.bbox()
        if side in {"left", "right"}:
            x = box.left if side == "left" else box.right
            values = [
                box.center.y + duplicate_offset,
                box.top,
                box.top + 12,
                box.top + 24,
                box.bottom - 24,
                box.bottom - 12,
                box.bottom,
            ]
            return _unique_points([Point(x, _clamp(value, box.top, box.bottom)) for value in values])
        if side in {"top", "bottom"}:
            y = box.top if side == "top" else box.bottom
            values = [
                box.center.x + duplicate_offset,
                box.left,
                box.left + 12,
                box.left + 24,
                box.right - 24,
                box.right - 12,
                box.right,
            ]
            return _unique_points([Point(_clamp(value, box.left, box.right), y) for value in values])

    return [node.port(side, _port_offset(side, duplicate_offset))]


def _offset_usecase_point(
    node: Node,
    other_center: Point,
    duplicate_offset: float,
    *,
    angle_offset: float,
) -> Point:
    box = node.bbox()
    if angle_offset == 0:
        point = ellipse_boundary_point(box, other_center)
    else:
        center = box.center
        angle = atan2(other_center.y - center.y, other_center.x - center.x)
        toward = Point(
            center.x + cos(angle + radians(angle_offset)),
            center.y + sin(angle + radians(angle_offset)),
        )
        point = ellipse_boundary_point(box, toward)

    if duplicate_offset == 0:
        return point
    center = box.center
    dx = point.x - center.x
    dy = point.y - center.y
    length = (dx * dx + dy * dy) ** 0.5
    if length == 0:
        return point
    return Point(
        point.x - dy / length * duplicate_offset,
        point.y + dx / length * duplicate_offset,
    )


def route_usecase_collisions(
    edge: Edge,
    points: list[Point],
    nodes: dict[str, Node],
    *,
    padding: float = 6.0,
) -> list[str]:
    collisions: list[str] = []
    for node in nodes.values():
        if node.kind is not NodeKind.USECASE or node.id in {edge.source, edge.target}:
            continue
        if any(
            segment_intersects_ellipse(start, end, node.bbox(), padding=padding)
            for start, end in zip(points, points[1:])
        ):
            collisions.append(node.id)
    return collisions


def _unique_points(points: list[Point]) -> list[Point]:
    result: list[Point] = []
    seen: set[tuple[float, float]] = set()
    for point in points:
        key = (round(point.x, 3), round(point.y, 3))
        if key not in seen:
            result.append(point)
            seen.add(key)
    return result


def _clamp(value: float, lower: float, upper: float) -> float:
    if lower > upper:
        return value
    return max(lower, min(upper, value))


def _simple_route(start: Point, goal: Point, obstacles: list[Rect]) -> list[Point] | None:
    candidates: list[list[Point]] = []
    if start.x == goal.x or start.y == goal.y:
        candidates.append([start, goal])

    mid_x = (start.x + goal.x) / 2
    mid_y = (start.y + goal.y) / 2
    candidates.extend(
        [
            [start, Point(mid_x, start.y), Point(mid_x, goal.y), goal],
            [start, Point(start.x, mid_y), Point(goal.x, mid_y), goal],
            [start, Point(start.x, goal.y), goal],
            [start, Point(goal.x, start.y), goal],
        ]
    )

    for candidate in candidates:
        candidate = _compress(candidate)
        if _path_is_clear(candidate, obstacles):
            return candidate
    return None


def _astar_route(
    start: Point,
    goal: Point,
    obstacles: list[Rect],
    nodes: object,
    options: RouteOptions,
) -> list[Point]:
    x_values, y_values = _build_grid(start, goal, obstacles, nodes, options)
    start_key = _key(start)
    goal_key = _key(goal)
    x_index = {value: index for index, value in enumerate(x_values)}
    y_index = {value: index for index, value in enumerate(y_values)}

    open_set: list[tuple[float, int, float, tuple[float, float]]] = []
    counter = 0
    heappush(open_set, (_manhattan(start, goal), counter, 0.0, start_key))
    came_from: dict[tuple[float, float], tuple[float, float]] = {}
    g_score: dict[tuple[float, float], float] = {start_key: 0.0}

    while open_set:
        _, _, current_cost, current = heappop(open_set)
        if current == goal_key:
            return _reconstruct(came_from, current)
        if current_cost > g_score.get(current, inf):
            continue

        current_point = Point(*current)
        for neighbor in _neighbors(current_point, x_values, y_values, x_index, y_index):
            neighbor_key = _key(neighbor)
            if _point_blocked(neighbor, obstacles):
                continue
            if not _segment_is_clear(current_point, neighbor, obstacles):
                continue

            tentative = current_cost + _manhattan(current_point, neighbor)
            if tentative >= g_score.get(neighbor_key, inf):
                continue

            came_from[neighbor_key] = current
            g_score[neighbor_key] = tentative
            counter += 1
            priority = tentative + _manhattan(neighbor, goal)
            heappush(open_set, (priority, counter, tentative, neighbor_key))

    top_escape = min(start.y, goal.y, *(rect.top for rect in obstacles)) - options.outer_padding
    fallback = [start, Point(start.x, top_escape), Point(goal.x, top_escape), goal]
    return fallback


def _build_grid(
    start: Point,
    goal: Point,
    obstacles: list[Rect],
    nodes: object,
    options: RouteOptions,
) -> tuple[list[float], list[float]]:
    boxes = [node.bbox() for node in nodes if isinstance(node, Node)]
    left = min([start.x, goal.x, *(box.left for box in boxes)] or [0]) - options.outer_padding
    right = max([start.x, goal.x, *(box.right for box in boxes)] or [640]) + options.outer_padding
    top = min([start.y, goal.y, *(box.top for box in boxes)] or [0]) - options.outer_padding
    bottom = max([start.y, goal.y, *(box.bottom for box in boxes)] or [360]) + options.outer_padding

    x_values = {left, right, start.x, goal.x}
    y_values = {top, bottom, start.y, goal.y}
    clearance = 1.0
    for rect in obstacles:
        x_values.update({rect.left - clearance, rect.right + clearance})
        y_values.update({rect.top - clearance, rect.bottom + clearance})

    return sorted(x_values), sorted(y_values)


def _neighbors(
    point: Point,
    x_values: list[float],
    y_values: list[float],
    x_index: dict[float, int],
    y_index: dict[float, int],
) -> list[Point]:
    xi = x_index[point.x]
    yi = y_index[point.y]
    result: list[Point] = []
    if xi > 0:
        result.append(Point(x_values[xi - 1], point.y))
    if xi < len(x_values) - 1:
        result.append(Point(x_values[xi + 1], point.y))
    if yi > 0:
        result.append(Point(point.x, y_values[yi - 1]))
    if yi < len(y_values) - 1:
        result.append(Point(point.x, y_values[yi + 1]))
    return result


def _path_is_clear(points: list[Point], obstacles: list[Rect]) -> bool:
    return all(_segment_is_clear(start, end, obstacles) for start, end in zip(points, points[1:]))


def _segment_is_clear(start: Point, end: Point, obstacles: list[Rect]) -> bool:
    if start == end:
        return True
    return not any(rect.intersects_segment(start, end) for rect in obstacles)


def _point_blocked(point: Point, obstacles: list[Rect]) -> bool:
    return any(rect.contains_point(point) for rect in obstacles)


def _compress(points: list[Point]) -> list[Point]:
    unique: list[Point] = []
    for point in points:
        if not unique or unique[-1] != point:
            unique.append(point)

    changed = True
    while changed:
        changed = False
        compact: list[Point] = []
        for point in unique:
            compact.append(point)
            while len(compact) >= 3 and _collinear(compact[-3], compact[-2], compact[-1]):
                compact.pop(-2)
                changed = True
        unique = compact
    return unique


def _collinear(a: Point, b: Point, c: Point) -> bool:
    return (a.x == b.x == c.x) or (a.y == b.y == c.y)


def _reconstruct(
    came_from: dict[tuple[float, float], tuple[float, float]], current: tuple[float, float]
) -> list[Point]:
    path = [Point(*current)]
    while current in came_from:
        current = came_from[current]
        path.append(Point(*current))
    path.reverse()
    return path


def _key(point: Point) -> tuple[float, float]:
    return (point.x, point.y)


def _manhattan(a: Point, b: Point) -> float:
    return abs(a.x - b.x) + abs(a.y - b.y)
