#!/usr/bin/env python3
"""Seedream 5.0 Pro image generation via the Volcengine Ark API.

Default model: doubao-seedream-5-0-pro-260628 (Ark images/generations endpoint).
Supports text-to-image and reference-image (i2i) generation for character
consistency. Local reference images are inlined as base64 data URLs.

Credentials, resolved in order:
1. --api-key flag
2. ARK_API_KEY environment variable
3. .env file at the skill root (ARK_API_KEY=...)
"""

import argparse
import base64
import json
import os
import sys
import time
import urllib.error
import urllib.request

ARK_ENDPOINT = "https://ark.cn-beijing.volces.com/api/v3/images/generations"
DEFAULT_MODEL = "doubao-seedream-5-0-pro-260628"
SKILL_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load_api_key(cli_key: str) -> str:
    if cli_key:
        return cli_key
    key = os.environ.get("ARK_API_KEY", "").strip()
    if key:
        return key
    env_path = os.path.join(SKILL_ROOT, ".env")
    if os.path.exists(env_path):
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line.startswith("ARK_API_KEY="):
                    return line.split("=", 1)[1].strip().strip('"').strip("'")
    sys.exit(
        "错误：未找到 ARK_API_KEY。请设置环境变量、传入 --api-key，"
        "或在 skill 根目录 .env 中配置 ARK_API_KEY=...\n"
        "获取地址: https://console.volcengine.com/ark/region:ark+cn-beijing/apikey"
    )


def to_reference(src: str) -> str:
    """Turn a local path into a base64 data URL; pass URLs through."""
    if src.startswith("http://") or src.startswith("https://"):
        return src
    if not os.path.exists(src):
        sys.exit(f"错误：参考图不存在: {src}")
    with open(src, "rb") as f:
        b64 = base64.b64encode(f.read()).decode()
    ext = os.path.splitext(src)[1].lstrip(".").lower() or "jpeg"
    if ext == "jpg":
        ext = "jpeg"
    return f"data:image/{ext};base64,{b64}"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prompt", required=True, help="生成提示词（要出现在图中的文字用引号包住）")
    parser.add_argument("--model", default=DEFAULT_MODEL, help=f"模型 ID，默认 {DEFAULT_MODEL}")
    parser.add_argument("--size", default="2K",
                        help="尺寸：1K / 2K / 4K 或显式 宽x高（如 2048x2048），默认 2K")
    parser.add_argument("--image", nargs="*", default=[], help="参考图（垫图）路径或 URL，最多 10 张")
    parser.add_argument("--sequential", action="store_true",
                        help="组图模式（sequential_image_generation=auto），适合多张成组输出")
    parser.add_argument("--max-images", type=int, default=None, help="组图模式下的最大张数")
    parser.add_argument("--seed", type=int, default=None, help="随机种子")
    parser.add_argument("--watermark", action="store_true", help="添加 AI 生成水印")
    parser.add_argument("--api-key", default="", help="ARK_API_KEY（可选，默认读环境变量/.env）")
    parser.add_argument("--output-dir", default=os.path.join(os.getcwd(), "output", "seedream5"))
    parser.add_argument("--prefix", default="seedream5", help="输出文件名前缀")
    args = parser.parse_args()

    api_key = load_api_key(args.api_key)

    body = {
        "model": args.model,
        "prompt": args.prompt,
        "response_format": "url",
        "size": args.size,
        "stream": False,
        "watermark": args.watermark,
    }
    if args.image:
        body["image"] = [to_reference(src) for src in args.image]
    if args.sequential:
        body["sequential_image_generation"] = "auto"
        if args.max_images:
            body["sequential_image_generation_options"] = {"max_images": args.max_images}
    if args.seed is not None:
        body["seed"] = args.seed

    os.makedirs(args.output_dir, exist_ok=True)
    started = time.time()
    req = urllib.request.Request(
        ARK_ENDPOINT,
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"},
    )
    try:
        with urllib.request.urlopen(req, timeout=600) as resp:
            result = json.load(resp)
    except urllib.error.HTTPError as e:
        print(f"HTTP {e.code}", file=sys.stderr)
        print(e.read().decode("utf-8", "replace")[:3000], file=sys.stderr)
        sys.exit(1)

    if "data" not in result:
        print(json.dumps(result, ensure_ascii=False, indent=2)[:3000], file=sys.stderr)
        sys.exit(1)

    saved = []
    for i, item in enumerate(result["data"]):
        out_path = os.path.join(args.output_dir, f"{args.prefix}-{i + 1:02d}.jpg")
        if item.get("url"):
            urllib.request.urlretrieve(item["url"], out_path)
        elif item.get("b64_json"):
            with open(out_path, "wb") as f:
                f.write(base64.b64decode(item["b64_json"]))
        else:
            print(f"警告：第 {i + 1} 张无 url/b64_json，跳过", file=sys.stderr)
            continue
        saved.append(out_path)
        print(f"已保存 {out_path}  size={item.get('size', '?')}  "
              f"{os.path.getsize(out_path)} bytes  耗时 {time.time() - started:.0f}s")

    sidecar = {
        "model": args.model,
        "prompt": args.prompt,
        "reference_images": args.image,
        "size": args.size,
        "seed": args.seed,
        "sequential": args.sequential,
        "saved_files": saved,
        "usage": result.get("usage"),
        "raw_response": {k: v for k, v in result.items() if k != "data"},
    }
    sidecar_path = os.path.join(args.output_dir, f"{args.prefix}-result.json")
    with open(sidecar_path, "w", encoding="utf-8") as f:
        json.dump(sidecar, f, ensure_ascii=False, indent=2)
    print(f"已保存 {sidecar_path}")


if __name__ == "__main__":
    main()
