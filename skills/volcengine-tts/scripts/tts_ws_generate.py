#!/usr/bin/env python3
"""Seed TTS 2.0 via Volcengine WebSocket bidirectional streaming API.

wss://openspeech.bytedance.com/api/v3/tts/bidirection
X-Api-Resource-Id: seed-tts-2.0 (standard voices) / seed-icl-2.0 (cloned voices)
Auth: X-Api-Key header (new speech console).

Binary protocol (v1, per official "TTS Websocket Bidirection protocols"):
  header 4B: (ver<<4)|hdr_size, (type<<4)|flags, (serialization<<4)|compression, 0x00
  WithEvent frames: header | event(i32) | session_id(u32 len + bytes, skipped for
  connection events) | payload(u32 len + bytes). JSON, uncompressed.

Message flow follows the official demo:
  StartConnection → StartSession{"event":100,"req_params":{...}} →
  TaskRequest per text chunk {"event":200,"req_params":{...,"text":chunk}} →
  FinishSession → collect AudioOnlyServer payloads → FinishConnection.
Note: TaskRequest text lives INSIDE req_params (top-level {"text":...} is
silently ignored — synthesizes nothing).
"""

import argparse
import gzip
import json
import os
import re
import struct
import sys
import time
import uuid

import websocket

WSS_URL = "wss://openspeech.bytedance.com/api/v3/tts/bidirection"
SKILL_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

EV_START_CONNECTION, EV_FINISH_CONNECTION = 1, 2
EV_CONNECTION_STARTED, EV_CONNECTION_FAILED, EV_CONNECTION_FINISHED = 50, 51, 52
EV_START_SESSION, EV_FINISH_SESSION = 100, 102
EV_SESSION_STARTED, EV_SESSION_FAILED, EV_SESSION_FINISHED = 150, 153, 152
EV_TASK_REQUEST = 200
EV_TTS_SENTENCE_START, EV_TTS_SENTENCE_END, EV_TTS_RESPONSE, EV_TTS_SUBTITLE = 350, 351, 352, 364

EVENT_NAMES = {
    EV_START_CONNECTION: "StartConnection", EV_FINISH_CONNECTION: "FinishConnection",
    EV_CONNECTION_STARTED: "ConnectionStarted", EV_CONNECTION_FAILED: "ConnectionFailed",
    EV_CONNECTION_FINISHED: "ConnectionFinished", EV_START_SESSION: "StartSession",
    EV_FINISH_SESSION: "FinishSession", EV_SESSION_STARTED: "SessionStarted",
    EV_SESSION_FAILED: "SessionFailed", EV_SESSION_FINISHED: "SessionFinished",
    EV_TASK_REQUEST: "TaskRequest", EV_TTS_SENTENCE_START: "TTSSentenceStart",
    EV_TTS_SENTENCE_END: "TTSSentenceEnd", EV_TTS_RESPONSE: "TTSResponse",
    EV_TTS_SUBTITLE: "TTSSubtitle",
}
CONNECTION_EVENTS = {EV_START_CONNECTION, EV_FINISH_CONNECTION,
                     EV_CONNECTION_STARTED, EV_CONNECTION_FAILED, EV_CONNECTION_FINISHED}
TYPE_FULL_SERVER, TYPE_AUDIO, TYPE_ERROR = 9, 11, 15


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
    sys.exit("错误：未找到 API Key。设置 VOLCENGINE_TTS_API_KEY、传 --api-key 或配置 .env。")


def build_request(event: int, session_id: str = "", payload: bytes = b"{}") -> bytes:
    header = bytes([0x11, (1 << 4) | 0b100, 0x10, 0x00])  # v1|size4, FullClientRequest|WithEvent, JSON|none
    frame = bytearray(header)
    frame += struct.pack(">i", event)
    if event not in CONNECTION_EVENTS:
        sid = session_id.encode("utf-8")
        frame += struct.pack(">I", len(sid)) + sid
    frame += struct.pack(">I", len(payload)) + payload
    return bytes(frame)


