from __future__ import annotations

import math

from .geometry import segment_intersects_rect, segments_intersect, shares_endpoint
from .model import (
    Edge,
    Layout,
    compute_territory_circle_radius,
    euclidean_path_length,
    path_segments,
    turn_count,
)
from .score import aspect_ratio_penalty, score_from_stats


def route_stats(layout: Layout) -> dict[str, float | int]:
    relationship_edges = [edge for edge in layout.edges if edge.class_name == "relationship-edge"]
    attribute_edges = [edge for edge in layout.edges if edge.class_name == "attribute-edge"]
    relationship_hits = 0
    relationship_territory_hits = 0
    relationship_segments = []
    for edge_index, edge in enumerate(relationship_edges):
        path = layout.paths[(edge.source, edge.target, edge.label)]
        allowed_territories = relationship_edge_territories(layout, edge)
        for segment in path_segments(path):
            relationship_segments.append((edge_index, segment))
        obstacles = [
            node.rect.inflate(1)
            for node_id, node in layout.nodes.items()
            if node_id not in {edge.source, edge.target} and node.kind != "attribute"
        ]
        for segment in path_segments(path):
            for obstacle in obstacles:
                if segment_intersects_rect(segment, obstacle):
                    relationship_hits += 1
            for entity_id, territory in layout.territories.items():
                if entity_id in allowed_territories:
                    continue
                if segment_intersects_rect(segment, territory.outer_rect):
                    relationship_territory_hits += 1
    crossings = 0
    for index, (edge_index, segment) in enumerate(relationship_segments):
        for other_edge_index, other_segment in relationship_segments[index + 1 :]:
            if edge_index == other_edge_index:
                continue
            if edges_share_node(relationship_edges[edge_index], relationship_edges[other_edge_index]):
                continue
            if shares_endpoint(segment, other_segment):
                continue
            if segments_intersect(segment, other_segment):
                crossings += 1
    relationship_lengths = [euclidean_path_length(layout.paths[(edge.source, edge.target, edge.label)]) for edge in relationship_edges]
    relationship_bends = sum(turn_count(layout.paths[(edge.source, edge.target, edge.label)]) for edge in relationship_edges)
    attr_lengths = [euclidean_path_length(layout.paths[(edge.source, edge.target, edge.label)]) for edge in attribute_edges]
    result = {
        "nodes": len(layout.nodes),
        "edges": len(layout.edges),
        "relationship_edges": len(relationship_edges),
        "attribute_edges": len(attribute_edges),
        "segments": sum(len(path_segments(path)) for path in layout.paths.values()),
        "relationship_crossings": crossings,
        "relationship_obstacle_hits": relationship_hits,
        "territory_overlaps": territory_overlap_count(layout),
        "attribute_out_of_territory": attribute_out_of_territory_count(layout),
        "relationship_crosses_territory": relationship_territory_hits,
        "node_overlaps": node_overlap_count(layout),
        "total_relationship_length": round(sum(relationship_lengths), 2),
        "max_relationship_length": round(max(relationship_lengths, default=0), 2),
        "relationship_bends": relationship_bends,
        "aspect_ratio_penalty": round(aspect_ratio_penalty(layout, layout.spec.layout.target_aspect), 4),
        "max_attribute_length": round(max(attr_lengths, default=0), 2),
        "avg_attribute_length": round(sum(attr_lengths) / len(attr_lengths), 2) if attr_lengths else 0,
        "astar_edges": sum(1 for kind in layout.route_kinds.values() if kind == "astar"),
    }
    result["layout_score"] = round(score_from_stats(result), 2)
    return result


def print_stats(layout: Layout) -> None:
    for key, value in route_stats(layout).items():
        print(f"{key}: {value}")


def node_overlap_count(layout: Layout) -> int:
    count = 0
    items = list(layout.nodes.items())
    for index, (_, left) in enumerate(items):
        for _, right in items[index + 1 :]:
            if left.rect.inflate(2).intersects(right.rect.inflate(2)):
                count += 1
    return count


def territory_overlap_count(layout: Layout) -> int:
    count = 0
    items = list(layout.territories.items())
    for index, (_, left) in enumerate(items):
        for _, right in items[index + 1 :]:
            left_radius = compute_territory_circle_radius(len(layout.spec.entities), left.outer_rect.width, left.outer_rect.height)
            right_radius = compute_territory_circle_radius(len(layout.spec.entities), right.outer_rect.width, right.outer_rect.height)
            if math.dist(left.outer_rect.center, right.outer_rect.center) < left_radius + right_radius - 1e-6:
                count += 1
    return count


def attribute_out_of_territory_count(layout: Layout) -> int:
    count = 0
    for node in layout.nodes.values():
        if node.kind != "attribute" or node.owner not in layout.territories:
            continue
        territory = layout.territories[node.owner].outer_rect
        if not (
            territory.contains(node.rect.left, node.rect.top)
            and territory.contains(node.rect.right, node.rect.bottom)
        ):
            count += 1
    return count


def edges_share_node(first: Edge, second: Edge) -> bool:
    return first.source in {second.source, second.target} or first.target in {second.source, second.target}


def relationship_edge_territories(layout: Layout, edge: Edge) -> set[str]:
    allowed = {edge.source}
    if edge.class_name == "relationship-edge":
        allowed.update(
            other_edge.source
            for other_edge in layout.edges
            if other_edge.class_name == "relationship-edge" and other_edge.target == edge.target
        )
    return allowed
