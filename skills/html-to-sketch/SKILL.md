---
name: html-to-sketch
description: Convert an HTML page into a layered .sketch file whose text stays editable, then import it into Sketch, Figma, or 即时设计 (js.design). Use when the user wants a coded web page turned into a design file, asks to "HTML 转 Sketch / 转 Figma / 导入即时设计 / 网页转设计稿", needs handoff mockups with selectable text instead of flat screenshots, or wants several pages stacked as artboards in one file. Produces one artboard per page with real text layers over a text-free background render.
---

# HTML to Sketch

Turn a rendered HTML page into a `.sketch` file with **real, editable text layers** sitting on a text-free background render. `.sketch` is the one format that both Figma (native importer) and 即时设计 accept, so the output is portable.

## What this does and does not do

It produces a faithful **visual** replica with editable copy: every text run becomes a `Text` layer at its measured position; everything else — gradients, glows, blur, masks, photos, borders — stays baked into a single background PNG per page.

It does **not** rebuild CSS boxes as vector shapes. If the user needs every rectangle and gradient as an editable vector layer, that is a different problem; tell them plainly rather than shipping a pile of empty shapes.

## Install

```bash
npm i sketch-constructor
```

`extract.cjs` needs only Node and Chrome. Chrome is auto-detected on macOS/Linux; override with `--chrome /path/to/chrome` or `CHROME_PATH`.

## Quick start

1. Render a text-free background for each page (the layout, images and borders stay):

```bash
node scripts/extract.cjs shot --root ./site --page p1.html --out ./out/bg-p1.png
```

2. Extract the text layers as JSON:

```bash
node scripts/extract.cjs text --root ./site --page p1.html --out ./out/p1.json
```

3. Describe the file in a manifest and build it:

```json
{
  "canvas": { "w": 1440, "h": 900, "bg": "#04070a" },
  "gap": 160,
  "pages": [
    { "name": "01 Hero", "text": "p1.json", "bg": "bg-p1.png" },
    { "name": "02 Roster", "text": "p2.json", "bg": "bg-p2.png" }
  ]
}
```

```bash
node scripts/build-sketch.cjs manifest.json out.sketch
```

Artboards are laid out left to right at `x = i * (w + gap)`; set `x`/`y` on a page to override. Paths in the manifest resolve relative to the manifest file.

## How it works

`extract.cjs` boots a throwaway static server so the harness and the target page share an origin (cross-origin `iframe.contentDocument` is `null`), drives headless Chrome, and either captures a screenshot or scrapes a JSON payload out of the DOM.

Text geometry comes from `Range.getBoundingClientRect()`, not from CSS boxes — so flex, grid, absolute positioning and transformed layouts all measure correctly. Horizontal runs are measured as one rect per text node; vertical (`writing-mode: vertical-*`) runs are measured glyph by glyph, because a whole-column rect cannot be laid out as one horizontal text layer.

`build-sketch.cjs` emits **flat** artboards: every text layer is parented directly to its artboard with absolute coordinates. Nested `group` layers are deliberately avoided — several importers silently drop children whose relative offset lands outside the parent's bounds, which shows up as missing glyphs in vertical headlines.

## Constraints worth knowing before you start

Text colour must not be `transparent`. Gradient-clipped headings (`background-clip: text`) report `rgba(0,0,0,0)`; the extractor recovers the first opaque stop so the glyph stays visible, which means a gradient headline becomes a flat colour. If the gradient matters, leave that heading in the background render instead of exporting it as text.

Backgrounds must be text-free. Screenshotting the live page and then stacking text on top double-prints every word. `shot` mode injects `color: transparent` plus `background-clip` suppression before capture — always use it, never a plain screenshot.

One Text per glyph for large headings. Some CJK pairs render with a collapsed advance inside 即时设计, overlapping their own characters, regardless of font, size, kerning or frame width. Any horizontal run at `>= 28px` with 2–6 characters is split into one layer per glyph. Tune with `splitMinSize` / `splitMaxChars` in the manifest.

Fonts resolve to installed PostScript names (`PingFangSC-Heavy`, `Menlo-Bold`, …). Override per file with `"font": { "cjk": "SongtiSC", "mono": "SFMono-Regular" }`. A name that is not installed falls back silently at import time — check one headline after importing.

## After building

Import the `.sketch` by dragging it into Figma, Sketch, or 即时设计's workspace. Verify three things before declaring it done: a vertical headline shows every glyph, a multiline paragraph wraps instead of clipping, and no word appears twice.

Read `references/pitfalls.md` when something looks wrong after import — it maps each symptom to its cause.
