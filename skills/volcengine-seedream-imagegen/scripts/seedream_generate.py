#!/usr/bin/env python3
"""Generate images with Volcengine Seedream and save the result locally."""

from __future__ import annotations

import argparse
import base64
import hashlib
import hmac
import json
import mimetypes
import os
import sys
import time
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse
from urllib.request import Request, urlopen

DEFAULT_HOST = "visual.volcengineapi.com"
DEFAULT_SCHEME = "https"
DEFAULT_REGION = "cn-north-1"
DEFAULT_SERVICE = "cv"
DEFAULT_VERSION = "2022-08-31"
DEFAULT_REQ_KEY = "high_aes_general_v30l_zt2i"
DEFAULT_WIDTH = 1328
DEFAULT_HEIGHT = 1328
DEFAULT_SCALE = 2.5
DEFAULT_POLL_INTERVAL = 2.0
DEFAULT_TIMEOUT = 180.0
DEFAULT_CONTENT_TYPE = "application/json"
SUBMIT_ACTION = "CVSync2AsyncSubmitTask"
RESULT_ACTION = "CVSync2AsyncGetResult"
ENV_ALIASES = {
    "access_key": ("VOLCENGINE_ACCESS_KEY", "VOLCENGINE_ACCESS_KEY_ID"),
    "secret_key": ("VOLCENGINE_SECRET_KEY", "VOLCENGINE_SECRET_ACCESS_KEY"),
    "session_token": ("VOLCENGINE_SESSION_TOKEN", "VOLCENGINE_SECURITY_TOKEN"),
}
WATERMARK_POSITION_MAP = {
    "lower-right": 0,
    "lower-left": 1,
    "upper-left": 2,
    "upper-right": 3,
}
WATERMARK_LANGUAGE_MAP = {"zh": 0, "en": 1}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Submit or query Volcengine Seedream image generation tasks."
    )
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--prompt", help="Prompt used to generate an image.")
    source.add_argument("--task-id", help="Query an existing Seedream task id.")

    parser.add_argument(
        "--output-dir",
        default=".",
        help="Directory used to save images and seedream-result.json.",
    )
    parser.add_argument(
        "--filename-prefix",
        default="seedream",
        help="Filename prefix for saved images. Defaults to seedream.",
    )
    parser.add_argument("--width", type=int, default=DEFAULT_WIDTH, help="Output width.")
    parser.add_argument(
        "--height", type=int, default=DEFAULT_HEIGHT, help="Output height."
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=-1,
        help="Random seed. Use -1 for a random seed.",
    )
    parser.add_argument(
        "--scale",
        type=float,
        default=DEFAULT_SCALE,
        help="Prompt influence scale. Defaults to 2.5.",
    )
    parser.add_argument(
        "--use-pre-llm",
        action="store_true",
        help="Enable prompt expansion for short or rough prompts.",
    )
    parser.add_argument(
        "--req-key",
        default=DEFAULT_REQ_KEY,
        help="Model req_key. Defaults to high_aes_general_v30l_zt2i.",
    )
    parser.add_argument(
        "--result-mode",
        choices=["url", "base64"],
        default="url",
        help="Ask the query API to return image URLs or base64 payloads.",
    )
    parser.add_argument(
        "--submit-only",
        action="store_true",
        help="Submit a new task and stop after printing the task id.",
    )
    parser.add_argument(
        "--poll-interval",
        type=float,
        default=DEFAULT_POLL_INTERVAL,
        help="Seconds between polling attempts. Defaults to 2.",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=DEFAULT_TIMEOUT,
        help="Overall timeout for polling in seconds. Defaults to 180.",
    )
    parser.add_argument(
        "--no-download",
        action="store_true",
        help="Do not download image files; only write the JSON sidecar.",
    )
    parser.add_argument(
        "--watermark-text",
        help="Visible watermark text. When set, logo_info.add_logo becomes true.",
    )
    parser.add_argument(
        "--watermark-position",
        choices=sorted(WATERMARK_POSITION_MAP),
        default="lower-right",
        help="Visible watermark position.",
    )
    parser.add_argument(
        "--watermark-language",
        choices=sorted(WATERMARK_LANGUAGE_MAP),
        default="zh",
        help="Visible watermark language.",
    )
    parser.add_argument(
        "--watermark-opacity",
        type=float,
        default=1.0,
        help="Visible watermark opacity in the range 0-1.",
    )
    parser.add_argument("--producer-id", help="Optional AIGC producer_id field.")
    parser.add_argument(
        "--content-producer", help="Optional AIGC content_producer field."
    )
    parser.add_argument(
        "--content-propagator", help="Optional AIGC content_propagator field."
    )
    parser.add_argument("--propagate-id", help="Optional AIGC propagate_id field.")
    parser.add_argument(
        "--access-key",
        help="Volcengine access key override. Otherwise read from env or .env.",
    )
    parser.add_argument(
        "--secret-key",
        help="Volcengine secret key override. Otherwise read from env or .env.",
    )
    parser.add_argument(
        "--session-token",
        help="Optional STS session token override. Otherwise read from env or .env.",
    )
    parser.add_argument(
        "--host",
        default=DEFAULT_HOST,
        help="API host. Defaults to visual.volcengineapi.com.",
    )
    parser.add_argument(
        "--scheme",
        choices=["https", "http"],
        default=DEFAULT_SCHEME,
        help=argparse.SUPPRESS,
    )

    args = parser.parse_args()

    if args.width < 512 or args.width > 2048:
        parser.error("--width must be between 512 and 2048")
    if args.height < 512 or args.height > 2048:
        parser.error("--height must be between 512 and 2048")
    if not 1 <= args.scale <= 10:
        parser.error("--scale must be between 1 and 10")
    if not 0 <= args.watermark_opacity <= 1:
        parser.error("--watermark-opacity must be between 0 and 1")
    if args.task_id and args.submit_only:
        parser.error("--submit-only can only be used together with --prompt")

    return args


