from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .model import (
    ERError,
    AttributeSpec,
    EntityLayoutHint,
    EntitySpec,
    ERSpec,
    LayoutConfig,
    ParticipantSpec,
    RelationshipLayoutHint,
    RelationshipSpec,
    VALID_ATTRIBUTE_MODES,
    VALID_POST_LAYOUTS,
    VALID_SIDES,
    VALID_ZONES,
)


def load_spec(path: Path) -> ERSpec:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ERError(f"Invalid JSON: {exc}") from exc
    except OSError as exc:
        raise ERError(f"Cannot read input file: {exc}") from exc
    return parse_spec(data)


def parse_spec(data: Any) -> ERSpec:
    if not isinstance(data, dict):
        raise ERError("Top-level JSON value must be an object")
    layout = parse_layout_config(data)
    raw_entities = data.get("entities")
    if not isinstance(raw_entities, list) or not raw_entities:
        raise ERError("entities must be a non-empty array")

    entities: dict[str, EntitySpec] = {}
    for index, raw_entity in enumerate(raw_entities):
        if not isinstance(raw_entity, dict):
            raise ERError(f"entities[{index}] must be an object")
        entity_id = require_id(raw_entity, f"entities[{index}]")
        if entity_id in entities:
            raise ERError(f"Duplicate entity id: {entity_id}")
        raw_attrs = raw_entity.get("attributes", [])
        if not isinstance(raw_attrs, list):
            raise ERError(f"Entity {entity_id} attributes must be an array")
        attributes: list[AttributeSpec] = []
        seen_attrs: set[str] = set()
        for attr_index, raw_attr in enumerate(raw_attrs):
            if not isinstance(raw_attr, dict):
                raise ERError(f"Entity {entity_id} attributes[{attr_index}] must be an object")
            attr_id = require_id(raw_attr, f"Entity {entity_id} attributes[{attr_index}]")
            if attr_id in seen_attrs:
                raise ERError(f"Duplicate attribute id in entity {entity_id}: {attr_id}")
            seen_attrs.add(attr_id)
            attributes.append(
                AttributeSpec(
                    id=attr_id,
                    label=label_of(raw_attr, attr_id),
                    key=bool(raw_attr.get("key", False)),
                    multivalued=bool(raw_attr.get("multivalued", False)),
                    derived=bool(raw_attr.get("derived", False)),
                )
            )
        entities[entity_id] = EntitySpec(entity_id, label_of(raw_entity, entity_id), attributes, parse_entity_layout(raw_entity, entity_id))

    if layout.center is not None and layout.center not in entities:
        raise ERError(f"layout.center references unknown entity: {layout.center}")
    for entity_id in layout.entity_positions:
        if entity_id not in entities:
            raise ERError(f"layout.positions.entities references unknown entity: {entity_id}")
    for entity in entities.values():
        for near_id in entity.layout.near:
            if near_id not in entities:
                raise ERError(f"Entity {entity.id} layout.near references unknown entity: {near_id}")

    relationships: list[RelationshipSpec] = []
    seen_relationships: set[str] = set()
    raw_relationships = data.get("relationships", [])
    if not isinstance(raw_relationships, list):
        raise ERError("relationships must be an array when provided")
    for index, raw_rel in enumerate(raw_relationships):
        if not isinstance(raw_rel, dict):
            raise ERError(f"relationships[{index}] must be an object")
        rel_id = require_id(raw_rel, f"relationships[{index}]")
        if rel_id in seen_relationships:
            raise ERError(f"Duplicate relationship id: {rel_id}")
        seen_relationships.add(rel_id)
        participants = parse_participants(raw_rel, rel_id, entities)
        rel_attrs = parse_relationship_attributes(raw_rel, rel_id)
        relationships.append(RelationshipSpec(rel_id, label_of(raw_rel, rel_id), participants, parse_relationship_layout(raw_rel, rel_id), rel_attrs))
    for rel_id in layout.relationship_positions:
        if rel_id not in seen_relationships:
            raise ERError(f"layout.positions.relationships references unknown relationship: {rel_id}")

    title = data.get("title")
    if title is not None and not isinstance(title, str):
        raise ERError("title must be a string when provided")
    return ERSpec(title.strip() if isinstance(title, str) and title.strip() else None, entities, relationships, layout)


