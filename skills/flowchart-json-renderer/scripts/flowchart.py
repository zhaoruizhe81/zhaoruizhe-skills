#!/usr/bin/env python3
"""Render a JSON flowchart to SVG, then convert it to PNG.

The renderer keeps node placement deterministic, then routes edges over a
coarse cost grid with orthogonal A* search. That makes side ports and retry
edges much less brittle than hand-written branch-specific routing rules.
"""

from __future__ import annotations

import argparse
import heapq
import json
import math
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from enum import IntEnum
from html import escape
from pathlib import Path
from typing import Any


VALID_PORTS = {"n", "e", "s", "w", "c"}
NODE_TYPE_ALIASES = {
    "rect": "rect",
    "rectangle": "rect",
    "box": "rect",
    "diamond": "diamond",
    "decision": "diamond",
    "terminal": "terminal",
    "capsule": "terminal",
    "round": "terminal",
    "rounded": "terminal",
    "start": "terminal",
    "end": "terminal",
}
DEFAULT_NODE_SIZES = {
    "terminal": (190.0, 64.0),
    "rect": (210.0, 70.0),
    "diamond": (300.0, 125.0),
}
DIRS = {
    "n": (0, -1),
    "e": (1, 0),
    "s": (0, 1),
    "w": (-1, 0),
}
DIR_INDEX = {
    (0, -1): 0,
    (1, 0): 1,
    (0, 1): 2,
    (-1, 0): 3,
}
INDEX_DIR = {value: key for key, value in DIR_INDEX.items()}
OPPOSITE_PORT = {"n": "s", "e": "w", "s": "n", "w": "e"}


class FlowchartError(ValueError):
    """Raised when the flowchart JSON cannot be rendered safely."""


class CellKind(IntEnum):
    EMPTY = 0
    RESERVED = 1
    NODE_PAD = 2
    LINE = 3
    LABEL = 4
    NODE = 5


@dataclass(frozen=True)
class Point:
    x: float
    y: float


@dataclass(frozen=True)
class Rect:
    left: float
    top: float
    right: float
    bottom: float

    @property
    def width(self) -> float:
        return self.right - self.left

    @property
    def height(self) -> float:
        return self.bottom - self.top

    def inflate(self, amount: float) -> Rect:
        return Rect(
            self.left - amount,
            self.top - amount,
            self.right + amount,
            self.bottom + amount,
        )

    def contains(self, point: Point) -> bool:
        return self.left <= point.x <= self.right and self.top <= point.y <= self.bottom

    def translated(self, dx: float, dy: float) -> Rect:
        return Rect(self.left + dx, self.top + dy, self.right + dx, self.bottom + dy)


@dataclass
class RenderOptions:
    grid_size: float = 10.0
    margin_x: float = 58.0
    margin_top: float = 38.0
    margin_bottom: float = 44.0
    node_gap: float = 46.0
    title_space: float = 58.0
    lane_gap: float = 42.0
    lane_clearance: float = 92.0
    side_stub: float = 28.0
    port_stub: float = 18.0
    node_pad: float = 18.0
    label_pad: float = 6.0
    node_font_size: int = 20
    label_font_size: int = 20
    title_font_size: int = 28
    node_stroke_width: float = 1.4
    edge_stroke_width: float = 1.4
    arrow_size: float = 7.0
    font: str = "PingFang SC"
    theme: str = "white"
    debug_grid: bool = False


@dataclass
class Node:
    id: str
    kind: str
    text: str
    width: float
    height: float
    fixed_x: float | None = None
    fixed_y: float | None = None
    x: float = 0.0
    y: float = 0.0

    @property
    def bbox(self) -> Rect:
        return Rect(
            self.x - self.width / 2,
            self.y - self.height / 2,
            self.x + self.width / 2,
            self.y + self.height / 2,
        )

    def port(self, name: str) -> Point:
        half_w = self.width / 2
        half_h = self.height / 2
        if name == "n":
            return Point(self.x, self.y - half_h)
        if name == "e":
            return Point(self.x + half_w, self.y)
        if name == "s":
            return Point(self.x, self.y + half_h)
        if name == "w":
            return Point(self.x - half_w, self.y)
        if name == "c":
            return Point(self.x, self.y)
        raise FlowchartError(f"unknown port: {name}")


@dataclass(frozen=True)
class Edge:
    source: str
    target: str
    label: str
    source_port: str | None
    target_port: str | None
    route_hint: str | None = None


@dataclass
class Route:
    edge: Edge
    points: list[Point]
    is_back_edge: bool
    label_position: Point | None = None


@dataclass
class Layout:
    nodes: list[Node]
    edges: list[Edge]
    width: float
    height: float
    title: str | None
    options: RenderOptions
    left_lanes: list[float] = field(default_factory=list)
    right_lanes: list[float] = field(default_factory=list)