def skill_root() -> Path:
    return Path(__file__).resolve().parent.parent


def load_dotenv(path: Path) -> Dict[str, str]:
    values: Dict[str, str] = {}
    if not path.exists():
        return values
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].strip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("'").strip('"')
        if key:
            values[key] = value
    return values


def resolve_credential(
    cli_value: Optional[str], env_names: Iterable[str], dotenv_values: Dict[str, str]
) -> Optional[str]:
    if cli_value:
        return cli_value
    for name in env_names:
        if os.environ.get(name):
            return os.environ[name]
    for name in env_names:
        if dotenv_values.get(name):
            return dotenv_values[name]
    return None


def resolve_credentials(args: argparse.Namespace) -> Tuple[str, str, Optional[str]]:
    dotenv_values = load_dotenv(skill_root() / ".env")
    access_key = resolve_credential(
        args.access_key, ENV_ALIASES["access_key"], dotenv_values
    )
    secret_key = resolve_credential(
        args.secret_key, ENV_ALIASES["secret_key"], dotenv_values
    )
    session_token = resolve_credential(
        args.session_token, ENV_ALIASES["session_token"], dotenv_values
    )
    if not access_key or not secret_key:
        raise SystemExit(
            "Missing Volcengine credentials. Set VOLCENGINE_ACCESS_KEY and "
            "VOLCENGINE_SECRET_KEY, or create <skill-path>/.env."
        )
    return access_key, secret_key, session_token


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def hmac_sha256(key: bytes, message: str) -> bytes:
    return hmac.new(key, message.encode("utf-8"), hashlib.sha256).digest()


def utc_timestamp() -> str:
    return time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())


def encode_query(query: Dict[str, str]) -> str:
    items = sorted((str(k), str(v)) for k, v in query.items())
    return urlencode(items)


def canonical_header_items(headers: Dict[str, str]) -> List[Tuple[str, str]]:
    items = []
    for key, value in headers.items():
        items.append((key.lower().strip(), " ".join(value.strip().split())))
    items.sort(key=lambda item: item[0])
    return items


