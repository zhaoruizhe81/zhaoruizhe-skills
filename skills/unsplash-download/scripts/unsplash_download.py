#!/usr/bin/env python3
"""Search and download Unsplash photos with local sidecar metadata."""

from __future__ import annotations

import argparse
import json
import mimetypes
import os
import re
import sys
import time
from pathlib import Path
from typing import Dict, Iterable, List, Optional
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qsl, urlencode, urljoin, urlparse, urlunparse
from urllib.request import Request, urlopen

DEFAULT_API_BASE = "https://api.unsplash.com"
DEFAULT_TIMEOUT = 30


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Search and download Unsplash photos to a local folder."
    )
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--query", help="Search query for Unsplash photos.")
    source.add_argument("--photo-id", help="Download a specific Unsplash photo id.")

    parser.add_argument(
        "--output-dir",
        default=".",
        help="Directory to save downloaded files into. Defaults to the current directory.",
    )
    parser.add_argument(
        "--count",
        type=int,
        default=1,
        help="Number of photos to download in search mode. Defaults to 1.",
    )
    parser.add_argument(
        "--page",
        type=int,
        default=1,
        help="Starting page for search mode. Defaults to 1.",
    )
    parser.add_argument(
        "--orientation",
        choices=["landscape", "portrait", "squarish"],
        help="Optional Unsplash orientation filter for search mode.",
    )
    parser.add_argument(
        "--order-by",
        choices=["relevant", "latest"],
        default="relevant",
        help="Search result ordering. Defaults to relevant.",
    )
    parser.add_argument(
        "--content-filter",
        choices=["low", "high"],
        default="low",
        help="Unsplash content filter. Defaults to low.",
    )
    parser.add_argument(
        "--url-kind",
        choices=["raw", "full", "regular", "small", "thumb"],
        default="full",
        help="Base URL variant to download when no custom transforms are requested.",
    )
    parser.add_argument("--width", type=int, help="Optional output width.")
    parser.add_argument("--height", type=int, help="Optional output height.")
    parser.add_argument(
        "--format",
        choices=["jpg", "png", "webp"],
        help="Optional output format hint passed to Imgix.",
    )
    parser.add_argument(
        "--quality",
        type=int,
        help="Optional output quality hint (1-100) passed to Imgix.",
    )
    parser.add_argument(
        "--access-key",
        help="Unsplash access key. Defaults to the UNSPLASH_ACCESS_KEY environment variable.",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=DEFAULT_TIMEOUT,
        help=f"Request timeout in seconds. Defaults to {DEFAULT_TIMEOUT}.",
    )
    parser.add_argument(
        "--api-base-url",
        default=DEFAULT_API_BASE,
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--skip-sidecar-files",
        action="store_true",
        help="Skip writing manifest and attribution sidecar files.",
    )
    parser.add_argument(
        "--skip-download-tracking",
        action="store_true",
        help="Skip the Unsplash download tracking request.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print selected photo metadata without downloading image files.",
    )
    args = parser.parse_args()

    if args.count < 1:
        parser.error("--count must be at least 1")
    if args.page < 1:
        parser.error("--page must be at least 1")
    if args.quality is not None and not 1 <= args.quality <= 100:
        parser.error("--quality must be between 1 and 100")

    return args


def resolve_access_key(args: argparse.Namespace) -> str:
    access_key = args.access_key or os.environ.get("UNSPLASH_ACCESS_KEY")
    if not access_key:
        raise SystemExit(
            "Missing Unsplash access key. Set UNSPLASH_ACCESS_KEY or pass --access-key."
        )
    return access_key