def apply_layout_file(spec: ERSpec, path: Path) -> None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ERError(f"Invalid layout JSON: {exc}") from exc
    except OSError as exc:
        raise ERError(f"Cannot read layout file: {exc}") from exc
    external = parse_layout_config(data)
    for entity_id in external.entity_positions:
        if entity_id not in spec.entities:
            raise ERError(f"layout file references unknown entity: {entity_id}")
    relationship_ids = {relationship.id for relationship in spec.relationships}
    for rel_id in external.relationship_positions:
        if rel_id not in relationship_ids:
            raise ERError(f"layout file references unknown relationship: {rel_id}")
    spec.layout.entity_positions.update(external.entity_positions)
    spec.layout.relationship_positions.update(external.relationship_positions)


def parse_relationship_attributes(raw_rel: dict[str, Any], rel_id: str) -> list[AttributeSpec]:
    raw_attrs = raw_rel.get("attributes", [])
    if not isinstance(raw_attrs, list):
        raise ERError(f"Relationship {rel_id} attributes must be an array")
    attributes: list[AttributeSpec] = []
    seen: set[str] = set()
    for attr_index, raw_attr in enumerate(raw_attrs):
        if not isinstance(raw_attr, dict):
            raise ERError(f"Relationship {rel_id} attributes[{attr_index}] must be an object")
        attr_id = require_id(raw_attr, f"Relationship {rel_id} attributes[{attr_index}]")
        if attr_id in seen:
            raise ERError(f"Duplicate attribute id in relationship {rel_id}: {attr_id}")
        seen.add(attr_id)
        attributes.append(
            AttributeSpec(
                id=attr_id,
                label=label_of(raw_attr, attr_id),
                key=bool(raw_attr.get("key", False)),
                multivalued=bool(raw_attr.get("multivalued", False)),
                derived=bool(raw_attr.get("derived", False)),
            )
        )
    return attributes


def parse_participants(raw_rel: dict[str, Any], rel_id: str, entities: dict[str, EntitySpec]) -> list[ParticipantSpec]:
    raw_participants = raw_rel.get("participants")
    if not isinstance(raw_participants, list) or not raw_participants:
        raise ERError(f"Relationship {rel_id} participants must be a non-empty array")
    participants: list[ParticipantSpec] = []
    for index, raw_part in enumerate(raw_participants):
        if not isinstance(raw_part, dict):
            raise ERError(f"Relationship {rel_id} participants[{index}] must be an object")
        entity_id = raw_part.get("entity")
        if not isinstance(entity_id, str) or entity_id not in entities:
            raise ERError(f"Relationship {rel_id} references unknown entity: {entity_id}")
        cardinality = raw_part.get("cardinality", "")
        role = raw_part.get("role", "")
        if not isinstance(cardinality, str) or not isinstance(role, str):
            raise ERError(f"Relationship {rel_id} participant labels must be strings")
        side = raw_part.get("side")
        if side is not None:
            if not isinstance(side, str) or side not in VALID_SIDES:
                raise ERError(f"Relationship {rel_id} participant side must be one of: {', '.join(sorted(VALID_SIDES))}")
        participants.append(ParticipantSpec(entity_id, cardinality.strip(), role.strip(), side))
    return participants


