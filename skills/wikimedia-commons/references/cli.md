# wikimedia-commons — CLI & API reference

## Options

| Flag | Meaning |
|---|---|
| `--search "kw"` | Keyword search (File namespace, ns=6). Mutually exclusive with `--category` / `--file`. |
| `--category "Category:X"` | List files in a category (`Category:` prefix optional). |
| `--file "File:Y.jpg"` | Download one specific file (`File:` prefix optional). |
| `--count N` | Max files to fetch (default 6). |
| `--output-dir DIR` | Output folder (required unless `--dry-run`). |
| `--width N` | Server-side thumbnail width in px (default 1600; `0` = original). |
| `--min-width N` | Skip images whose original width is below N. |
| `--dry-run` | Print matches only; no download. |
| `--json` | Print a JSON summary to stdout. |
| `--user-agent STR` | Override User-Agent (or env `WIKIMEDIA_UA`). |
| `--api URL` | Override API endpoint (or env `WIKIMEDIA_API`). |

## Output

- Images: `<NN>_<sanitized title>.<ext>` in `--output-dir`.
- `wikimedia-manifest.json`: `{source, query, generated_at, count, files:[...]}` — each file has
  `title, descriptionurl, original_url, thumb_url, downloaded_url, width, height, mime, license,
  license_url, usage_terms, artist, credit, attribution_required, description, saved_as`.
- `wikimedia-attribution.txt`: human-readable one-line-per-file attribution.

## Underlying API (MediaWiki Action API)

Base: `https://commons.wikimedia.org/w/api.php` (`format=json&formatversion=2`).

**Search** (generator + imageinfo):
```
?action=query&generator=search&gsrsearch=<query>&gsrnamespace=6&gsrlimit=<n>
&prop=imageinfo&iiprop=url|size|mime|extmetadata&iiurlwidth=<W>
```

**Category** (generator=categorymembers):
```
?action=query&generator=categorymembers&gcmtitle=Category:<name>&gcmtype=file&gcmlimit=<n>
&prop=imageinfo&iiprop=url|size|mime|extmetadata&iiurlwidth=<W>
```

**Single file**:
```
?action=query&titles=File:<name>&prop=imageinfo&iiprop=url|size|mime|extmetadata&iiurlwidth=<W>
```

Pagination: responses may include a `continue` object; pass all its keys back to fetch the next page
(the script does this automatically until it reaches `--count`).

## Attribution fields (`imageinfo.extmetadata`)

| Field | Use |
|---|---|
| `LicenseShortName` | Short license, e.g. `CC BY-SA 4.0`, `Public domain` |
| `UsageTerms` | Longer human terms |
| `LicenseUrl` | License deed URL |
| `Artist` | Author (HTML stripped) |
| `Credit` | Credit line / source attribution |
| `AttributionRequired` | `true/false` |
| `ImageDescription` | Caption/description |
| `DateTimeOriginal` | Original date |

`iiurlwidth` returns a `thumburl` at the closest available size; `url` is the original file.

## Recipes

```bash
# JSON inspect for a broad topic, then download the good ones
python scripts/wikimedia_commons.py --search "osaka castle" --count 10 --dry-run --json
python scripts/wikimedia_commons.py --search "osaka castle" --count 4 --width 1400 --min-width 1000 --output-dir ./out

# raster-only search
python scripts/wikimedia_commons.py --search "flowchart filetype:bitmap" --count 5 --dry-run

# exact file → original resolution
python scripts/wikimedia_commons.py --file "File:Example.jpg" --width 0 --output-dir ./out
```

## Troubleshooting

- **403 / blocked**: set a real `--user-agent` (include a contact/repo URL). Wikimedia policy requires it.
- **429 / slow**: reduce `--count`, wait, split batches. The script already sleeps between downloads.
- **No results**: try English keywords (Commons categories/descriptions are mostly English); loosen the query;
  or browse a `Category:` instead.
- **Wrong size**: `--width` snaps to server thumbnails; use `--width 0` to get the original file.
- **License caution**: Commons files are free but many are **CC BY / CC BY-SA** (attribution, share-alike).
  Check `attribution_required` / `license` before publishing; keep the sidecars.
