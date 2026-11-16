#!/usr/bin/env python3
"""いらすとや (irasutoya.com) 逆向接口 CLI.

站点是 Blogger 托管,所以不用抓 HTML,直接吃 GData JSON feed:
  /feeds/posts/default?alt=json&q=KEYWORD&max-results=N&start-index=M
  /feeds/posts/default/-/LABEL?alt=json
  /feeds/posts/default/POST_ID?alt=json
图片走 blogger.googleusercontent.com 的路径式尺寸参数,可任意改写。

只依赖标准库。
"""

from __future__ import annotations

import argparse
import gzip
import html as htmllib
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

BASE = "https://www.irasutoya.com"
FEED = BASE + "/feeds/posts/default"
UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)
TIMEOUT = 30
PAGE_MAX = 150  # Blogger 单页上限 500,但 150 更稳

IMG_RE = re.compile(r"https://blogger\.googleusercontent\.com/img/[^\"'\s<>]+?\.(?:png|jpe?g|gif|webp)")
SIZE_SEG_RE = re.compile(r"^[swh]\d")
JUNK = ("thumbnail", "banner", "sidebar", "body_background", "noimage", "logo", "profile")


# ---------------------------------------------------------------- transport
def http_get(url: str, tries: int = 3) -> bytes:
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(
                url,
                headers={"User-Agent": UA, "Accept-Encoding": "gzip", "Accept": "*/*"},
            )
            with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
                raw = r.read()
                if r.headers.get("Content-Encoding") == "gzip":
                    raw = gzip.decompress(raw)
                return raw
        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
            last = e
            if i < tries - 1:
                time.sleep(1.2 * (i + 1))
    raise SystemExit(f"[http] {url}\n  -> {last}")


def feed_json(path: str = "", **params) -> dict:
    params.setdefault("alt", "json")
    qs = urllib.parse.urlencode(params, safe="")
    return json.loads(http_get(f"{FEED}{path}?{qs}").decode("utf-8"))


def t(node, *keys, default=None):
    """安全取 Blogger 的 {'$t': ...} 结构。"""
    cur = node
    for k in keys:
        if not isinstance(cur, dict) or k not in cur:
            return default
        cur = cur[k]
    if isinstance(cur, dict):
        return cur.get("$t", default)
    return cur if cur is not None else default


# ---------------------------------------------------------------- parsing
def size_of(url: str) -> int:
    seg = url.rsplit("/", 2)[-2]
    m = re.match(r"^[swh](\d+)", seg)
    return int(m.group(1)) if m else 0


def resize(url: str, size: str) -> str:
    """把 /s450/ 这类尺寸段换成目标尺寸。size 例:s1600 / w1200 / s400-c"""
    parts = url.rsplit("/", 2)
    if len(parts) != 3:
        return url
    if SIZE_SEG_RE.match(parts[1]):
        parts[1] = size
        return "/".join(parts)
    return url


def basename_of(url: str) -> str:
    return urllib.parse.unquote(url.rsplit("/", 1)[-1])


def extract_images(content_html: str) -> list[dict]:
    """同一张图在正文里出现两次(href 大图 / src 缩略),按文件名去重保留最大尺寸。"""
    seen: dict[str, dict] = {}
    order: list[str] = []
    for url in IMG_RE.findall(content_html):
        name = basename_of(url)
        low = name.lower()
        if any(low.startswith(j) or j in low.split(".")[0] for j in JUNK):
            continue
        prev = seen.get(name)
        if prev is None:
            seen[name] = {"file": name, "url": url, "size": size_of(url)}
            order.append(name)
        elif size_of(url) > prev["size"]:
            prev["url"], prev["size"] = url, size_of(url)
    return [seen[n] for n in order]


def extract_desc(content_html: str) -> str:
    txt = htmllib.unescape(re.sub(r"<[^>]+>", "\n", content_html))
    lines = [ln.strip() for ln in txt.split("\n") if ln.strip()]
    cand = [ln for ln in lines if len(ln) >= 8]
    return cand[-1] if cand else ""


def parse_entry(e: dict) -> dict:
    content = t(e, "content") or t(e, "summary") or ""
    url = ""
    for link in e.get("link", []):
        if link.get("rel") == "alternate":
            url = link.get("href", "")
    post_id = (t(e, "id") or "").rsplit("/", 1)[-1]
    return {
        "id": post_id,
        "title": t(e, "title"),
        "url": url,
        "published": (t(e, "published") or "")[:10],
        "labels": [c["term"] for c in e.get("category", [])],
        "desc": extract_desc(content),
        "images": extract_images(content),
    }


def collect(path: str = "", q: str | None = None, limit: int = 20, all_pages: bool = False) -> list[dict]:
    out: list[dict] = []
    start = 1
    while True:
        want = PAGE_MAX if all_pages or limit > PAGE_MAX else max(limit, 1)
        params = {"max-results": want, "start-index": start}
        if q:
            params["q"] = q
        feed = feed_json(path, **params).get("feed", {})
        entries = feed.get("entry", [])
        if not entries:
            break
        for e in entries:
            out.append(parse_entry(e))
            if not all_pages and len(out) >= limit:
                return out
        if len(entries) < want:
            break
        start += len(entries)
        if start > 3000:
            break
    return out


# ---------------------------------------------------------------- output
def fmt_row(i: int, it: dict, size: str, show_img: bool) -> str:
    head = f"{i:>2}. {it['title']}"
    meta = f"    {it['published']}  {' / '.join(it['labels'][:4])}"
    lines = [head, meta, f"    {it['url']}"]
    if show_img:
        for img in it["images"]:
            lines.append(f"    - {resize(img['url'], size)}")
    return "\n".join(lines)


