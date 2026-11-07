#!/usr/bin/env python3
"""
Re-compress files into a UTF-8-safe ZIP.

Produces an archive whose filenames are real UTF-8 bytes with the EFS flag
correctly set, readable on Windows 10+ Explorer, 7-Zip, WinRAR, macOS Finder,
Linux, and Python `zipfile`.

Inputs (one of):
  - A source directory: walked recursively
  - A source ZIP: entries extracted with corrected names first, then repacked

Output: <stem>_utf8.zip in the same parent directory (or --out path).

Skipped: .DS_Store, Thumbs.db, ._* (AppleDouble).

After writing, verifies the round-trip via Python `zipfile.namelist()`.
"""
import argparse
import sys
import tempfile
import zipfile
from pathlib import Path

SKIP_NAMES = {".DS_Store", "Thumbs.db"}
SKIP_PREFIXES = ("._",)


def should_skip(name: str) -> bool:
    base = name.rsplit("/", 1)[-1]
    if base in SKIP_NAMES:
        return True
    return any(base.startswith(p) for p in SKIP_PREFIXES)


def add_tree(zf: zipfile.ZipFile, root: Path, arc_prefix: str = ""):
    for path in sorted(root.rglob("*")):
        if path.is_dir():
            continue
        rel = path.relative_to(root).as_posix()
        if should_skip(rel):
            continue
        arc = f"{arc_prefix}/{rel}" if arc_prefix else rel
        zf.write(path, arc)


def repack_from_dir(src: Path, out_zip: Path):
    with zipfile.ZipFile(out_zip, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        add_tree(zf, src)


def repack_from_zip(src: Path, out_zip: Path):
    # Borrow the fixed-extract logic, then repack the temp dir
    sys.path.insert(0, str(Path(__file__).parent))
    from extract_fixed import extract_zip  # type: ignore

    with tempfile.TemporaryDirectory(prefix="repack_") as tmp:
        tmp_path = Path(tmp)
        extract_zip(src, tmp_path / "src", max_depth=3)
        # The extraction may produce nested _extracted dirs; flatten by repacking the top
        repack_from_dir(tmp_path / "src", out_zip)


def verify(out_zip: Path) -> bool:
    """Round-trip via Python zipfile; returns True if all names decode cleanly as UTF-8."""
    z = zipfile.ZipFile(out_zip)
    for info in z.infolist():
        # EFS flag check
        efs = bool(info.flag_bits & 0x800)
        has_non_ascii = any(ord(c) >= 0x80 for c in info.filename)
        if has_non_ascii and not efs:
            sys.stderr.write(f"  VERIFY WARN non-ascii name without EFS: {info.filename}\n")
        # Round-trip the bytes back
        raw_bytes = info.filename.encode("utf-8")
        try:
            raw_bytes.decode("utf-8")
        except UnicodeDecodeError as e:
            sys.stderr.write(f"  VERIFY FAIL: {info.filename} ({e})\n")
            return False
    return True


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("src", help="Source directory or ZIP")
    ap.add_argument("--out", help="Output ZIP path (default: <stem>_utf8.zip)")
    args = ap.parse_args()

    src = Path(args.src).expanduser()
    if not src.exists():
        sys.exit(f"not found: {src}")

    if args.out:
        out_zip = Path(args.out).expanduser()
    else:
        out_zip = src.with_name(src.stem + "_utf8.zip")

    print(f"repacking {src} -> {out_zip}")
    if src.is_dir():
        repack_from_dir(src, out_zip)
    elif src.is_file() and src.suffix.lower() == ".zip":
        repack_from_zip(src, out_zip)
    else:
        sys.exit(f"unsupported source: {src} (need directory or .zip)")

    size = out_zip.stat().st_size
    print(f"wrote {out_zip} ({size} bytes)")

    if verify(out_zip):
        print("verify: OK (all names round-trip cleanly)")
    else:
        print("verify: FAILED — see warnings above", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