def parse_message(data: bytes) -> dict:
    header_size = data[0] & 0x0F
    msg_type = (data[1] >> 4) & 0x0F
    flag = data[1] & 0x0F
    serialization = (data[2] >> 4) & 0x0F
    compression = data[2] & 0x0F
    pos = header_size * 4
    event, session_id, connect_id, error_code = None, "", "", None

    if msg_type == TYPE_ERROR:
        error_code = struct.unpack(">I", data[pos:pos + 4])[0]
        pos += 4
    if flag == 0b100:  # WithEvent
        event = struct.unpack(">i", data[pos:pos + 4])[0]
        pos += 4
        if event not in CONNECTION_EVENTS:
            size = struct.unpack(">I", data[pos:pos + 4])[0]
            pos += 4
            session_id = data[pos:pos + size].decode("utf-8")
            pos += size
        if event in (50, 51, 52):
            size = struct.unpack(">I", data[pos:pos + 4])[0]
            pos += 4
            connect_id = data[pos:pos + size].decode("utf-8")
            pos += size
    size = struct.unpack(">I", data[pos:pos + 4])[0]
    pos += 4
    payload = data[pos:pos + size]
    if compression == 1:
        payload = gzip.decompress(payload)

    result = {"type": msg_type, "event": event, "event_name": EVENT_NAMES.get(event, str(event)),
              "session_id": session_id, "connect_id": connect_id, "error_code": error_code,
              "payload": payload}
    if msg_type == TYPE_ERROR:
        result["error_message"] = payload.decode("utf-8", "replace")
    elif serialization == 1 and payload:
        try:
            result["json"] = json.loads(payload.decode("utf-8"))
        except json.JSONDecodeError:
            pass
    return result


def split_text(text: str, maxlen: int = 40) -> list:
    """Split into chunks at clause boundaries (official demo streams small pieces)."""
    parts = re.findall(r"[^，。！？；：,.!?;:…\n]+[，。！？；：,.!?;:…\n]*", text)
    chunks, cur = [], ""
    for p in parts:
        if not p:
            continue
        while len(p) > maxlen:
            if cur:
                chunks.append(cur)
                cur = ""
            chunks.append(p[:maxlen])
            p = p[maxlen:]
        if len(cur) + len(p) <= maxlen:
            cur += p
        else:
            if cur:
                chunks.append(cur)
            cur = p
    if cur:
        chunks.append(cur)
    return chunks or [text]


