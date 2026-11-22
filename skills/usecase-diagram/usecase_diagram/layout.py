from __future__ import annotations

from dataclasses import dataclass

from .model import ActorSide, Diagram, EdgeType, LayoutMode, Node, NodeKind, Rect


@dataclass(frozen=True)
class LayoutOptions:
    margin: float = 48.0
    actor_x: float = 56.0
    usecase_x: float = 300.0
    detail_usecase_x: float = 620.0
    top_y: float = 64.0
    vertical_gap: float = 30.0
    detail_vertical_gap: float = 34.0
    boundary_padding: float = 42.0
    complex_column_gap: float = 96.0
    complex_usecase_gap: float = 34.0
    complex_boundary_padding_x: float = 56.0
    complex_boundary_padding_y: float = 62.0
    complex_actor_gap: float = 68.0
    complex_actor_vertical_gap: float = 72.0


def layout_diagram(diagram: Diagram, options: LayoutOptions | None = None) -> Diagram:
    options = options or LayoutOptions()

    actors = [node for node in diagram.nodes.values() if node.kind is NodeKind.ACTOR]
    usecases = [node for node in diagram.nodes.values() if node.kind is NodeKind.USECASE]
    boundaries = [node for node in diagram.nodes.values() if node.kind is NodeKind.BOUNDARY]

    for node in actors + usecases:
        node.width, node.height = node.measure_size()

    if diagram.layout.mode is LayoutMode.COMPLEX:
        _layout_complex(diagram, actors, usecases, boundaries, options)
    else:
        _layout_usecases(diagram, usecases, options)
        _layout_actors(actors, usecases, options)
        _layout_boundaries(boundaries, usecases, options)

    _set_canvas_size(diagram, options)
    return diagram


def _layout_complex(
    diagram: Diagram,
    actors: list[Node],
    usecases: list[Node],
    boundaries: list[Node],
    options: LayoutOptions,
) -> None:
    actor_sides = _resolve_actor_sides(actors)
    columns = _complex_usecase_columns(diagram, usecases, actor_sides)
    primary_boundary = boundaries[0] if boundaries else None

    boundary_x = _complex_boundary_x(primary_boundary, actor_sides, actors, options)
    boundary_y = primary_boundary.y if primary_boundary and primary_boundary.y is not None else options.top_y
    column_widths = {
        column: max((node.width or node.measure_size()[0] for node in nodes), default=0.0)
        for column, nodes in columns.items()
    }
    inner_width = sum(column_widths.values())
    inner_width += options.complex_column_gap * max(0, len(columns) - 1)
    inner_width = max(180.0, inner_width)
    needed_boundary_width = inner_width + options.complex_boundary_padding_x * 2
    boundary_width = (
        max(primary_boundary.width, needed_boundary_width)
        if primary_boundary and primary_boundary.width is not None
        else needed_boundary_width
    )

    column_heights = {
        column: _stack_height(nodes, options.complex_usecase_gap)
        for column, nodes in columns.items()
    }
    inner_height = max(column_heights.values(), default=0.0)
    inner_height = max(120.0, inner_height)
    needed_boundary_height = inner_height + options.complex_boundary_padding_y * 2
    boundary_height = (
        max(primary_boundary.height, needed_boundary_height)
        if primary_boundary and primary_boundary.height is not None
        else needed_boundary_height
    )

    start_x = boundary_x + options.complex_boundary_padding_x
    extra_x = max(0.0, boundary_width - needed_boundary_width)
    current_x = start_x + extra_x / 2
    extra_y = max(0.0, boundary_height - needed_boundary_height)
    usecase_top = boundary_y + options.complex_boundary_padding_y + extra_y / 2

    for column in sorted(columns):
        nodes = columns[column]
        column_width = column_widths[column]
        current_y = usecase_top + (inner_height - column_heights[column]) / 2
        for node in nodes:
            node_width = node.width or node.measure_size()[0]
            node_height = node.height or node.measure_size()[1]
            if node.x is None:
                node.x = current_x + (column_width - node_width) / 2
            if node.y is None:
                node.y = current_y
            current_y = node.y + node_height + options.complex_usecase_gap
        current_x += column_width + options.complex_column_gap

    _layout_complex_boundaries(boundaries, usecases, options)
    _layout_complex_actors(
        diagram,
        actors,
        actor_sides,
        _complex_system_box(boundaries, usecases),
        options,
    )


