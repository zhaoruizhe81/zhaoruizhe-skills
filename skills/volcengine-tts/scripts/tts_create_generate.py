#!/usr/bin/env python3
"""Seed Audio TTS via Volcengine non-streaming HTTP API (/api/v3/tts/create).

Model: seed-audio-1.0. Up to 120 s audio per call; supports plain text,
reference audio (@音频N in text) and reference image generation, plus optional
word-level subtitles. Recommended for dubbing and narration.

Credentials, resolved in order: --api-key flag → VOLCENGINE_TTS_API_KEY env →
.env at the skill root. Auth header: X-Api-Key (new console API Key).

Error 45000030 "requested resource not granted" means the 语音合成大模型
service is not activated on the account — enable it in the speech console.
"""

import argparse
import base64
import json
import os
import sys
import time
import urllib.error
import urllib.request
import uuid

API_URL = "https://openspeech.bytedance.com/api/v3/tts/create"
SKILL_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load_api_key(cli_key: str) -> str:
    if cli_key:
        return cli_key
    key = os.environ.get("VOLCENGINE_TTS_API_KEY", "").strip()
    if key:
        return key
    env_path = os.path.join(SKILL_ROOT, ".env")
    if os.path.exists(env_path):
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line.startswith("VOLCENGINE_TTS_API_KEY="):
                    return line.split("=", 1)[1].strip().strip('"').strip("'")
    sys.exit(
        "错误：未找到 API Key。请设置 VOLCENGINE_TTS_API_KEY、传 --api-key，"
        "或在 skill 根目录 .env 中配置。"
    )


def read_text(args) -> str:
    if args.text:
        return args.text
    if args.text_file:
        with open(args.text_file, "r", encoding="utf-8") as f:
            return f.read()
    sys.exit("错误：--text 与 --text-file 必须提供一个")


def to_b64(path: str) -> str:
    if not os.path.exists(path):
        sys.exit(f"错误：参考文件不存在: {path}")
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--text", help="待合成文本/提示词（≤3000字符；引用参考音频用 @音频N）")
    parser.add_argument("--text-file", help="从文件读取文本")
    parser.add_argument("--model", default="seed-audio-1.0")
    parser.add_argument("--speaker", default=None, help="音色ID（豆包语音合成2.0音色或复刻音色）")
    parser.add_argument("--reference-audio", nargs="*", default=[],
                        help="参考音频文件路径（≤3条，每条≤30s；文本中用 @音频N 引用）")
    parser.add_argument("--reference-image", default=None,
                        help="参考图片路径（与音频参考/音色互斥）")
    parser.add_argument("--format", default="mp3", choices=["wav", "mp3", "pcm", "ogg_opus"])
    parser.add_argument("--sample-rate", type=int, default=None,
                        help="采样率Hz；mp3 默认 44100，wav/pcm 默认 40000")
    parser.add_argument("--speech-rate", type=int, default=0, help="语速 [-50, 100]")
    parser.add_argument("--loudness-rate", type=int, default=0, help="音量 [-50, 100]")
    parser.add_argument("--pitch-rate", type=int, default=0, help="音调 [-12, 12]")
    parser.add_argument("--enable-subtitle", action="store_true", help="返回字级时间戳")
    parser.add_argument("--api-key", default="")
    parser.add_argument("--timeout", type=int, default=300, help="请求超时秒数")
    parser.add_argument("--out", default=None, help="输出音频路径，默认 ./tts_create_output.<format>")
    args = parser.parse_args()

    api_key = load_api_key(args.api_key)
    text = read_text(args)

    body = {"model": args.model, "text_prompt": text}
    if args.speaker:
        body["speaker"] = args.speaker
    if args.reference_audio and args.reference_image:
        sys.exit("错误：音频参考与图片参考不能混用")
    if args.reference_audio and len(args.reference_audio) > 3:
        sys.exit("错误：参考音频最多 3 条")
    if args.reference_audio:
        body["references"] = [{"audio_data": to_b64(p)} for p in args.reference_audio]
    if args.reference_image:
        if args.speaker:
            sys.exit("错误：图片参考不能与 speaker/audio 参考同时传入")
        body["references"] = [{"image_data": to_b64(args.reference_image)}]

    audio_config = {
        "format": args.format,
        "speech_rate": args.speech_rate,
        "loudness_rate": args.loudness_rate,
        "pitch_rate": args.pitch_rate,
        "enable_subtitle": args.enable_subtitle,
    }
    if args.sample_rate:
        audio_config["sample_rate"] = args.sample_rate
    body["audio_config"] = audio_config

    out_path = args.out or f"./tts_create_output.{args.format}"
    started = time.time()
    req = urllib.request.Request(
        API_URL,
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "X-Api-Key": api_key,
            "X-Api-Request-Id": str(uuid.uuid4()),
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=args.timeout) as resp:
            result = json.load(resp)
    except urllib.error.HTTPError as e:
        print(f"HTTP {e.code}", file=sys.stderr)
        print(e.read().decode("utf-8", "replace")[:2000], file=sys.stderr)
        sys.exit(1)

    if result.get("code") != 0:
        print(f"API 错误 code={result.get('code')}: {result.get('message')}", file=sys.stderr)
        if result.get("code") == 45000030:
            print("提示：服务未开通。请到语音控制台开通“语音合成大模型”"
                  "（https://console.volcengine.com/speech/new）", file=sys.stderr)
        sys.exit(1)

    audio = base64.b64decode(result["audio"])
    with open(out_path, "wb") as f:
        f.write(audio)
    print(f"已保存 {out_path}  {len(audio)} bytes  "
          f"时长 {result.get('duration', '?')}s  耗时 {time.time() - started:.0f}s")
    if result.get("url"):
        print(f"临时音频URL（2小时有效）: {result['url'][:100]}...")

    meta_keys = ("code", "audio", "url")
    meta = {k: v for k, v in result.items() if k not in meta_keys and v is not None}
    sidecar = os.path.splitext(out_path)[0] + "-meta.json"
    with open(sidecar, "w", encoding="utf-8") as f:
        json.dump({"request": {k: v for k, v in body.items()
                               if k not in ("references",)},
                   "response": meta}, f, ensure_ascii=False, indent=2)
    print(f"已保存 {sidecar}")
    if result.get("subtitle"):
        sub_path = os.path.splitext(out_path)[0] + "-subtitle.json"
        with open(sub_path, "w", encoding="utf-8") as f:
            json.dump(result["subtitle"], f, ensure_ascii=False, indent=2)
        print(f"已保存 {sub_path}")


if __name__ == "__main__":
    main()
