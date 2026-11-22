from __future__ import annotations

import math
import unicodedata
from dataclasses import dataclass, field
from typing import Any


GRID = 20
FONT_STACK = "PingFang SC, Songti SC, SimSun, Arial, sans-serif"
# A full diagonal radius makes wide attribute bands reserve empty corner space.
# Keep ordinary diagrams close to their actual footprint; dense diagrams still
# use the more conservative value below.
DEFAULT_TERRITORY_DIAGONAL_BLEND = 0.08
DENSE_TERRITORY_DIAGONAL_BLEND = 0.72
DENSE_TERRITORY_THRESHOLD = 16
VALID_SIDES = {"top", "right", "bottom", "left"}
VALID_ZONES = {
    "center",
    "left",
    "right",
    "top",
    "bottom",
    "far_left",
    "far_right",
    "lower_left",
    "lower_right",
}
VALID_ATTRIBUTE_MODES = {"auto", "radial", "compact", "hidden", "keys_only"}
VALID_POST_LAYOUTS = {"none", "align", "arrange", "align-arrange"}


class ERError(ValueError):
    pass


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

    @property
    def center(self) -> tuple[float, float]:
        return ((self.left + self.right) / 2, (self.top + self.bottom) / 2)

    def inflate(self, amount: float) -> "Rect":
        return Rect(self.left - amount, self.top - amount, self.right + amount, self.bottom + amount)

    def contains(self, x: float, y: float) -> bool:
        return self.left <= x <= self.right and self.top <= y <= self.bottom

    def intersects(self, other: "Rect") -> bool:
        return not (
            self.right < other.left
            or self.left > other.right
            or self.bottom < other.top
            or self.top > other.bottom
        )


@dataclass
class AttributeSpec:
    id: str
    label: str
    key: bool = False
    multivalued: bool = False
    derived: bool = False


@dataclass
class EntityLayoutHint:
    zone: str | None = None
    priority: float = 0
    order: float | None = None
    near: list[str] = field(default_factory=list)
    x: float | None = None
    y: float | None = None
    attributes_mode: str = "auto"
    attributes_side: str | None = None


@dataclass
class RelationshipLayoutHint:
    side: str | None = None
    order: float | None = None
    x: float | None = None
    y: float | None = None


@dataclass
class LayoutConfig:
    mode: str = "greedy"
    center: str | None = None
    spacing_x: float = 420
    spacing_y: float = 360
    post_layout: str = "none"
    territory_safe_gap: float = 80
    territory_attribute_padding: float = 26
    territory_port_lane: float = 40
    territory_debug: bool = False
    target_aspect: float = 1.6
    entity_positions: dict[str, tuple[float, float]] = field(default_factory=dict)
    relationship_positions: dict[str, tuple[float, float]] = field(default_factory=dict)


@dataclass
class EntitySpec:
    id: str
    label: str
    attributes: list[AttributeSpec]
    layout: EntityLayoutHint = field(default_factory=EntityLayoutHint)


@dataclass
class ParticipantSpec:
    entity: str
    cardinality: str = ""
    role: str = ""
    side: str | None = None


@dataclass
class RelationshipSpec:
    id: str
    label: str
    participants: list[ParticipantSpec]
    layout: RelationshipLayoutHint = field(default_factory=RelationshipLayoutHint)
    attributes: list[AttributeSpec] = field(default_factory=list)


@dataclass
class ERSpec:
    title: str | None
    entities: dict[str, EntitySpec]
    relationships: list[RelationshipSpec]
    layout: LayoutConfig = field(default_factory=LayoutConfig)


@dataclass
class Node:
    id: str
    label: str
    kind: str
    x: float
    y: float
    width: float
    height: float
    owner: str | None = None
    key: bool = False
    multivalued: bool = False
    derived: bool = False

    @property
    def rect(self) -> Rect:
        return Rect(self.x - self.width / 2, self.y - self.height / 2, self.x + self.width / 2, self.y + self.height / 2)


@dataclass
class Edge:
    source: str
    target: str
    label: str = ""
    class_name: str = "edge"
    source_side: str | None = None
    target_side: str | None = None
    display_label: str | None = None


