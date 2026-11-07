#!/usr/bin/env python3
"""
Render source snippets or plain text into PNG images.
"""

from __future__ import annotations

import argparse
import io
import locale
import shutil
import subprocess
import sys
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Iterable

from PIL import Image, ImageChops, ImageDraw, ImageFont
from pygments import highlight
from pygments.formatters import ImageFormatter
from pygments.formatters.img import FontManager, FontNotFound
from pygments.lexers import get_lexer_by_name, get_lexer_for_filename
from pygments.styles.monokai import MonokaiStyle
from pygments.util import ClassNotFound
from rich.ansi import AnsiDecoder
from rich.console import Console
from rich.terminal_theme import DEFAULT_TERMINAL_THEME, MONOKAI, TerminalTheme


LIGHT_STYLE = "default"
DARK_STYLE = "monokai"
IMAGE_PAD = 20
LINE_PAD = 4
LINE_NUMBER_PAD = 8
LINE_NUMBER_COLOR_LIGHT = "#6B7280"
LINE_NUMBER_COLOR_DARK = "#9CA3AF"
TEXT_COLOR_LIGHT = "#111827"
TEXT_COLOR_DARK = "#F9FAFB"
BACKGROUND_LIGHT = "#FFFFFF"
BACKGROUND_PAPER = "#F3F4F6"
BACKGROUND_DARK = "#111827"
BACKGROUND_BW = "#000000"
BACKGROUND_GRAPHITE = "#24292F"
BACKGROUND_NAVY = "#0F172A"
BACKGROUND_UBUNTU = "#300A24"
TEXT_COLOR_PAPER = "#111827"
TEXT_COLOR_BW = "#FFFFFF"
TEXT_COLOR_GRAPHITE = "#F3F4F6"
TEXT_COLOR_NAVY = "#F8FAFC"
TEXT_COLOR_UBUNTU = "#EEEEEC"
LINE_NUMBER_COLOR_PAPER = "#6B7280"
LINE_NUMBER_COLOR_BW = "#A3A3A3"
LINE_NUMBER_COLOR_GRAPHITE = "#9CA3AF"
LINE_NUMBER_COLOR_NAVY = "#94A3B8"
LINE_NUMBER_COLOR_UBUNTU = "#9A95A3"
PAPER_NORMAL_COLORS = [
    (243, 244, 246),
    (17, 24, 39),
    (17, 24, 39),
    (17, 24, 39),
    (17, 24, 39),
    (17, 24, 39),
    (17, 24, 39),
    (17, 24, 39),
]
PAPER_BRIGHT_COLORS = [
    (229, 231, 235),
    (17, 24, 39),
    (17, 24, 39),
    (17, 24, 39),
    (17, 24, 39),
    (17, 24, 39),
    (17, 24, 39),
    (0, 0, 0),
]
BW_NORMAL_COLORS = [
    (0, 0, 0),
    (255, 255, 255),
    (255, 255, 255),
    (255, 255, 255),
    (255, 255, 255),
    (255, 255, 255),
    (255, 255, 255),
    (255, 255, 255),
]
BW_BRIGHT_COLORS = [
    (64, 64, 64),
    (255, 255, 255),
    (255, 255, 255),
    (255, 255, 255),
    (255, 255, 255),
    (255, 255, 255),
    (255, 255, 255),
    (255, 255, 255),
]
GRAPHITE_NORMAL_COLORS = [
    (36, 41, 47),
    (243, 244, 246),
    (243, 244, 246),
    (243, 244, 246),
    (243, 244, 246),
    (243, 244, 246),
    (243, 244, 246),
    (243, 244, 246),
]
GRAPHITE_BRIGHT_COLORS = [
    (55, 61, 68),
    (255, 255, 255),
    (255, 255, 255),
    (255, 255, 255),
    (255, 255, 255),
    (255, 255, 255),
    (255, 255, 255),
    (255, 255, 255),
]
NAVY_NORMAL_COLORS = [
    (15, 23, 42),
    (248, 250, 252),
    (248, 250, 252),
    (248, 250, 252),
    (248, 250, 252),
    (248, 250, 252),
    (248, 250, 252),
    (248, 250, 252),
]
NAVY_BRIGHT_COLORS = [
    (30, 41, 59),
    (248, 250, 252),
    (248, 250, 252),
    (248, 250, 252),
    (248, 250, 252),
    (248, 250, 252),
    (248, 250, 252),
    (255, 255, 255),
]
UBUNTU_NORMAL_COLORS = [
    (46, 52, 54),
    (204, 0, 0),
    (78, 154, 6),
    (196, 160, 0),
    (52, 101, 164),
    (117, 80, 123),
    (6, 152, 154),
    (211, 215, 207),
]
UBUNTU_BRIGHT_COLORS = [
    (85, 87, 83),
    (239, 41, 41),
    (138, 226, 52),
    (252, 233, 79),
    (114, 159, 207),
    (173, 127, 168),
    (52, 226, 226),
    (238, 238, 236),
]
PREFERRED_CJK_CANDIDATES = [
    ("Sarasa Mono SC", True, True),
    ("Noto Sans Mono CJK SC", True, True),
    ("Source Han Mono SC", True, True),
    ("LXGW WenKai Mono", True, True),
    ("Hiragino Sans GB", False, True),
    ("PingFang SC", False, True),
]
PREFERRED_MONO_CANDIDATES = [
    ("Menlo", True, False),
    ("Monaco", True, False),
    ("SF Mono", True, False),
    ("DejaVu Sans Mono", True, False),
]