def parse_entity_layout(raw_entity: dict[str, Any], entity_id: str) -> EntityLayoutHint:
    raw_layout = raw_entity.get("layout", {}) or {}
    if not isinstance(raw_layout, dict):
        raise ERError(f"Entity {entity_id} layout must be an object when provided")
    zone = raw_layout.get("zone")
    if zone is not None and (not isinstance(zone, str) or zone not in VALID_ZONES):
        raise ERError(f"Entity {entity_id} layout.zone must be one of: {', '.join(sorted(VALID_ZONES))}")
    priority = raw_layout.get("priority", 0)
    if not isinstance(priority, int | float):
        raise ERError(f"Entity {entity_id} layout.priority must be a number")
    order = raw_layout.get("order")
    if order is not None and not isinstance(order, int | float):
        raise ERError(f"Entity {entity_id} layout.order must be a number")
    near = raw_layout.get("near", []) or []
    if not isinstance(near, list) or not all(isinstance(item, str) and item.strip() for item in near):
        raise ERError(f"Entity {entity_id} layout.near must be an array of entity ids")
    raw_attrs_layout = raw_layout.get("attributes", {}) or {}
    if not isinstance(raw_attrs_layout, dict):
        raise ERError(f"Entity {entity_id} layout.attributes must be an object when provided")
    attr_mode = raw_attrs_layout.get("mode", "auto")
    if not isinstance(attr_mode, str) or attr_mode not in VALID_ATTRIBUTE_MODES:
        raise ERError(f"Entity {entity_id} layout.attributes.mode must be one of: {', '.join(sorted(VALID_ATTRIBUTE_MODES))}")
    attr_side = raw_attrs_layout.get("side")
    if attr_side is not None and (not isinstance(attr_side, str) or attr_side not in VALID_SIDES):
        raise ERError(f"Entity {entity_id} layout.attributes.side must be one of: {', '.join(sorted(VALID_SIDES))}")
    return EntityLayoutHint(
        zone=zone,
        priority=float(priority),
        order=float(order) if order is not None else None,
        near=[item.strip() for item in near],
        x=parse_optional_number(raw_layout.get("x"), f"Entity {entity_id} layout.x"),
        y=parse_optional_number(raw_layout.get("y"), f"Entity {entity_id} layout.y"),
        attributes_mode=attr_mode,
        attributes_side=attr_side,
    )


def parse_relationship_layout(raw_rel: dict[str, Any], rel_id: str) -> RelationshipLayoutHint:
    raw_layout = raw_rel.get("layout", {}) or {}
    if not isinstance(raw_layout, dict):
        raise ERError(f"Relationship {rel_id} layout must be an object when provided")
    side = raw_layout.get("side")
    if side is not None and (not isinstance(side, str) or side not in VALID_SIDES):
        raise ERError(f"Relationship {rel_id} layout.side must be one of: {', '.join(sorted(VALID_SIDES))}")
    order = raw_layout.get("order")
    if order is not None and not isinstance(order, int | float):
        raise ERError(f"Relationship {rel_id} layout.order must be a number")
    return RelationshipLayoutHint(
        side=side,
        order=float(order) if order is not None else None,
        x=parse_optional_number(raw_layout.get("x"), f"Relationship {rel_id} layout.x"),
        y=parse_optional_number(raw_layout.get("y"), f"Relationship {rel_id} layout.y"),
    )