def read_text(args) -> str:
    if args.text:
        return args.text
    if args.text_file:
        with open(args.text_file, "r", encoding="utf-8") as f:
            return f.read()
    sys.exit("错误：--text 与 --text-file 必须提供一个")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--text", help="待合成文本")
    parser.add_argument("--text-file", help="从文件读取文本")
    parser.add_argument("--speaker", default="en_female_dacey_uranus_bigtts",
                        help="音色ID，须与 Resource-Id 匹配（2.0 音色见 console 音色库，"
                             "如 en_female_dacey_uranus_bigtts / zh_female_gaolengyujie_uranus_bigtts）")
    parser.add_argument("--resource-id", default="seed-tts-2.0",
                        help="seed-tts-2.0（标准音色）/ seed-icl-2.0（复刻音色）")
    parser.add_argument("--model", default=None, help="复刻音色时指定模型版本")
    parser.add_argument("--format", default="mp3", choices=["mp3", "pcm", "ogg_opus", "wav"])
    parser.add_argument("--sample-rate", type=int, default=24000)
    parser.add_argument("--speech-rate", type=int, default=0, help="[-50, 100]")
    parser.add_argument("--loudness-rate", type=int, default=0, help="[-50, 100]")
    parser.add_argument("--pitch", type=int, default=0, help="post_process.pitch [-12, 12]")
    parser.add_argument("--explicit-language", default=None,
                        help="指定朗读语种：en / zh-cn / ja 等（其他语种内容会被跳过）")
    parser.add_argument("--context-text", action="append", default=[],
                        help="语音指令（情感/语气控制），可多次传入")
    parser.add_argument("--enable-subtitle", action="store_true", help="返回字级时间戳（中英）")
    parser.add_argument("--api-key", default="")
    parser.add_argument("--timeout", type=int, default=60, help="单次 recv 超时秒数")
    parser.add_argument("--chunk-size", type=int, default=40, help="分块发送的块大小（字符）")
    parser.add_argument("--out", default=None, help="输出音频路径，默认 ./tts_ws_output.<format>")
    args = parser.parse_args()

    api_key = load_api_key(args.api_key)
    text = read_text(args)
    out_path = args.out or f"./tts_ws_output.{args.format}"

    audio_params = {
        "format": args.format,
        "sample_rate": args.sample_rate,
        "speech_rate": args.speech_rate,
        "loudness_rate": args.loudness_rate,
        "enable_subtitle": args.enable_subtitle,
    }
    req_params = {"speaker": args.speaker, "audio_params": audio_params}
    if args.model:
        req_params["model"] = args.model
    if args.explicit_language:
        req_params["explicit_language"] = args.explicit_language
    if args.context_text:
        req_params["context_texts"] = args.context_text
    if args.pitch:
        req_params["post_process"] = {"pitch": args.pitch}

    session_id = str(uuid.uuid4())
    ws = websocket.WebSocket()
    ws.connect(WSS_URL, timeout=30, header=[
        f"X-Api-Key: {api_key}",
        f"X-Api-Resource-Id: {args.resource_id}",
        f"X-Api-Connect-Id: {session_id}",
    ])
    ws.settimeout(args.timeout)

    def recv_until(want_event: int, collect: dict) -> None:
        """Read frames until a given event arrives; collect audio/subtitles on the way."""
        deadline = time.time() + 120
        while time.time() < deadline:
            try:
                raw = ws.recv()
            except websocket.WebSocketConnectionClosedException:
                sys.exit("错误：连接被服务端关闭")
            if not raw:
                continue
            if isinstance(raw, str):
                raw = raw.encode()
            msg = parse_message(raw)
            name = msg["event_name"]
            if msg["type"] == TYPE_AUDIO and msg["payload"]:
                collect["audio"].append(msg["payload"])
            if name == "TTSSubtitle" and msg.get("json"):
                collect["subtitles"].append(msg["json"])
            if name == "TTSSentenceEnd" and msg.get("json"):
                collect["usage"] = msg["json"].get("usage", collect["usage"])
            if msg["type"] == TYPE_ERROR or name in ("SessionFailed", "ConnectionFailed"):
                detail = msg.get("error_message") or json.dumps(msg.get("json", {}), ensure_ascii=False)
                sys.exit(f"失败 [{name}] code={msg.get('error_code')}: {detail[:600]}\n"
                         f"提示：55000000 资源不匹配通常是音色与 --resource-id 不配套"
                         f"（2.0 标准音色须用 seed-tts-2.0）")
            if msg["event"] == want_event:
                return
        sys.exit(f"错误：等待 {EVENT_NAMES.get(want_event, want_event)} 超时")

    state = {"audio": [], "subtitles": [], "usage": {}}
    started = time.time()

    ws.send_binary(build_request(EV_START_CONNECTION))
    recv_until(EV_CONNECTION_STARTED, state)
    ws.send_binary(build_request(EV_START_SESSION, session_id,
                                 json.dumps({"event": EV_START_SESSION,
                                             "req_params": req_params}).encode()))
    recv_until(EV_SESSION_STARTED, state)

    chunks = split_text(text, args.chunk_size)
    for i, chunk in enumerate(chunks):
        body = {"event": EV_TASK_REQUEST,
                "req_params": {**req_params, "text": chunk}}
        ws.send_binary(build_request(EV_TASK_REQUEST, session_id, json.dumps(body).encode()))
        time.sleep(0.02)
    ws.send_binary(build_request(EV_FINISH_SESSION, session_id))

    deadline = time.time() + 300
    while time.time() < deadline:
        try:
            raw = ws.recv()
        except (websocket.WebSocketTimeoutException, TimeoutError):
            print("警告：recv 超时，按已收内容结束", file=sys.stderr)
            break
        except websocket.WebSocketConnectionClosedException:
            print("提示：连接已由服务端关闭", file=sys.stderr)
            break
        if not raw:
            continue
        if isinstance(raw, str):
            raw = raw.encode()
        msg = parse_message(raw)
        name = msg["event_name"]
        if msg["type"] == TYPE_AUDIO and msg["payload"]:
            state["audio"].append(msg["payload"])
        if name == "TTSSubtitle" and msg.get("json"):
            state["subtitles"].append(msg["json"])
        if name == "TTSSentenceEnd" and msg.get("json"):
            state["usage"] = msg["json"].get("usage", state["usage"])
        if msg["type"] == TYPE_ERROR or name in ("SessionFailed", "ConnectionFailed"):
            detail = msg.get("error_message") or json.dumps(msg.get("json", {}), ensure_ascii=False)
            sys.exit(f"失败 [{name}] code={msg.get('error_code')}: {detail[:600]}")
        if name == EV_SESSION_FINISHED or name == "SessionFinished":
            ws.send_binary(build_request(EV_FINISH_CONNECTION))
        if name == "ConnectionFinished":
            break

    try:
        ws.close()
    except Exception:
        pass

    audio = b"".join(state["audio"])
    if not audio:
        sys.exit("错误：未收到任何音频")
    with open(out_path, "wb") as f:
        f.write(audio)
    print(f"已保存 {out_path}  {len(audio)} bytes  耗时 {time.time() - started:.0f}s  "
          f"计费字数 {state['usage'].get('text_words', '?') if isinstance(state['usage'], dict) else state['usage']}")

    meta_path = os.path.splitext(out_path)[0] + "-meta.json"
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump({"request": {"speaker": args.speaker, "resource_id": args.resource_id,
                               "audio_params": audio_params, "text": text,
                               "text_length": len(text), "chunks": len(chunks)},
                   "usage": state["usage"]}, f, ensure_ascii=False, indent=2)
    print(f"已保存 {meta_path}")
    if state["subtitles"]:
        sub_path = os.path.splitext(out_path)[0] + "-subtitle.json"
        with open(sub_path, "w", encoding="utf-8") as f:
            json.dump(state["subtitles"], f, ensure_ascii=False, indent=2)
        print(f"已保存 {sub_path}")


if __name__ == "__main__":
    main()
