# Volcengine Seedream CLI

## Credentials

The script reads credentials from:

1. `--access-key` and `--secret-key`
2. environment variables
3. `"<skill-path>/.env"`

Supported variable names:

- `VOLCENGINE_ACCESS_KEY`
- `VOLCENGINE_ACCESS_KEY_ID`
- `VOLCENGINE_SECRET_KEY`
- `VOLCENGINE_SECRET_ACCESS_KEY`
- `VOLCENGINE_SESSION_TOKEN`

## Common Commands

Generate an image:

```bash
python "<skill-path>/scripts/seedream_generate.py" \
  --prompt "未来校园主楼，电影感，蓝金色夜景" \
  --output-dir "/absolute/path/output"
```

Generate a 16:9 cover:

```bash
python "<skill-path>/scripts/seedream_generate.py" \
  --prompt "智慧校园封面图，纪实摄影风格，晨光，适合作为PPT背景" \
  --width 1664 \
  --height 936 \
  --output-dir "/absolute/path/output"
```

Query an existing task:

```bash
python "<skill-path>/scripts/seedream_generate.py" \
  --task-id "7392616336519610409" \
  --output-dir "/absolute/path/output"
```

## Useful Flags

- `--use-pre-llm`: enable prompt expansion for short prompts
- `--seed`: keep results more repeatable when other parameters match
- `--scale`: control how strongly the prompt affects the image
- `--result-mode url|base64`: choose returned result format
- `--submit-only`: submit and stop after returning a task id
- `--poll-interval`: seconds between polling attempts
- `--timeout`: overall polling timeout in seconds
- `--watermark-text`: add a visible watermark
- `--watermark-position`: `lower-right`, `lower-left`, `upper-left`, `upper-right`
- `--watermark-language`: `zh` or `en`
- `--watermark-opacity`: `0` to `1`

## Output Files

The script normally writes:

- one or more image files
- `seedream-result.json`

The JSON sidecar keeps the prompt, task id, request ids, output URLs, saved files, and task status.
