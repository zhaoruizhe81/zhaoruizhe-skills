---
name: unsplash-download
description: Search and download photos from Unsplash to a local folder with a repeatable CLI workflow. Use when Codex needs to handle requests like "download Unsplash images", "search Unsplash for campus photos", "从 Unsplash 下载图片", "搜几张猫咪图保存到本地", or when a user wants keyword-based photo download, direct photo-id download, resized exports, and local attribution/manifest sidecar files.
---

# Unsplash Download

Download Unsplash photos with a local CLI that handles search, pagination, optional resizing, local file naming, and sidecar metadata. Prefer the bundled script over ad hoc one-off code so the workflow stays consistent and the output includes attribution details.

## Quick Start

- If this machine already has `UNSPLASH_ACCESS_KEY` in the shell profile such as `~/.zshenv`, run the script directly with no extra setup.
- Run `python "<skill-path>/scripts/unsplash_download.py" --query "campus night" --count 5 --output-dir "/absolute/path/output"` for keyword downloads.
- Run `python "<skill-path>/scripts/unsplash_download.py" --photo-id "<unsplash-photo-id>" --output-dir "/absolute/path/output"` when the user already knows the photo id.
- Read `references/cli.md` for more command recipes.

## Workflow

1. Decide whether the request is search-based or photo-id based.
   - Use `--query` for prompts like "下载 5 张校园风景图".
   - Use `--photo-id` when the user gives a specific Unsplash photo id.
2. Confirm or choose the output folder.
3. Set download shape.
   - Use `--count` for the number of files.
   - Use `--orientation landscape|portrait|squarish` when composition matters.
   - Use `--width`, `--height`, `--format`, and `--quality` only when a resized export is actually needed.
4. Run the bundled script.
5. Return the saved files and mention the sidecar files:
   - `unsplash-manifest.json`
   - `unsplash-attribution.txt`

## Environment

- Require `UNSPLASH_ACCESS_KEY` for public search and download.
- This machine may already have `UNSPLASH_ACCESS_KEY` configured in the local shell profile such as `~/.zshenv` for personal use.
- Do not require `UNSPLASH_SECRET_KEY` for this skill's normal workflow; public image search/download only needs the access key.
- `UNSPLASH_SECRET_KEY` can still exist locally for future private integrations, but the current download script does not read it.
- Do not ask the user to paste secrets into chat again. Prefer local environment variables.

Example shell setup:

```bash
export UNSPLASH_ACCESS_KEY="your_access_key_here"
```

## Common Commands

Basic search download:

```bash
python "<skill-path>/scripts/unsplash_download.py" \
  --query "smart campus" \
  --count 6 \
  --output-dir "/absolute/path/output"
```

Landscape images resized to width 1600:

```bash
python "<skill-path>/scripts/unsplash_download.py" \
  --query "university library" \
  --count 4 \
  --orientation landscape \
  --width 1600 \
  --format jpg \
  --output-dir "/absolute/path/output"
```

Direct photo id download:

```bash
python "<skill-path>/scripts/unsplash_download.py" \
  --photo-id "abc123def45" \
  --output-dir "/absolute/path/output"
```

Preview matches without downloading:

```bash
python "<skill-path>/scripts/unsplash_download.py" \
  --query "campus sunset" \
  --count 3 \
  --dry-run
```

## Practical Notes

- The script writes sidecar files by default so the photographer and source links stay attached to the downloaded set.
- The script triggers the Unsplash download endpoint before fetching the actual image unless `--skip-download-tracking` is explicitly used.
- Prefer `--dry-run` first when the query is broad and the user may want to inspect selections.
- Use an empty destination folder or a dedicated subfolder for each batch to keep manifests easy to read.
- If a user asks for very large batches, remember Unsplash API demo mode has a low rate limit; reduce `--count` or spread requests across runs.

## Bundled Resources

### scripts/unsplash_download.py

Search Unsplash, resolve images, trigger download tracking, download files, and write attribution metadata.

### references/cli.md

Command recipes, option notes, and guidance for selecting resize/output flags.
