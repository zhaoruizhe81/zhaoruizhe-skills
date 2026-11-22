from __future__ import annotations

from .model import Rect, path_segments


def orientation(a: tuple[float, float], b: tuple[float, float], c: tuple[float, float]) -> float:
    value = (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])
    return 0 if abs(value) < 1e-9 else value


def point_on_segment(point: tuple[float, float], start: tuple[float, float], end: tuple[float, float]) -> bool:
    return (
        min(start[0], end[0]) - 1e-9 <= point[0] <= max(start[0], end[0]) + 1e-9
        and min(start[1], end[1]) - 1e-9 <= point[1] <= max(start[1], end[1]) + 1e-9
    )


def segments_intersect(
    first: tuple[tuple[float, float], tuple[float, float]],
    second: tuple[tuple[float, float], tuple[float, float]],
) -> bool:
    a, b = first
    c, d = second
    o1 = orientation(a, b, c)
    o2 = orientation(a, b, d)
    o3 = orientation(c, d, a)
    o4 = orientation(c, d, b)
    if o1 == 0 and point_on_segment(c, a, b):
        return True
    if o2 == 0 and point_on_segment(d, a, b):
        return True
    if o3 == 0 and point_on_segment(a, c, d):
        return True
    if o4 == 0 and point_on_segment(b, c, d):
        return True
    return (o1 > 0) != (o2 > 0) and (o3 > 0) != (o4 > 0)


def segment_intersects_rect(
    segment: tuple[tuple[float, float], tuple[float, float]],
    rect: Rect,
) -> bool:
    a, b = segment
    if rect.contains(*a) or rect.contains(*b):
        return True
    corners = [
        (rect.left, rect.top),
        (rect.right, rect.top),
        (rect.right, rect.bottom),
        (rect.left, rect.bottom),
    ]
    edges = list(zip(corners, [*corners[1:], corners[0]]))
    return any(segments_intersect(segment, edge) for edge in edges)


def simplify_path(points: list[tuple[float, float]]) -> list[tuple[float, float]]:
    deduped: list[tuple[float, float]] = []
    for point in points:
        if not deduped or point != deduped[-1]:
            deduped.append(point)
    if len(deduped) <= 2:
        return deduped
    simplified = [deduped[0]]
    for index, point in enumerate(deduped[1:-1], start=1):
        previous = simplified[-1]
        next_point = deduped[index + 1]
        if previous[0] == point[0] == next_point[0] or previous[1] == point[1] == next_point[1]:
            continue
        simplified.append(point)
    simplified.append(deduped[-1])
    return simplified


def shares_endpoint(
    first: tuple[tuple[float, float], tuple[float, float]],
    second: tuple[tuple[float, float], tuple[float, float]],
) -> bool:
    return first[0] in second or first[1] in second


def path_obstacle_hits(path: list[tuple[float, float]], obstacles: list[Rect]) -> int:
    hits = 0
    for segment in path_segments(path):
        for obstacle in obstacles:
            if segment_intersects_rect(segment, obstacle):
                hits += 1
    return hits


def crossing_count(
    path: list[tuple[float, float]],
    used_segments: list[tuple[tuple[float, float], tuple[float, float]]],
) -> int:
    count = 0
    for segment in path_segments(path):
        for used in used_segments:
            if shares_endpoint(segment, used):
                continue
            if segments_intersect(segment, used):
                count += 1
    return count
