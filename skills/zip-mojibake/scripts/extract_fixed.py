#!/usr/bin/env python3
"""
Recursively extract a ZIP with corrected Chinese filenames.

Handles:
  - Windows-tool double-encoding bug (EFS=1 but bytes are latin-1(GBK) -> utf-8)
  - Pure GBK zips (EFS=0)
  - Nested zips (auto-expand, depth limit configurable)

Safety:
  - Strips leading slashes
  - Rejects '..' path components
  - Rejects Windows reserved names (CON, PRN, AUX, NUL, COM1-9, LPT1-9)
"""
import argparse
import os
import struct
import sys
import zipfile
from pathlib import Path

ZIP_MAGIC = b"PK\x03\x04"
WIN_RESERVED = {"CON", "PRN", "AUX", "NUL"} | {
    f"COM{i}" for i in range(1, 10)
} | {f"LPT{i}" for i in range(1, 10)}


def decode_name(gpf: int, nb: bytes) -> str:
    """Mirrors diagnose.decode_name. Returns best-effort name."""
    efs = bool(gpf & 0x800)
    has_non_ascii = any(b >= 0x80 for b in nb)
    if not has_non_ascii:
        return nb.decode("ascii")
    if efs:
        try:
            return nb.decode("utf-8").encode("latin-1").decode("gbk")
        except (UnicodeDecodeError, UnicodeEncodeError):
            pass
        try:
            return nb.decode("utf-8")
        except UnicodeDecodeError:
            pass
    try:
        return nb.decode("gbk")
    except UnicodeDecodeError:
        pass
    try:
        return nb.decode("gb18030")
    except UnicodeDecodeError:
        pass
    sys.stderr.write(f"  WARN: failed to decode {nb.hex(' ')} cleanly, using replace\n")
    return "_RECOVERFAILED_" + nb.decode("utf-8", errors="replace")


def read_central_pairs(path: Path):
    """Yield (gpf, name_bytes) for each entry, in CD order."""
    data = path.read_bytes()
    eocd = data.rfind(b"PK\x05\x06")
    if eocd < 0:
        raise ValueError(f"not a zip: {path}")
    cd_off = struct.unpack("<I", data[eocd + 16 : eocd + 20])[0]
    cd_size = struct.unpack("<I", data[eocd + 12 : eocd + 16])[0]
    p, end = cd_off, cd_off + cd_size
    while p < end:
        if data[p : p + 4] != b"PK\x01\x02":
            break
        gpf = struct.unpack("<H", data[p + 8 : p + 10])[0]
        fn_len = struct.unpack("<H", data[p + 28 : p + 30])[0]
        extra_len = struct.unpack("<H", data[p + 30 : p + 32])[0]
        com_len = struct.unpack("<H", data[p + 32 : p + 34])[0]
        nb = data[p + 46 : p + 46 + fn_len]
        yield gpf, nb
        p += 46 + fn_len + extra_len + com_len


def safe_join(base: Path, name: str) -> Path | None:
    """
    Reject unsafe paths. Returns None if the entry should be skipped.
    Backslashes are converted to forward slashes (Windows source archives).
    """
    name = name.replace("\\", "/")
    parts = []
    for seg in name.split("/"):
        if seg in ("", ".", ".."):
            continue
        stem = seg.split(".")[0].rstrip(" .")
        if stem.upper() in WIN_RESERVED:
            seg = "_" + seg
        parts.append(seg)
    if not parts:
        return None
    full = base.joinpath(*parts)
    try:
        full.resolve().relative_to(base.resolve())
    except ValueError:
        return None
    return full


ZIP_LIKE_EXTS = {".zip", ".jar", ".war", ".apk", ".whl"}


def looks_like_zip(payload: bytes, target_name: str) -> bool:
    """Only recurse into files that are real archives by both magic and extension.
    docx/xlsx/pptx/jar/etc are also PK-zip but we don't want to expand them."""
    if payload[:4] != ZIP_MAGIC:
        return False
    suffix = Path(target_name).suffix.lower()
    return suffix in ZIP_LIKE_EXTS


def extract_zip(zip_path: Path, out_dir: Path, max_depth: int, depth: int = 0):
    out_dir.mkdir(parents=True, exist_ok=True)
    z = zipfile.ZipFile(zip_path)
    cd_pairs = list(read_central_pairs(zip_path))
    if len(cd_pairs) != len(z.infolist()):
        sys.stderr.write(
            f"  WARN: CD count mismatch in {zip_path}, falling back to zipfile names\n"
        )
        cd_pairs = [(i.flag_bits, i.filename.encode("utf-8", "replace")) for i in z.infolist()]

    for info, (gpf, nb) in zip(z.infolist(), cd_pairs):
        real_name = decode_name(gpf, nb)
        if real_name.endswith("/"):
            continue
        target = safe_join(out_dir, real_name)
        if target is None:
            sys.stderr.write(f"  SKIP unsafe path: {real_name}\n")
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        with z.open(info) as src, open(target, "wb") as dst:
            payload = src.read()
        dst_write_ok = True
        try:
            target.write_bytes(payload)
        except OSError as e:
            sys.stderr.write(f"  WARN writing {target}: {e}\n")
            dst_write_ok = False

        # Recurse into nested zips
        if dst_write_ok and depth < max_depth and looks_like_zip(payload, target.name):
            nested_out = target.parent / (target.stem + "_extracted")
            sys.stderr.write(f"  -> nested zip, extracting to {nested_out}\n")
            extract_zip(target, nested_out, max_depth, depth + 1)

    print(f"extracted {zip_path} -> {out_dir}  (depth={depth})")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("zip", help="Path to ZIP file")
    ap.add_argument("--out", help="Output directory (default: <zip>_recovered)")
    ap.add_argument("--max-depth", type=int, default=3, help="Nested zip recursion depth (default 3)")
    args = ap.parse_args()

    src = Path(args.zip).expanduser()
    if not src.exists():
        sys.exit(f"not found: {src}")
    out = Path(args.out).expanduser() if args.out else src.with_name(src.stem + "_recovered")
    if out.exists() and any(out.iterdir()):
        sys.exit(f"output dir not empty: {out} (remove or pass --out)")
    extract_zip(src, out, args.max_depth)


if __name__ == "__main__":
    main()
