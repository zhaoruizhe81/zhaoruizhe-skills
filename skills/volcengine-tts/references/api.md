# Volcengine Doubao TTS API Quick Reference

## Endpoint

```
POST https://openspeech.bytedance.com/api/v3/tts/unidirectional
Content-Type: application/json
```

## Authentication

| Header | Required | Description |
|--------|----------|-------------|
| `X-Api-Key` | Yes | API key from Volcengine console |
| `X-Api-Resource-Id` | Yes | Model version: `seed-tts-2.0` or `seed-tts-1.0` |
| `X-Api-Request-Id` | No | UUID for request tracing |

## Key Parameters

| Parameter | Default | Range / Options |
|-----------|---------|-----------------|
| `resource_id` | `seed-tts-1.0` | `seed-tts-1.0`, `seed-tts-1.0-concurr`, `seed-tts-2.0` |
| `speaker` | — | See voice list below |
| `audio_params.format` | `mp3` | `mp3`, `ogg_opus`, `pcm` |
| `audio_params.sample_rate` | `24000` | 8000, 16000, 22050, 24000, 32000, 44100, 48000 |
| `audio_params.speech_rate` | `0` | [-50, 100] — 100 = 2x, -50 = 0.5x |
| `audio_params.loudness_rate` | `0` | [-50, 100] |
| `audio_params.emotion` | — | Speaker-dependent |
| `audio_params.emotion_scale` | `4` | [1, 5] |
| `additions.disable_markdown_filter` | `false` | Set `false` to strip markdown |
| `additions.enable_language_detector` | `false` | Auto-detect language |
| `additions.silence_duration` | `0` | [0, 30000] ms trailing silence |
| `additions.context_texts` | — | Voice instructions for TTS 2.0 |

## Recommended Voices (TTS 1.0, default)

| Speaker ID | Description |
|------------|-------------|
| `zh_female_shuangkuaisisi_moon_bigtts` | Female, cheerful (default) |
| `zh_male_ahu_conversation_wvae_bigtts` | Male, conversational |

Full list: https://www.volcengine.com/docs/6561/1257544

## Error Codes

| Code | Message | Meaning |
|------|---------|---------|
| `20000000` | ok | Synthesis complete |
| `40402003` | exceed max limit | Text too long |
| `45000000` | speaker permission denied | Unauthorized speaker |
| `45000000` | quota exceeded | Concurrency limit |
| `55000000` | server error | Server-side error |

## Response Format

Each chunk is a JSON line:
- `code: 0` + `data: <base64>` — audio data chunk
- `code: 0` + `sentence: {...}` — timestamp info
- `code: 20000000` — synthesis finished (terminal)
