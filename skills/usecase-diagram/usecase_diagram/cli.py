from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .model import load_diagram
from .png import write_png
from .render_svg import render_svg


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Render a UML use case diagram to SVG or PNG.")
    parser.add_argument("input", help="Path to a JSON diagram file, or '-' for stdin.")
    parser.add_argument("-o", "--output", required=True, help="Path for the output SVG or PNG file.")
    parser.add_argument(
        "--format",
        choices=["auto", "svg", "png"],
        default="auto",
        help="Output format. Defaults to the --output extension.",
    )
    parser.add_argument(
        "--scale",
        type=float,
        default=3.0,
        help="PNG scale factor when exact PNG dimensions are not set. Default: 3.",
    )
    parser.add_argument("--png-width", type=int, help="Exact PNG output width in pixels.")
    parser.add_argument("--png-height", type=int, help="Exact PNG output height in pixels.")
    args = parser.parse_args(argv)

    try:
        data = _read_json(args.input)
        diagram = load_diagram(data)
        base_dir = _base_dir(args.input)
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output_format = _resolve_format(output, args.format)
        if output_format == "svg":
            svg = render_svg(diagram, base_dir=base_dir)
            output.write_text(svg, encoding="utf-8")
        else:
            write_png(
                diagram,
                output,
                scale=args.scale,
                output_width=args.png_width,
                output_height=args.png_height,
                base_dir=base_dir,
            )
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


def _read_json(path: str) -> object:
    if path == "-":
        return json.load(sys.stdin)
    with Path(path).open("r", encoding="utf-8") as file:
        return json.load(file)


def _base_dir(path: str) -> Path:
    if path == "-":
        return Path.cwd()
    return Path(path).resolve().parent


def _resolve_format(output: Path, requested: str) -> str:
    if requested != "auto":
        return requested
    suffix = output.suffix.lower()
    if suffix == ".svg":
        return "svg"
    if suffix == ".png":
        return "png"
    raise ValueError("Cannot infer output format. Use --format svg or --format png.")


if __name__ == "__main__":
    raise SystemExit(main())
