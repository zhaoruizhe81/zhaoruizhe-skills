from __future__ import annotations

from .model import Layout, Rect


SCORE_WEIGHTS = {
    "territory_overlaps": 100000,
    "attribute_out_of_territory": 100000,
    "relationship_crosses_territory": 80000,
    "relationship_obstacle_hits": 60000,
    "relationship_crossings": 50000,
    "node_overlaps": 40000,
    "max_relationship_length": 4,
    "total_relationship_length": 1,
    "relationship_bends": 30,
    "aspect_ratio_penalty": 200,
}


def score_from_stats(stats: dict[str, float | int]) -> float:
    return sum(float(stats.get(key, 0)) * weight for key, weight in SCORE_WEIGHTS.items())


def aspect_ratio_penalty(layout: Layout, target_aspect: float) -> float:
    bounds = layout_bounds(layout)
    if bounds.height <= 0 or target_aspect <= 0:
        return 0
    aspect = bounds.width / bounds.height
    return abs(aspect - target_aspect)


def layout_bounds(layout: Layout) -> Rect:
    rects = [node.rect for node in layout.nodes.values()]
    rects.extend(territory.outer_rect for territory in layout.territories.values())
    points = [point for path in layout.paths.values() for point in path]
    if not rects and not points:
        return Rect(0, 0, 0, 0)
    all_left = [rect.left for rect in rects] + [point[0] for point in points]
    all_top = [rect.top for rect in rects] + [point[1] for point in points]
    all_right = [rect.right for rect in rects] + [point[0] for point in points]
    all_bottom = [rect.bottom for rect in rects] + [point[1] for point in points]
    return Rect(min(all_left), min(all_top), max(all_right), max(all_bottom))
