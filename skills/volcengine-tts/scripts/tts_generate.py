#!/usr/bin/env python3
"""Volcengine Doubao TTS — text-to-speech via HTTP Chunked streaming API."""

from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import uuid
from pathlib import Path
from typing import Optional

API_URL = "https://openspeech.bytedance.com/api/v3/tts/unidirectional"
DEFAULT_RESOURCE_ID = "seed-tts-1.0"
DEFAULT_SPEAKER = "zh_female_shuangkuaisisi_moon_bigtts"
DEFAULT_FORMAT = "mp3"
DEFAULT_SAMPLE_RATE = 24000
DEFAULT_SPEED = 0
DEFAULT_VOLUME = 0
DEFAULT_BIT_RATE = 0
ENV_KEY_NAME = "VOLCENGINE_TTS_API_KEY"


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Volcengine Doubao TTS generator")
    input_group = p.add_mutually_exclusive_group(required=True)
    input_group.add_argument("--text", help="Text to synthesize")
    input_group.add_argument("--text-file", help="Read text from a file")
    p.add_argument("--speaker", default=DEFAULT_SPEAKER, help="Speaker ID (default: %(default)s)")
    p.add_argument("--format", dest="audio_format", default=DEFAULT_FORMAT, choices=["mp3", "ogg_opus", "pcm"], help="Audio format (default: %(default)s)")
    p.add_argument("--sample-rate", type=int, default=DEFAULT_SAMPLE_RATE, help="Sample rate in Hz (default: %(default)s)")
    p.add_argument("--speed", type=int, default=DEFAULT_SPEED, help="Speech rate [-50, 100] (default: %(default)s)")
    p.add_argument("--volume", type=int, default=DEFAULT_VOLUME, help="Volume [-50, 100] (default: %(default)s)")
    p.add_argument("--bit-rate", type=int, default=DEFAULT_BIT_RATE, help="Bit rate for MP3 (default: auto)")
    p.add_argument("--emotion", help="Emotion tag (speaker-dependent)")
    p.add_argument("--emotion-scale", type=int, help="Emotion intensity [1, 5]")
    p.add_argument("--resource-id", default=DEFAULT_RESOURCE_ID, help="Model version (default: %(default)s)")
    p.add_argument("--out", default=None, help="Output file path (default: ./output.<format>)")
    p.add_argument("--api-key", default=None, help="API Key (or set env var)")
    p.add_argument("--enable-markdown-filter", action="store_true", help="Strip markdown syntax before synthesis")
    p.add_argument("--enable-language-detector", action="store_true", help="Auto-detect language")
    p.add_argument("--silence-duration", type=int, default=0, help="Trailing silence in ms [0, 30000]")
    p.add_argument("--context-text", help="Voice instruction for TTS 2.0 (e.g. 'say it slower')")
    return p.parse_args()


def resolve_api_key(cli_key: Optional[str]) -> str:
    if cli_key:
        return cli_key
    env_val = os.environ.get(ENV_KEY_NAME, "").strip()
    if env_val:
        return env_val
    env_path = Path(__file__).resolve().parent.parent / ".env"
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                if k.strip() == ENV_KEY_NAME:
                    return v.strip().strip("\"'")
    print(f"Error: API key not found. Set {ENV_KEY_NAME} env var, use --api-key, or create .env file.", file=sys.stderr)
    sys.exit(1)


def read_text(args: argparse.Namespace) -> str:
    if args.text:
        return args.text
    path = Path(args.text_file)
    if not path.exists():
        print(f"Error: file not found: {path}", file=sys.stderr)
        sys.exit(1)
    return path.read_text(encoding="utf-8")


def build_payload(text: str, args: argparse.Namespace) -> dict:
    audio_params: dict = {
        "format": args.audio_format,
        "sample_rate": args.sample_rate,
    }
    if args.speed != DEFAULT_SPEED:
        audio_params["speech_rate"] = args.speed
    if args.volume != DEFAULT_VOLUME:
        audio_params["loudness_rate"] = args.volume
    if args.bit_rate:
        audio_params["bit_rate"] = args.bit_rate
    if args.emotion:
        audio_params["emotion"] = args.emotion
    if args.emotion_scale is not None:
        audio_params["emotion_scale"] = args.emotion_scale

    additions: dict = {}
    if args.enable_markdown_filter:
        additions["disable_markdown_filter"] = False
    if args.enable_language_detector:
        additions["enable_language_detector"] = True
    if args.silence_duration > 0:
        additions["silence_duration"] = args.silence_duration

    req_params: dict = {
        "text": text,
        "speaker": args.speaker,
        "audio_params": audio_params,
    }
    if args.context_text:
        additions["context_texts"] = [args.context_text]
    if additions:
        req_params["additions"] = json.dumps(additions)

    payload = {
        "user": {"uid": "cli-user"},
        "req_params": req_params,
    }
    return payload


def synthesize(payload: dict, api_key: str, resource_id: str) -> bytes:
    headers = {
        "Content-Type": "application/json",
        "X-Api-Key": api_key,
        "X-Api-Resource-Id": resource_id,
        "X-Api-Request-Id": str(uuid.uuid4()),
    }

    try:
        import requests
        resp = requests.post(API_URL, headers=headers, json=payload, stream=True, timeout=120)
        resp.raise_for_status()
    except ImportError:
        from urllib.request import Request, urlopen
        from urllib.error import HTTPError

        req = Request(API_URL, data=json.dumps(payload).encode("utf-8"), headers=headers)
        try:
            resp_obj = urlopen(req, timeout=120)
        except HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")
            print(f"HTTP {e.code}: {body}", file=sys.stderr)
            sys.exit(1)
        audio_data = bytearray()
        for line in resp_obj:
            line = line.strip()
            if not line:
                continue
            try:
                chunk = json.loads(line)
            except json.JSONDecodeError:
                continue
            code = chunk.get("code", -1)
            if code == 20000000:
                break
            if code != 0:
                print(f"API error: code={code}, message={chunk.get('message', '')}", file=sys.stderr)
                sys.exit(1)
            if chunk.get("data"):
                audio_data.extend(base64.b64decode(chunk["data"]))
        return bytes(audio_data)

    audio_data = bytearray()
    for line in resp.iter_lines(decode_unicode=True):
        if not line:
            continue
        try:
            chunk = json.loads(line)
        except json.JSONDecodeError:
            continue
        code = chunk.get("code", -1)
        if code == 20000000:
            break
        if code != 0:
            print(f"API error: code={code}, message={chunk.get('message', '')}", file=sys.stderr)
            sys.exit(1)
        if chunk.get("data"):
            audio_data.extend(base64.b64decode(chunk["data"]))
    return bytes(audio_data)


def main() -> None:
    args = parse_args()
    api_key = resolve_api_key(args.api_key)
    text = read_text(args)
    payload = build_payload(text, args)
    out_path = args.out or f"output.{args.audio_format}"

    print(f"Synthesizing {len(text)} chars with speaker={args.speaker} ...", file=sys.stderr)
    audio = synthesize(payload, api_key, args.resource_id)

    if not audio:
        print("Error: no audio data received.", file=sys.stderr)
        sys.exit(1)

    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(audio)
    print(f"Saved {len(audio)} bytes -> {out}", file=sys.stderr)


if __name__ == "__main__":
    main()
