#!/usr/bin/env python3
"""
Diagnose ZIP filename encoding.

For each entry in the central directory, prints:
  EFS | utf8_valid | double_encoded | gbk_decodable | recommended_name

Logic (in priority order):
  1. EFS=1 + double-encoded: bytes -> utf-8 str -> latin-1 bytes -> gbk str
  2. EFS=1 + true UTF-8: bytes -> utf-8 str
  3. EFS=0 + GBK: bytes -> gbk str
  4. EFS=0 + GB18030 superset fallback
  5. UTF-8 errors='replace' as last resort
"""
import argparse
import struct
import sys
from pathlib import Path


def read_central_directory(path: Path):
    """Yield (flag_bits, name_bytes, name_len) for each central-dir entry."""
    data = path.read_bytes()
    eocd = data.rfind(b"PK\x05\x06")
    if eocd < 0:
        raise ValueError(f"{path}: not a ZIP (no EOCD signature)")
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


def decode_name(gpf: int, nb: bytes):
    """Return (recommended_name, method) where method explains what worked."""
    efs = bool(gpf & 0x800)
    has_non_ascii = any(b >= 0x80 for b in nb)

    # Pure ASCII: no decoding needed
    if not has_non_ascii:
        return nb.decode("ascii"), "ascii"

    # EFS=1: try double-encoding reversal first, then plain UTF-8
    if efs:
        try:
            return nb.decode("utf-8").encode("latin-1").decode("gbk"), "double-encoded (latin-1 -> gbk)"
        except (UnicodeDecodeError, UnicodeEncodeError):
            pass
        try:
            return nb.decode("utf-8"), "true UTF-8"
        except UnicodeDecodeError:
            pass

    # EFS=0: try GBK then GB18030
    try:
        return nb.decode("gbk"), "gbk"
    except UnicodeDecodeError:
        pass
    try:
        return nb.decode("gb18030"), "gb18030"
    except UnicodeDecodeError:
        pass

    # Last resort
    return nb.decode("utf-8", errors="replace"), "FAILED (replace)"


def classify(gpf: int, nb: bytes) -> dict:
    efs = bool(gpf & 0x800)
    utf8_valid, double_enc, gbk_ok = False, False, False
    try:
        nb.decode("utf-8"); utf8_valid = True
    except UnicodeDecodeError:
        pass
    if utf8_valid:
        try:
            nb.decode("utf-8").encode("latin-1").decode("gbk")
            # Only count as double-encoded if non-ASCII present
            double_enc = any(b >= 0x80 for b in nb)
        except (UnicodeDecodeError, UnicodeEncodeError):
            pass
    try:
        nb.decode("gbk"); gbk_ok = True
    except UnicodeDecodeError:
        pass
    name, method = decode_name(gpf, nb)
    return dict(
        efs=efs,
        utf8_valid=utf8_valid,
        double_enc=double_enc,
        gbk_ok=gbk_ok,
        method=method,
        name=name,
    )


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("zip", help="Path to ZIP file")
    ap.add_argument("--raw-hex", action="store_true", help="Show raw bytes hex")
    args = ap.parse_args()

    path = Path(args.zip).expanduser()
    if not path.exists():
        sys.exit(f"not found: {path}")

    print(f"Archive: {path}")
    print(f"{'EFS':4}  {'utf8':4}  {'2x?':4}  {'gbk':4}  method                              name")
    print("-" * 110)
    n_double = 0
    for gpf, nb in read_central_directory(path):
        info = classify(gpf, nb)
        if info["double_enc"]:
            n_double += 1
        print(
            f"{'Y' if info['efs'] else 'N':4}  "
            f"{'Y' if info['utf8_valid'] else 'N':4}  "
            f"{'Y' if info['double_enc'] else 'N':4}  "
            f"{'Y' if info['gbk_ok'] else 'N':4}  "
            f"{info['method']:<36}  "
            f"{info['name']}"
        )
        if args.raw_hex:
            print(f"       raw hex: {nb.hex(' ')}")
    print("-" * 110)
    print(f"double-encoded entries: {n_double}")
    if n_double > 0:
        print(
            ">> This archive has Windows-tool double-encoding bug. "
            "Use extract_fixed.py to recover real names."
        )


if __name__ == "__main__":
    main()
