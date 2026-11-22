from __future__ import annotations

from math import sqrt

from .model import Point, Rect


def point_inside_ellipse(point: Point, box: Rect, *, padding: float = 0.0) -> bool:
    center = box.center
    rx = box.width / 2 + padding
    ry = box.height / 2 + padding
    if rx <= 0 or ry <= 0:
        return False
    return ((point.x - center.x) / rx) ** 2 + ((point.y - center.y) / ry) ** 2 <= 1


def segment_intersects_ellipse(
    start: Point,
    end: Point,
    box: Rect,
    *,
    padding: float = 0.0,
) -> bool:
    if start == end:
        return point_inside_ellipse(start, box, padding=padding)

    center = box.center
    rx = box.width / 2 + padding
    ry = box.height / 2 + padding
    if rx <= 0 or ry <= 0:
        return False

    sx = start.x - center.x
    sy = start.y - center.y
    dx = end.x - start.x
    dy = end.y - start.y

    a = (dx * dx) / (rx * rx) + (dy * dy) / (ry * ry)
    b = 2 * ((sx * dx) / (rx * rx) + (sy * dy) / (ry * ry))
    c = (sx * sx) / (rx * rx) + (sy * sy) / (ry * ry) - 1
    if c <= 0 or point_inside_ellipse(end, box, padding=padding):
        return True

    discriminant = b * b - 4 * a * c
    if discriminant < 0 or a == 0:
        return False

    root = sqrt(discriminant)
    t1 = (-b - root) / (2 * a)
    t2 = (-b + root) / (2 * a)
    return 0 <= t1 <= 1 or 0 <= t2 <= 1


def ellipse_boundary_point(
    box: Rect,
    toward: Point,
    *,
    padding: float = 0.0,
) -> Point:
    center = box.center
    dx = toward.x - center.x
    dy = toward.y - center.y
    if dx == 0 and dy == 0:
        dx = 1.0

    rx = box.width / 2 + padding
    ry = box.height / 2 + padding
    scale = 1 / sqrt((dx / rx) ** 2 + (dy / ry) ** 2)
    return Point(center.x + dx * scale, center.y + dy * scale)