def sign_headers(
    method: str,
    path: str,
    query: Dict[str, str],
    body: bytes,
    host: str,
    region: str,
    service: str,
    access_key: str,
    secret_key: str,
    content_type: str = DEFAULT_CONTENT_TYPE,
    session_token: Optional[str] = None,
) -> Dict[str, str]:
    x_date = utc_timestamp()
    x_content_sha256 = sha256_hex(body)
    headers = {
        "Content-Type": content_type,
        "Host": host,
        "X-Content-Sha256": x_content_sha256,
        "X-Date": x_date,
    }
    if session_token:
        headers["X-Security-Token"] = session_token

    canonical_items = canonical_header_items(headers)
    canonical_headers = "".join(f"{key}:{value}\n" for key, value in canonical_items)
    signed_headers = ";".join(key for key, _ in canonical_items)
    canonical_request = "\n".join(
        [
            method.upper(),
            path,
            encode_query(query),
            canonical_headers,
            signed_headers,
            x_content_sha256,
        ]
    )
    short_date = x_date[:8]
    credential_scope = f"{short_date}/{region}/{service}/request"
    string_to_sign = "\n".join(
        [
            "HMAC-SHA256",
            x_date,
            credential_scope,
            sha256_hex(canonical_request.encode("utf-8")),
        ]
    )
    k_date = hmac_sha256(secret_key.encode("utf-8"), short_date)
    k_region = hmac.new(k_date, region.encode("utf-8"), hashlib.sha256).digest()
    k_service = hmac.new(k_region, service.encode("utf-8"), hashlib.sha256).digest()
    k_signing = hmac.new(k_service, b"request", hashlib.sha256).digest()
    signature = hmac.new(
        k_signing, string_to_sign.encode("utf-8"), hashlib.sha256
    ).hexdigest()
    headers["Authorization"] = (
        "HMAC-SHA256 "
        f"Credential={access_key}/{credential_scope}, "
        f"SignedHeaders={signed_headers}, "
        f"Signature={signature}"
    )
    return headers


def make_url(scheme: str, host: str, path: str, query: Dict[str, str]) -> str:
    base = f"{scheme}://{host}{path}"
    parsed = urlparse(base)
    merged_query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    merged_query.update(query)
    return urlunparse(parsed._replace(query=encode_query(merged_query)))


def request_json(
    *,
    method: str,
    host: str,
    scheme: str,
    path: str,
    query: Dict[str, str],
    body_obj: Dict[str, object],
    region: str,
    service: str,
    access_key: str,
    secret_key: str,
    session_token: Optional[str],
    timeout: float,
) -> Dict[str, object]:
    body = json.dumps(body_obj, ensure_ascii=False, separators=(",", ":")).encode(
        "utf-8"
    )
    headers = sign_headers(
        method=method,
        path=path,
        query=query,
        body=body,
        host=host,
        region=region,
        service=service,
        access_key=access_key,
        secret_key=secret_key,
        session_token=session_token,
    )
    url = make_url(scheme, host, path, query)
    request = Request(url, data=body, method=method.upper(), headers=headers)
    try:
        with urlopen(request, timeout=timeout) as response:
            return json.load(response)
    except HTTPError as exc:
        response_body = exc.read().decode("utf-8", errors="replace")
        raise SystemExit(
            f"Volcengine API error {exc.code}: {response_body or exc.reason}"
        ) from exc
    except URLError as exc:
        raise SystemExit(f"Volcengine API request failed: {exc.reason}") from exc


def build_submit_body(args: argparse.Namespace) -> Dict[str, object]:
    return {
        "req_key": args.req_key,
        "prompt": args.prompt,
        "use_pre_llm": bool(args.use_pre_llm),
        "seed": int(args.seed),
        "scale": float(args.scale),
        "width": int(args.width),
        "height": int(args.height),
    }


