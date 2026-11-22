from __future__ import annotations

from collections.abc import Callable, Iterable

from .geometry import crossing_count, path_obstacle_hits, simplify_path
from .model import (
    Edge,
    Layout,
    Port,
    Rect,
    VALID_SIDES,
    dominant_side,
    manhattan_path_length,
    path_segments,
    turn_count,
)
from .ports import DEFAULT_PORT_OFFSET, make_port

RouteBuilder = Callable[[Port, Port], Iterable[tuple[list[tuple[float, float]], str]]]
AStarBuilder = Callable[[Port, Port], list[tuple[float, float]] | None]
# Dynamic port search usually finds clean orthogonal routes; per-port A* remains available but is expensive.
ENABLE_ASTAR_FALLBACK = False


def solve_relationship_route(
    layout: Layout,
    edge: Edge,
    used_segments: list[tuple[tuple[float, float], tuple[float, float]]],
    obstacles: list[Rect],
    route_builder: RouteBuilder,
    astar_builder: AStarBuilder,
) -> tuple[list[tuple[float, float]], str, Port, Port]:
    source_candidates = port_candidates(layout, edge, edge.source)
    target_candidates = port_candidates(layout, edge, edge.target)
    best: tuple[float, list[tuple[float, float]], str, Port, Port] | None = None
    pair_order: list[tuple[float, Port, Port]] = []

    for source_port, source_cost in source_candidates:
        for target_port, target_cost in target_candidates:
            pair_cost = source_cost + target_cost
            pair_order.append((pair_cost + manhattan_between(source_port.outside, target_port.outside) * 0.08, source_port, target_port))

    straight_best: tuple[float, list[tuple[float, float]], Port, Port] | None = None
    for _, source_port, target_port in sorted(pair_order, key=lambda item: item[0]):
        pair_cost = port_cost(layout, edge, edge.source, source_port) + port_cost(layout, edge, edge.target, target_port)
        path = simplify_path([source_port.anchor, source_port.outside, target_port.outside, target_port.anchor])
        if path_obstacle_hits(path, obstacles) or crossing_count(path, used_segments):
            continue
        score = route_score(path, obstacles, used_segments, pair_cost)
        if straight_best is None or score < straight_best[0]:
            straight_best = (score, path, source_port, target_port)
    if straight_best is not None:
        _, path, source_port, target_port = straight_best
        remember_ports(layout, edge, source_port, target_port)
        return path, "straight", source_port, target_port

    pair_limit = 40 if len(source_candidates) > 10 or len(target_candidates) > 10 else 32
    for _, source_port, target_port in sorted(pair_order, key=lambda item: item[0])[:pair_limit]:
        pair_cost = port_cost(layout, edge, edge.source, source_port) + port_cost(layout, edge, edge.target, target_port)
        for path, kind in route_builder(source_port, target_port):
            score = route_score(path, obstacles, used_segments, pair_cost)
            if best is None or score < best[0]:
                best = (score, path, kind, source_port, target_port)

    if best is None:
        raise ValueError("No route candidates generated")

    if crossing_count(best[1], used_segments):
        for _, source_port, target_port in sorted(pair_order, key=lambda item: item[0])[: min(24, len(pair_order))]:
            pair_cost = port_cost(layout, edge, edge.source, source_port) + port_cost(layout, edge, edge.target, target_port)
            for path in avoidance_candidates(source_port, target_port, used_segments):
                score = route_score(path, obstacles, used_segments, pair_cost)
                if score < best[0]:
                    best = (score, path, "avoid", source_port, target_port)

    if ENABLE_ASTAR_FALLBACK and path_obstacle_hits(best[1], obstacles):
        for _, source_port, target_port in sorted(pair_order, key=lambda item: item[0])[:6]:
            path = astar_builder(source_port, target_port)
            if not path:
                continue
            score = route_score(path, obstacles, used_segments, port_cost(layout, edge, edge.source, source_port) + port_cost(layout, edge, edge.target, target_port))
            if score < best[0]:
                best = (score, path, "astar", source_port, target_port)

    _, path, kind, source_port, target_port = best
    remember_ports(layout, edge, source_port, target_port)
    return path, kind, source_port, target_port