def save_images(items: list[dict], out_dir: str, size: str, per_post: int = 0, flat: bool = False) -> int:
    os.makedirs(out_dir, exist_ok=True)
    n = 0
    for it in items:
        imgs = it["images"][: per_post or None]
        if not imgs:
            continue
        sub = out_dir if flat else os.path.join(out_dir, re.sub(r"[\\/:*?\"<>|]", "_", it["title"])[:80])
        os.makedirs(sub, exist_ok=True)
        for img in imgs:
            path = os.path.join(sub, img["file"])
            if os.path.exists(path) and os.path.getsize(path) > 0:
                print(f"  skip  {path}")
                continue
            with open(path, "wb") as f:
                f.write(http_get(resize(img["url"], size)))
            print(f"  ok    {path}  ({os.path.getsize(path)//1024}KB)")
            n += 1
    return n


def emit(items: list[dict], args, dump=None) -> None:
    if args.json:
        payload = dump if dump is not None else items
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return
    if not items:
        print("(0 条)")
        return
    for i, it in enumerate(items, 1):
        print(fmt_row(i, it, args.size, not args.no_images))
    print(f"\n共 {len(items)} 条")


# ---------------------------------------------------------------- commands
def cmd_search(args) -> None:
    q = " ".join(args.query)
    items = collect(q=q, limit=args.n, all_pages=args.all)
    emit(items, args)
    if args.download:
        if not items:
            return
        k = args.dl_posts or len(items)
        got = save_images(items[:k], args.download, args.size, args.per_post, args.flat)
        print(f"\n下载 {got} 张 -> {args.download}")


def cmd_label(args) -> None:
    label = urllib.parse.quote(args.label, safe="")
    items = collect(f"/-/{label}", limit=args.n, all_pages=args.all)
    emit(items, args)
    if args.download:
        if not items:
            return
        k = args.dl_posts or len(items)
        got = save_images(items[:k], args.download, args.size, args.per_post, args.flat)
        print(f"\n下载 {got} 张 -> {args.download}")


def cmd_labels(args) -> None:
    feed = feed_json("", **{"max-results": 1}).get("feed", {})
    cats = sorted({c["term"] for c in feed.get("category", [])})
    if args.grep:
        cats = [c for c in cats if args.grep.lower() in c.lower()]
    if args.json:
        print(json.dumps(cats, ensure_ascii=False, indent=2))
        return
    print(f"共 {len(cats)} 个官方标签:")
    for c in cats:
        print("  " + c)


def cmd_post(args) -> None:
    target = args.target.strip()
    post_id = target if target.isdigit() else None
    if not post_id:
        page = http_get(target).decode("utf-8", "ignore")
        m = re.search(r"'postId':\s*'?(\d{6,})", page)
        if not m:
            raise SystemExit(f"[post] 解析不到 postId: {target}")
        post_id = m.group(1)
    entry = feed_json(f"/{post_id}").get("entry")
    if not entry:
        raise SystemExit(f"[post] 空结果: {post_id}")
    it = parse_entry(entry)
    if args.json:
        print(json.dumps(it, ensure_ascii=False, indent=2))
    else:
        print(f"{it['title']}\n{it['url']}\n{it['published']}  {' / '.join(it['labels'])}\n{it['desc']}\n")
        for img in it["images"]:
            print("  " + resize(img["url"], args.size))
    if args.download:
        got = save_images([it], args.download, args.size, args.per_post, args.flat)
        print(f"\n下载 {got} 张 -> {args.download}")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="irasutoya", description="いらすとや 素材检索/下载")
    sub = p.add_subparsers(dest="cmd", required=True)

    def common(sp):
        sp.add_argument("--size", default="s1600", help="图片尺寸段:s1600 / w1200 / s400-c(方形裁切)")
        sp.add_argument("--json", action="store_true", help="输出 JSON")
        sp.add_argument("--no-images", action="store_true", help="列表不打印图片 URL")
        sp.add_argument("--download", metavar="DIR", help="同时下载到目录")
        sp.add_argument("--per-post", type=int, default=0, help="每个文章最多下载几张,0=全部")
        sp.add_argument("--dl-posts", type=int, default=0, help="下载时只看前 N 篇,0=全部")
        sp.add_argument("--flat", action="store_true", help="下载不按标题建子目录")

    s = sub.add_parser("search", help="全文检索(日文关键词)")
    s.add_argument("query", nargs="+")
    s.add_argument("-n", type=int, default=20)
    s.add_argument("--all", action="store_true", help="翻完所有页")
    common(s)
    s.set_defaults(func=cmd_search)

    lab = sub.add_parser("label", help="按官方标签列举")
    lab.add_argument("label")
    lab.add_argument("-n", type=int, default=20)
    lab.add_argument("--all", action="store_true")
    common(lab)
    lab.set_defaults(func=cmd_label)

    labs = sub.add_parser("labels", help="列出全部官方标签")
    labs.add_argument("--grep", default="")
    labs.add_argument("--json", action="store_true")
    labs.set_defaults(func=cmd_labels, size="s1600", no_images=True)

    po = sub.add_parser("post", help="查看单篇文章(URL 或 postId)")
    po.add_argument("target")
    common(po)
    po.set_defaults(func=cmd_post)

    return p


def main() -> None:
    args = build_parser().parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