def build_req_json(args: argparse.Namespace) -> Optional[str]:
    payload: Dict[str, object] = {"return_url": args.result_mode == "url"}

    if args.watermark_text:
        payload["logo_info"] = {
            "add_logo": True,
            "position": WATERMARK_POSITION_MAP[args.watermark_position],
            "language": WATERMARK_LANGUAGE_MAP[args.watermark_language],
            "opacity": args.watermark_opacity,
            "logo_text_content": args.watermark_text,
        }

    if any(
        value
        for value in (
            args.producer_id,
            args.content_producer,
            args.content_propagator,
            args.propagate_id,
        )
    ):
        if not args.producer_id:
            raise SystemExit("--producer-id is required when setting aigc_meta fields.")
        payload["aigc_meta"] = {
            "producer_id": args.producer_id,
            "content_producer": args.content_producer,
            "content_propagator": args.content_propagator,
            "propagate_id": args.propagate_id,
        }

    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def build_result_body(task_id: str, args: argparse.Namespace) -> Dict[str, object]:
    body: Dict[str, object] = {"req_key": args.req_key, "task_id": task_id}
    req_json = build_req_json(args)
    if req_json:
        body["req_json"] = req_json
    return body


def assert_success(payload: Dict[str, object], context: str) -> None:
    code = payload.get("code")
    if code != 10000:
        raise SystemExit(
            f"{context} failed: code={code}, message={payload.get('message')}, "
            f"request_id={payload.get('request_id')}"
        )


def submit_task(
    args: argparse.Namespace,
    access_key: str,
    secret_key: str,
    session_token: Optional[str],
) -> Dict[str, object]:
    payload = request_json(
        method="POST",
        host=args.host,
        scheme=args.scheme,
        path="/",
        query={"Action": SUBMIT_ACTION, "Version": DEFAULT_VERSION},
        body_obj=build_submit_body(args),
        region=DEFAULT_REGION,
        service=DEFAULT_SERVICE,
        access_key=access_key,
        secret_key=secret_key,
        session_token=session_token,
        timeout=args.timeout,
    )
    assert_success(payload, "Task submission")
    return payload


def query_task(
    task_id: str,
    args: argparse.Namespace,
    access_key: str,
    secret_key: str,
    session_token: Optional[str],
) -> Dict[str, object]:
    payload = request_json(
        method="POST",
        host=args.host,
        scheme=args.scheme,
        path="/",
        query={"Action": RESULT_ACTION, "Version": DEFAULT_VERSION},
        body_obj=build_result_body(task_id, args),
        region=DEFAULT_REGION,
        service=DEFAULT_SERVICE,
        access_key=access_key,
        secret_key=secret_key,
        session_token=session_token,
        timeout=args.timeout,
    )
    assert_success(payload, "Task query")
    return payload


def poll_until_done(
    task_id: str,
    args: argparse.Namespace,
    access_key: str,
    secret_key: str,
    session_token: Optional[str],
) -> Dict[str, object]:
    deadline = time.time() + args.timeout
    last_payload: Optional[Dict[str, object]] = None
    while time.time() <= deadline:
        payload = query_task(task_id, args, access_key, secret_key, session_token)
        last_payload = payload
        data = payload.get("data") or {}
        status = data.get("status")
        print(f"Task {task_id} status: {status}")
        if status == "done":
            return payload
        if status in {"not_found", "expired"}:
            raise SystemExit(
                f"Task {task_id} returned terminal status {status}. "
                f"request_id={payload.get('request_id')}"
            )
        time.sleep(args.poll_interval)
    raise SystemExit(
        f"Timed out while waiting for task {task_id}. "
        f"Last payload: {json.dumps(last_payload, ensure_ascii=False)}"
    )


def guess_extension_from_response(content_type: str, url: str) -> str:
    if content_type:
        content_type = content_type.split(";", 1)[0].strip().lower()
        guess = mimetypes.guess_extension(content_type)
        if guess == ".jpe":
            return ".jpg"
        if guess:
            return guess
    parsed = urlparse(url)
    suffix = Path(parsed.path).suffix
    return suffix or ".jpg"


def download_file(url: str, timeout: float) -> Tuple[bytes, str]:
    request = Request(url, headers={"User-Agent": "codex-seedream-skill/1.0"})
    try:
        with urlopen(request, timeout=timeout) as response:
            return response.read(), response.headers.get("Content-Type", "")
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise SystemExit(f"Image download failed: HTTP {exc.code} {body or exc.reason}")
    except URLError as exc:
        raise SystemExit(f"Image download failed: {exc.reason}")