def port_candidates(layout: Layout, edge: Edge, node_id: str) -> list[tuple[Port, float]]:
    node = layout.nodes[node_id]
    sides = sorted(VALID_SIDES)
    candidates: list[tuple[Port, float]] = []
    for side in sides:
        for slot in expanded_slots(layout, node_id):
            port = make_port(node, side, slot, offset=DEFAULT_PORT_OFFSET)
            candidates.append((port, port_cost(layout, edge, node_id, port)))
    candidates.sort(key=lambda item: item[1])
    return prune_candidates(candidates, limit=12)


def prune_candidates(candidates: list[tuple[Port, float]], limit: int) -> list[tuple[Port, float]]:
    selected = candidates[:limit]
    selected_keys = {(port.side, port.slot) for port, _ in selected}
    selected_sides = {port.side for port, _ in selected}
    for side in sorted(VALID_SIDES - selected_sides):
        best_for_side = next((item for item in candidates if item[0].side == side), None)
        if best_for_side is not None and (best_for_side[0].side, best_for_side[0].slot) not in selected_keys:
            selected.append(best_for_side)
            selected_keys.add((best_for_side[0].side, best_for_side[0].slot))
    selected.sort(key=lambda item: item[1])
    return selected


def expanded_slots(layout: Layout, node_id: str) -> list[int]:
    density = sum(
        1
        for edge in layout.edges
        if edge.class_name == "relationship-edge" and node_id in {edge.source, edge.target}
    )
    limit = 3 if density >= 5 else 2
    return list(range(-limit, limit + 1))


def port_cost(layout: Layout, edge: Edge, node_id: str, port: Port) -> float:
    preferred = edge.source_side if node_id == edge.source else edge.target_side
    node = layout.nodes[node_id]
    other_node = layout.nodes[edge.target if node_id == edge.source else edge.source]
    natural = dominant_side(node, other_node)
    cost = abs(port.slot) * 4
    if preferred in VALID_SIDES and port.side != preferred:
        cost += 120
    if port.side != natural:
        cost += 36
    if preferred in VALID_SIDES and port.side == preferred:
        cost -= 18
    return cost


def remember_ports(layout: Layout, edge: Edge, source_port: Port, target_port: Port) -> None:
    layout.ports[(edge.source, edge.target, edge.label, edge.source)] = source_port
    layout.ports[(edge.source, edge.target, edge.label, edge.target)] = target_port


def route_score(
    path: list[tuple[float, float]],
    obstacles: list[Rect],
    used_segments: list[tuple[tuple[float, float], tuple[float, float]]],
    port_pair_cost: float,
) -> float:
    return (
        path_obstacle_hits(path, obstacles) * 80000
        + crossing_count(path, used_segments) * 50000
        + manhattan_path_length(path)
        + turn_count(path) * 30
        + port_pair_cost
    )


def avoidance_candidates(
    source: Port,
    target: Port,
    used_segments: list[tuple[tuple[float, float], tuple[float, float]]],
) -> list[list[tuple[float, float]]]:
    s = source.anchor
    t = target.anchor
    so = source.outside
    to = target.outside
    candidates: list[list[tuple[float, float]]] = []
    for a, b in used_segments:
        if abs(a[1] - b[1]) < 1e-6:
            left, right = sorted((a[0], b[0]))
            for x in (left - 60, right + 60):
                candidates.append(simplify_path([s, so, (x, so[1]), (x, to[1]), to, t]))
        if abs(a[0] - b[0]) < 1e-6:
            top, bottom = sorted((a[1], b[1]))
            for y in (top - 60, bottom + 60):
                candidates.append(simplify_path([s, so, (so[0], y), (to[0], y), to, t]))
    return candidates


def manhattan_between(left: tuple[float, float], right: tuple[float, float]) -> float:
    return abs(left[0] - right[0]) + abs(left[1] - right[1])
