---
name: snippet-to-image
description: Render code snippets, ANSI-colored terminal output, or plain text directly into PNG images for reports, papers, docs, and other places where the user would otherwise take a screenshot. Use when you need to turn a `.py`, `.txt`, Markdown snippet, config block, terminal log, or pasted text into a clean image; when the user asks to “把代码生成图片”, “不要截图，直接导出代码图”, “把这段文本/代码渲染成 PNG”, “模拟终端输出”, or wants consistent code-image styling with light/dark themes, ANSI terminal colors, zero-margin terminal captures, and Chinese (CJK) text support — prefer it over manual screenshots for report inserts and batchable image export.
---

# Snippet To Image

## Overview

Use this skill to render code, plain text, or ANSI terminal content into PNG images with a repeatable local workflow. Prefer it over manual screenshots when the user needs report-ready inserts, consistent styling, or batchable output. Output is **zero-margin, hard-coded** (content cropped flush to the edges on all four sides). The renderer has no margin flags by design — never bake a margin into the PNG.

Choose the renderer by content semantics, not only by file extension:

- Code and config with syntax structure: use the lexer-based renderer.
- Plain prose or logs without ANSI color escapes: use the plain-text renderer.
- Terminal output that already contains ANSI color sequences: use the ANSI renderer.

When unsure, read `references/renderer-selection.md` first.

## Quick Start

Use the bundled script at `scripts/render_snippet.py`.

Install dependencies first if needed:

```bash
pip install Pygments Pillow rich
```

Render a Python snippet from inline text:

```bash
python3 scripts/render_snippet.py \
  --text $'def hello(name):\n    print(f"Hello, {name}")\n' \
  --lexer python \
  --output /tmp/hello.png
```

Render a source file and infer the lexer from the filename:

```bash
python3 scripts/render_snippet.py \
  --input /path/to/example.py \
  --output /tmp/example.png
```

Render plain Chinese text without syntax highlighting:

```bash
python3 scripts/render_snippet.py \
  --text $'实验结果表明，该算法在小样本条件下仍可稳定收敛。\n第二行。' \
  --plain-text \
  --output /tmp/paragraph.png
```

If the shell input contains literal escape text such as `\n`, decode it explicitly:

```bash
python3 scripts/render_snippet.py \
  --text '第一行\n第二行' \
  --plain-text \
  --decode-escapes \
  --output /tmp/paragraph.png
```

Render ANSI-colored terminal output:

```bash
python3 scripts/render_snippet.py \
  --text '\033[32mSUCCESS\033[0m build finished\n\033[31mERROR\033[0m failed to upload artifact' \
  --ansi \
  --decode-escapes \
  --theme dark \
  --scale 2 \
  --output /tmp/terminal.png
```

Render a plain terminal log without ANSI colors:

```bash
python3 scripts/render_snippet.py \
  --input /path/to/ip_addr.txt \
  --plain-text \
  --theme dark \
  --output /tmp/ip_addr.png
```

## Workflow

1. Choose one input mode: `--input` for an existing file or `--text` for inline content.
2. Choose the renderer before styling:
   - Use `--lexer <name>` for syntax-highlighted code.
   - Use `--ansi` for terminal output with ANSI color sequences.
   - Use `--plain-text` for prose, notes, or unhighlighted blocks.
   - If `--input` is used and no lexer is given, let the script infer from the filename and fall back to plain text if inference fails.
3. Match the renderer to the actual artifact:
   - `.py`, `.js`, `.java`, `.json`, `.yaml`, `.xml` and similar source/config files: prefer `--lexer` or filename inference.
   - Terminal transcript copied from shell but without color escape sequences: prefer `--plain-text`, usually with `--theme dark`.
   - `grep --color=always`, `ls --color=always`, colored CI output, or text containing `\x1b[`/`\033[` escapes: prefer `--ansi`.
   - Chinese paragraphs, report正文, or generic notes: prefer `--plain-text`, usually with `--theme light`.
   - If the user wants a screenshot-like terminal look, do not use `--lexer` just because the file extension is `.txt`; pick `--plain-text` or `--ansi` based on whether ANSI colors are present.
4. Choose optional styling:
   - `--theme light|dark`
   - `--font <family>`
   - `--font-size <n>`
   - `--line-numbers`
   - `--decode-escapes` when `--text` contains literal `\n` or `\t`
   - `--scale <n>` and `--dpi <n>` for sharper report exports
   - Margin: not configurable. The renderer always outputs zero-margin (see Pitfalls); spacing around the image belongs to the surrounding document, not the PNG.
5. Write the final PNG with `--output`.

## Renderer Selection

Use this decision rule:

1. If the content contains real ANSI escape sequences, use `--ansi`.
2. Else if the content is source code or structured config and syntax coloring helps comprehension, use `--lexer` or filename inference.
3. Else use `--plain-text`.

Practical defaults:

- Report code snippets: `--lexer`, theme usually `light`
- Report terminal screenshots: `--plain-text --theme dark`
- Report terminal screenshots with true color output: `--ansi --theme dark`
- Chinese prose or explanatory blocks: `--plain-text --theme light`

Read `references/renderer-selection.md` when the content mixes code, logs, and terminal output.

## Defaults