def require_mapping(value: Any, name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise FlowchartError(f"{name} must be an object")
    return value


def require_list(value: Any, name: str) -> list[Any]:
    if not isinstance(value, list):
        raise FlowchartError(f"{name} must be an array")
    return value


def read_flowchart(path: Path) -> dict[str, Any]:
    try:
        with path.open("r", encoding="utf-8") as file:
            data = json.load(file)
    except FileNotFoundError as exc:
        raise FlowchartError(f"JSON file not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise FlowchartError(f"Invalid JSON at line {exc.lineno}, column {exc.colno}: {exc.msg}") from exc
    return require_mapping(data, "root")


def normalize_port(value: Any, name: str) -> str | None:
    if value in ("", None):
        return None
    port = str(value).lower()
    if port not in VALID_PORTS:
        raise FlowchartError(f"{name} must be one of {', '.join(sorted(VALID_PORTS))}")
    return port


def normalize_hint(value: Any, name: str) -> str | None:
    if value in ("", None):
        return None
    hint = str(value).lower()
    if hint not in {"auto", "left", "right"}:
        raise FlowchartError(f"{name} must be one of auto, left, right")
    return None if hint == "auto" else hint


def positive_number(value: Any, fallback: float, name: str) -> float:
    if value in ("", None):
        return fallback
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise FlowchartError(f"{name} must be a number") from exc
    if not math.isfinite(number) or number <= 0:
        raise FlowchartError(f"{name} must be greater than 0")
    return number


def optional_number(value: Any, name: str) -> float | None:
    if value in ("", None):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise FlowchartError(f"{name} must be a number") from exc
    if not math.isfinite(number):
        raise FlowchartError(f"{name} must be finite")
    return number


def parse_options(data: dict[str, Any]) -> RenderOptions:
    theme = str(data.get("theme", "white") or "white").lower()
    if theme not in {"white", "black"}:
        raise FlowchartError("theme must be one of white or black")
    return RenderOptions(
        grid_size=positive_number(data.get("grid_size"), 10.0, "grid_size"),
        margin_x=positive_number(data.get("margin_x"), 58.0, "margin_x"),
        margin_top=positive_number(data.get("margin_top"), 38.0, "margin_top"),
        margin_bottom=positive_number(data.get("margin_bottom"), 44.0, "margin_bottom"),
        node_gap=positive_number(data.get("node_gap"), 46.0, "node_gap"),
        lane_gap=positive_number(data.get("lane_gap"), 42.0, "lane_gap"),
        lane_clearance=positive_number(data.get("lane_clearance"), 92.0, "lane_clearance"),
        side_stub=positive_number(data.get("side_stub"), 28.0, "side_stub"),
        port_stub=positive_number(data.get("port_stub"), 18.0, "port_stub"),
        node_pad=positive_number(data.get("node_pad"), 18.0, "node_pad"),
        label_pad=positive_number(data.get("label_pad"), 6.0, "label_pad"),
        node_font_size=int(positive_number(data.get("node_font_size"), 20.0, "node_font_size")),
        label_font_size=int(positive_number(data.get("label_font_size"), 20.0, "label_font_size")),
        title_font_size=int(positive_number(data.get("title_font_size"), 28.0, "title_font_size")),
        node_stroke_width=positive_number(data.get("node_stroke_width"), 1.4, "node_stroke_width"),
        edge_stroke_width=positive_number(data.get("edge_stroke_width"), 1.4, "edge_stroke_width"),
        arrow_size=positive_number(data.get("arrow_size"), 7.0, "arrow_size"),
        font=str(data.get("font", "PingFang SC") or "PingFang SC"),
        theme=theme,
    )


def parse_flowchart(data: dict[str, Any]) -> tuple[list[Node], list[Edge], str | None, RenderOptions]:
    direction = str(data.get("direction", "TB")).upper()
    if direction != "TB":
        raise FlowchartError("only top-to-bottom direction 'TB' is supported by the SVG renderer")

    raw_nodes = require_list(data.get("nodes"), "nodes")
    raw_edges = require_list(data.get("edges"), "edges")
    options = parse_options(data)

    nodes: list[Node] = []
    seen: set[str] = set()
    for index, item in enumerate(raw_nodes, start=1):
        raw_node = require_mapping(item, f"nodes[{index}]")
        node_id = str(raw_node.get("id", "")).strip()
        if not node_id:
            raise FlowchartError(f"nodes[{index}].id is required")
        if node_id in seen:
            raise FlowchartError(f"duplicate node id: {node_id}")
        seen.add(node_id)

        raw_type = str(raw_node.get("type", "rect")).lower()
        kind = NODE_TYPE_ALIASES.get(raw_type)
        if kind is None:
            raise FlowchartError(f"node {node_id!r} has unknown type {raw_type!r}; use rect, diamond, or terminal")

        default_width, default_height = DEFAULT_NODE_SIZES[kind]
        nodes.append(
            Node(
                id=node_id,
                kind=kind,
                text=str(raw_node.get("text", raw_node.get("label", node_id))),
                width=positive_number(raw_node.get("width"), default_width, f"nodes[{index}].width"),
                height=positive_number(raw_node.get("height"), default_height, f"nodes[{index}].height"),
                fixed_x=optional_number(raw_node.get("x"), f"nodes[{index}].x"),
                fixed_y=optional_number(raw_node.get("y"), f"nodes[{index}].y"),
            )
        )

    edges: list[Edge] = []
    for index, item in enumerate(raw_edges, start=1):
        raw_edge = require_mapping(item, f"edges[{index}]")
        source = str(raw_edge.get("from", "")).strip()
        target = str(raw_edge.get("to", "")).strip()
        if not source or not target:
            raise FlowchartError(f"edges[{index}] must include from and to")
        if source not in seen:
            raise FlowchartError(f"edges[{index}].from references unknown node: {source}")
        if target not in seen:
            raise FlowchartError(f"edges[{index}].to references unknown node: {target}")
        edges.append(
            Edge(
                source=source,
                target=target,
                label=str(raw_edge.get("label", "")),
                source_port=normalize_port(raw_edge.get("from_port"), f"edges[{index}].from_port"),
                target_port=normalize_port(raw_edge.get("to_port"), f"edges[{index}].to_port"),
                route_hint=normalize_hint(raw_edge.get("route_hint"), f"edges[{index}].route_hint"),
            )
        )

    title = data.get("title")
    return nodes, edges, str(title) if title not in ("", None) else None, options


def default_ports(edge: Edge, order: dict[str, int]) -> tuple[str, str]:
    is_back_edge = order[edge.target] <= order[edge.source]
    return (
        edge.source_port or ("e" if is_back_edge else "s"),
        edge.target_port or ("e" if is_back_edge else "n"),
    )


def resolved_ports(edge: Edge, node_by_id: dict[str, Node], order: dict[str, int]) -> tuple[str, str]:
    source_port, target_port = default_ports(edge, order)
    if order[edge.target] <= order[edge.source]:
        return source_port, target_port

    source_node = node_by_id[edge.source]
    target_node = node_by_id[edge.target]
    if (
        source_node.kind == "rect"
        and target_node.kind == "terminal"
        and source_port == "s"
        and target_port in {"e", "w"}
        and source_node.bbox.bottom < target_node.bbox.top
    ):
        if target_port == "w" and source_node.x < target_node.x:
            return "w", target_port
        if target_port == "e" and source_node.x > target_node.x:
            return "e", target_port
    if target_node.kind != "rect" or source_port not in {"e", "w"} or target_port not in {"n", "s"}:
        return source_port, target_port
    source_side_y = source_node.port(source_port).y
    if not (target_node.bbox.top <= source_side_y <= target_node.bbox.bottom):
        return source_port, target_port
    if source_port == "w" and target_node.x < source_node.x:
        return source_port, "e"
    if source_port == "e" and target_node.x > source_node.x:
        return source_port, "w"
    return source_port, target_port


def route_side(edge: Edge, order: dict[str, int]) -> str:
    source_port, target_port = default_ports(edge, order)
    if edge.route_hint in {"left", "right"}:
        return edge.route_hint
    is_back_edge = order[edge.target] <= order[edge.source]
    if is_back_edge and source_port in {"e", "w"}:
        return "right" if source_port == "e" else "left"
    if not is_back_edge and source_port in {"e", "w"}:
        return "right" if source_port == "e" else "left"
    if target_port in {"e", "w"}:
        return "right" if target_port == "e" else "left"
    return "right"


def compute_layout(nodes: list[Node], edges: list[Edge], title: str | None, options: RenderOptions) -> Layout:
    if not nodes:
        raise FlowchartError("nodes must contain at least one node")

    order = {node.id: index for index, node in enumerate(nodes)}
    left_back_count = 0
    right_back_count = 0
    left_side_count = 0
    right_side_count = 0
    for edge in edges:
        source_port, target_port = default_ports(edge, order)
        if order[edge.target] <= order[edge.source]:
            if route_side(edge, order) == "left":
                left_back_count += 1
            else:
                right_back_count += 1
        elif source_port in {"e", "w"} or target_port in {"e", "w"}:
            if route_side(edge, order) == "left":
                left_side_count += 1
            else:
                right_side_count += 1

    left_lane_count = max(left_back_count, 1 if left_side_count else 0)
    right_lane_count = max(right_back_count, 1 if right_side_count else 0)
    max_width = max(node.width for node in nodes)
    left_clearance = options.margin_x + options.lane_clearance + left_lane_count * options.lane_gap
    center_x = left_clearance + max_width / 2

    title_space = options.title_space if title else 0.0
    y = options.margin_top + title_space
    for node in nodes:
        node.x = node.fixed_x if node.fixed_x is not None else center_x
        node.y = node.fixed_y if node.fixed_y is not None else y + node.height / 2
        y += node.height + options.node_gap
    y -= options.node_gap

    node_bounds = union_rects([node.bbox for node in nodes])
    left_edge = node_bounds.left
    right_edge = node_bounds.right
    left_lanes = [left_edge - options.lane_clearance - i * options.lane_gap for i in range(left_lane_count)]
    right_lanes = [right_edge + options.lane_clearance + i * options.lane_gap for i in range(right_lane_count)]
    max_label_chars = 0
    for edge in edges:
        max_label_chars = max(max_label_chars, *(len(line) for line in edge.label.splitlines())) if edge.label else max_label_chars
    label_extra = max(40.0, max_label_chars * options.label_font_size + options.label_pad * 2 + 24.0)
    canvas_left = min([node_bounds.left, *left_lanes]) - options.margin_x - label_extra
    canvas_right = max([node_bounds.right, *right_lanes]) + options.margin_x + label_extra
    shift_x = -canvas_left
    shift_y = max(0.0, options.margin_top - node_bounds.top)
    for node in nodes:
        node.x += shift_x
        node.y += shift_y
    left_lanes = [x + shift_x for x in left_lanes]
    right_lanes = [x + shift_x for x in right_lanes]
    shifted_bounds = union_rects([node.bbox for node in nodes])

    return Layout(
        nodes=nodes,
        edges=edges,
        width=canvas_right - canvas_left,
        height=max(y + shift_y, shifted_bounds.bottom) + options.margin_bottom,
        title=title,
        options=options,
        left_lanes=left_lanes,
        right_lanes=right_lanes,
    )


def points_to_attr(points: list[Point]) -> str:
    return " ".join(f"{point.x:.1f},{point.y:.1f}" for point in points)


def union_rects(rects: list[Rect]) -> Rect:
    if not rects:
        return Rect(0.0, 0.0, 1.0, 1.0)
    return Rect(
        min(rect.left for rect in rects),
        min(rect.top for rect in rects),
        max(rect.right for rect in rects),
        max(rect.bottom for rect in rects),
    )


def points_bounds(points: list[Point]) -> Rect:
    return Rect(
        min(point.x for point in points),
        min(point.y for point in points),
        max(point.x for point in points),
        max(point.y for point in points),
    )


def snap(value: float, grid_size: float) -> float:
    return round(value / grid_size) * grid_size


def direction_index(port: str) -> int | None:
    vector = DIRS.get(port)
    return DIR_INDEX[vector] if vector else None


def adaptive_stub(point: Point, port: str, other: Point, options: RenderOptions) -> Point:
    if port not in DIRS:
        return point
    dx, dy = DIRS[port]
    base = options.side_stub if port in {"e", "w"} else options.port_stub
    available = base
    if dx and (other.x - point.x) * dx > 0:
        available = min(base, max(options.grid_size, abs(other.x - point.x) / 3))
    if dy and (other.y - point.y) * dy > 0:
        available = min(base, max(options.grid_size, abs(other.y - point.y) / 3))
    return Point(point.x + dx * available, point.y + dy * available)


def snap_stub(stub: Point, origin: Point, port: str, grid_size: float) -> Point:
    if port in {"e", "w"}:
        return Point(snap(stub.x, grid_size), origin.y)
    if port in {"n", "s"}:
        return Point(origin.x, snap(stub.y, grid_size))
    return Point(snap(stub.x, grid_size), snap(stub.y, grid_size))


class CostGrid:
    def __init__(self, width: float, height: float, options: RenderOptions) -> None:
        self.options = options
        self.grid_size = options.grid_size
        self.cols = max(3, int(math.ceil(width / self.grid_size)) + 1)
        self.rows = max(3, int(math.ceil(height / self.grid_size)) + 1)
        self.kinds = [[CellKind.EMPTY for _ in range(self.cols)] for _ in range(self.rows)]

    def in_bounds(self, cell: tuple[int, int]) -> bool:
        x, y = cell
        return 0 <= x < self.cols and 0 <= y < self.rows

    def to_cell(self, point: Point) -> tuple[int, int]:
        return (
            min(max(round(point.x / self.grid_size), 0), self.cols - 1),
            min(max(round(point.y / self.grid_size), 0), self.rows - 1),
        )

    def to_point(self, cell: tuple[int, int]) -> Point:
        return Point(cell[0] * self.grid_size, cell[1] * self.grid_size)

    def mark_rect(self, rect: Rect, kind: CellKind, *, overwrite: bool = True) -> None:
        left = max(0, math.floor(rect.left / self.grid_size))
        right = min(self.cols - 1, math.ceil(rect.right / self.grid_size))
        top = max(0, math.floor(rect.top / self.grid_size))
        bottom = min(self.rows - 1, math.ceil(rect.bottom / self.grid_size))
        for row in range(top, bottom + 1):
            for col in range(left, right + 1):
                if overwrite or self.kinds[row][col] < kind:
                    self.kinds[row][col] = kind

    def mark_node(self, node: Node) -> None:
        self.mark_rect(node.bbox.inflate(self.options.node_pad), CellKind.NODE_PAD, overwrite=False)
        self.mark_rect(node.bbox, CellKind.NODE)

    def mark_segment(self, start: Point, end: Point, kind: CellKind) -> None:
        start_cell = self.to_cell(start)
        end_cell = self.to_cell(end)
        x1, y1 = start_cell
        x2, y2 = end_cell
        if x1 == x2:
            lo, hi = sorted((y1, y2))
            for row in range(lo, hi + 1):
                if self.kinds[row][x1] != CellKind.NODE:
                    self.kinds[row][x1] = max(self.kinds[row][x1], kind)
        elif y1 == y2:
            lo, hi = sorted((x1, x2))
            for col in range(lo, hi + 1):
                if self.kinds[y1][col] != CellKind.NODE:
                    self.kinds[y1][col] = max(self.kinds[y1][col], kind)

    def mark_polyline(self, points: list[Point], kind: CellKind) -> None:
        for start, end in zip(points, points[1:]):
            self.mark_segment(start, end, kind)

    def reserve_lane(self, x: float) -> None:
        col = self.to_cell(Point(x, 0))[0]
        for row in range(self.rows):
            if self.kinds[row][col] not in {CellKind.NODE, CellKind.LINE, CellKind.LABEL}:
                self.kinds[row][col] = max(self.kinds[row][col], CellKind.RESERVED)

    def clear_cells(self, points: list[Point], radius: int = 1) -> None:
        for point in points:
            col, row = self.to_cell(point)
            for y in range(row - radius, row + radius + 1):
                for x in range(col - radius, col + radius + 1):
                    if 0 <= x < self.cols and 0 <= y < self.rows:
                        if self.kinds[y][x] == CellKind.NODE:
                            continue
                        self.kinds[y][x] = CellKind.EMPTY

    def cell_cost(self, cell: tuple[int, int], preferred_side: str | None = None, center_x: float | None = None) -> float:
        x, y = cell
        kind = self.kinds[y][x]
        if kind == CellKind.NODE:
            return math.inf
        costs = {
            CellKind.EMPTY: 1.0,
            CellKind.RESERVED: 1.4,
            CellKind.NODE_PAD: 32.0,
            CellKind.LINE: 70.0,
            CellKind.LABEL: 120.0,
        }
        cost = costs.get(kind, 1.0)
        if preferred_side and center_x is not None:
            point_x = x * self.grid_size
            if preferred_side == "right" and point_x < center_x:
                cost += 6.0
            if preferred_side == "left" and point_x > center_x:
                cost += 6.0
        return cost

    def rect_cost(self, rect: Rect) -> float:
        left = max(0, math.floor(rect.left / self.grid_size))
        right = min(self.cols - 1, math.ceil(rect.right / self.grid_size))
        top = max(0, math.floor(rect.top / self.grid_size))
        bottom = min(self.rows - 1, math.ceil(rect.bottom / self.grid_size))
        total = 0.0
        for row in range(top, bottom + 1):
            for col in range(left, right + 1):
                kind = self.kinds[row][col]
                if kind == CellKind.NODE:
                    return math.inf
                total += {
                    CellKind.EMPTY: 0.0,
                    CellKind.RESERVED: 1.0,
                    CellKind.NODE_PAD: 20.0,
                    CellKind.LINE: 60.0,
                    CellKind.LABEL: 100.0,
                }.get(kind, 0.0)
        return total

    def debug_svg(self) -> str:
        colors = {
            CellKind.RESERVED: ("debug-reserved", "#e5f2ff"),
            CellKind.NODE_PAD: ("debug-node-pad", "#fff1a8"),
            CellKind.LINE: ("debug-line", "#ffc4c4"),
            CellKind.LABEL: ("debug-label", "#d5c4ff"),
            CellKind.NODE: ("debug-node", "#d0d0d0"),
        }
        rects: list[str] = ['<g class="debug-grid">']
        for row in range(self.rows):
            for col in range(self.cols):
                kind = self.kinds[row][col]
                if kind == CellKind.EMPTY:
                    continue
                css_class, color = colors[kind]
                rects.append(
                    f'<rect class="debug-cell {css_class}" '
                    f'x="{col * self.grid_size:.1f}" y="{row * self.grid_size:.1f}" '
                    f'width="{self.grid_size:.1f}" height="{self.grid_size:.1f}" '
                    f'fill="{color}" opacity="0.35" />'
                )
        rects.append("</g>")
        return "\n".join(rects)


def heuristic(cell: tuple[int, int], goal: tuple[int, int]) -> float:
    return abs(cell[0] - goal[0]) + abs(cell[1] - goal[1])


def reconstruct_path(
    came_from: dict[tuple[int, int, int], tuple[int, int, int]],
    state: tuple[int, int, int],
) -> list[tuple[int, int]]:
    cells = [(state[0], state[1])]
    while state in came_from:
        state = came_from[state]
        cells.append((state[0], state[1]))
    cells.reverse()
    return cells


def astar(
    grid: CostGrid,
    start: Point,
    goal: Point,
    *,
    initial_dir: int | None,
    final_dir: int | None,
    preferred_side: str | None,
    center_x: float,
) -> list[Point]:
    start_cell = grid.to_cell(start)
    goal_cell = grid.to_cell(goal)
    if start_cell == goal_cell:
        return [grid.to_point(start_cell)]

    start_dir = initial_dir if initial_dir is not None else 4
    start_state = (start_cell[0], start_cell[1], start_dir)
    frontier: list[tuple[float, float, tuple[int, int, int]]] = [(0.0, 0.0, start_state)]
    best_cost: dict[tuple[int, int, int], float] = {start_state: 0.0}
    came_from: dict[tuple[int, int, int], tuple[int, int, int]] = {}
    best_goal: tuple[float, tuple[int, int, int]] | None = None

    while frontier:
        priority, current_cost, current = heapq.heappop(frontier)
        if current_cost != best_cost.get(current):
            continue
        current_cell = (current[0], current[1])
        if best_goal and priority > best_goal[0]:
            break
        if current_cell == goal_cell:
            final_penalty = 0.0 if final_dir is None or current[2] == final_dir else 14.0
            scored = current_cost + final_penalty
            if best_goal is None or scored < best_goal[0]:
                best_goal = (scored, current)
            continue

        for dir_index, (dx, dy) in INDEX_DIR.items():
            next_cell = (current_cell[0] + dx, current_cell[1] + dy)
            if not grid.in_bounds(next_cell):
                continue
            step_cost = grid.cell_cost(next_cell, preferred_side, center_x)
            if math.isinf(step_cost):
                continue
            turn_penalty = 0.0
            if current[2] != 4 and current[2] != dir_index:
                turn_penalty = 8.0
            if next_cell == goal_cell and final_dir is not None and dir_index != final_dir:
                turn_penalty += 12.0
            next_cost = current_cost + step_cost + turn_penalty
            next_state = (next_cell[0], next_cell[1], dir_index)
            if next_cost >= best_cost.get(next_state, math.inf):
                continue
            best_cost[next_state] = next_cost
            came_from[next_state] = current
            next_priority = next_cost + heuristic(next_cell, goal_cell)
            heapq.heappush(frontier, (next_priority, next_cost, next_state))

    if best_goal is None:
        raise FlowchartError("could not route an edge without crossing blocked nodes")

    return [grid.to_point(cell) for cell in reconstruct_path(came_from, best_goal[1])]


def dedupe_points(points: list[Point]) -> list[Point]:
    deduped: list[Point] = []
    for point in points:
        if deduped and abs(deduped[-1].x - point.x) < 0.001 and abs(deduped[-1].y - point.y) < 0.001:
            continue
        deduped.append(point)
    return deduped


def simplify_points(points: list[Point]) -> list[Point]:
    points = dedupe_points(points)
    if len(points) <= 2:
        return points
    simplified = [points[0]]
    for prev, current, next_point in zip(points, points[1:], points[2:]):
        same_x = abs(prev.x - current.x) < 0.001 and abs(current.x - next_point.x) < 0.001
        same_y = abs(prev.y - current.y) < 0.001 and abs(current.y - next_point.y) < 0.001
        if not (same_x or same_y):
            simplified.append(current)
    simplified.append(points[-1])
    return dedupe_points(simplified)


def align_route_to_stubs(points: list[Point], start_stub: Point, end_stub: Point) -> list[Point]:
    if not points:
        return [start_stub, end_stub]
    if len(points) == 1:
        return [start_stub]

    old_points = points
    aligned = list(points)

    first, second = old_points[0], old_points[1]
    if abs(first.x - second.x) < 0.001:
        index = 0
        while index < len(old_points) and abs(old_points[index].x - first.x) < 0.001:
            aligned[index] = Point(start_stub.x, aligned[index].y)
            index += 1
    elif abs(first.y - second.y) < 0.001:
        index = 0
        while index < len(old_points) and abs(old_points[index].y - first.y) < 0.001:
            aligned[index] = Point(aligned[index].x, start_stub.y)
            index += 1
    else:
        aligned[0] = start_stub

    before_last, last = old_points[-2], old_points[-1]
    if abs(before_last.x - last.x) < 0.001:
        index = len(old_points) - 1
        while index >= 0 and abs(old_points[index].x - last.x) < 0.001:
            aligned[index] = Point(end_stub.x, aligned[index].y)
            index -= 1
    elif abs(before_last.y - last.y) < 0.001:
        index = len(old_points) - 1
        while index >= 0 and abs(old_points[index].y - last.y) < 0.001:
            aligned[index] = Point(aligned[index].x, end_stub.y)
            index -= 1
    else:
        aligned[-1] = end_stub

    return simplify_points(aligned)


def back_edge_skeleton(
    start_stub: Point,
    end_stub: Point,
    source_node: Node,
    target_node: Node,
    source_port: str,
    target_port: str,
    lane_x: float,
    options: RenderOptions,
) -> list[Point]:
    lane_x = snap(lane_x, options.grid_size)
    points = [start_stub, Point(lane_x, start_stub.y)]
    if target_node.y <= source_node.y:
        bypass_y = target_node.bbox.top - options.node_pad - options.port_stub
    else:
        bypass_y = target_node.bbox.bottom + options.node_pad + options.port_stub
    bypass_y = snap(bypass_y, options.grid_size)

    lane_is_right = lane_x >= target_node.x
    target_side_is_left = target_port == "w"
    target_side_is_right = target_port == "e"
    opposite_side_target = (lane_is_right and target_side_is_left) or ((not lane_is_right) and target_side_is_right)

    if target_port in {"e", "w"} and opposite_side_target:
        points.extend([Point(lane_x, bypass_y), Point(end_stub.x, bypass_y), end_stub])
    elif target_port in {"e", "w"}:
        points.extend([Point(lane_x, end_stub.y), end_stub])
    elif target_port == "n":
        points.extend([Point(lane_x, end_stub.y), end_stub])
    elif target_port == "s":
        points.extend([Point(lane_x, end_stub.y), end_stub])
    else:
        points.extend([Point(lane_x, end_stub.y), end_stub])

    return simplify_points(points)


def forward_side_skeleton(
    start_stub: Point,
    end_stub: Point,
    source_port: str,
    side_x: float,
    blockers: list[Node],
    options: RenderOptions,
) -> list[Point]:
    if blockers:
        bend_x = snap(side_x, options.grid_size)
    else:
        bend_x = start_stub.x
    return simplify_points(
        [
            start_stub,
            Point(bend_x, start_stub.y),
            Point(bend_x, end_stub.y),
            end_stub,
        ]
    )


def direct_side_to_vertical_skeleton(start_stub: Point, end_stub: Point) -> list[Point]:
    return simplify_points([start_stub, Point(end_stub.x, start_stub.y), end_stub])


def edge_priority(edge: Edge, index: int, order: dict[str, int]) -> tuple[int, int]:
    source_port, target_port = default_ports(edge, order)
    is_back_edge = order[edge.target] <= order[edge.source]
    if not is_back_edge and source_port == "s" and target_port == "n":
        return (0, index)
    if not is_back_edge:
        return (1, index)
    return (2, index)


def choose_lane(edge: Edge, order: dict[str, int], lane_usage: dict[str, int], layout: Layout) -> tuple[str, float]:
    side = route_side(edge, order)
    lanes = layout.left_lanes if side == "left" else layout.right_lanes
    if not lanes:
        fallback = layout.nodes[0].x + (layout.nodes[0].width if side == "right" else -layout.nodes[0].width)
        return side, fallback
    key = f"{side}:{edge.source}->{edge.target}:{edge.label}"
    lane_index = lane_usage.get(side, 0) % len(lanes)
    lane_usage[side] = lane_usage.get(side, 0) + 1
    if key in lane_usage:
        lane_index = lane_usage[key] % len(lanes)
    else:
        lane_usage[key] = lane_index
    return side, lanes[lane_index]


def point_strictly_inside(rect: Rect, point: Point) -> bool:
    return rect.left < point.x < rect.right and rect.top < point.y < rect.bottom


def route_crosses_node_interiors(points: list[Point], nodes: list[Node]) -> bool:
    for start, end in zip(points, points[1:]):
        length = abs(start.x - end.x) + abs(start.y - end.y)
        steps = max(1, int(length // 5))
        for index in range(1, steps):
            ratio = index / steps
            sample = Point(start.x + (end.x - start.x) * ratio, start.y + (end.y - start.y) * ratio)
            if any(point_strictly_inside(node.bbox, sample) for node in nodes):
                return True
    return False


def side_fanin_route_points(
    edge: Edge,
    node_by_id: dict[str, Node],
    order: dict[str, int],
    bus_x: float,
    options: RenderOptions,
) -> list[Point]:
    source_node = node_by_id[edge.source]
    target_node = node_by_id[edge.target]
    source_port, target_port = resolved_ports(edge, node_by_id, order)
    start = source_node.port(source_port)
    end = target_node.port(target_port)
    start_stub = snap_stub(adaptive_stub(start, source_port, end, options), start, source_port, options.grid_size)
    end_stub = snap_stub(adaptive_stub(end, target_port, start, options), end, target_port, options.grid_size)
    return simplify_points(
        [
            start,
            start_stub,
            Point(bus_x, start_stub.y),
            Point(bus_x, end_stub.y),
            end_stub,
            end,
        ]
    )


def build_shared_bus_maps(
    layout: Layout,
    node_by_id: dict[str, Node],
    order: dict[str, int],
) -> tuple[dict[tuple[str, str], float], dict[tuple[str, str], float], dict[tuple[str, str], float]]:
    options = layout.options
    fanout_groups: dict[tuple[str, str], list[Edge]] = {}
    fanin_groups: dict[tuple[str, str], list[Edge]] = {}
    side_fanin_groups: dict[tuple[str, str], list[Edge]] = {}

    for edge in layout.edges:
        source_port, target_port = resolved_ports(edge, node_by_id, order)
        if order[edge.target] <= order[edge.source]:
            continue
        if source_port == "s" and target_port == "n":
            fanout_groups.setdefault((edge.source, source_port), []).append(edge)
            fanin_groups.setdefault((edge.target, target_port), []).append(edge)
        if target_port in {"e", "w"}:
            side_fanin_groups.setdefault((edge.target, target_port), []).append(edge)

    fanout_buses: dict[tuple[str, str], float] = {}
    for key, edges in fanout_groups.items():
        if len(edges) < 2:
            continue
        source_node = node_by_id[key[0]]
        source_y = source_node.port(key[1]).y
        target_y = min(node_by_id[edge.target].port("n").y for edge in edges)
        gap = target_y - source_y
        if gap <= options.port_stub * 3:
            continue
        offset = min(max(options.port_stub * 2, gap * 0.42), gap - options.port_stub * 1.5)
        fanout_buses[key] = snap(source_y + offset, options.grid_size)

    fanin_buses: dict[tuple[str, str], float] = {}
    for key, edges in fanin_groups.items():
        if len(edges) < 2:
            continue
        target_node = node_by_id[key[0]]
        target_y = target_node.port(key[1]).y
        source_y = max(node_by_id[edge.source].port("s").y for edge in edges)
        gap = target_y - source_y
        if gap <= options.port_stub * 3:
            continue
        offset = min(max(options.port_stub * 2, gap * 0.7), gap - options.port_stub)
        fanin_buses[key] = snap(source_y + offset, options.grid_size)

    side_fanin_buses: dict[tuple[str, str], float] = {}
    for key, edges in side_fanin_groups.items():
        if len(edges) < 2:
            continue
        target_node = node_by_id[key[0]]
        target_port = key[1]
        group_nodes = [target_node, *(node_by_id[edge.source] for edge in edges)]
        if target_port == "e":
            local_x = max(node.bbox.right for node in group_nodes) + options.side_stub + options.node_pad
            fallback_x = layout.right_lanes[0] if layout.right_lanes else local_x
        else:
            local_x = min(node.bbox.left for node in group_nodes) - options.side_stub - options.node_pad
            fallback_x = layout.left_lanes[0] if layout.left_lanes else local_x
        candidates: list[float] = []
        for candidate in (local_x, fallback_x):
            snapped = snap(candidate, options.grid_size)
            if all(abs(snapped - existing) >= 0.001 for existing in candidates):
                candidates.append(snapped)
        for candidate in candidates:
            candidate_routes = [side_fanin_route_points(edge, node_by_id, order, candidate, options) for edge in edges]
            if not any(route_crosses_node_interiors(points, layout.nodes) for points in candidate_routes):
                side_fanin_buses[key] = candidate
                break

    return fanout_buses, fanin_buses, side_fanin_buses


def shared_bus_route(start: Point, end: Point, bus_y: float) -> list[Point]:
    return simplify_points([start, Point(start.x, bus_y), Point(end.x, bus_y), end])


def route_edge(
    edge: Edge,
    layout: Layout,
    grid: CostGrid,
    node_by_id: dict[str, Node],
    order: dict[str, int],
    lane_usage: dict[str, int],
    fanout_buses: dict[tuple[str, str], float],
    fanin_buses: dict[tuple[str, str], float],
    side_fanin_buses: dict[tuple[str, str], float],
) -> Route:
    source_node = node_by_id[edge.source]
    target_node = node_by_id[edge.target]
    source_port, target_port = resolved_ports(edge, node_by_id, order)
    is_back_edge = order[edge.target] <= order[edge.source]
    start = source_node.port(source_port)
    end = target_node.port(target_port)
    if not is_back_edge and source_port == "s" and target_port == "n":
        fanout_y = fanout_buses.get((edge.source, source_port))
        if fanout_y is not None:
            return Route(edge=edge, points=shared_bus_route(start, end, fanout_y), is_back_edge=False)
        fanin_y = fanin_buses.get((edge.target, target_port))
        if fanin_y is not None:
            return Route(edge=edge, points=shared_bus_route(start, end, fanin_y), is_back_edge=False)

    if not is_back_edge and source_port == "s" and target_port == "n" and abs(start.x - end.x) < 0.001:
        return Route(edge=edge, points=[start, end], is_back_edge=False)

    start_stub = adaptive_stub(start, source_port, end, layout.options)
    end_stub = adaptive_stub(end, target_port, start, layout.options)
    start_stub = snap_stub(start_stub, start, source_port, layout.options.grid_size)
    end_stub = snap_stub(end_stub, end, target_port, layout.options.grid_size)
    side_fanin_x = None if is_back_edge else side_fanin_buses.get((edge.target, target_port))
    if side_fanin_x is not None:
        points = simplify_points(
            [
                start,
                start_stub,
                Point(side_fanin_x, start_stub.y),
                Point(side_fanin_x, end_stub.y),
                end_stub,
                end,
            ]
        )
        if not route_crosses_node_interiors(points, layout.nodes):
            return Route(edge=edge, points=points, is_back_edge=False)

    side, lane_x = choose_lane(edge, order, lane_usage, layout) if is_back_edge else (route_side(edge, order), 0.0)
    low_order = min(order[edge.source], order[edge.target])
    high_order = max(order[edge.source], order[edge.target])
    blockers = [node for node in node_by_id.values() if low_order < order[node.id] < high_order]

    grid.clear_cells([start_stub, end_stub], radius=1)
    initial_dir = direction_index(source_port)
    final_dir = direction_index(OPPOSITE_PORT[target_port]) if target_port in OPPOSITE_PORT else None

    if is_back_edge:
        grid.reserve_lane(lane_x)
        routed = back_edge_skeleton(
            start_stub,
            end_stub,
            source_node,
            target_node,
            source_port,
            target_port,
            lane_x,
            layout.options,
        )
    elif source_port in {"e", "w"} and target_port in {"n", "s"}:
        direct_routed = direct_side_to_vertical_skeleton(start_stub, end_stub)
        direct_points = simplify_points([start, start_stub, *direct_routed, end_stub, end])
        if not route_crosses_node_interiors(direct_points, layout.nodes):
            routed = direct_routed
        else:
            side_lanes = layout.right_lanes if side == "right" else layout.left_lanes
            side_x = side_lanes[0] if side_lanes else start_stub.x
            routed = forward_side_skeleton(
                start_stub,
                end_stub,
                source_port,
                side_x,
                blockers,
                layout.options,
            )
    else:
        routed = astar(
            grid,
            start_stub,
            end_stub,
            initial_dir=initial_dir,
            final_dir=final_dir,
            preferred_side=edge.route_hint,
            center_x=source_node.x,
        )
        routed = align_route_to_stubs(routed, start_stub, end_stub)

    points = simplify_points([start, start_stub, *routed, end_stub, end])
    return Route(edge=edge, points=points, is_back_edge=is_back_edge)


def estimate_text_rect(position: Point, text: str, size: int, pad: float) -> Rect:
    lines = str(text).splitlines() or [""]
    width = max(max(len(line) for line in lines) * size, size * 1.5) + pad * 2
    height = len(lines) * size * 1.25 + pad * 2
    return Rect(
        position.x - width / 2,
        position.y - height / 2,
        position.x + width / 2,
        position.y + height / 2,
    )


def content_bounds(layout: Layout, routes: list[Route]) -> Rect:
    rects = [node.bbox.inflate(4.0) for node in layout.nodes]
    stroke_pad = 12.0
    for route in routes:
        if route.points:
            rects.append(points_bounds(route.points).inflate(stroke_pad))
        if route.edge.label and route.label_position:
            rects.append(
                estimate_text_rect(
                    route.label_position,
                    route.edge.label,
                    layout.options.label_font_size,
                    layout.options.label_pad,
                )
            )
    if layout.title:
        title_position = Point(layout.width / 2, 38)
        rects.append(
            estimate_text_rect(
                title_position,
                layout.title,
                layout.options.title_font_size,
                layout.options.label_pad,
            )
        )
    padding = max(12.0, layout.options.grid_size)
    bounds = union_rects(rects).inflate(padding)
    return Rect(
        math.floor(bounds.left),
        math.floor(bounds.top),
        math.ceil(bounds.right),
        math.ceil(bounds.bottom),
    )


def label_candidates(points: list[Point]) -> list[Point]:
    candidates: list[Point] = []
    segments = list(zip(points, points[1:]))
    for start, end in segments:
        if abs(start.y - end.y) < 0.001 and abs(start.x - end.x) > 20:
            candidates.append(Point((start.x + end.x) / 2, start.y - 16))
            candidates.append(Point((start.x + end.x) / 2, start.y + 16))
            break
    for start, end in segments:
        if abs(start.x - end.x) < 0.001 and abs(start.y - end.y) > 20:
            side = 18 if start.x >= points[0].x else -18
            candidates.append(Point(start.x + side, (start.y + end.y) / 2))
            candidates.append(Point(start.x - side, (start.y + end.y) / 2))
            break
    longest = max(segments, key=lambda item: abs(item[0].x - item[1].x) + abs(item[0].y - item[1].y), default=None)
    if longest:
        start, end = longest
        if abs(start.y - end.y) < 0.001:
            candidates.append(Point((start.x + end.x) / 2, start.y - 16))
            candidates.append(Point((start.x + end.x) / 2, start.y + 16))
        else:
            candidates.append(Point(start.x + 18, (start.y + end.y) / 2))
            candidates.append(Point(start.x - 18, (start.y + end.y) / 2))
    return candidates


def place_label(route: Route, grid: CostGrid, options: RenderOptions) -> None:
    if not route.edge.label:
        return
    candidates = label_candidates(route.points)
    if not candidates:
        return
    best = min(
        candidates,
        key=lambda point: grid.rect_cost(
            estimate_text_rect(point, route.edge.label, options.label_font_size, options.label_pad)
        ),
    )
    route.label_position = best
    grid.mark_rect(
        estimate_text_rect(best, route.edge.label, options.label_font_size, options.label_pad),
        CellKind.LABEL,
        overwrite=False,
    )


def build_grid(layout: Layout) -> CostGrid:
    grid = CostGrid(layout.width, layout.height, layout.options)
    for lane in layout.left_lanes + layout.right_lanes:
        grid.reserve_lane(lane)
    for node in layout.nodes:
        grid.mark_node(node)
    return grid


def route_edges(layout: Layout) -> tuple[list[Route], CostGrid]:
    node_by_id = {node.id: node for node in layout.nodes}
    order = {node.id: index for index, node in enumerate(layout.nodes)}
    grid = build_grid(layout)
    fanout_buses, fanin_buses, side_fanin_buses = build_shared_bus_maps(layout, node_by_id, order)
    lane_usage: dict[str, int] = {}
    indexed_edges = list(enumerate(layout.edges))
    routes_by_index: dict[int, Route] = {}
    for index, edge in sorted(indexed_edges, key=lambda item: edge_priority(item[1], item[0], order)):
        try:
            route = route_edge(
                edge,
                layout,
                grid,
                node_by_id,
                order,
                lane_usage,
                fanout_buses,
                fanin_buses,
                side_fanin_buses,
            )
        except FlowchartError as exc:
            raise FlowchartError(f"{edge.source} -> {edge.target}: {exc}") from exc
        routes_by_index[index] = route
        grid.mark_polyline(route.points, CellKind.LINE)
        place_label(route, grid, layout.options)
    return [routes_by_index[index] for index, _edge in indexed_edges], grid


def render_text(x: float, y: float, text: str, size: int, *, weight: str = "normal", css_class: str = "") -> str:
    lines = str(text).splitlines() or [""]
    line_height = size * 1.25
    first_dy = -((len(lines) - 1) * line_height) / 2
    tspans = []
    for index, line in enumerate(lines):
        dy = first_dy if index == 0 else line_height
        tspans.append(f'<tspan x="{x:.1f}" dy="{dy:.1f}">{escape(line)}</tspan>')
    class_attr = f' class="{escape(css_class)}"' if css_class else ""
    return (
        f'<text{class_attr} x="{x:.1f}" y="{y:.1f}" text-anchor="middle" '
        f'font-size="{size}" font-weight="{weight}">' + "".join(tspans) + "</text>"
    )


def render_node(node: Node, options: RenderOptions) -> str:
    left = node.x - node.width / 2
    top = node.y - node.height / 2
    if node.kind == "rect":
        shape = f'<rect x="{left:.1f}" y="{top:.1f}" width="{node.width:.1f}" height="{node.height:.1f}" />'
    elif node.kind == "terminal":
        radius = node.height / 2
        shape = (
            f'<rect x="{left:.1f}" y="{top:.1f}" width="{node.width:.1f}" height="{node.height:.1f}" '
            f'rx="{radius:.1f}" ry="{radius:.1f}" />'
        )
    else:
        points = [node.port("n"), node.port("e"), node.port("s"), node.port("w")]
        shape = f'<polygon points="{points_to_attr(points)}" />'
    return f'<g class="node {node.kind}">{shape}{render_text(node.x, node.y, node.text, options.node_font_size)}</g>'


def build_svg(layout: Layout, routes: list[Route], grid: CostGrid, *, font: str) -> str:
    if layout.options.theme == "black":
        background = "black"
        node_fill = "white"
        node_stroke = "black"
        node_text = "black"
        edge_color = "white"
        label_color = "white"
    else:
        background = "white"
        node_fill = "white"
        node_stroke = "#333333"
        node_text = "#222222"
        edge_color = "#333333"
        label_color = "#222222"

    bounds = content_bounds(layout, routes)
    marker_width = layout.options.arrow_size
    marker_height = layout.options.arrow_size * 0.78
    body: list[str] = []
    if layout.options.debug_grid:
        body.append(grid.debug_svg())
    if layout.title:
        body.append(
            render_text(
                layout.width / 2,
                38,
                layout.title,
                layout.options.title_font_size,
                weight="600",
                css_class="title",
            )
        )

    for route in routes:
        body.append(
            '<polyline class="edge" '
            f'points="{points_to_attr(route.points)}" marker-end="url(#arrow)" />'
        )
        if route.edge.label and route.label_position:
            body.append(
                render_text(
                    route.label_position.x,
                    route.label_position.y,
                    route.edge.label,
                    layout.options.label_font_size,
                    css_class="edge-label",
                )
            )

    for node in layout.nodes:
        body.append(render_node(node, layout.options))

    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{bounds.width:.0f}" height="{bounds.height:.0f}" viewBox="{bounds.left:.1f} {bounds.top:.1f} {bounds.width:.1f} {bounds.height:.1f}">
<defs>
  <marker id="arrow" viewBox="0 0 10 8" refX="9" refY="4" markerWidth="{marker_width:.2f}" markerHeight="{marker_height:.2f}" orient="auto" markerUnits="strokeWidth">
    <path d="M 0 0 L 10 4 L 0 8 z" fill="{edge_color}" />
  </marker>
</defs>
<style>
  svg {{
    background: {background};
    color: {node_text};
    font-family: "{escape(font)}", "PingFang SC", "Songti SC", "Heiti SC", Arial, sans-serif;
  }}
  .node rect,
  .node polygon {{
    fill: {node_fill};
    stroke: {node_stroke};
    stroke-width: {layout.options.node_stroke_width:.2f};
  }}
  .node text {{
    fill: {node_text};
  }}
  .edge {{
    fill: none;
    stroke: {edge_color};
    stroke-width: {layout.options.edge_stroke_width:.2f};
    stroke-linecap: square;
    stroke-linejoin: miter;
  }}
  .edge-label,
  .title {{
    fill: {label_color};
  }}
  .debug-grid .debug-cell {{
    pointer-events: none;
  }}
  text {{
    dominant-baseline: middle;
  }}
</style>
<rect x="{bounds.left:.1f}" y="{bounds.top:.1f}" width="{bounds.width:.1f}" height="{bounds.height:.1f}" fill="{background}" />
{chr(10).join(body)}
</svg>
'''


def render_png(svg_path: Path, png_path: Path) -> None:
    converter = shutil.which("rsvg-convert")
    if not converter:
        raise FlowchartError("rsvg-convert was not found in PATH; install librsvg to export PNG")

    png_path.parent.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        [converter, str(svg_path), "-o", str(png_path)],
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        message = result.stderr.strip() or result.stdout.strip() or "SVG to PNG conversion failed"
        raise FlowchartError(message)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Render a JSON flowchart to SVG and PNG.")
    parser.add_argument("json_file", type=Path, help="Input flowchart JSON file")
    parser.add_argument("-o", "--output", type=Path, help="Output PNG path")
    parser.add_argument("--svg-output", type=Path, help="Output SVG path")
    parser.add_argument("--font", default=None, help="Font used for labels")
    parser.add_argument("--debug-grid", action="store_true", help="Render routing grid overlays in the SVG")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    png_path = args.output or args.json_file.with_suffix(".png")
    svg_path = args.svg_output or png_path.with_suffix(".svg")

    try:
        data = read_flowchart(args.json_file)
        nodes, edges, title, options = parse_flowchart(data)
        if args.font:
            options.font = args.font
        options.debug_grid = bool(args.debug_grid)
        layout = compute_layout(nodes, edges, title, options)
        routes, grid = route_edges(layout)
        svg_path.parent.mkdir(parents=True, exist_ok=True)
        svg_path.write_text(build_svg(layout, routes, grid, font=options.font), encoding="utf-8")
        render_png(svg_path, png_path)
    except FlowchartError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    print(f"generated: {svg_path}")
    print(f"generated: {png_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
