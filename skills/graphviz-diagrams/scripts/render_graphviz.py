#!/usr/bin/env python3
"""Validate and render Graphviz DOT/GV files."""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path


FORMATS = ("png", "svg", "pdf")
LAYOUTS = ("dot", "neato", "fdp", "sfdp", "twopi", "circo")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate or render a Graphviz .dot/.gv file."
    )
    parser.add_argument("input", type=Path, help="Input .dot or .gv file")
    parser.add_argument(
        "--format",
        choices=FORMATS,
        default="png",
        help="Output format for rendering",
    )
    parser.add_argument(
        "--layout",
        choices=LAYOUTS,
        default="dot",
        help="Graphviz layout engine to run",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Output path. Defaults to input path with the selected format suffix.",
    )
    parser.add_argument(
        "--check-only",
        action="store_true",
        help="Validate syntax without writing an output file.",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=30.0,
        help="Seconds before aborting the Graphviz process.",
    )
    return parser.parse_args()


def fail(message: str, code: int = 1) -> int:
    print(f"error: {message}", file=sys.stderr)
    return code


def validate_input(path: Path) -> int:
    if not path.exists():
        return fail(f"input file does not exist: {path}")
    if not path.is_file():
        return fail(f"input path is not a file: {path}")
    if path.suffix.lower() not in {".dot", ".gv"}:
        return fail("input file must have a .dot or .gv suffix")
    return 0


def run_graphviz(
    executable: str,
    input_path: Path,
    output_path: Path | None,
    output_format: str,
    check_only: bool,
    timeout: float,
) -> subprocess.CompletedProcess[str]:
    render_format = "dot" if check_only else output_format
    command = [executable, f"-T{render_format}", str(input_path)]
    if not check_only:
        command.extend(["-o", str(output_path)])

    return subprocess.run(
        command,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
        check=False,
    )


def main() -> int:
    args = parse_args()

    input_path = args.input.expanduser().resolve()
    invalid = validate_input(input_path)
    if invalid:
        return invalid

    executable = shutil.which(args.layout)
    if executable is None:
        return fail(
            f"Graphviz layout engine '{args.layout}' was not found on PATH. "
            "Install Graphviz or choose an available layout."
        )

    output_path = None
    if not args.check_only:
        output_path = (
            args.output.expanduser().resolve()
            if args.output
            else input_path.with_suffix(f".{args.format}")
        )
        output_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        result = run_graphviz(
            executable=executable,
            input_path=input_path,
            output_path=output_path,
            output_format=args.format,
            check_only=args.check_only,
            timeout=args.timeout,
        )
    except subprocess.TimeoutExpired:
        return fail(
            f"Graphviz timed out after {args.timeout:g} seconds. "
            "Simplify the graph or increase --timeout."
        )

    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip() or "unknown Graphviz error"
        return fail(f"Graphviz failed:\n{detail}", result.returncode)

    if args.check_only:
        print(f"OK: {input_path} is valid DOT/GV")
    else:
        print(f"OK: wrote {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
