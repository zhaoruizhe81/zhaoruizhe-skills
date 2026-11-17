#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Search and download free-licensed images from Wikimedia Commons.

Pure standard library (urllib/json/re/argparse) — no third-party deps.

Examples:
  python wikimedia_commons.py --search "Eiffel Tower" --count 5 --dry-run
  python wikimedia_commons.py --search "cat" --count 5 --width 1200 --output-dir ./out
  python wikimedia_commons.py --category "Category:Cats" --count 5 --output-dir ./out
  python wikimedia_commons.py --file "File:Example.jpg" --output-dir ./out

Notes:
  - Wikimedia requires a descriptive User-Agent; default includes the project URL. Override with --user-agent.
  - Every file has its own license (CC0 / CC BY / CC BY-SA / public domain ...). Keep the generated
    attribution files; they carry LicenseShortName / Artist / LicenseUrl / source page for each file.
"""

import argparse
import html
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request

API_DEFAULT = "https://commons.wikimedia.org/w/api.php"
UA_DEFAULT = "wikimedia-commons-skill/1.0 (+https://github.com/zhaoruizhe81/zhaoruizhe-skills)"


def strip_html(s):
    if not s:
        return ""
    s = re.sub(r"<[^>]+>", "", str(s))
    s = html.unescape(s)
    return re.sub(r"\s+", " ", s).strip()


def dedupe(s):
    """Collapse an exactly-doubled string like "Unknown authorUnknown author"."""
    n = len(s)
    if n and n % 2 == 0 and s[: n // 2] == s[n // 2 :]:
        return s[: n // 2]
    return s


def em(extmeta, key):
    """Read an extmetadata field value."""
    v = (extmeta or {}).get(key)
    if isinstance(v, dict):
        return dedupe(strip_html(v.get("value")))
    return dedupe(strip_html(v)) if v else ""


def api_get(api, params, user_agent, retries=3):
    params = dict(params)
    params.setdefault("format", "json")
    params.setdefault("formatversion", "2")
    url = api + "?" + urllib.parse.urlencode(params)
    last = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": user_agent, "Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=40) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(1.0 + attempt)
    raise RuntimeError(f"API request failed: {last}\nURL: {url}")


def norm_title(t):
    t = (t or "").strip()
    if not t:
        return t
    if not t.lower().startswith(("file:", "image:")):
        t = "File:" + t
    return t


def query_pages(api, base_params, user_agent, max_items):
    """Run a query/generator and yield page dicts (with imageinfo), following continuation."""
    params = dict(base_params)
    got = []
    while True:
        data = api_get(api, params, user_agent)
        for p in (data.get("query", {}) or {}).get("pages", []) or []:
            got.append(p)
            if len(got) >= max_items:
                return got
        cont = data.get("continue")
        if not cont:
            return got
        params.update(cont)


def fetch_candidates(args):
    if args.file:
        params = {
            "action": "query",
            "titles": norm_title(args.file),
            "prop": "imageinfo",
            "iiprop": "url|size|mime|extmetadata",
            "iiurlwidth": args.width,
        }
        return query_pages(args.api, params, args.user_agent, 1)

    if args.category:
        cat = args.category.strip()
        if not cat.lower().startswith("category:"):
            cat = "Category:" + cat
        params = {
            "action": "query",
            "generator": "categorymembers",
            "gcmtitle": cat,
            "gcmtype": "file",
            "gcmlimit": min(max(args.count * 3, 20), 500),
            "prop": "imageinfo",
            "iiprop": "url|size|mime|extmetadata",
            "iiurlwidth": args.width,
        }
        return query_pages(args.api, params, args.user_agent, args.count)

    # default: search
    params = {
        "action": "query",
        "generator": "search",
        "gsrsearch": args.search,
        "gsrnamespace": 6,  # File namespace
        "gsrlimit": min(max(args.count * 3, 20), 500),
        "prop": "imageinfo",
        "iiprop": "url|size|mime|extmetadata",
        "iiurlwidth": args.width,
    }
    return query_pages(args.api, params, args.user_agent, args.count)


def sanitize_filename(title, url):
    name = re.sub(r"^File:", "", title, flags=re.I).strip()
    name = re.sub(r"[\\/:*?\"<>|\r\n\t]+", "_", name)
    name = re.sub(r"\s+", " ", name).strip()
    ext = os.path.splitext(urllib.parse.urlparse(url).path)[1].lower()
    if not ext:
        ext = ".jpg"
    base = os.path.splitext(name)[0]
    return (base[:120] or "image") + ext


def download(url, dest, user_agent):
    req = urllib.request.Request(url, headers={"User-Agent": user_agent})
    with urllib.request.urlopen(req, timeout=60) as resp, open(dest, "wb") as f:
        f.write(resp.read())


def build_record(page):
    ii = (page.get("imageinfo") or [{}])[0]
    ext = ii.get("extmetadata") or {}
    return {
        "pageid": page.get("pageid"),
        "title": page.get("title") or "",
        "descriptionurl": ii.get("descriptionurl") or page.get("descriptionurl") or "",
        "original_url": ii.get("url") or "",
        "thumb_url": ii.get("thumburl") or "",
        "width": ii.get("width"),
        "height": ii.get("height"),
        "mime": ii.get("mime") or "",
        "license": em(ext, "LicenseShortName") or em(ext, "UsageTerms"),
        "license_url": em(ext, "LicenseUrl"),
        "usage_terms": em(ext, "UsageTerms"),
        "artist": em(ext, "Artist"),
        "credit": em(ext, "Credit"),
        "attribution_required": em(ext, "AttributionRequired").lower() in ("true", "1", "yes"),
        "description": strip_html(em(ext, "ImageDescription"))[:500],
    }


def write_sidecars(records, output_dir, query_desc):
    manifest = {
        "source": "Wikimedia Commons",
        "query": query_desc,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "note": "Each file carries its own license; attribution may be required. See per-file fields.",
        "count": len(records),
        "files": records,
    }
    with open(os.path.join(output_dir, "wikimedia-manifest.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)

    lines = [f"Wikimedia Commons images — {query_desc}", ""]
    for r in records:
        who = r["artist"] or r["credit"] or "Unknown"
        lic = r["license"] or "see source"
        line = f"- {r.get('saved_as','')}  “{r['title']}”  by {who}  ({lic})"
        if r["license_url"]:
            line += f"  License: {r['license_url']}"
        if r["descriptionurl"]:
            line += f"  Source: {r['descriptionurl']}"
        lines.append(line)
    lines += ["", "License/author per file; verify before reuse. Generated from Wikimedia Commons API."]
    with open(os.path.join(output_dir, "wikimedia-attribution.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def main():
    ap = argparse.ArgumentParser(description="Search and download free images from Wikimedia Commons.")
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--search", help="Keyword search query")
    src.add_argument("--category", help="Category name, e.g. 'Category:Cats' or 'Cats'")
    src.add_argument("--file", help="A specific file title, e.g. 'File:Example.jpg'")
    ap.add_argument("--count", type=int, default=6, help="Max images (default 6)")
    ap.add_argument("--output-dir", help="Directory to save images + sidecars (required unless --dry-run)")
    ap.add_argument("--width", type=int, default=1600, help="Thumbnail width in px (default 1600; use 0 for original)")
    ap.add_argument("--min-width", type=int, default=0, help="Skip images narrower than this")
    ap.add_argument("--dry-run", action="store_true", help="Only list matches, do not download")
    ap.add_argument("--json", action="store_true", help="Print JSON summary to stdout")
    ap.add_argument("--user-agent", default=os.environ.get("WIKIMEDIA_UA", UA_DEFAULT))
    ap.add_argument("--api", default=os.environ.get("WIKIMEDIA_API", API_DEFAULT))
    args = ap.parse_args()

    if not args.output_dir and not args.dry_run:
        ap.error("--output-dir is required unless --dry-run")

    query_desc = args.search or args.category or args.file
    pages = fetch_candidates(args)

    records = []
    for p in pages:
        r = build_record(p)
        if not (r["original_url"] or r["thumb_url"]):
            continue
        if args.min_width and (r["width"] or 0) < args.min_width:
            continue
        records.append(r)
        if len(records) >= args.count:
            break

    if not records:
        print("No matching files found.", file=sys.stderr)
        sys.exit(1)

    if args.dry_run:
        for i, r in enumerate(records, 1):
            print(f"{i:02d}  {r['title']}  [{r['width']}x{r['height']}]  {r['license'] or '?'}  {r['descriptionurl']}")
        if args.json:
            print(json.dumps({"query": query_desc, "count": len(records), "files": records}, ensure_ascii=False, indent=2))
        return

    os.makedirs(args.output_dir, exist_ok=True)
    saved = []
    for i, r in enumerate(records, 1):
        url = r["thumb_url"] or r["original_url"]
        if args.width and args.width > 0 and r["thumb_url"]:
            url = r["thumb_url"]
        else:
            url = r["original_url"] or r["thumb_url"]
        fname = f"{i:02d}_{sanitize_filename(r['title'], url)}"
        dest = os.path.join(args.output_dir, fname)
        try:
            download(url, dest, args.user_agent)
            r["saved_as"] = fname
            r["saved_path"] = os.path.abspath(dest)
            r["downloaded_url"] = url
            saved.append(r)
            print(f"✔ {fname}  ({r['width']}x{r['height']}, {r['license'] or '?'})", file=sys.stderr)
        except Exception as e:  # noqa: BLE001
            print(f"✘ 下载失败 {r['title']}: {e}", file=sys.stderr)
        time.sleep(0.3)

    write_sidecars(saved, args.output_dir, query_desc)
    out = {"query": query_desc, "output_dir": os.path.abspath(args.output_dir), "downloaded": len(saved),
           "manifest": os.path.join(os.path.abspath(args.output_dir), "wikimedia-manifest.json"),
           "files": [s.get("saved_as") for s in saved]}
    if args.json:
        print(json.dumps(out, ensure_ascii=False, indent=2))
    else:
        print(os.path.abspath(args.output_dir))


if __name__ == "__main__":
    main()
