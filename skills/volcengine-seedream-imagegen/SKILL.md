---
name: volcengine-seedream-imagegen
description: Generate images with Volcengine Seedream 5.0 Pro via the Ark API (default, supports reference images / i2i for character consistency), or legacy Seedream 3.0 via the Visual Intelligence CV API. Use when the user says "用 Seedream 生图", "文生图", "生成海报/三视图/插画", "垫图生成", or wants repeatable local CLI generation with prompt records saved alongside images.
---

# Volcengine Seedream Imagegen

Two execution paths:

- **Default — Seedream 5.0 Pro via Ark API** (`scripts/seedream_ark_generate.py`): synchronous REST call, no polling, supports reference images (i2i 垫图) for character/style consistency. Credentials: `ARK_API_KEY`.
- **Legacy — Seedream 3.0 via CV API** (`scripts/seedream_generate.py`): async HMAC-signed CV task + polling. Credentials: `VOLCENGINE_ACCESS_KEY` / `VOLCENGINE_SECRET_KEY`. Kept for backward compatibility only.

Prefer the default path for all new work.

## Default path: Seedream 5.0 Pro (Ark API)

### Credentials

Resolved in order: `--api-key` flag → `ARK_API_KEY` env var → `.env` at the skill root (`ARK_API_KEY=...`).
Get a key: https://console.volcengine.com/ark/region:ark+cn-beijing/apikey

### Quick start

```bash
python "<skill-path>/scripts/seedream_ark_generate.py" \
  --prompt "一只可爱的圆滚滚的小机器人吉祥物，天蓝色和白色配色，扁平插画，纯白背景"
```

Files land in `--output-dir` (default `./output/seedream5/`): the image(s) plus `<prefix>-result.json`, a sidecar recording prompt / references / size / seed / usage. Keep these sidecars — they double as the prompt log users often need to submit.

### Reference images (i2i 垫图) — use for character consistency

Pass one or more reference images (local paths are inlined as base64 data URLs; http(s) URLs pass through). The model keeps subject identity, palette and style of the references. This is the reliable way to produce consistent multi-view character sheets, merch mockups, and scene shots of the same IP character:

```bash
python "<skill-path>/scripts/seedream_ark_generate.py" \
  --prompt "参考图片中的角色，严格保持其外形特征、配色和风格完全一致，生成它的背面视角，纯白背景" \
  --image "/abs/path/character_front.jpg" \
  --output-dir /abs/path/output --prefix character-back
```

Up to 10 reference images. For an IP workflow: generate one canonical character sheet first, approve it, then always pass it as the reference for every subsequent shot.

### Options

| Flag | Default | 说明 |
|---|---|---|
| `--prompt` | — | 提示词；要出现在图中的文字用引号包住原文 |
| `--model` | `doubao-seedream-5-0-pro-260628` | 模型 ID |
| `--size` | `2K` | `1K` / `2K` / `4K` 或显式 `宽x高`（如 `2048x2048`）；不指定画幅时模型按提示词自行选比例，需要特定比例时写显式宽高 |
| `--image` | 无 | 参考图路径/URL 列表（i2i 垫图） |
| `--sequential` | off | 组图模式（`sequential_image_generation=auto`），一次生成成组图片 |
| `--max-images` | 无 | 组图模式的最大张数 |
| `--seed` | 无 | 随机种子，复现用 |
| `--watermark` | off | 加 AI 生成水印 |
| `--output-dir` | `./output/seedream5` | 输出目录 |
| `--prefix` | `seedream5` | 文件名前缀 |

### Practical notes

- Single image takes roughly 1–2 minutes; set generous timeouts (≥300s).
- Known failure mode: `OutputImageSensitiveContentDetected.PolicyViolation` (HTTP 400) when the output resembles a copyrighted character. Rephrase the prompt away from existing IP names/looks (e.g. avoid "机器猫" → Doraemon); it is a content-policy rejection, not a billing problem.
- A 401/403 from this endpoint usually means `ARK_API_KEY` is wrong or the model is not enabled in the Ark console; a 402/ arrears error mentions insufficient balance.
- Avoid special symbols in prompts unless needed for text layout.

## Legacy path: Seedream 3.0 (CV API)

Read `references/cli.md` and `references/api.md` for `scripts/seedream_generate.py` (submit `--prompt`, poll task, optional watermark). Fixed `Region=cn-north-1`, `Service=cv`, `req_key=high_aes_general_v30l_zt2i`. Returned `image_urls` expire after 24 hours — download promptly. No reference-image support.