def api_get_json(
    url: str,
    access_key: str,
    timeout: int,
    params: Optional[Dict[str, object]] = None,
) -> Dict[str, object]:
    if params:
        url = build_url(url, params)
    request = Request(
        url,
        headers={
            "Authorization": f"Client-ID {access_key}",
            "Accept-Version": "v1",
            "User-Agent": "codex-unsplash-download-skill/1.0",
        },
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            return json.load(response)
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise SystemExit(
            f"Unsplash API request failed with HTTP {exc.code}: {body or exc.reason}"
        ) from exc
    except URLError as exc:
        raise SystemExit(f"Unsplash API request failed: {exc.reason}") from exc


def build_url(url: str, params: Dict[str, object]) -> str:
    parsed = urlparse(url)
    query_items = dict(parse_qsl(parsed.query, keep_blank_values=True))
    for key, value in params.items():
        if value is None:
            continue
        query_items[str(key)] = str(value)
    return urlunparse(parsed._replace(query=urlencode(query_items, doseq=True)))


def fetch_search_results(
    args: argparse.Namespace, access_key: str
) -> List[Dict[str, object]]:
    api_base = args.api_base_url.rstrip("/")
    collected: List[Dict[str, object]] = []
    page = args.page
    while len(collected) < args.count:
        per_page = min(30, args.count - len(collected))
        payload = api_get_json(
            f"{api_base}/search/photos",
            access_key,
            args.timeout,
            params={
                "query": args.query,
                "page": page,
                "per_page": per_page,
                "order_by": args.order_by,
                "content_filter": args.content_filter,
                "orientation": args.orientation,
            },
        )
        results = payload.get("results") or []
        if not isinstance(results, list):
            raise SystemExit("Unexpected Unsplash response: results is not a list.")
        if not results:
            break
        collected.extend(results)
        if len(results) < per_page:
            break
        page += 1
    return collected[: args.count]


def fetch_photo(args: argparse.Namespace, access_key: str) -> List[Dict[str, object]]:
    api_base = args.api_base_url.rstrip("/")
    payload = api_get_json(
        f"{api_base}/photos/{args.photo_id}",
        access_key,
        args.timeout,
    )
    return [payload]


def make_download_url(photo: Dict[str, object], args: argparse.Namespace) -> str:
    urls = photo.get("urls")
    if not isinstance(urls, dict):
        raise SystemExit("Unexpected Unsplash response: photo.urls is missing.")

    transforms_requested = any(
        value is not None for value in (args.width, args.height, args.format, args.quality)
    )
    if transforms_requested:
        raw_url = urls.get("raw")
        if not isinstance(raw_url, str) or not raw_url:
            raise SystemExit("Unexpected Unsplash response: photo.urls.raw is missing.")
        return build_url(
            raw_url,
            {
                "w": args.width,
                "h": args.height,
                "fm": args.format,
                "q": args.quality,
            },
        )

    download_url = urls.get(args.url_kind)
    if not isinstance(download_url, str) or not download_url:
        raise SystemExit(
            f"Unexpected Unsplash response: photo.urls.{args.url_kind} is missing."
        )
    return download_url


def trigger_download_tracking(
    photo: Dict[str, object], args: argparse.Namespace, access_key: str
) -> None:
    if args.skip_download_tracking:
        return

    links = photo.get("links")
    if not isinstance(links, dict):
        return
    download_location = links.get("download_location")
    if not isinstance(download_location, str) or not download_location:
        return
    if not download_location.startswith("http"):
        download_location = urljoin(args.api_base_url.rstrip("/") + "/", download_location)
    api_get_json(download_location, access_key, args.timeout)


def slugify(text: str) -> str:
    text = text.strip().lower()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[-\s]+", "-", text)
    return text.strip("-") or "photo"


def choose_filename(photo: Dict[str, object], index: int, content_type: str) -> str:
    photo_id = str(photo.get("id") or f"photo-{index}")
    user = photo.get("user") or {}
    username = ""
    if isinstance(user, dict):
        username = str(user.get("username") or "")
    description = str(
        photo.get("description")
        or photo.get("alt_description")
        or username
        or photo_id
    )
    stem = f"{index:02d}-{photo_id}-{slugify(description)[:48]}".strip("-")
    ext = extension_for_type(content_type) or ".jpg"
    return stem + ext


def extension_for_type(content_type: str) -> str:
    if not content_type:
        return ""
    content_type = content_type.split(";")[0].strip().lower()
    guess = mimetypes.guess_extension(content_type)
    if guess == ".jpe":
        return ".jpg"
    return guess or ""


def download_binary(url: str, access_key: str, timeout: int) -> tuple[bytes, str]:
    del access_key
    request = Request(url, headers={"User-Agent": "codex-unsplash-download-skill/1.0"})
    try:
        with urlopen(request, timeout=timeout) as response:
            return response.read(), response.headers.get("Content-Type", "")
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise SystemExit(
            f"Image download failed with HTTP {exc.code}: {body or exc.reason}"
        ) from exc
    except URLError as exc:
        raise SystemExit(f"Image download failed: {exc.reason}") from exc


def photo_manifest_entry(
    photo: Dict[str, object],
    local_path: Optional[Path],
    selected_url: str,
    query: Optional[str],
) -> Dict[str, object]:
    user = photo.get("user") or {}
    user_links = user.get("links") if isinstance(user, dict) else {}
    return {
        "id": photo.get("id"),
        "query": query,
        "description": photo.get("description"),
        "alt_description": photo.get("alt_description"),
        "width": photo.get("width"),
        "height": photo.get("height"),
        "selected_url": selected_url,
        "unsplash_url": (photo.get("links") or {}).get("html"),
        "download_location": (photo.get("links") or {}).get("download_location"),
        "photographer_name": user.get("name") if isinstance(user, dict) else None,
        "photographer_username": user.get("username") if isinstance(user, dict) else None,
        "photographer_profile": user_links.get("html") if isinstance(user_links, dict) else None,
        "local_path": str(local_path) if local_path else None,
        "downloaded_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }


def attribution_line(photo: Dict[str, object]) -> str:
    user = photo.get("user") or {}
    links = photo.get("links") or {}
    photographer_name = user.get("name") or "Unknown photographer"
    username = user.get("username") or "unknown"
    html_url = links.get("html") or ""
    return f'{photographer_name} (@{username}) - {html_url}'


def write_sidecars(output_dir: Path, manifest: Iterable[Dict[str, object]], photos: List[Dict[str, object]]) -> None:
    manifest_path = output_dir / "unsplash-manifest.json"
    attribution_path = output_dir / "unsplash-attribution.txt"
    manifest_path.write_text(
        json.dumps(list(manifest), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    attribution_path.write_text(
        "\n".join(attribution_line(photo) for photo in photos) + "\n",
        encoding="utf-8",
    )


def print_dry_run(photos: List[Dict[str, object]], args: argparse.Namespace) -> None:
    for index, photo in enumerate(photos, start=1):
        user = photo.get("user") or {}
        print(
            json.dumps(
                {
                    "index": index,
                    "id": photo.get("id"),
                    "description": photo.get("description") or photo.get("alt_description"),
                    "photographer": user.get("name") if isinstance(user, dict) else None,
                    "username": user.get("username") if isinstance(user, dict) else None,
                    "selected_url": make_download_url(photo, args),
                    "unsplash_url": (photo.get("links") or {}).get("html"),
                },
                ensure_ascii=False,
            )
        )


def main() -> int:
    args = parse_args()
    access_key = resolve_access_key(args)
    output_dir = Path(args.output_dir).expanduser().resolve()

    photos = (
        fetch_search_results(args, access_key)
        if args.query
        else fetch_photo(args, access_key)
    )
    if not photos:
        raise SystemExit("No matching photos found.")

    if args.dry_run:
        print_dry_run(photos, args)
        return 0

    output_dir.mkdir(parents=True, exist_ok=True)
    manifest_entries: List[Dict[str, object]] = []

    for index, photo in enumerate(photos, start=1):
        trigger_download_tracking(photo, args, access_key)
        selected_url = make_download_url(photo, args)
        content, content_type = download_binary(selected_url, access_key, args.timeout)
        filename = choose_filename(photo, index, content_type)
        output_path = output_dir / filename
        output_path.write_bytes(content)
        manifest_entries.append(
            photo_manifest_entry(photo, output_path, selected_url, args.query)
        )
        print(f"Saved {output_path}")

    if not args.skip_sidecar_files:
        write_sidecars(output_dir, manifest_entries, photos)
        print(f"Saved {output_dir / 'unsplash-manifest.json'}")
        print(f"Saved {output_dir / 'unsplash-attribution.txt'}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