def save_url_results(
    urls: List[str], output_dir: Path, filename_prefix: str, timeout: float
) -> List[str]:
    saved: List[str] = []
    for index, url in enumerate(urls, start=1):
        content, content_type = download_file(url, timeout)
        ext = guess_extension_from_response(content_type, url)
        path = output_dir / f"{filename_prefix}-{index:02d}{ext}"
        path.write_bytes(content)
        saved.append(str(path))
        print(f"Saved {path}")
    return saved


def save_base64_results(
    items: List[str], output_dir: Path, filename_prefix: str
) -> List[str]:
    saved: List[str] = []
    for index, item in enumerate(items, start=1):
        content = base64.b64decode(item)
        path = output_dir / f"{filename_prefix}-{index:02d}.jpg"
        path.write_bytes(content)
        saved.append(str(path))
        print(f"Saved {path}")
    return saved


def write_result_sidecar(output_dir: Path, payload: Dict[str, object]) -> Path:
    result_path = output_dir / "seedream-result.json"
    result_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"Saved {result_path}")
    return result_path


def build_manifest(
    *,
    args: argparse.Namespace,
    submit_payload: Optional[Dict[str, object]],
    result_payload: Dict[str, object],
    saved_files: List[str],
) -> Dict[str, object]:
    data = result_payload.get("data") or {}
    return {
        "skill": "volcengine-seedream-imagegen",
        "req_key": args.req_key,
        "prompt": args.prompt,
        "task_id": (data.get("task_id") or None)
        or (((submit_payload or {}).get("data") or {}).get("task_id")),
        "submit_request_id": (submit_payload or {}).get("request_id"),
        "result_request_id": result_payload.get("request_id"),
        "status": data.get("status"),
        "result_mode": args.result_mode,
        "parameters": {
            "width": args.width,
            "height": args.height,
            "seed": args.seed,
            "scale": args.scale,
            "use_pre_llm": args.use_pre_llm,
        },
        "image_urls": data.get("image_urls"),
        "saved_files": saved_files,
        "raw_result": result_payload,
    }


def main() -> int:
    args = parse_args()
    access_key, secret_key, session_token = resolve_credentials(args)
    output_dir = Path(args.output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    submit_payload: Optional[Dict[str, object]] = None

    if args.prompt:
        submit_payload = submit_task(args, access_key, secret_key, session_token)
        task_id = ((submit_payload.get("data") or {}).get("task_id")) or ""
        if not task_id:
            raise SystemExit(
                f"Task submission succeeded but no task_id was returned: {submit_payload}"
            )
        print(f"Submitted task_id: {task_id}")
        if args.submit_only:
            manifest = {
                "skill": "volcengine-seedream-imagegen",
                "prompt": args.prompt,
                "task_id": task_id,
                "submit_request_id": submit_payload.get("request_id"),
                "submit_response": submit_payload,
            }
            write_result_sidecar(output_dir, manifest)
            return 0
    else:
        task_id = args.task_id

    result_payload = poll_until_done(
        task_id, args, access_key, secret_key, session_token
    )
    data = result_payload.get("data") or {}
    saved_files: List[str] = []

    if not args.no_download:
        if args.result_mode == "url":
            urls = data.get("image_urls") or []
            if not isinstance(urls, list):
                raise SystemExit("Expected image_urls to be a list.")
            saved_files = save_url_results(
                [str(url) for url in urls], output_dir, args.filename_prefix, args.timeout
            )
        else:
            binary_items = data.get("binary_data_base64") or []
            if not isinstance(binary_items, list):
                raise SystemExit("Expected binary_data_base64 to be a list.")
            saved_files = save_base64_results(
                [str(item) for item in binary_items], output_dir, args.filename_prefix
            )

    manifest = build_manifest(
        args=args,
        submit_payload=submit_payload,
        result_payload=result_payload,
        saved_files=saved_files,
    )
    write_result_sidecar(output_dir, manifest)
    return 0


if __name__ == "__main__":
    sys.exit(main())
