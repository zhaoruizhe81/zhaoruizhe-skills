from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping


class NodeKind(str, Enum):
    ACTOR = "actor"
    USECASE = "usecase"
    BOUNDARY = "boundary"


class LayoutMode(str, Enum):
    SIMPLE = "simple"
    COMPLEX = "complex"


class ActorSide(str, Enum):
    AUTO = "auto"
    LEFT = "left"
    RIGHT = "right"


class BoundaryShape(str, Enum):
    BOX = "box"
    FRAME = "frame"


class EdgeType(str, Enum):
    ASSOCIATION = "association"
    INCLUDE = "include"
    EXTEND = "extend"
    GENERALIZATION = "generalization"


class LineStyle(str, Enum):
    SOLID = "solid"
    DASHED = "dashed"


class ArrowHead(str, Enum):
    NONE = "none"
    OPEN = "open"
    TRIANGLE = "triangle"


class RouteMode(str, Enum):
    STRAIGHT = "straight"
    ORTHOGONAL = "orthogonal"


@dataclass(frozen=True)
class LayoutConfig:
    mode: LayoutMode = LayoutMode.SIMPLE
    association_arrow: ArrowHead | None = None

    def resolved_association_arrow(self) -> ArrowHead:
        if self.association_arrow is not None:
            return self.association_arrow
        if self.mode is LayoutMode.COMPLEX:
            return ArrowHead.OPEN
        return ArrowHead.NONE


@dataclass(frozen=True)
class Point:
    x: float
    y: float

    def shifted(self, dx: float = 0.0, dy: float = 0.0) -> Point:
        return Point(self.x + dx, self.y + dy)


@dataclass(frozen=True)
class Rect:
    x: float
    y: float
    width: float
    height: float

    @property
    def left(self) -> float:
        return self.x

    @property
    def right(self) -> float:
        return self.x + self.width

    @property
    def top(self) -> float:
        return self.y

    @property
    def bottom(self) -> float:
        return self.y + self.height

    @property
    def center(self) -> Point:
        return Point(self.x + self.width / 2, self.y + self.height / 2)

    def inflate(self, amount: float) -> Rect:
        return Rect(
            self.x - amount,
            self.y - amount,
            self.width + amount * 2,
            self.height + amount * 2,
        )

    def contains_point(self, point: Point, *, include_boundary: bool = True) -> bool:
        if include_boundary:
            return (
                self.left <= point.x <= self.right
                and self.top <= point.y <= self.bottom
            )
        return (
            self.left < point.x < self.right and self.top < point.y < self.bottom
        )

    def intersects_segment(self, start: Point, end: Point) -> bool:
        if start.x == end.x:
            seg_top = min(start.y, end.y)
            seg_bottom = max(start.y, end.y)
            return self.left <= start.x <= self.right and max(seg_top, self.top) <= min(
                seg_bottom, self.bottom
            )
        if start.y == end.y:
            seg_left = min(start.x, end.x)
            seg_right = max(start.x, end.x)
            return self.top <= start.y <= self.bottom and max(seg_left, self.left) <= min(
                seg_right, self.right
            )

        return (
            self.contains_point(start)
            or self.contains_point(end)
            or _segments_intersect(start, end, Point(self.left, self.top), Point(self.right, self.top))
            or _segments_intersect(start, end, Point(self.right, self.top), Point(self.right, self.bottom))
            or _segments_intersect(start, end, Point(self.right, self.bottom), Point(self.left, self.bottom))
            or _segments_intersect(start, end, Point(self.left, self.bottom), Point(self.left, self.top))
        )


def _orientation(a: Point, b: Point, c: Point) -> float:
    return (b.y - a.y) * (c.x - b.x) - (b.x - a.x) * (c.y - b.y)


def _on_segment(a: Point, b: Point, c: Point) -> bool:
    return (
        min(a.x, c.x) <= b.x <= max(a.x, c.x)
        and min(a.y, c.y) <= b.y <= max(a.y, c.y)
    )