def _resolve_actor_sides(actors: list[Node]) -> dict[str, ActorSide]:
    explicit = {
        node.id: node.side
        for node in actors
        if node.side in {ActorSide.LEFT, ActorSide.RIGHT}
    }
    auto = [node for node in actors if node.id not in explicit]
    if not auto:
        return explicit

    resolved = dict(explicit)
    if not explicit:
        left_quota = (len(actors) + 1) // 2
        for index, node in enumerate(actors):
            resolved[node.id] = ActorSide.LEFT if index < left_quota else ActorSide.RIGHT
        return resolved

    left_count = sum(1 for side in resolved.values() if side is ActorSide.LEFT)
    right_count = sum(1 for side in resolved.values() if side is ActorSide.RIGHT)
    for node in auto:
        if right_count < left_count:
            resolved[node.id] = ActorSide.RIGHT
            right_count += 1
        else:
            resolved[node.id] = ActorSide.LEFT
            left_count += 1
    return resolved


def _complex_usecase_columns(
    diagram: Diagram,
    usecases: list[Node],
    actor_sides: dict[str, ActorSide],
) -> dict[int, list[Node]]:
    if not usecases:
        return {}

    nodes = diagram.nodes
    usecase_ids = {node.id for node in usecases}
    actor_ids = {
        node_id for node_id, node in nodes.items() if node.kind is NodeKind.ACTOR
    }
    associations: dict[str, set[ActorSide]] = {node.id: set() for node in usecases}
    for edge in diagram.edges:
        if edge.type is not EdgeType.ASSOCIATION:
            continue
        source = nodes.get(edge.source)
        target = nodes.get(edge.target)
        if source is None or target is None:
            continue
        if source.id in actor_ids and target.id in usecase_ids:
            associations[target.id].add(actor_sides.get(source.id, ActorSide.LEFT))
        elif target.id in actor_ids and source.id in usecase_ids:
            associations[source.id].add(actor_sides.get(target.id, ActorSide.LEFT))

    columns: dict[str, int] = {}
    for node in usecases:
        sides = associations[node.id]
        if sides == {ActorSide.RIGHT}:
            columns[node.id] = 2
        elif sides == {ActorSide.LEFT}:
            columns[node.id] = 0
        else:
            columns[node.id] = 1

    relation_sources = {
        edge.source
        for edge in diagram.edges
        if edge.type in {EdgeType.INCLUDE, EdgeType.EXTEND, EdgeType.GENERALIZATION}
        and edge.source in usecase_ids
        and edge.target in usecase_ids
    }
    relation_targets = {
        edge.target
        for edge in diagram.edges
        if edge.type in {EdgeType.INCLUDE, EdgeType.EXTEND, EdgeType.GENERALIZATION}
        and edge.source in usecase_ids
        and edge.target in usecase_ids
    }

    for _ in range(len(usecases)):
        changed = False
        for edge in diagram.edges:
            if edge.type not in {EdgeType.INCLUDE, EdgeType.EXTEND, EdgeType.GENERALIZATION}:
                continue
            source = nodes.get(edge.source)
            target = nodes.get(edge.target)
            if (
                source is None
                or target is None
                or source.id not in usecase_ids
                or target.id not in usecase_ids
            ):
                continue
            source_column = columns[source.id]
            target_column = source_column + 1 if source_column <= 1 else source_column - 1
            target_column = max(0, min(2, target_column))
            if columns[target.id] != target_column:
                columns[target.id] = target_column
                changed = True
        if not changed:
            break

    _balance_actor_side_columns(usecases, columns, associations, relation_sources, relation_targets)

    by_column: dict[int, list[Node]] = {}
    for node in usecases:
        by_column.setdefault(columns[node.id], []).append(node)
    return {column: nodes for column, nodes in by_column.items() if nodes}


def _balance_actor_side_columns(
    usecases: list[Node],
    columns: dict[str, int],
    associations: dict[str, set[ActorSide]],
    relation_sources: set[str],
    relation_targets: set[str],
) -> None:
    pinned = relation_sources | relation_targets
    _spread_side_nodes(usecases, columns, associations, ActorSide.LEFT, 0, pinned)
    _spread_side_nodes(usecases, columns, associations, ActorSide.RIGHT, 2, pinned)


def _spread_side_nodes(
    usecases: list[Node],
    columns: dict[str, int],
    associations: dict[str, set[ActorSide]],
    side: ActorSide,
    outer_column: int,
    pinned: set[str],
) -> None:
    middle_column = 1
    candidates = [
        node
        for node in usecases
        if associations[node.id] == {side}
        and node.id not in pinned
        and columns[node.id] == outer_column
    ]
    if len(candidates) < 2:
        return

    outer_height = _column_height(usecases, columns, outer_column)
    middle_height = _column_height(usecases, columns, middle_column)
    for node in reversed(candidates):
        node_height = node.height or node.measure_size()[1]
        if outer_height <= middle_height + node_height:
            break
        columns[node.id] = middle_column
        outer_height -= node_height
        middle_height += node_height


