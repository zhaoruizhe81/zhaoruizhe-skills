# ER JSON Format

Use this reference when creating or checking input JSON for `er-svg-generator`.

## Minimal Shape

```json
{
  "title": "图书借阅 ER 图",
  "layout": {
    "mode": "greedy",
    "center": "borrow_record",
    "postLayout": "arrange",
    "targetAspect": 1.6,
    "territory": {
      "safeGap": 120,
      "attributePadding": 36,
      "portLane": 52
    }
  },
  "entities": [],
  "relationships": []
}
```

`layout.mode` is accepted for compatibility, but the generator always uses greedy circle layout. `layout.center` is only a tie-breaker; the first entity is normally the highest-degree entity.

## Entities

```json
{
  "id": "borrow_record",
  "label": "借阅记录",
  "layout": {
    "priority": 100,
    "attributes": { "mode": "compact", "side": "top" }
  },
  "attributes": [
    { "id": "record_id", "label": "记录编号", "key": true },
    { "id": "borrow_date", "label": "借阅日期" },
    { "id": "due_date", "label": "应还日期" }
  ]
}
```

Required fields:

- `id`: stable unique id, preferably `snake_case`.
- `label`: diagram label.
- `attributes`: non-empty array. Final ER diagrams must render attributes for every entity; include the primary/identifier attribute and concise core business attributes.

Attribute completeness rules:

- Do not leave an entity with `attributes: []` in final output.
- Do not use `hidden` or `keys_only` in final output unless the user explicitly requests an attribute-suppressed variant.
- When converting SQL DDL, map table columns to attributes and mark primary keys with `key: true`.
- When converting natural-language descriptions, infer a stable identifier plus the essential business attributes where the source is clear; ask for missing attributes if they cannot be inferred safely.
- If an entity has too many fields, choose representative attributes or split the diagram instead of omitting all attributes.

Attribute options:

- `key: true`: underline the label.
- `multivalued: true`: draw a double ellipse.
- `derived: true`: draw dashed outline.

Attribute layout modes:

- `radial`: default; spreads attributes around the entity.
- `compact`: puts attributes on one preferred side.
- `keys_only`: renders only key attributes; use only for debugging or an explicitly requested compact variant, not final ER output.
- `hidden`: hides attributes; use only for debugging or an explicitly requested attribute-suppressed variant, not final ER output.

## Relationships

```json
{
  "id": "student_borrow_record",
  "label": "产生",
  "layout": { "order": 1 },
  "participants": [
    { "entity": "student", "cardinality": "1", "role": "借阅人" },
    { "entity": "borrow_record", "cardinality": "N", "role": "记录" }
  ]
}
```

Rules:

- `id` must be unique.
- `participants` must reference existing entity ids.
- Binary relationships are preferred for clean Chen-style diagrams.
- `role` and `cardinality` are combined into edge labels.
- Participant `side` hints are accepted, but routing still prioritizes four-port shortest straight paths.

### Relationship Attributes

Relationships can carry their own `attributes` array. This is **required** for M:N relationships that produce business data (e.g. order quantity, supply date). Attributes render as ellipses connected to the diamond.

```json
{
  "id": "order",
  "label": "订购",
  "attributes": [
    { "id": "amount", "label": "订购数量" },
    { "id": "odate", "label": "订购日期" }
  ],
  "participants": [
    { "entity": "client", "cardinality": "N" },
    { "entity": "product", "cardinality": "M" }
  ]
}
```

- Attribute format is the same as entity attributes (`id`, `label`, `key`, `multivalued`, `derived`).
- Placement is handled by `place_relationship_attr()` in `attributes.py` — attributes are positioned diagonally offset from the diamond.
- Derived / aggregated tables (e.g. materialized views, trigger-populated stats tables) should generally **not** be modeled as separate entities in the conceptual ER diagram.

## Layout Behavior

Entity placement:

- Choose the first entity by highest relationship degree.
- Place later entities by already-placed neighbor count, total degree, topology score, priority, then JSON order.
- Generate candidate centers from circle tangency, two-circle intersections, and multi-anchor projections.
- Use a small beam search to keep several low-score partial layouts.

Relationship placement:

- Place binary relationship diamonds near the tangent gap between participant territory circles.
- Relationship edges use four standard ports: top, right, bottom, left.
- Straight collision-free edges are preferred over L/Z/U routes.

Debug output:

- `--debug-territory` draws entity territory circles and inner attribute territory circles.
- Each debug circle is labeled with the greedy placement order, e.g. `#1 订单`.

## Validation Metrics

Clean diagrams should have:

```text
relationship_crossings: 0
relationship_obstacle_hits: 0
territory_overlaps: 0
attribute_out_of_territory: 0
relationship_crosses_territory: 0
node_overlaps: 0
```

Useful secondary metrics:

- `total_relationship_length`
- `max_relationship_length`
- `relationship_bends`
- `aspect_ratio_penalty`
- `layout_score`
