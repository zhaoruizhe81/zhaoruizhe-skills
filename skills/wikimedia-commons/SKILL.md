---
name: wikimedia-commons
description: Search and download freely-licensed images from Wikimedia Commons (Wikipedia's media library) with a pure-HTTP CLI and per-file attribution manifests. Use when the user wants free/open-license photos for a topic, illustrative images for reports/slides/articles, or a licensed image list — 从 Wikimedia Commons 搜图/下载图片、找免版权配图、按分类取图、下某个 File 文件。Supports keyword search, category browsing, direct file download, thumbnail width control, dry-run preview, and sidecar attribution files (author + license + source).
---

# Wikimedia Commons

Search and download images from **Wikimedia Commons** (commons.wikimedia.org) — millions of freely-licensed
photos, diagrams and media. Pure standard-library Python; no API key needed for read/download.

Every file has **its own license** (CC0 / CC BY / CC BY-SA / public domain …). Always keep the generated
`wikimedia-attribution.txt` / `wikimedia-manifest.json` so author + license + source stay attached.

## Quick Start

```bash
# preview matches (no download)
python "<skill-path>/scripts/wikimedia_commons.py" --search "Eiffel Tower" --count 5 --dry-run

# download 6 images at ~1600px wide + attribution sidecars
python "<skill-path>/scripts/wikimedia_commons.py" --search "smart campus" --count 6 \
  --output-dir "/absolute/path/out"

# browse a category
python "<skill-path>/scripts/wikimedia_commons.py" --category "Category:Cats" --count 5 \
  --output-dir "/absolute/path/out"

# a specific file
python "<skill-path>/scripts/wikimedia_commons.py" --file "File:Example.jpg" \
  --output-dir "/absolute/path/out"
```

## Workflow

1. Pick the mode: `--search "<keywords>"` (usual), `--category "Category:X"` (browse), or `--file "File:..."` (known file).
2. Decide the output folder (`--output-dir`) — use a dedicated empty folder per batch.
3. Choose size: `--width N` for a resized thumbnail (server-side, default 1600; `0` = original), optionally `--min-width N` to skip small images.
4. Run the script. Prefer `--dry-run` first for broad queries; add `--json` for machine-readable output.
5. Return the saved files and mention the sidecars:
   - `wikimedia-manifest.json` — structured metadata per file (author, license, URLs, dimensions)
   - `wikimedia-attribution.txt` — ready-to-paste attribution lines

## Common Commands

```bash
# landscape-ish illustrations for a slide, resized to 1200px
python "<skill-path>/scripts/wikimedia_commons.py" --search "data visualization diagram" \
  --count 4 --width 1200 --min-width 800 --output-dir "./out"

# dry-run + json to inspect before downloading
python "<skill-path>/scripts/wikimedia_commons.py" --search "athens acropolis" --count 8 --dry-run --json

# original resolution for a known file
python "<skill-path>/scripts/wikimedia_commons.py" --file "File:Mona Lisa.jpg" --width 0 --output-dir "./out"
```

## Environment & Notes

- **No API key** for search/download. Wikimedia requires a descriptive **User-Agent**; the script sets a default
  (`wikimedia-commons-skill/1.0 (+repo)`). Override with `--user-agent` or env `WIKIMEDIA_UA`.
- **Licenses differ per file.** CC BY / CC BY-SA require attribution (and SA derivatives share alike). The script
  records `license`, `license_url`, `artist`, `credit`, `attribution_required` per file — use them.
- Search runs in the **File namespace (ns=6)**; you can add `filetype:bitmap` to a query to limit to raster images.
- Thumbnails are produced server-side, so requested `--width` may snap to the nearest available size (e.g. 960/1280).
- Be polite: the script sleeps briefly between downloads. Avoid large batches; split runs.
- Custom endpoints (rare): env `WIKIMEDIA_API` or `--api` to point at another MediaWiki API.

## Bundled Resources

### scripts/wikimedia_commons.py
Search/category/file lookup via the MediaWiki Action API, server-side thumbnails, download, and sidecar generation.

### references/cli.md
Full option reference, the underlying API calls/params, `extmetadata` fields used for attribution, and troubleshooting.
