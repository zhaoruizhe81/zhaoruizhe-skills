# Pitfalls

Symptom → cause → fix. Every entry below was hit in practice, not theorised.

## Import fails with "file parse error" / 文件解析失败

The `.sketch` archive's JSON is not valid UTF-8. `sketch-constructor` serialises pages through `JsonStreamStringify`, which slices its output on byte boundaries and cuts multi-byte characters in half — non-ASCII layer names become invalid bytes and the importer rejects the archive.

`build-sketch.cjs` patches this automatically on first run (`new JsonStreamStringify(x)` → `JSON.stringify(x)`) and prints a warning when it does. If the dependency directory is read-only, apply the replacement by hand in `models/Sketch/Sketch.js`.

## Import reports success but the canvas is empty

You imported a `.fig`, not a `.sketch`. Figma's binary `.fig` container uses an internal schema version that 即时设计 reports as "导入完成" while silently producing zero layers (observed with `fig-kiwi` v106). Only `.sketch` is reliably readable by both Figma and 即时设计.

## All text renders black

Two separate causes, both in how the layer is constructed:

`Color` takes a CSS string or `{r, g, b, a}` in 0–1 floats, **not** `{red, green, blue}` in 0–255. Passing `{red: 4, green: 7, blue: 10}` fails to parse and yields black.

`Text({ fontName, fontSize, color })` builds `Style.TextStyle` from those fields, but the resulting `style.textStyle.encodedAttributes` still lands on `Helvetica / 16 / black`. The `attributedString` branch accepts the values while the `style` branch does not — and importers read `style`. Always overwrite `encodedAttributes` after construction; `build-sketch.cjs` does this in `emitText`.

## Text sits lower than the design, overlapping the body copy

Wrong measurement source. Libraries that compute positions from CSS boxes (or from `html2asketch`-style layer accumulation) add an extra offset for `writing-mode: vertical-rl` — a headline that starts at `y=118` gets reported at `y=281`, pushing it 163px down into the paragraph.

Measure with `Range.getBoundingClientRect()` instead. That is what `harness.html` does, and it also handles flex/grid reflow, transforms and line wrapping for free.

## A vertical headline shows only its first one or two glyphs

Nested `group` layers are clipped to the parent's frame by some importers. A vertical column measured as one tall layer, then split into per-glyph children, produces children whose relative `y` exceeds the parent's height — those children are dropped rather than clipped.

Parent every text layer directly to the artboard using absolute coordinates. `build-sketch.cjs` never emits groups for this reason.

## Every word appears twice, slightly offset

The background PNG was captured from the live page, so it already contains the text. Stacking text layers on top double-prints everything.

Use `extract.cjs shot`, which injects `color: transparent`, kills `text-shadow`, and disables `background-image` on any element using `background-clip: text` before capture. A plain screenshot will always double-print.

## Two-glyph heading renders with its characters overlapping

Certain CJK pairs render with a collapsed advance inside 即时设计 — both glyphs land within roughly half the expected width, so they visually merge. Confirmed independent of font family (five tested), font size (32/40/58), `kerning` (+12 / 0 / −3.84), frame width, and `textBehaviour`.

Emit one `Text` per glyph for horizontal runs of `>= 28px` and 2–6 characters. `build-sketch.cjs` does this by default; adjust with `splitMinSize` and `splitMaxChars`.

## A gradient headline is invisible

Gradient text is styled `background-clip: text; color: transparent`, so the computed colour is `rgba(0,0,0,0)` and the layer is exported fully transparent. The extractor recovers the first opaque stop from `background-image`.

The tradeoff is honest: the heading comes out a **flat colour**, not a gradient. If the gradient is part of the design, exclude that element from text extraction and let the background render carry it.

## A paragraph is clipped to one line, or a single line wraps into two

`textBehaviour` controls this and the values are not interchangeable:

`0` is auto-width — the frame's width is ignored and nothing wraps. Use it for single-line runs and for individual glyphs.

`1` is fixed-width with auto height — wraps normally. Use it for multi-line paragraphs.

`2` (the library default) is fixed width **and** fixed height, so overflow is clipped. Never leave it in place.

Decide with `height / (fontSize * 1.4)`: below ~1.7 lines it is a single-line run.

## Fonts look wrong after import

Names must be the installed PostScript name — `PingFangSC-Heavy`, `PingFangSC-Semibold`, `Menlo-Bold` — not the CSS family (`PingFang SC`) plus a numeric weight. A missing name falls back silently, so the file imports cleanly and simply looks wrong. Override the family per manifest with `"font": { "cjk": "...", "mono": "..." }` and eyeball one headline after importing.