@dataclass(frozen=True)
class FontChoice:
    family: str
    path: str
    monospace: bool
    cjk_capable: bool
    index: int = 0


class UbuntuStyle(MonokaiStyle):
    background_color = BACKGROUND_UBUNTU


class BwStyle(MonokaiStyle):
    background_color = BACKGROUND_BW


class PaperStyle(MonokaiStyle):
    background_color = BACKGROUND_PAPER


class GraphiteStyle(MonokaiStyle):
    background_color = BACKGROUND_GRAPHITE


class NavyStyle(MonokaiStyle):
    background_color = BACKGROUND_NAVY


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Render code or plain text into a PNG image.",
    )
    parser.add_argument("--input", type=Path, help="Path to a text source file.")
    parser.add_argument("--text", help="Inline text to render.")
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="Output PNG path.",
    )
    parser.add_argument("--lexer", help="Pygments lexer name for highlighted code.")
    parser.add_argument(
        "--ansi",
        action="store_true",
        help="Render ANSI-colored terminal text.",
    )
    parser.add_argument(
        "--plain-text",
        action="store_true",
        help="Render without syntax highlighting.",
    )
    parser.add_argument(
        "--theme",
        choices=("light", "dark", "ubuntu", "bw", "navy", "paper", "graphite"),
        default="light",
        help="Color theme. Defaults to light.",
    )
    parser.add_argument(
        "--font",
        help="Preferred font family. Must be installed locally.",
    )
    parser.add_argument(
        "--font-size",
        type=int,
        default=18,
        help="Font size in points. Defaults to 18.",
    )
    parser.add_argument(
        "--line-numbers",
        action="store_true",
        help="Include line numbers.",
    )
    parser.add_argument(
        "--decode-escapes",
        action="store_true",
        help="Decode common escape sequences in --text, such as \\n and \\t.",
    )
    parser.add_argument(
        "--scale",
        type=float,
        default=1.0,
        help="Resolution multiplier. Use 2 or 3 for sharper images in reports.",
    )
    parser.add_argument(
        "--dpi",
        type=int,
        default=300,
        help="PNG DPI metadata. Defaults to 300.",
    )
    args = parser.parse_args()
    if args.font_size <= 0:
        fail("--font-size must be greater than 0")
    if args.scale <= 0:
        fail("--scale must be greater than 0")
    if args.dpi <= 0:
        fail("--dpi must be greater than 0")
    return args


def get_spacing(args: argparse.Namespace) -> tuple[int, int, int]:
    # Zero-margin is hard-coded: these pads only pad the pre-crop canvas and
    # crop_to_content() always trims the output flush to the content.
    return IMAGE_PAD, LINE_PAD, LINE_NUMBER_PAD