def _segments_intersect(a: Point, b: Point, c: Point, d: Point) -> bool:
    o1 = _orientation(a, b, c)
    o2 = _orientation(a, b, d)
    o3 = _orientation(c, d, a)
    o4 = _orientation(c, d, b)

    if o1 == 0 and _on_segment(a, c, b):
        return True
    if o2 == 0 and _on_segment(a, d, b):
        return True
    if o3 == 0 and _on_segment(c, a, d):
        return True
    if o4 == 0 and _on_segment(c, b, d):
        return True
    return (o1 > 0) != (o2 > 0) and (o3 > 0) != (o4 > 0)


@dataclass
class Node:
    id: str
    label: str
    x: float | None = None
    y: float | None = None
    width: float | None = None
    height: float | None = None
    boundary: str | None = None
    icon: str | None = None
    side: ActorSide = ActorSide.AUTO
    shape: BoundaryShape | None = None
    kind: NodeKind = NodeKind.USECASE

    def measure_size(self) -> tuple[float, float]:
        if self.width is not None and self.height is not None:
            return self.width, self.height

        if self.kind is NodeKind.ACTOR:
            default_width, default_height = 72.0, 96.0
        elif self.kind is NodeKind.BOUNDARY:
            default_width, default_height = 360.0, 260.0
        else:
            label_width = max((len(line) for line in self.label.splitlines()), default=8)
            default_width = max(120.0, label_width * 7.5 + 36.0)
            default_height = max(52.0, len(self.label.splitlines() or [""]) * 18.0 + 30.0)

        return self.width or default_width, self.height or default_height

    def bbox(self) -> Rect:
        if self.x is None or self.y is None:
            raise ValueError(f"Node {self.id!r} has not been positioned")
        width, height = self.measure_size()
        return Rect(self.x, self.y, width, height)

    def port(self, side: str, offset: float = 0.0) -> Point:
        box = self.bbox()
        if side == "left":
            return Point(box.left, _clamp(box.center.y + offset, box.top + 8, box.bottom - 8))
        if side == "right":
            return Point(box.right, _clamp(box.center.y + offset, box.top + 8, box.bottom - 8))
        if side == "top":
            return Point(_clamp(box.center.x + offset, box.left + 8, box.right - 8), box.top)
        if side == "bottom":
            return Point(_clamp(box.center.x + offset, box.left + 8, box.right - 8), box.bottom)
        raise ValueError(f"Unknown port side: {side}")


@dataclass
class ActorNode(Node):
    kind: NodeKind = field(default=NodeKind.ACTOR, init=False)


@dataclass
class UseCaseNode(Node):
    kind: NodeKind = field(default=NodeKind.USECASE, init=False)


@dataclass
class BoundaryNode(Node):
    kind: NodeKind = field(default=NodeKind.BOUNDARY, init=False)


@dataclass
class Edge:
    source: str
    target: str
    type: EdgeType = EdgeType.ASSOCIATION
    id: str | None = None
    label: str | None = None
    style: LineStyle | None = None
    arrow: ArrowHead | None = None
    route: RouteMode | None = None

    def resolved_style(self) -> LineStyle:
        if self.style is not None:
            return self.style
        if self.type in {EdgeType.INCLUDE, EdgeType.EXTEND}:
            return LineStyle.DASHED
        return LineStyle.SOLID

    def resolved_arrow(
        self, default_association_arrow: ArrowHead | None = None
    ) -> ArrowHead:
        if self.arrow is not None:
            return self.arrow
        if self.type is EdgeType.ASSOCIATION and default_association_arrow is not None:
            return default_association_arrow
        if self.type in {EdgeType.INCLUDE, EdgeType.EXTEND}:
            return ArrowHead.OPEN
        if self.type is EdgeType.GENERALIZATION:
            return ArrowHead.TRIANGLE
        return ArrowHead.NONE

    def resolved_label(self) -> str | None:
        if self.label is not None:
            return self.label
        if self.type is EdgeType.INCLUDE:
            return "<<include>>"
        if self.type is EdgeType.EXTEND:
            return "<<extend>>"
        return None

    def resolved_route(self) -> RouteMode:
        return self.route or RouteMode.STRAIGHT