- Output format is PNG only.
- Default theme is `light`.
- Line numbers are off unless `--line-numbers` is supplied.
- Default scale is `1.0`; use `2` or `3` when the image will be resized in Word or PDF.
- Default DPI metadata is `300`.
- Default margin is zero, and this is **hard-coded**: the script always crops the output flush to the content on all four sides. There are no `--pad`/`--tight`/`--zero-margin` flags anymore — passing them is an argument error. Reason: a baked-in margin cannot be removed from the PNG afterwards, while the surrounding document can always add its own spacing.
- The script probes local fonts with `fc-list`.
- When the content includes Chinese, the script prefers installed CJK-capable fonts before falling back to `Hiragino Sans GB`.
- When the fallback font is not truly monospace, the script warns that mixed Chinese and ASCII alignment may drift.

## Font Guidance

Prefer the script defaults unless the user explicitly wants a specific font. The fallback order is tuned for this machine class:

- CJK-first candidates for Chinese content: `Sarasa Mono SC`, `Noto Sans Mono CJK SC`, `Source Han Mono SC`, `LXGW WenKai Mono`, `Hiragino Sans GB`, `PingFang SC`
- Latin-first monospace candidates for code-only content: `Menlo`, `Monaco`, `SF Mono`, `DejaVu Sans Mono`

If the user requests a specific font with `--font`, the script validates that the family is installed. If not, it fails with a clear error instead of silently substituting another family.

**Known trap — `--font` + `--lexer`:** on macOS, Pygments resolves code-render fonts by font *filename*, so families whose file is a differently-named `.ttc` collection fail with `not compatible with Pygments image rendering` — concretely, `--font "Sarasa Mono SC"` fails with `--lexer` on this machine. The default auto-selection already skips such fonts for code renders (it falls back to e.g. `Hiragino Sans GB`), so only hand-passing the font triggers this. `Sarasa Mono SC` remains the recommended font for `--plain-text` and `--ansi` renders, including CJK terminal tables.

### Terminal tables with Chinese (CJK)

For a terminal table that contains Chinese (e.g. a `+----+` MySQL/`\G` dump with CJK columns), every CJK glyph must be exactly **2×** the ASCII cell width, or the `|` columns drift. `Sarasa Mono SC` is the recommended font here — it is a true CJK monospace, so `|` rules and CJK cells line up flush. Avoid Latin-only fonts like `Menlo` (no CJK glyphs → tofu) and proportional CJK fonts like `PingFang SC` / `Hiragino Sans GB` (non-monospace → drift). The script warns when the loaded face is not monospace or lacks CJK glyphs.

### Font collections (.ttc) and sub-face selection

When `fc-match` resolves a family to a TrueType Collection (`.ttc`), PIL's `ImageFont.truetype` defaults to **index 0**, which is frequently the wrong face. Concretely, on this machine `Sarasa Mono SC` resolves to `~/Library/Fonts/Sarasa-SuperTTC.ttc` (480 bundled faces), and index 0 is `Sarasa Gothic CL ExtraLight` — a **proportional** face (CJK ≈ 0.89× ASCII) that silently misaligns CJK tables. The script therefore probes the collection and selects the sub-face whose family name matches, that is monospace (and CJK = 2× ASCII when the content has CJK), preferring the `Regular` style — for Sarasa Mono SC that is **index 205**. The `Using font:` log line reports the resolved index, e.g. `Using font: Sarasa Mono SC (ttc index 205)`, so you can confirm the right face was loaded. Selection is cached per `(path, family, cjk)` so the one-time probe cost is paid only once.

## Notes

- This skill renders text directly. It does not capture IDE windows, terminal windows, or GUI screenshots.
- This skill supports repeated single renders. It does not implement directory batch processing in v1.
- For report workflows, prefer `light` theme for code and prose unless the user explicitly wants an editor-like dark image.
- For terminal-like output, prefer `dark` theme unless the user explicitly wants a white command prompt style.
- Do not fake ANSI by choosing `--lexer`; if terminal colors matter, use `--ansi`.

## Pitfalls (踩坑记录)

**Zero-margin is hard-coded — never work around it.** (2026-10 incident) While building report inserts, the agent saw what looked like end-of-line characters ("c", "{", "0") sliced in half at the right edge of dark-theme renders, and "fixed" it by passing `--pad` — violating the contract and wasting a rebuild cycle. Pixel forensics later proved the zero-margin output was **pixel-identical in ink** to the padded render: `crop_to_content()` computes the bounding box of all ink on the same canvas, so by construction it can never drop ink. The "sliced glyphs" were an optical artifact: right-edge-flush glyphs on a dark background blend with the white page when the final document is rasterized at finite DPI.

Rules derived from this:

1. Render zero-margin, always. The flags are gone from the CLI; do not re-add them or simulate margins via post-processing.
2. If flush edge glyphs look shaved in the *final document* (PDF/page render), fix it at the **document layout level** (spacing, placement, scale — the report owns spacing), never by editing the PNG.
3. To adjudicate a "is the glyph clipped?" dispute, compare the **actual delivered artifact** (the PDF/page raster), not the source PNGs — source-level comparisons cannot see what the layout pipeline does. And trust the renderer's code path first: `crop_to_content` on a fixed canvas cannot lose ink.
