from collections import deque

from .model import ERSpec


def entity_adjacency(spec: ERSpec) -> dict[str, set[str]]:
    adjacency: dict[str, set[str]] = {entity_id: set() for entity_id in spec.entities}
    for rel in spec.relationships:
        ids = [participant.entity for participant in rel.participants]
        for i, left in enumerate(ids):
            for right in ids[i + 1 :]:
                if left != right:
                    adjacency[left].add(right)
                    adjacency[right].add(left)
    return adjacency


def relationship_degree(spec: ERSpec) -> dict[str, int]:
    degree = {entity_id: 0 for entity_id in spec.entities}
    for rel in spec.relationships:
        for entity_id in {participant.entity for participant in rel.participants}:
            degree[entity_id] += 1
    return degree


def entity_weights(spec: ERSpec) -> dict[str, dict[str, float]]:
    degree = relationship_degree(spec)
    bridge = bridge_score(spec)
    result: dict[str, dict[str, float]] = {}
    for entity_id, entity in spec.entities.items():
        visual = len(visible_attribute_ids(entity)) * 1.2 + len(entity.label) * 0.2
        topology = degree[entity_id] * 4 + bridge.get(entity_id, 0) * 2 + entity.layout.priority / 20
        result[entity_id] = {"topology": topology, "visual": visual, "degree": degree[entity_id]}
    return result


def bridge_score(spec: ERSpec) -> dict[str, int]:
    adjacency = entity_adjacency(spec)
    score = {entity_id: 0 for entity_id in spec.entities}
    for removed in spec.entities:
        remaining = [entity_id for entity_id in spec.entities if entity_id != removed]
        if len(remaining) < 2:
            continue
        seen = set()
        components = 0
        for start in remaining:
            if start in seen:
                continue
            components += 1
            queue = deque([start])
            seen.add(start)
            while queue:
                current = queue.popleft()
                for neighbor in adjacency[current]:
                    if neighbor == removed or neighbor in seen:
                        continue
                    seen.add(neighbor)
                    queue.append(neighbor)
        score[removed] = max(0, components - 1)
    return score


def choose_center(spec: ERSpec) -> str:
    degree = relationship_degree(spec)
    weights = entity_weights(spec)
    order = {entity_id: index for index, entity_id in enumerate(spec.entities)}
    return max(
        spec.entities,
        key=lambda entity_id: (
            degree[entity_id],
            1 if spec.layout.center == entity_id else 0,
            weights[entity_id]["topology"],
            spec.entities[entity_id].layout.priority,
            -order[entity_id],
        ),
    )


def visible_attribute_ids(entity) -> list[str]:
    if entity.layout.attributes_mode == "hidden":
        return []
    if entity.layout.attributes_mode == "keys_only":
        return [attr.id for attr in entity.attributes if attr.key]
    return [attr.id for attr in entity.attributes]
