from __future__ import annotations

from math import atan2, cos, degrees, hypot, radians, sin
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFont

from .icons import load_raster_icon
from .layout import layout_diagram
from .model import ArrowHead, BoundaryShape, Diagram, Edge, LineStyle, Node, NodeKind, Point
from .router import Route, route_edges


def write_png(
    diagram: Diagram,
    output: Path,
    *,
    scale: float = 3.0,
    output_width: int | None = None,
    output_height: int | None = None,
    base_dir: Path | None = None,
    trim_whitespace: bool = True,
) -> None:
    if scale <= 0:
        raise ValueError("--scale must be greater than 0")
    if output_width is not None and output_width <= 0:
        raise ValueError("--png-width must be greater than 0")
    if output_height is not None and output_height <= 0:
        raise ValueError("--png-height must be greater than 0")

    layout_diagram(diagram)
    base_width = float(diagram.width or 640)
    base_height = float(diagram.height or 360)
    pixel_width, pixel_height, scale_x, scale_y = _resolve_png_size(
        base_width,
        base_height,
        scale,
        output_width,
        output_height,
    )

    image = Image.new("RGB", (pixel_width, pixel_height), "white")
    draw = ImageDraw.Draw(image)
    ctx = _DrawContext(image=image, draw=draw, scale_x=scale_x, scale_y=scale_y)
    routes = route_edges(diagram)
    default_association_arrow = diagram.layout.resolved_association_arrow()

    for node in diagram.visible_nodes():
        if node.kind is NodeKind.BOUNDARY:
            _draw_boundary(ctx, node, diagram)

    for route in routes:
        _draw_edge(ctx, route, default_association_arrow=default_association_arrow)

    for node in diagram.visible_nodes():
        if node.kind is NodeKind.ACTOR:
            _draw_actor(ctx, node, base_dir=base_dir)
        elif node.kind is NodeKind.USECASE:
            _draw_usecase(ctx, node)

    if trim_whitespace:
        image = _trim_whitespace(image, padding=ctx.width(12))
        image = _resize_to_requested_size(
            image,
            output_width=output_width,
            output_height=output_height,
        )

    output.parent.mkdir(parents=True, exist_ok=True)
    image.save(output, "PNG")


def _trim_whitespace(image: Image.Image, *, padding: int = 0) -> Image.Image:
    background = Image.new(image.mode, image.size, "white")
    bbox = ImageChops.difference(image, background).getbbox()
    if bbox is None:
        return image

    left, top, right, bottom = bbox
    left = max(0, left - padding)
    top = max(0, top - padding)
    right = min(image.width, right + padding)
    bottom = min(image.height, bottom + padding)
    return image.crop((left, top, right, bottom))


def _resize_to_requested_size(
    image: Image.Image,
    *,
    output_width: int | None,
    output_height: int | None,
) -> Image.Image:
    if output_width is None and output_height is None:
        return image

    if output_width is not None and output_height is not None:
        target_size = (output_width, output_height)
    elif output_width is not None:
        target_size = (output_width, round(image.height * (output_width / image.width)))
    else:
        assert output_height is not None
        target_size = (round(image.width * (output_height / image.height)), output_height)

    if image.size == target_size:
        return image
    return image.resize(target_size, Image.Resampling.LANCZOS)