def _column_height(usecases: list[Node], columns: dict[str, int], column: int) -> float:
    return sum(
        node.height or node.measure_size()[1]
        for node in usecases
        if columns[node.id] == column
    )


def _complex_boundary_x(
    primary_boundary: Node | None,
    actor_sides: dict[str, ActorSide],
    actors: list[Node],
    options: LayoutOptions,
) -> float:
    if primary_boundary is not None and primary_boundary.x is not None:
        return primary_boundary.x

    left_width = max(
        (
            actor.width or actor.measure_size()[0]
            for actor in actors
            if actor_sides.get(actor.id) is ActorSide.LEFT
        ),
        default=0.0,
    )
    if left_width:
        return options.margin + left_width + options.complex_actor_gap
    return options.margin


def _layout_complex_boundaries(
    boundaries: list[Node],
    usecases: list[Node],
    options: LayoutOptions,
) -> None:
    for index, boundary in enumerate(boundaries):
        children = [node for node in usecases if node.boundary == boundary.id]
        if not children and index == 0:
            children = usecases

        if children:
            left = min(node.bbox().left for node in children) - options.complex_boundary_padding_x
            top = min(node.bbox().top for node in children) - options.complex_boundary_padding_y
            right = max(node.bbox().right for node in children) + options.complex_boundary_padding_x
            bottom = max(node.bbox().bottom for node in children) + options.complex_boundary_padding_y
        else:
            left = options.usecase_x - options.complex_boundary_padding_x
            top = options.top_y - options.complex_boundary_padding_y
            right = left + 420
            bottom = top + 260

        if boundary.x is None:
            boundary.x = left
        if boundary.y is None:
            boundary.y = top
        if boundary.width is None:
            boundary.width = max(240.0, right - boundary.x)
        if boundary.height is None:
            boundary.height = max(160.0, bottom - boundary.y)


def _layout_complex_actors(
    diagram: Diagram,
    actors: list[Node],
    actor_sides: dict[str, ActorSide],
    system_box: Rect | None,
    options: LayoutOptions,
) -> None:
    if not actors:
        return

    if system_box is None:
        system_box = Rect(options.usecase_x, options.top_y, 420.0, 260.0)

    for side in (ActorSide.LEFT, ActorSide.RIGHT):
        side_actors = [node for node in actors if actor_sides.get(node.id) is side]
        desired_centers = {
            node.id: _actor_desired_center_y(diagram, node, system_box)
            for node in side_actors
        }
        current_bottom: float | None = None
        for node in sorted(side_actors, key=lambda item: desired_centers[item.id]):
            node_width = node.width or node.measure_size()[0]
            node_height = node.height or node.measure_size()[1]
            if node.x is None:
                if side is ActorSide.LEFT:
                    node.x = system_box.left - options.complex_actor_gap - node_width
                else:
                    node.x = system_box.right + options.complex_actor_gap
            if node.y is None:
                desired_top = desired_centers[node.id] - node_height / 2
                if current_bottom is not None:
                    desired_top = max(
                        desired_top,
                        current_bottom + options.vertical_gap,
                    )
                node.y = desired_top
            current_bottom = node.y + node_height


def _actor_desired_center_y(diagram: Diagram, actor: Node, fallback_box: Rect) -> float:
    target_centers: list[float] = []
    for edge in diagram.edges:
        if edge.type is not EdgeType.ASSOCIATION:
            continue
        source = diagram.nodes.get(edge.source)
        target = diagram.nodes.get(edge.target)
        if source is None or target is None:
            continue
        if source.id == actor.id and target.kind is NodeKind.USECASE:
            target_centers.append(target.bbox().center.y)
        elif target.id == actor.id and source.kind is NodeKind.USECASE:
            target_centers.append(source.bbox().center.y)

    if not target_centers:
        return fallback_box.center.y
    return sum(target_centers) / len(target_centers)


def _complex_system_box(boundaries: list[Node], usecases: list[Node]) -> Rect | None:
    if boundaries:
        return boundaries[0].bbox()
    if not usecases:
        return None

    left = min(node.bbox().left for node in usecases)
    top = min(node.bbox().top for node in usecases)
    right = max(node.bbox().right for node in usecases)
    bottom = max(node.bbox().bottom for node in usecases)
    return Rect(left, top, right - left, bottom - top)


