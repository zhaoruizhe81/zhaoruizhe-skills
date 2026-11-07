# Unsplash Download CLI

## Environment

- Required: `UNSPLASH_ACCESS_KEY`
- Optional override: `--access-key`
- If this machine already has the variable in a shell profile such as `~/.zshenv`, the CLI can usually run without any extra setup.

Public search and download use the access key only. The secret key is not required for this skill.

## Main Modes

Search by keyword:

```bash
python "<skill-path>/scripts/unsplash_download.py" \
  --query "campus lake" \
  --count 5 \
  --output-dir "/absolute/path/output"
```

Download by photo id:

```bash
python "<skill-path>/scripts/unsplash_download.py" \
  --photo-id "abc123def45" \
  --output-dir "/absolute/path/output"
```

## Helpful Flags

- `--count`: number of photos to fetch for search mode
- `--page`: first search page to read from
- `--orientation`: `landscape`, `portrait`, or `squarish`
- `--order-by`: `relevant` or `latest`
- `--content-filter`: `low` or `high`
- `--width`, `--height`: apply Imgix resize parameters
- `--format`: `jpg`, `png`, or `webp`
- `--quality`: output quality hint for Imgix-compatible formats
- `--url-kind`: choose from `raw`, `full`, `regular`, `small`, or `thumb`
- `--dry-run`: print selected photos without downloading files
- `--skip-sidecar-files`: skip `unsplash-manifest.json` and `unsplash-attribution.txt`
- `--skip-download-tracking`: skip the download event call if the user explicitly wants that behavior

## Output Files

Downloaded batches normally contain:

- image files
- `unsplash-manifest.json`
- `unsplash-attribution.txt`

The manifest keeps ids, creator names, source URLs, and saved file paths. The attribution file is a quick human-readable sidecar.

## Suggested Usage Patterns

Use `--dry-run` first for broad or subjective queries.

Use `--width` without `--height` when the user wants a predictable maximum width and is fine with aspect ratio preservation.

Use `--photo-id` when the user already picked a photo from Unsplash and only needs a local copy plus sidecar metadata.

Use a dedicated output folder per batch so repeated runs do not mix unrelated manifests.