class _DrawContext:
    def __init__(
        self,
        *,
        image: Image.Image,
        draw: ImageDraw.ImageDraw,
        scale_x: float,
        scale_y: float,
    ) -> None:
        self.image = image
        self.draw = draw
        self.scale_x = scale_x
        self.scale_y = scale_y
        self.font_scale = min(scale_x, scale_y)

    def x(self, value: float) -> int:
        return round(value * self.scale_x)

    def y(self, value: float) -> int:
        return round(value * self.scale_y)

    def point(self, point: Point) -> tuple[int, int]:
        return self.x(point.x), self.y(point.y)

    def width(self, value: float) -> int:
        return max(1, round(value * self.font_scale))

    def font(self, size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
        return _font(round(size * self.font_scale))


def _resolve_png_size(
    base_width: float,
    base_height: float,
    scale: float,
    output_width: int | None,
    output_height: int | None,
) -> tuple[int, int, float, float]:
    if output_width is None and output_height is None:
        return (
            round(base_width * scale),
            round(base_height * scale),
            scale,
            scale,
        )

    if output_width is not None and output_height is None:
        resolved_scale = output_width / base_width
        return output_width, round(base_height * resolved_scale), resolved_scale, resolved_scale

    if output_height is not None and output_width is None:
        resolved_scale = output_height / base_height
        return round(base_width * resolved_scale), output_height, resolved_scale, resolved_scale

    assert output_width is not None and output_height is not None
    return (
        output_width,
        output_height,
        output_width / base_width,
        output_height / base_height,
    )


def _draw_boundary(ctx: _DrawContext, node: Node, diagram: Diagram) -> None:
    if _boundary_shape(node, diagram) is BoundaryShape.FRAME:
        _draw_frame_boundary(ctx, node)
        return

    box = node.bbox()
    ctx.draw.rectangle(
        [ctx.x(box.left), ctx.y(box.top), ctx.x(box.right), ctx.y(box.bottom)],
        outline="#111",
        width=ctx.width(1.2),
    )
    _draw_text(ctx, node.label, box.x + 12, box.y + 18, anchor="start", size=13)


def _draw_frame_boundary(ctx: _DrawContext, node: Node) -> None:
    box = node.bbox()
    stroke = ctx.width(1.2)
    ctx.draw.rectangle(
        [ctx.x(box.left), ctx.y(box.top), ctx.x(box.right), ctx.y(box.bottom)],
        outline="#111",
        width=stroke,
    )

    tab_height = 26.0
    tab_width = _boundary_tab_width(ctx, node.label, box.width)
    slant = min(18.0, tab_width * 0.22)
    points = [
        (ctx.x(box.x), ctx.y(box.y)),
        (ctx.x(box.x + tab_width), ctx.y(box.y)),
        (ctx.x(box.x + tab_width - slant), ctx.y(box.y + tab_height)),
        (ctx.x(box.x), ctx.y(box.y + tab_height)),
    ]
    ctx.draw.polygon(points, fill="white")
    ctx.draw.line(points + [points[0]], fill="#111", width=stroke)
    _draw_text(ctx, node.label, box.x + 12, box.y + 6, anchor="start", size=13)


def _boundary_shape(node: Node, diagram: Diagram) -> BoundaryShape:
    if node.shape is not None:
        return node.shape
    if diagram.layout.mode.value == "complex":
        return BoundaryShape.FRAME
    return BoundaryShape.BOX


def _draw_actor(ctx: _DrawContext, node: Node, *, base_dir: Path | None = None) -> None:
    if node.icon:
        _draw_actor_icon(ctx, node, base_dir=base_dir)
        return

    box = node.bbox()
    cx = box.center.x
    top = box.top + 8
    head_cy = top + 10
    body_top = head_cy + 10
    body_bottom = body_top + 30
    arm_y = body_top + 12
    leg_bottom = body_bottom + 24
    stroke = ctx.width(1.4)

    _ellipse_center(ctx, cx, head_cy, 10, 10, outline="#111", width=stroke)
    _line(ctx, Point(cx, body_top), Point(cx, body_bottom), width=stroke)
    _line(ctx, Point(cx - 20, arm_y), Point(cx + 20, arm_y), width=stroke)
    _line(ctx, Point(cx, body_bottom), Point(cx - 16, leg_bottom), width=stroke)
    _line(ctx, Point(cx, body_bottom), Point(cx + 16, leg_bottom), width=stroke)
    _draw_text(ctx, node.label, cx, box.bottom - 4, anchor="middle", size=13)


def _draw_actor_icon(ctx: _DrawContext, node: Node, *, base_dir: Path | None = None) -> None:
    box = node.bbox()
    image_box = _actor_icon_box(node)
    icon = load_raster_icon(node.icon or "", base_dir)
    target_width, target_height = _contain_size(
        icon.width,
        icon.height,
        ctx.x(image_box.width),
        ctx.y(image_box.height),
    )
    resized = icon.resize((target_width, target_height), Image.Resampling.LANCZOS)
    left = ctx.x(image_box.x) + (ctx.x(image_box.width) - target_width) // 2
    top = ctx.y(image_box.y) + (ctx.y(image_box.height) - target_height) // 2
    ctx.image.paste(resized, (left, top), resized)
    _draw_text(ctx, node.label, box.center.x, box.bottom - 4, anchor="middle", size=13)


def _actor_icon_box(node: Node) -> "IconBox":
    box = node.bbox()
    padding_x = min(10.0, box.width * 0.14)
    top_padding = 6.0
    label_space = 28.0
    return IconBox(
        x=box.x + padding_x,
        y=box.y + top_padding,
        width=max(1.0, box.width - padding_x * 2),
        height=max(1.0, box.height - top_padding - label_space),
    )


class IconBox:
    def __init__(self, *, x: float, y: float, width: float, height: float) -> None:
        self.x = x
        self.y = y
        self.width = width
        self.height = height


def _contain_size(
    source_width: int,
    source_height: int,
    max_width: int,
    max_height: int,
) -> tuple[int, int]:
    ratio = min(max_width / source_width, max_height / source_height)
    return max(1, round(source_width * ratio)), max(1, round(source_height * ratio))


def _draw_usecase(ctx: _DrawContext, node: Node) -> None:
    box = node.bbox()
    ctx.draw.ellipse(
        [ctx.x(box.left), ctx.y(box.top), ctx.x(box.right), ctx.y(box.bottom)],
        fill="white",
        outline="#111",
        width=ctx.width(1.4),
    )
    _draw_text(ctx, node.label, box.center.x, box.center.y, anchor="middle", size=13, middle=True)


def _draw_edge(
    ctx: _DrawContext,
    route: Route,
    *,
    default_association_arrow: ArrowHead,
) -> None:
    edge = route.edge
    points = route.points
    width = ctx.width(1.35)
    if edge.resolved_style() is LineStyle.DASHED:
        _dashed_polyline(ctx, points, dash=6, gap=4, width=width)
    else:
        _polyline(ctx, points, width=width)

    _draw_arrow(ctx, edge, points, width, default_association_arrow)

    label = edge.resolved_label()
    if label:
        point, angle = _path_midpoint_with_angle(points)
        label_x, label_y = _offset_label_point(point, angle, 6)
        _draw_rotated_label(ctx, label, label_x, label_y, angle=angle, size=12)


def _draw_arrow(
    ctx: _DrawContext,
    edge: Edge,
    points: list[Point],
    width: int,
    default_association_arrow: ArrowHead,
) -> None:
    arrow = edge.resolved_arrow(default_association_arrow)
    if arrow is ArrowHead.NONE or len(points) < 2:
        return

    end = points[-1]
    prev = next((point for point in reversed(points[:-1]) if point != end), points[-2])
    angle = atan2(ctx.y(end.y) - ctx.y(prev.y), ctx.x(end.x) - ctx.x(prev.x))
    tip = ctx.point(end)
    length = ctx.width(11)
    spread = radians(32)

    left = (
        round(tip[0] - length * cos(angle - spread)),
        round(tip[1] - length * sin(angle - spread)),
    )
    right = (
        round(tip[0] - length * cos(angle + spread)),
        round(tip[1] - length * sin(angle + spread)),
    )

    if arrow is ArrowHead.OPEN:
        ctx.draw.line([left, tip, right], fill="#111", width=width, joint="curve")
    elif arrow is ArrowHead.TRIANGLE:
        ctx.draw.polygon([tip, left, right], fill="white", outline="#111")
        ctx.draw.line([tip, left, right, tip], fill="#111", width=width)


def _polyline(ctx: _DrawContext, points: list[Point], *, width: int) -> None:
    for start, end in zip(points, points[1:]):
        _line(ctx, start, end, width=width)


def _dashed_polyline(
    ctx: _DrawContext,
    points: list[Point],
    *,
    dash: float,
    gap: float,
    width: int,
) -> None:
    dash_px = dash * ctx.font_scale
    gap_px = gap * ctx.font_scale
    pattern = dash_px + gap_px

    for start, end in zip(points, points[1:]):
        x1, y1 = ctx.point(start)
        x2, y2 = ctx.point(end)
        dx = x2 - x1
        dy = y2 - y1
        length = hypot(dx, dy)
        if length == 0:
            continue
        unit_x = dx / length
        unit_y = dy / length
        distance = 0.0
        while distance < length:
            visible = min(dash_px, length - distance)
            seg_start = (
                round(x1 + unit_x * distance),
                round(y1 + unit_y * distance),
            )
            seg_end = (
                round(x1 + unit_x * (distance + visible)),
                round(y1 + unit_y * (distance + visible)),
            )
            ctx.draw.line([seg_start, seg_end], fill="#111", width=width)
            distance += pattern


def _line(ctx: _DrawContext, start: Point, end: Point, *, width: int) -> None:
    ctx.draw.line([ctx.point(start), ctx.point(end)], fill="#111", width=width)


def _ellipse_center(
    ctx: _DrawContext,
    cx: float,
    cy: float,
    rx: float,
    ry: float,
    *,
    outline: str,
    width: int,
) -> None:
    ctx.draw.ellipse(
        [ctx.x(cx - rx), ctx.y(cy - ry), ctx.x(cx + rx), ctx.y(cy + ry)],
        fill="white",
        outline=outline,
        width=width,
    )


def _draw_text(
    ctx: _DrawContext,
    label: str,
    x: float,
    y: float,
    *,
    anchor: str,
    size: int,
    middle: bool = False,
) -> None:
    font = ctx.font(size)
    lines = label.splitlines() or [label]
    line_height = round((size + 3) * ctx.font_scale)
    if middle:
        top = ctx.y(y) - (line_height * len(lines)) // 2
    else:
        top = ctx.y(y)

    for index, line in enumerate(lines):
        text_width = _text_width(ctx, line, font)
        if anchor == "middle":
            left = ctx.x(x) - text_width // 2
        else:
            left = ctx.x(x)
        ctx.draw.text((left, top + index * line_height), line, fill="#111", font=font)


def _draw_label_mask(ctx: _DrawContext, label: str, x: float, y: float, *, size: int) -> None:
    font = ctx.font(size)
    lines = label.splitlines() or [label]
    line_height = round((size + 3) * ctx.font_scale)
    widths = [_text_width(ctx, line, font) for line in lines]
    text_width = max(widths, default=0)
    text_height = line_height * len(lines)
    padding_x = ctx.width(8)
    padding_y = ctx.width(4)
    left = ctx.x(x) - text_width // 2 - padding_x
    top = ctx.y(y) - round(text_height * 0.78) - padding_y
    right = ctx.x(x) + text_width // 2 + padding_x
    bottom = top + text_height + padding_y * 2
    ctx.draw.rectangle([left, top, right, bottom], fill="white")


def _draw_rotated_label(
    ctx: _DrawContext,
    label: str,
    x: float,
    y: float,
    *,
    angle: float,
    size: int,
) -> None:
    font = ctx.font(size)
    lines = label.splitlines() or [label]
    line_height = round((size + 3) * ctx.font_scale)
    widths = [_text_width(ctx, line, font) for line in lines]
    text_width = max(widths, default=0)
    text_height = line_height * len(lines)
    padding_x = ctx.width(8)
    padding_y = ctx.width(4)
    image_width = text_width + padding_x * 2
    image_height = text_height + padding_y * 2
    label_image = Image.new("RGBA", (image_width, image_height), (255, 255, 255, 0))
    label_draw = ImageDraw.Draw(label_image)
    label_draw.rectangle([0, 0, image_width, image_height], fill=(255, 255, 255, 255))

    for index, line in enumerate(lines):
        text_left = (image_width - widths[index]) // 2
        text_top = padding_y + index * line_height
        label_draw.text((text_left, text_top), line, fill="#111", font=font)

    rotated = label_image.rotate(-angle, expand=True, resample=Image.Resampling.BICUBIC)
    left = ctx.x(x) - rotated.width // 2
    top = ctx.y(y) - rotated.height // 2
    ctx.image.paste(rotated, (left, top), rotated)


def _text_width(ctx: _DrawContext, text: str, font: ImageFont.FreeTypeFont | ImageFont.ImageFont) -> int:
    bbox = ctx.draw.textbbox((0, 0), text, font=font)
    return bbox[2] - bbox[0]


def _boundary_tab_width(ctx: _DrawContext, label: str, boundary_width: float) -> float:
    font = ctx.font(13)
    desired = _text_width(ctx, label, font) / ctx.font_scale + 34.0
    maximum = max(70.0, boundary_width - 24.0)
    return min(max(90.0, desired), maximum)


def _font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = [
        "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
        "/Library/Fonts/Arial Unicode.ttf",
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/System/Library/Fonts/PingFang.ttc",
    ]
    for path in candidates:
        try:
            return ImageFont.truetype(path, size=size)
        except OSError:
            continue
    return ImageFont.load_default(size=size)


def _path_midpoint_with_angle(points: list[Point]) -> tuple[Point, float]:
    if len(points) == 1:
        return points[0], 0.0

    lengths: list[float] = []
    total = 0.0
    for start, end in zip(points, points[1:]):
        length = hypot(start.x - end.x, start.y - end.y)
        lengths.append(length)
        total += length

    halfway = total / 2
    walked = 0.0
    for (start, end), length in zip(zip(points, points[1:]), lengths):
        if walked + length >= halfway:
            ratio = 0 if length == 0 else (halfway - walked) / length
            point = Point(
                start.x + (end.x - start.x) * ratio,
                start.y + (end.y - start.y) * ratio,
            )
            return point, _readable_angle(start, end)
        walked += length
    return points[-1], _readable_angle(points[-2], points[-1])


def _readable_angle(start: Point, end: Point) -> float:
    angle = degrees(atan2(end.y - start.y, end.x - start.x))
    if angle > 90:
        angle -= 180
    elif angle <= -90:
        angle += 180
    return angle


def _offset_label_point(point: Point, angle: float, distance: float) -> tuple[float, float]:
    angle_radians = radians(angle)
    return (
        point.x + distance * sin(angle_radians),
        point.y - distance * cos(angle_radians),
    )
