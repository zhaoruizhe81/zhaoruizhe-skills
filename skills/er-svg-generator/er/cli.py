from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .export import export_layout
from .layout import build_layout
from .model import ERError, VALID_POST_LAYOUTS
from .parser import apply_layout_file, load_spec
from .png_export import export_png
from .post_layout import apply_post_layout
from .render_svg import render_svg
from .stats import print_stats


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Render a Chen ER diagram from JSON to SVG.")
    parser.add_argument("input", type=Path, help="Input JSON file")
    parser.add_argument("-o", "--output", type=Path, help="Output SVG path")
    parser.add_argument("--stats", action="store_true", help="Print routing statistics after rendering")
    parser.add_argument("--export-layout", type=Path, help="Write computed entity and relationship coordinates as JSON")
    parser.add_argument("--layout-file", type=Path, help="Apply exported coordinate JSON before rendering")
    parser.add_argument(
        "--post-layout",
        choices=sorted(VALID_POST_LAYOUTS),
        help="Apply post-layout: none, align, arrange, or align-arrange",
    )
    parser.add_argument("--png-output", type=Path, help="Also export a high-resolution PNG")
    parser.add_argument("--png-scale", type=float, default=3.0, help="PNG zoom scale when --png-width is not set. Default: 3")
    parser.add_argument("--png-dpi", type=int, default=300, help="PNG DPI metadata/rendering hint. Default: 300")
    parser.add_argument("--png-width", type=int, help="PNG output width in pixels; overrides --png-scale")
    parser.add_argument("--debug-territory", action="store_true", help="Draw entity territory circles in the SVG")
    parser.add_argument("--target-aspect", type=float, help="Target diagram aspect ratio for layout scoring")
    parser.add_argument(
        "--auto-layout-clean",
        action="store_true",
        help="Clear manual positions and attribute side hints before rendering",
    )
    args = parser.parse_args(argv)

    try:
        spec = load_spec(args.input)
        if args.layout_file:
            apply_layout_file(spec, args.layout_file)
        if args.auto_layout_clean:
            clear_manual_layout_hints(spec)
        if args.target_aspect is not None:
            if args.target_aspect <= 0:
                raise ERError("--target-aspect must be a positive number")
            spec.layout.target_aspect = args.target_aspect
        layout = build_layout(spec)
        post_layout_mode = args.post_layout or spec.layout.post_layout
        apply_post_layout(layout, post_layout_mode)
        layout.debug_territory = args.debug_territory or spec.layout.territory_debug
        svg = render_svg(layout, spec.title)
        output = args.output or args.input.with_suffix(".svg")
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(svg, encoding="utf-8")
        if args.png_output:
            export_png(output, args.png_output, scale=args.png_scale, dpi=args.png_dpi, width=args.png_width)
        if args.export_layout:
            export_layout(layout, args.export_layout)
        if args.stats:
            print_stats(layout)
    except ERError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except OSError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return 0


def clear_manual_layout_hints(spec) -> None:
    spec.layout.entity_positions.clear()
    spec.layout.relationship_positions.clear()
    for entity in spec.entities.values():
        entity.layout.x = None
        entity.layout.y = None
        entity.layout.attributes_side = None
    for relationship in spec.relationships:
        relationship.layout.x = None
        relationship.layout.y = None