def _stack_height(nodes: list[Node], gap: float) -> float:
    if not nodes:
        return 0.0
    total = sum(node.height or node.measure_size()[1] for node in nodes)
    total += gap * max(0, len(nodes) - 1)
    return total


def _layout_usecases(diagram: Diagram, usecases: list[Node], options: LayoutOptions) -> None:
    detail_targets = {
        edge.target
        for edge in diagram.edges
        if edge.type in {EdgeType.INCLUDE, EdgeType.EXTEND}
        and edge.target in diagram.nodes
        and diagram.nodes[edge.target].kind is NodeKind.USECASE
    }
    primary = [node for node in usecases if node.id not in detail_targets]
    details = [node for node in usecases if node.id in detail_targets]

    current_y = options.top_y
    for node in primary:
        if node.x is None:
            node.x = options.usecase_x
        if node.y is None:
            node.y = current_y
        current_y = max(current_y, node.y + (node.height or 0) + options.vertical_gap)

    detail_groups: dict[str, list[Node]] = {}
    for edge in diagram.edges:
        if edge.type not in {EdgeType.INCLUDE, EdgeType.EXTEND}:
            continue
        target = diagram.nodes.get(edge.target)
        if target is None or target.kind is not NodeKind.USECASE:
            continue
        detail_groups.setdefault(edge.source, []).append(target)

    placed: set[str] = set()
    fallback_y = options.top_y
    for source_id, targets in detail_groups.items():
        source = diagram.nodes.get(source_id)
        if source is None or source.kind is not NodeKind.USECASE or source.x is None or source.y is None:
            continue

        total_height = sum(target.height or target.measure_size()[1] for target in targets)
        total_height += options.detail_vertical_gap * max(0, len(targets) - 1)
        current_detail_y = source.bbox().center.y - total_height / 2
        for target in targets:
            if target.x is None:
                target.x = options.detail_usecase_x
            if target.y is None:
                target.y = current_detail_y
            current_detail_y = target.y + (target.height or 0) + options.detail_vertical_gap
            fallback_y = max(fallback_y, current_detail_y)
            placed.add(target.id)

    for node in details:
        if node.id in placed:
            continue
        if node.x is None:
            node.x = options.detail_usecase_x
        if node.y is None:
            node.y = fallback_y
        fallback_y = node.y + (node.height or 0) + options.vertical_gap


def _layout_actors(actors: list[Node], usecases: list[Node], options: LayoutOptions) -> None:
    if not actors:
        return

    if usecases:
        top = min(node.bbox().top for node in usecases)
        bottom = max(node.bbox().bottom for node in usecases)
        center_y = (top + bottom) / 2
    else:
        center_y = options.top_y + 70

    total_height = sum(node.height or node.measure_size()[1] for node in actors)
    total_height += options.vertical_gap * max(0, len(actors) - 1)
    current_y = center_y - total_height / 2

    for node in actors:
        if node.x is None:
            node.x = options.actor_x
        if node.y is None:
            node.y = current_y
        current_y = node.y + (node.height or 0) + options.vertical_gap


def _layout_boundaries(
    boundaries: list[Node], usecases: list[Node], options: LayoutOptions
) -> None:
    for boundary in boundaries:
        children = [node for node in usecases if node.boundary == boundary.id]
        if not children and len(boundaries) == 1:
            children = usecases

        if children:
            left = min(node.bbox().left for node in children) - options.boundary_padding
            top = min(node.bbox().top for node in children) - options.boundary_padding
            right = max(node.bbox().right for node in children) + options.boundary_padding
            bottom = max(node.bbox().bottom for node in children) + options.boundary_padding
        else:
            left = options.usecase_x - options.boundary_padding
            top = options.top_y - options.boundary_padding
            right = left + 360
            bottom = top + 260

        if boundary.x is None:
            boundary.x = left
        if boundary.y is None:
            boundary.y = top
        if boundary.width is None:
            boundary.width = max(180.0, right - boundary.x)
        if boundary.height is None:
            boundary.height = max(120.0, bottom - boundary.y)


def _set_canvas_size(diagram: Diagram, options: LayoutOptions) -> None:
    boxes = [node.bbox() for node in diagram.nodes.values()]
    if not boxes:
        diagram.width = diagram.width or 640
        diagram.height = diagram.height or 360
        return

    max_right = max(box.right for box in boxes)
    max_bottom = max(box.bottom for box in boxes)
    diagram.width = diagram.width or max(480.0, max_right + options.margin)
    diagram.height = diagram.height or max(320.0, max_bottom + options.margin)