def parse_layout_config(data: dict[str, Any]) -> LayoutConfig:
    raw_layout = data.get("layout", {}) or {}
    if not isinstance(raw_layout, dict):
        raise ERError("layout must be an object when provided")
    mode = raw_layout.get("mode", "greedy")
    if not isinstance(mode, str) or not mode.strip():
        raise ERError("layout.mode must be a non-empty string when provided")
    center = raw_layout.get("center")
    if center is not None and (not isinstance(center, str) or not center.strip()):
        raise ERError("layout.center must be a non-empty entity id when provided")
    spacing = raw_layout.get("spacing", {}) or {}
    if not isinstance(spacing, dict):
        raise ERError("layout.spacing must be an object when provided")
    spacing_x = parse_positive_number(spacing.get("x", 420), "layout.spacing.x")
    spacing_y = parse_positive_number(spacing.get("y", 360), "layout.spacing.y")
    post_layout = raw_layout.get("postLayout", raw_layout.get("post_layout", "none"))
    if not isinstance(post_layout, str) or post_layout not in VALID_POST_LAYOUTS:
        raise ERError(f"layout.postLayout must be one of: {', '.join(sorted(VALID_POST_LAYOUTS))}")
    territory = raw_layout.get("territory", {}) or {}
    if not isinstance(territory, dict):
        raise ERError("layout.territory must be an object when provided")
    safe_gap = parse_positive_number(territory.get("safeGap", territory.get("safe_gap", 80)), "layout.territory.safeGap")
    attribute_padding = parse_positive_number(
        territory.get("attributePadding", territory.get("attribute_padding", 26)),
        "layout.territory.attributePadding",
    )
    port_lane = parse_positive_number(territory.get("portLane", territory.get("port_lane", 40)), "layout.territory.portLane")
    debug = territory.get("debug", False)
    if not isinstance(debug, bool):
        raise ERError("layout.territory.debug must be a boolean")
    target_aspect = parse_target_aspect(raw_layout)
    raw_positions = raw_layout.get("positions", {}) or {}
    if not isinstance(raw_positions, dict):
        raise ERError("layout.positions must be an object when provided")
    return LayoutConfig(
        mode=mode,
        center=center.strip() if isinstance(center, str) else None,
        spacing_x=spacing_x,
        spacing_y=spacing_y,
        post_layout=post_layout,
        territory_safe_gap=safe_gap,
        territory_attribute_padding=attribute_padding,
        territory_port_lane=port_lane,
        territory_debug=debug,
        target_aspect=target_aspect,
        entity_positions=parse_position_map(raw_positions.get("entities", {}), "layout.positions.entities"),
        relationship_positions=parse_position_map(raw_positions.get("relationships", {}), "layout.positions.relationships"),
    )


def parse_target_aspect(raw_layout: dict[str, Any]) -> float:
    if "targetAspect" in raw_layout or "target_aspect" in raw_layout:
        return parse_positive_number(raw_layout.get("targetAspect", raw_layout.get("target_aspect")), "layout.targetAspect")
    return 1.6


def parse_position_map(raw_value: Any, context: str) -> dict[str, tuple[float, float]]:
    if raw_value is None:
        return {}
    if not isinstance(raw_value, dict):
        raise ERError(f"{context} must be an object when provided")
    positions: dict[str, tuple[float, float]] = {}
    for item_id, raw_position in raw_value.items():
        if not isinstance(item_id, str) or not item_id.strip():
            raise ERError(f"{context} keys must be non-empty ids")
        if not isinstance(raw_position, dict):
            raise ERError(f"{context}.{item_id} must be an object")
        x = parse_optional_number(raw_position.get("x"), f"{context}.{item_id}.x")
        y = parse_optional_number(raw_position.get("y"), f"{context}.{item_id}.y")
        if x is None or y is None:
            raise ERError(f"{context}.{item_id} must contain numeric x and y")
        positions[item_id.strip()] = (x, y)
    return positions


def require_id(item: dict[str, Any], context: str) -> str:
    value = item.get("id")
    if not isinstance(value, str) or not value.strip():
        raise ERError(f"{context} must contain a non-empty string id")
    return value.strip()


def label_of(item: dict[str, Any], fallback: str) -> str:
    value = item.get("label", fallback)
    if not isinstance(value, str) or not value.strip():
        raise ERError(f"{fallback} label must be a non-empty string when provided")
    return value.strip()


def parse_optional_number(value: Any, context: str) -> float | None:
    if value is None:
        return None
    if not isinstance(value, int | float):
        raise ERError(f"{context} must be a number")
    return float(value)


def parse_positive_number(value: Any, context: str) -> float:
    if not isinstance(value, int | float) or value <= 0:
        raise ERError(f"{context} must be a positive number")
    return float(value)