@dataclass(frozen=True)
class Port:
    node_id: str
    side: str
    slot: float
    anchor: tuple[float, float]
    outside: tuple[float, float]
    direction: tuple[int, int]


@dataclass
class Territory:
    entity_id: str
    entity_rect: Rect
    attribute_rect: Rect
    port_lane_rect: Rect
    outer_rect: Rect
    safe_gap: float


@dataclass
class Layout:
    spec: ERSpec
    nodes: dict[str, Node] = field(default_factory=dict)
    edges: list[Edge] = field(default_factory=list)
    paths: dict[tuple[str, str, str], list[tuple[float, float]]] = field(default_factory=dict)
    edge_labels: list[tuple[str, float, float]] = field(default_factory=list)
    ports: dict[tuple[str, str, str, str], Port] = field(default_factory=dict)
    route_kinds: dict[tuple[str, str, str], str] = field(default_factory=dict)
    territories: dict[str, Territory] = field(default_factory=dict)
    debug_territory: bool = False
    placement_order: dict[str, int] = field(default_factory=dict)


def text_units(value: str) -> float:
    units = 0.0
    for ch in value:
        units += 1.65 if unicodedata.east_asian_width(ch) in {"W", "F"} else 1.0
    return max(units, 1.0)


def text_width(value: str, font_size: int) -> float:
    return text_units(value) * font_size * 0.56


def entity_size(label: str) -> tuple[float, float]:
    return max(104, text_width(label, 16) + 48), 48


def relationship_size(label: str) -> tuple[float, float]:
    return max(90, text_width(label, 15) + 52), 64


def attribute_size(label: str) -> tuple[float, float]:
    return max(84, text_width(label, 14) + 42), 42


def node_radius(node: Node) -> float:
    return math.hypot(node.width, node.height) / 2


def territory_diagonal_blend_for_count(entity_count: int) -> float:
    return DENSE_TERRITORY_DIAGONAL_BLEND if entity_count >= DENSE_TERRITORY_THRESHOLD else DEFAULT_TERRITORY_DIAGONAL_BLEND


def territory_circle_radius_for_size(width: float, height: float, diagonal_blend: float) -> float:
    compact_radius = max(width, height) / 2
    diagonal_radius = math.hypot(width, height) / 2
    return compact_radius * (1 - diagonal_blend) + diagonal_radius * diagonal_blend


def normalize_angle(angle: float) -> float:
    result = angle % (math.pi * 2)
    return result + math.pi * 2 if result < 0 else result


def opposite_side(side: str) -> str:
    return {"top": "bottom", "bottom": "top", "left": "right", "right": "left"}[side]


def dominant_side(source: Node, target: Node) -> str:
    dx = target.x - source.x
    dy = target.y - source.y
    if abs(dx) >= abs(dy):
        return "right" if dx >= 0 else "left"
    return "bottom" if dy >= 0 else "top"


def clamp(value: float, low: float, high: float) -> float:
    if low > high:
        return value
    return max(low, min(high, value))


def centered_slot(index: int, count: int) -> float:
    if count <= 1:
        return 0
    return index - (count - 1) / 2


def path_segments(path: list[tuple[float, float]]) -> list[tuple[tuple[float, float], tuple[float, float]]]:
    return list(zip(path, path[1:]))


def manhattan_path_length(path: list[tuple[float, float]]) -> float:
    return sum(abs(a[0] - b[0]) + abs(a[1] - b[1]) for a, b in path_segments(path))


def euclidean_path_length(path: list[tuple[float, float]]) -> float:
    return sum(math.hypot(a[0] - b[0], a[1] - b[1]) for a, b in path_segments(path))


def turn_count(path: list[tuple[float, float]]) -> int:
    turns = 0
    for a, b, c in zip(path, path[1:], path[2:]):
        if (a[0] == b[0]) != (b[0] == c[0]):
            turns += 1
    return turns


def compute_territory_circle_radius(entity_count: int, rect_width: float, rect_height: float) -> float:
    return territory_circle_radius_for_size(
        rect_width, rect_height, territory_diagonal_blend_for_count(entity_count),
    )


def effective_attribute_mode(entity_count: int, attr_count: int, mode: str) -> str:
    if mode != "auto":
        return mode
    return "compact" if attr_count <= 6 or entity_count >= 4 else "radial"