@dataclass
class Diagram:
    nodes: dict[str, Node]
    edges: list[Edge]
    title: str | None = None
    width: float | None = None
    height: float | None = None
    layout: LayoutConfig = field(default_factory=LayoutConfig)

    def node(self, node_id: str) -> Node:
        try:
            return self.nodes[node_id]
        except KeyError as exc:
            raise KeyError(f"Unknown node id: {node_id}") from exc

    def visible_nodes(self) -> list[Node]:
        return list(self.nodes.values())


def load_diagram(data: Mapping[str, Any]) -> Diagram:
    nodes: dict[str, Node] = {}

    for item in data.get("actors", []):
        node = ActorNode(**_node_kwargs(item))
        _add_node(nodes, node)

    for item in data.get("usecases", []):
        node = UseCaseNode(**_node_kwargs(item))
        _add_node(nodes, node)

    for item in data.get("boundaries", []):
        node = BoundaryNode(**_node_kwargs(item))
        _add_node(nodes, node)

    edges = [_load_edge(item, index) for index, item in enumerate(data.get("edges", []), start=1)]

    return Diagram(
        nodes=nodes,
        edges=edges,
        title=_optional_str(data.get("title")),
        width=_optional_float(data.get("width")),
        height=_optional_float(data.get("height")),
        layout=_load_layout(data.get("layout")),
    )


def _add_node(nodes: dict[str, Node], node: Node) -> None:
    if node.id in nodes:
        raise ValueError(f"Duplicate node id: {node.id}")
    nodes[node.id] = node


def _node_kwargs(item: Mapping[str, Any]) -> dict[str, Any]:
    node_id = str(item["id"])
    side = item.get("side")
    shape = item.get("shape")
    return {
        "id": node_id,
        "label": str(item.get("label", node_id)),
        "x": _optional_float(item.get("x")),
        "y": _optional_float(item.get("y")),
        "width": _optional_float(item.get("width")),
        "height": _optional_float(item.get("height")),
        "boundary": _optional_str(item.get("boundary")),
        "icon": _optional_str(item.get("icon")),
        "side": ActorSide(str(side)) if side is not None else ActorSide.AUTO,
        "shape": BoundaryShape(str(shape)) if shape is not None else None,
    }


def _load_edge(item: Mapping[str, Any], index: int) -> Edge:
    edge_type = EdgeType(str(item.get("type", EdgeType.ASSOCIATION.value)))
    style = item.get("style")
    arrow = item.get("arrow")
    route = item.get("route")
    return Edge(
        id=_optional_str(item.get("id")) or f"edge_{index}",
        source=str(item["source"]),
        target=str(item["target"]),
        type=edge_type,
        label=_optional_str(item.get("label")),
        style=LineStyle(str(style)) if style is not None else None,
        arrow=ArrowHead(str(arrow)) if arrow is not None else None,
        route=RouteMode(str(route)) if route is not None else None,
    )


def _load_layout(value: Any) -> LayoutConfig:
    if value is None:
        return LayoutConfig()
    if not isinstance(value, Mapping):
        raise ValueError("layout must be an object")

    mode = LayoutMode(str(value.get("mode", LayoutMode.SIMPLE.value)))
    association_arrow = value.get("associationArrow", value.get("association_arrow"))
    return LayoutConfig(
        mode=mode,
        association_arrow=(
            ArrowHead(str(association_arrow)) if association_arrow is not None else None
        ),
    )


def _optional_float(value: Any) -> float | None:
    if value is None:
        return None
    return float(value)


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)


def _clamp(value: float, lower: float, upper: float) -> float:
    if lower > upper:
        return value
    return max(lower, min(upper, value))
