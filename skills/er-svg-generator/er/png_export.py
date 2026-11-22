from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from .model import ERError


def export_png(
    svg_path: Path,
    png_path: Path,
    scale: float = 3.0,
    dpi: int = 300,
    width: int | None = None,
) -> None:
    converter = shutil.which("rsvg-convert")
    if converter is None:
        raise ERError("PNG export requires rsvg-convert. Install librsvg or export SVG directly.")
    if scale <= 0:
        raise ERError("--png-scale must be a positive number")
    if dpi <= 0:
        raise ERError("--png-dpi must be a positive integer")
    if width is not None and width <= 0:
        raise ERError("--png-width must be a positive integer")

    png_path.parent.mkdir(parents=True, exist_ok=True)
    command = [
        converter,
        "--dpi-x",
        str(dpi),
        "--dpi-y",
        str(dpi),
        "--format",
        "png",
        "--output",
        str(png_path),
    ]
    if width is not None:
        command.extend(["--width", str(width)])
    else:
        command.extend(["--zoom", str(scale)])
    command.append(str(svg_path))

    try:
        subprocess.run(command, check=True, text=True, capture_output=True)
    except subprocess.CalledProcessError as exc:
        message = [f"PNG export failed: {' '.join(command)}", f"Exit code: {exc.returncode}"]
        if exc.stdout:
            message.extend(["STDOUT:", exc.stdout.rstrip()])
        if exc.stderr:
            message.extend(["STDERR:", exc.stderr.rstrip()])
        raise ERError("\n".join(message)) from exc