def fail(message: str) -> None:
    print(f"error: {message}", file=sys.stderr)
    raise SystemExit(1)


def warn(message: str) -> None:
    print(f"warning: {message}", file=sys.stderr)


def require_single_input(args: argparse.Namespace) -> tuple[str, str]:
    has_input = args.input is not None
    has_text = args.text is not None

    if has_input == has_text:
        fail("provide exactly one of --input or --text")

    if has_input:
        path = args.input.expanduser()
        if not path.exists():
            fail(f"input file not found: {path}")
        if not path.is_file():
            fail(f"input path is not a file: {path}")
        text = read_source_text(path)
        if args.ansi:
            text = decode_common_escapes(text)
        return text, path.name

    text = args.text
    if args.decode_escapes or args.ansi:
        text = decode_common_escapes(text)
    return text, "<inline>"


def read_source_text(path: Path) -> str:
    encodings = [
        "utf-8",
        locale.getpreferredencoding(False) or "utf-8",
        "gb18030",
        "utf-16",
    ]
    seen: set[str] = set()
    for encoding in encodings:
        if encoding in seen:
            continue
        seen.add(encoding)
        try:
            return path.read_text(encoding=encoding)
        except UnicodeDecodeError:
            continue
    fail(f"could not decode text file with common encodings: {path}")


def decode_common_escapes(text: str) -> str:
    replacements = {
        r"\u001b": "\x1b",
        r"\x1b": "\x1b",
        r"\033": "\x1b",
        r"\e": "\x1b",
        r"\r\n": "\n",
        r"\n": "\n",
        r"\t": "\t",
        r"\r": "\r",
        r"\\": "\\",
    }
    decoded = text
    for raw, actual in replacements.items():
        decoded = decoded.replace(raw, actual)
    return decoded


def contains_cjk(text: str) -> bool:
    for char in text:
        code = ord(char)
        if (
            0x3400 <= code <= 0x4DBF
            or 0x4E00 <= code <= 0x9FFF
            or 0xF900 <= code <= 0xFAFF
        ):
            return True
    return False


