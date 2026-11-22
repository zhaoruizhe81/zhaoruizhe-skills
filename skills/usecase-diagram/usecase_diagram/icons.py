from __future__ import annotations

import base64
from io import BytesIO
from pathlib import Path
from urllib.parse import urlparse

from PIL import Image


_MIME_BY_SUFFIX = {
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".gif": "image/gif",
}

_PNG_RASTER_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".gif"}


def icon_href(icon: str, base_dir: Path | None = None) -> str:
    if _is_data_uri(icon) or _is_remote_url(icon):
        return icon

    path = resolve_icon_path(icon, base_dir)
    suffix = path.suffix.lower()
    mime = _MIME_BY_SUFFIX.get(suffix)
    if mime is None:
        raise ValueError(f"Unsupported actor icon file type: {path.suffix}")

    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{encoded}"


def load_raster_icon(icon: str, base_dir: Path | None = None) -> Image.Image:
    if _is_remote_url(icon):
        raise ValueError("PNG export requires actor icons to be local files or data URIs")

    if _is_data_uri(icon):
        header, encoded = icon.split(",", 1)
        if ";base64" not in header:
            raise ValueError("Only base64 data URI actor icons are supported")
        mime = header.split(";", 1)[0].removeprefix("data:")
        if mime == "image/svg+xml":
            raise ValueError("PNG export does not support SVG actor icons; use PNG, JPG, or WebP")
        data = base64.b64decode(encoded)
        return Image.open(BytesIO(data)).convert("RGBA")

    path = resolve_icon_path(icon, base_dir)
    if path.suffix.lower() not in _PNG_RASTER_SUFFIXES:
        raise ValueError("PNG export supports PNG, JPG, WebP, and GIF actor icons")
    return Image.open(path).convert("RGBA")


def resolve_icon_path(icon: str, base_dir: Path | None = None) -> Path:
    path = Path(icon).expanduser()
    if not path.is_absolute():
        path = (base_dir or Path.cwd()) / path
    path = path.resolve()
    if not path.exists():
        raise FileNotFoundError(f"Actor icon not found: {path}")
    return path


def _is_data_uri(value: str) -> bool:
    return value.startswith("data:")


def _is_remote_url(value: str) -> bool:
    scheme = urlparse(value).scheme
    return scheme in {"http", "https"}
