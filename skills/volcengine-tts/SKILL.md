---
name: volcengine-tts
description: "Convert text to speech using Volcengine Doubao speech models. Default: Seed TTS 2.0 WebSocket bidirectional streaming (seed-tts-2.0, 2.0 voices like en_female_dacey_uranus_bigtts, word-level subtitle timestamps). Trigger when the user asks to generate audio from text, TTS, dubbing, 配音, 朗读, or convert text into spoken audio. Requires VOLCENGINE_TTS_API_KEY."
---

# Volcengine Doubao TTS

Execution paths:

- **Default — Seed TTS 2.0, WebSocket bidirectional** (`scripts/tts_ws_generate.py`): proven working end-to-end. Streaming synthesis with word-level subtitle timestamps. English + Chinese voices.
- Legacy — non-streaming HTTP `/api/v3/tts/create` (`scripts/tts_create_generate.py`): needs the separate "语音合成大模型(seed-audio)" resource grant; returns 45000030 until activated.
- Legacy — streaming `/api/v3/tts/unidirectional` (`scripts/tts_generate.py`): old console auth style.

## Default path: Seed TTS 2.0 WebSocket bidirectional

### Credentials

Auth header is a single `X-Api-Key` (new speech console API Key). Resolved in order: `--api-key` flag → `VOLCENGINE_TTS_API_KEY` env → `.env` at the skill root.
Get/renew: https://console.volcengine.com/speech/new/setting/apikeys
The account must have **语音合成2.0** activated (console 大模型 tab).

### Quick start

```bash
python "<skill-path>/scripts/tts_ws_generate.py" \
  --text "Hello everyone! Let me introduce my IP character." \
  --speaker en_female_dacey_uranus_bigtts \
  --enable-subtitle --out dubbing.mp3
```

Verified: Dacey (en_female_dacey_uranus_bigtts) produces valid mp3 (24 kHz/64 kbps) plus
word-level subtitle JSON. For Chinese, the official demo's 2.0 voice is
`zh_female_gaolengyujie_uranus_bigtts`. Pick voices from 控制台>音色库 filtered to 语音合成2.0.

### Critical protocol facts (learned the hard way)

1. **TaskRequest text goes INSIDE `req_params`**: payload is
   `{"event":200,"req_params":{...session req_params...,"text":chunk}}`.
   A top-level `{"text":...}` parses as JSON but is silently ignored → session completes
   with zero audio. The script implements the correct shape and streams the text in
   clause-boundary chunks (`--chunk-size`, default 40 chars) like the official demo.
2. **Speaker must match `X-Api-Resource-Id`**: a voice from another generation fails with
   `code 55000000 "resource ID is mismatched with speaker related resource"`
   (e.g. `zh_female_cancan_mars_bigtts` is NOT a seed-tts-2.0 voice).
3. Client must send `FinishConnection` after `SessionFinished`, then await `ConnectionFinished`.
4. Binary framing: 4-byte header (`0x11, (type<<4)|0b100, 0x10, 0x00`), then
   event(i32) | session_id(u32 len + bytes, skipped for connection events) | payload(u32 len + bytes).
   Server audio arrives as AudioOnlyServer frames; raw payload bytes concatenate into the audio file.

### Options

| Flag | Default | 说明 |
|---|---|---|
| `--text` / `--text-file` | — | 待合成文本 |
| `--speaker` | `en_female_dacey_uranus_bigtts` | 2.0 音色 ID（音色库：console.volcengine.com/speech/new/voices） |
| `--resource-id` | `seed-tts-2.0` | `seed-tts-2.0` 标准音色 / `seed-icl-2.0` 复刻音色 |
| `--model` | 无 | 复刻音色时指定（如 `seed-tts-2.0-standard`） |
| `--format` | `mp3` | `mp3`/`pcm`/`ogg_opus`/`wav`（流式推荐 pcm/mp3，勿用 wav） |
| `--sample-rate` | 24000 | 8000–48000（ogg_opus 仅 48000） |
| `--speech-rate` | 0 | 语速 [-50, 100]，100=2x |
| `--loudness-rate` | 0 | 音量 [-50, 100] |
| `--pitch` | 0 | 音调 [-12, 12] |
| `--explicit-language` | 无 | 强制语种：en / zh-cn / ja / de / fr …（20 种） |
| `--context-text` | 无 | 语音指令控制情感语气，可多次传入，不计费 |
| `--enable-subtitle` | off | 词级时间戳 → `<out>-subtitle.json`（视频字幕对轴可用） |
| `--chunk-size` | 40 | 文本分块字符数 |
| `--out` | `./tts_ws_output.<format>` | 输出路径；旁边写 `-meta.json`（参数+计费） |

Outputs: `<out>` audio + `<out>-meta.json` (request params, billing) + optional
`<out>-subtitle.json` (word-level timestamps). Account quota is character-based
(console shows remaining characters).

## Legacy: non-streaming /tts/create (seed-audio-1.0)

`scripts/tts_create_generate.py` — up to 120 s per call, reference-audio/image modes.
Requires the **seed-audio (语音合成大模型)** resource grant; otherwise HTTP 403
`code 45000030 "volc.service_type.10074 not granted"`. Not granted on this account so far.

## Legacy: streaming /tts/unidirectional

`scripts/tts_generate.py` — HTTP chunked streaming, `X-Api-Resource-Id: seed-tts-1.0/2.0`.
Kept for compatibility.