def available_families() -> set[str]:
    if not shutil.which("fc-list"):
        warn("fc-list not found; font probing will use built-in fallbacks only")
        return set()

    result = subprocess.run(
        ["fc-list", ":", "family"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        warn("fc-list failed; font probing will use built-in fallbacks only")
        return set()

    families: set[str] = set()
    for raw_line in result.stdout.splitlines():
        for family in raw_line.split(","):
            cleaned = family.strip()
            if cleaned:
                families.add(cleaned)
    return families


def resolve_font_path(family: str) -> str | None:
    if not shutil.which("fc-match"):
        return None

    result = subprocess.run(
        ["fc-match", "-f", "%{file}\n", family],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return None
    path = result.stdout.strip()
    return path or None


_TTC_INDEX_CACHE: dict[tuple[str, str, bool], int] = {}


def _face_is_monospace(font: ImageFont.FreeTypeFont, need_cjk: bool) -> bool:
    if abs(font.getlength("W" * 4) - font.getlength("i" * 4)) > 1:
        return False
    if need_cjk and abs(font.getlength("北京") - font.getlength("1234")) > 1:
        return False
    return True


def resolve_font_index(path: str, family: str, need_cjk: bool) -> int:
    """Pick the right sub-face from a font collection (.ttc).

    PIL's ``ImageFont.truetype`` defaults to index 0. For a collection such as
    Sarasa's Super TTC that lands on a proportional face (e.g.
    ``Sarasa Gothic CL ExtraLight``) instead of the requested monospace
    ``Sarasa Mono SC``, which breaks CJK column alignment in terminal tables.
    Probe the faces and prefer one whose family matches, that is monospace,
    and that has a ``Regular`` style.
    """
    if not path.lower().endswith(".ttc"):
        return 0
    key = (path, family, need_cjk)
    if key in _TTC_INDEX_CACHE:
        return _TTC_INDEX_CACHE[key]

    best_index = 0
    best_score = -1
    index = 0
    while True:
        try:
            face = ImageFont.truetype(path, 40, index=index)
        except Exception:
            break
        name, style = face.getname()
        score = 0
        if name == family:
            score += 100
        if _face_is_monospace(face, need_cjk):
            score += 10
        if style == "Regular":
            score += 5
        if score > best_score:
            best_index, best_score = index, score
        index += 1

    _TTC_INDEX_CACHE[key] = best_index
    return best_index


def is_pygments_font_compatible(family: str, font_size: int) -> bool:
    try:
        FontManager(family, font_size)
        return True
    except FontNotFound:
        return False


def pick_font(text: str, requested_family: str | None, *, for_code: bool, font_size: int) -> FontChoice:
    families = available_families()
    need_cjk = contains_cjk(text)

    if requested_family:
        if families and requested_family not in families:
            fail(f"requested font is not installed: {requested_family}")
        if for_code and not is_pygments_font_compatible(requested_family, font_size):
            fail(
                f"requested font is not compatible with Pygments image rendering on this machine: {requested_family}"
            )
        path = resolve_font_path(requested_family)
        if not path:
            fail(f"could not resolve font file for: {requested_family}")
        choice = FontChoice(
            family=requested_family,
            path=path,
            monospace=requested_family in {name for name, mono, _ in PREFERRED_CJK_CANDIDATES + PREFERRED_MONO_CANDIDATES if mono},
            cjk_capable=requested_family in {name for name, _, cjk in PREFERRED_CJK_CANDIDATES + PREFERRED_MONO_CANDIDATES if cjk},
        )
    else:
        candidates = list(iter_default_candidates(need_cjk))
        choice = choose_first_installed_font(candidates, families, for_code=for_code, font_size=font_size)
        if not choice:
            fail("no usable font found; install a supported font or pass --font")

    if need_cjk and not choice.cjk_capable:
        warn(
            f"selected font '{choice.family}' is not marked as CJK-capable; Chinese glyphs may be missing"
        )

    # Resolve the sub-face index for font collections so we load the right face
    # (e.g. index 205 'Sarasa Mono SC Regular' instead of index 0), then judge
    # monospace against the face we will actually render with.
    choice = replace(choice, index=resolve_font_index(choice.path, choice.family, need_cjk))
    try:
        actual_face = ImageFont.truetype(choice.path, 40, index=choice.index)
        actual_monospace = _face_is_monospace(actual_face, need_cjk)
    except Exception:
        actual_monospace = choice.monospace
    if not actual_monospace:
        warn(
            f"loaded font face '{choice.family}' is not monospace; mixed Chinese and ASCII alignment may drift"
        )

    label = choice.family + (f" (ttc index {choice.index})" if choice.index else "")
    print(f"Using font: {label}", file=sys.stderr)
    return choice


def iter_default_candidates(need_cjk: bool) -> Iterable[tuple[str, bool, bool]]:
    if need_cjk:
        yield from PREFERRED_CJK_CANDIDATES
        yield from PREFERRED_MONO_CANDIDATES
    else:
        yield from PREFERRED_MONO_CANDIDATES
        yield from PREFERRED_CJK_CANDIDATES


def choose_first_installed_font(
    candidates: Iterable[tuple[str, bool, bool]],
    families: set[str],
    *,
    for_code: bool,
    font_size: int,
) -> FontChoice | None:
    for family, monospace, cjk_capable in candidates:
        if families and family not in families:
            continue
        if for_code and not is_pygments_font_compatible(family, font_size):
            continue
        path = resolve_font_path(family)
        if path:
            return FontChoice(
                family=family,
                path=path,
                monospace=monospace,
                cjk_capable=cjk_capable,
            )
    return None


def choose_lexer(source_name: str, text: str, args: argparse.Namespace):
    if args.ansi and (args.plain_text or args.lexer):
        fail("use --ansi by itself, without --plain-text or --lexer")
    if args.ansi:
        return None
    if args.plain_text and args.lexer:
        fail("use either --plain-text or --lexer, not both")
    if args.plain_text:
        return None
    if args.lexer:
        try:
            return get_lexer_by_name(args.lexer)
        except ClassNotFound:
            fail(f"unsupported lexer: {args.lexer}")
    if args.input:
        try:
            return get_lexer_for_filename(source_name, text)
        except ClassNotFound:
            return None
    return None


def ensure_output_path(path: Path) -> Path:
    path = path.expanduser()
    if path.suffix.lower() != ".png":
        fail("output path must end with .png")
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def build_formatter(args: argparse.Namespace, font: FontChoice) -> ImageFormatter:
    scaled_font_size = max(1, round(args.font_size * args.scale))
    image_pad, line_pad, line_number_pad = get_spacing(args)
    scaled_image_pad = max(0, round(image_pad * args.scale))
    scaled_line_pad = max(0, round(line_pad * args.scale))
    scaled_line_number_pad = max(1, round(line_number_pad * args.scale))
    style = get_pygments_style(args.theme)
    return ImageFormatter(
        font_name=font.family,
        font_size=scaled_font_size,
        line_numbers=args.line_numbers,
        image_pad=scaled_image_pad,
        line_pad=scaled_line_pad,
        line_number_pad=scaled_line_number_pad,
        line_number_bg=get_background_color(args.theme),
        line_number_fg=get_line_number_color(args.theme),
        style=style,
        image_format="PNG",
    )


def get_pygments_style(theme_name: str):
    if theme_name == "dark":
        return DARK_STYLE
    if theme_name == "bw":
        return BwStyle
    if theme_name == "paper":
        return PaperStyle
    if theme_name == "graphite":
        return GraphiteStyle
    if theme_name == "navy":
        return NavyStyle
    if theme_name == "ubuntu":
        return UbuntuStyle
    return LIGHT_STYLE


def get_background_color(theme_name: str):
    if theme_name == "dark":
        return BACKGROUND_DARK
    if theme_name == "bw":
        return BACKGROUND_BW
    if theme_name == "paper":
        return BACKGROUND_PAPER
    if theme_name == "graphite":
        return BACKGROUND_GRAPHITE
    if theme_name == "navy":
        return BACKGROUND_NAVY
    if theme_name == "ubuntu":
        return BACKGROUND_UBUNTU
    return BACKGROUND_LIGHT


def get_foreground_color(theme_name: str):
    if theme_name == "dark":
        return TEXT_COLOR_DARK
    if theme_name == "bw":
        return TEXT_COLOR_BW
    if theme_name == "paper":
        return TEXT_COLOR_PAPER
    if theme_name == "graphite":
        return TEXT_COLOR_GRAPHITE
    if theme_name == "navy":
        return TEXT_COLOR_NAVY
    if theme_name == "ubuntu":
        return TEXT_COLOR_UBUNTU
    return TEXT_COLOR_LIGHT


def get_line_number_color(theme_name: str):
    if theme_name == "dark":
        return LINE_NUMBER_COLOR_DARK
    if theme_name == "bw":
        return LINE_NUMBER_COLOR_BW
    if theme_name == "paper":
        return LINE_NUMBER_COLOR_PAPER
    if theme_name == "graphite":
        return LINE_NUMBER_COLOR_GRAPHITE
    if theme_name == "navy":
        return LINE_NUMBER_COLOR_NAVY
    if theme_name == "ubuntu":
        return LINE_NUMBER_COLOR_UBUNTU
    return LINE_NUMBER_COLOR_LIGHT


def crop_to_content(image: Image.Image, background) -> Image.Image:
    background_image = Image.new(image.mode, image.size, background)
    diff = ImageChops.difference(image, background_image)
    bbox = diff.getbbox()
    if bbox is None:
        return image
    return image.crop(bbox)


def save_output(image: Image.Image, args: argparse.Namespace, output: Path, background=None) -> None:
    if background is None:
        background = image.getpixel((0, 0))
    # Zero-margin is hard-coded: always crop flush to content. There are no
    # margin flags by design — spacing around the image belongs to the
    # surrounding document layout, never to the PNG.
    final_image = crop_to_content(image, background)
    final_image.save(output, format="PNG", dpi=(args.dpi, args.dpi))


def render_code(text: str, lexer, args: argparse.Namespace, font: FontChoice, output: Path) -> None:
    formatter = build_formatter(args, font)
    data = highlight(text, lexer, formatter)
    with Image.open(io.BytesIO(data)) as image:
        save_output(image, args, output)


def render_plain_text(text: str, args: argparse.Namespace, font: FontChoice, output: Path) -> None:
    scaled_font_size = max(1, round(args.font_size * args.scale))
    image_pad, line_pad, line_number_pad = get_spacing(args)
    scaled_image_pad = max(0, round(image_pad * args.scale))
    scaled_line_pad = max(0, round(line_pad * args.scale))
    scaled_line_number_pad = max(1, round(line_number_pad * args.scale))
    font_obj = ImageFont.truetype(font.path, scaled_font_size, index=font.index)
    lines = text.splitlines() or [""]
    if text.endswith("\n"):
        lines.append("")

    dummy = Image.new("RGB", (10, 10))
    draw = ImageDraw.Draw(dummy)
    line_height = font_obj.getbbox("Ag")[3] - font_obj.getbbox("Ag")[1] + scaled_line_pad
    number_width = 0

    if args.line_numbers:
        digits = len(str(len(lines)))
        sample = "9" * digits
        bbox = draw.textbbox((0, 0), sample, font=font_obj)
        number_width = (bbox[2] - bbox[0]) + (scaled_line_number_pad * 2)

    content_width = 1
    for index, line in enumerate(lines, start=1):
        line_text = line if line else " "
        bbox = draw.textbbox((0, 0), line_text, font=font_obj)
        width = bbox[2] - bbox[0]
        content_width = max(content_width, width)

    width = scaled_image_pad * 2 + number_width + content_width
    height = scaled_image_pad * 2 + len(lines) * line_height
    background = get_background_color(args.theme)
    foreground = get_foreground_color(args.theme)
    line_number_color = get_line_number_color(args.theme)

    image = Image.new("RGB", (width, height), background)
    draw = ImageDraw.Draw(image)
    y = scaled_image_pad
    for index, line in enumerate(lines, start=1):
        x = scaled_image_pad
        if args.line_numbers:
            draw.text((x, y), str(index), fill=line_number_color, font=font_obj)
            x += number_width
        draw.text((x, y), line or " ", fill=foreground, font=font_obj)
        y += line_height

    save_output(image, args, output, background)


def get_terminal_theme(theme_name: str) -> TerminalTheme:
    if theme_name == "dark":
        return MONOKAI
    if theme_name == "bw":
        return TerminalTheme(
            (0, 0, 0),
            (255, 255, 255),
            BW_NORMAL_COLORS,
            BW_BRIGHT_COLORS,
        )
    if theme_name == "paper":
        return TerminalTheme(
            (243, 244, 246),
            (17, 24, 39),
            PAPER_NORMAL_COLORS,
            PAPER_BRIGHT_COLORS,
        )
    if theme_name == "graphite":
        return TerminalTheme(
            (36, 41, 47),
            (243, 244, 246),
            GRAPHITE_NORMAL_COLORS,
            GRAPHITE_BRIGHT_COLORS,
        )
    if theme_name == "navy":
        return TerminalTheme(
            (15, 23, 42),
            (248, 250, 252),
            NAVY_NORMAL_COLORS,
            NAVY_BRIGHT_COLORS,
        )
    if theme_name == "ubuntu":
        return TerminalTheme(
            (48, 10, 36),
            (238, 238, 236),
            UBUNTU_NORMAL_COLORS,
            UBUNTU_BRIGHT_COLORS,
        )
    return DEFAULT_TERMINAL_THEME


def resolve_ansi_colors(style, theme: TerminalTheme) -> tuple[tuple[int, int, int], tuple[int, int, int] | None]:
    default_fg = tuple(theme.foreground_color)
    fg = default_fg
    bg = None

    if style.color is not None:
        fg = tuple(style.color.get_truecolor(theme))
    if style.bgcolor is not None:
        bg = tuple(style.bgcolor.get_truecolor(theme, foreground=False))
    if style.reverse:
        fg, bg = (bg or tuple(theme.background_color)), fg
    return fg, bg


def iter_ansi_segments(line, console: Console, theme: TerminalTheme):
    plain = line.plain
    if not plain:
        return []

    segments = []
    start = 0
    active_style = line.get_style_at_offset(console, 0)
    for offset in range(1, len(plain)):
        style = line.get_style_at_offset(console, offset)
        if style != active_style:
            segments.append((plain[start:offset], active_style))
            start = offset
            active_style = style
    segments.append((plain[start:], active_style))

    resolved = []
    for text, style in segments:
        fg, bg = resolve_ansi_colors(style, theme)
        resolved.append((text, fg, bg))
    return resolved


def render_ansi(text: str, args: argparse.Namespace, font: FontChoice, output: Path) -> None:
    scaled_font_size = max(1, round(args.font_size * args.scale))
    image_pad, line_pad, line_number_pad = get_spacing(args)
    scaled_image_pad = max(0, round(image_pad * args.scale))
    scaled_line_pad = max(0, round(line_pad * args.scale))
    scaled_line_number_pad = max(1, round(line_number_pad * args.scale))
    font_obj = ImageFont.truetype(font.path, scaled_font_size, index=font.index)
    theme = get_terminal_theme(args.theme)
    background = tuple(theme.background_color)
    foreground = tuple(theme.foreground_color)
    line_number_color = get_line_number_color(args.theme)
    console = Console(force_terminal=True, color_system="truecolor")

    decoder = AnsiDecoder()
    lines = list(decoder.decode(text))
    if not lines:
        lines = list(decoder.decode(" "))
    if text.endswith("\n"):
        lines.append(decoder.decode_line(""))

    dummy = Image.new("RGB", (10, 10))
    draw = ImageDraw.Draw(dummy)
    line_height = font_obj.getbbox("Ag")[3] - font_obj.getbbox("Ag")[1] + scaled_line_pad
    number_width = 0

    if args.line_numbers:
        digits = len(str(len(lines)))
        sample = "9" * digits
        bbox = draw.textbbox((0, 0), sample, font=font_obj)
        number_width = (bbox[2] - bbox[0]) + (scaled_line_number_pad * 2)

    content_width = 1
    segment_lines = []
    for line in lines:
        segments = iter_ansi_segments(line, console, theme)
        segment_lines.append(segments)
        width = 0
        for segment_text, _, _ in segments:
            width += draw.textlength(segment_text, font=font_obj)
        content_width = max(content_width, round(width))

    width = scaled_image_pad * 2 + number_width + content_width
    height = scaled_image_pad * 2 + len(lines) * line_height
    image = Image.new("RGB", (width, height), background)
    draw = ImageDraw.Draw(image)
    y = scaled_image_pad

    for index, segments in enumerate(segment_lines, start=1):
        x = scaled_image_pad
        if args.line_numbers:
            draw.text((x, y), str(index), fill=line_number_color, font=font_obj)
            x += number_width

        if not segments:
            y += line_height
            continue

        for segment_text, segment_fg, segment_bg in segments:
            if not segment_text:
                continue
            segment_width = draw.textlength(segment_text, font=font_obj)
            if segment_bg is not None and segment_bg != background:
                draw.rectangle(
                    (
                        round(x),
                        round(y),
                        round(x + segment_width),
                        round(y + line_height),
                    ),
                    fill=segment_bg,
                )
            draw.text((x, y), segment_text, fill=segment_fg or foreground, font=font_obj)
            x += segment_width
        y += line_height

    save_output(image, args, output, background)


def main() -> None:
    args = parse_args()
    source_text, source_name = require_single_input(args)
    output = ensure_output_path(args.output)
    lexer = choose_lexer(source_name, source_text, args)
    font = pick_font(
        source_text,
        args.font,
        for_code=lexer is not None,
        font_size=args.font_size,
    )

    if lexer is None:
        if args.ansi:
            render_ansi(source_text, args, font, output)
        else:
            render_plain_text(source_text, args, font, output)
    else:
        render_code(source_text, lexer, args, font, output)

    print(f"Rendered {output}")


if __name__ == "__main__":
    main()
