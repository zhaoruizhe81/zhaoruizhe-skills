#!/usr/bin/env node
/**
 * h2s build — assemble extracted text layers plus a text-free background into a
 * flat .sketch file (one artboard per page). Flat by design: nested groups get
 * clipped by some importers, which drops vertical headline glyphs.
 *
 *   node build-sketch.cjs manifest.json out.sketch
 */
const fs = require("fs");
const path = require("path");

function loadSC() {
  const tries = ["sketch-constructor", "/tmp/node_modules/sketch-constructor"];
  for (const t of tries) {
    try {
      return { mod: require(t), dir: path.dirname(require.resolve(t + "/package.json")) };
    } catch (e) {
      /* keep looking */
    }
  }
  throw new Error("sketch-constructor not found. Run: npm i sketch-constructor");
}

// sketch-constructor streams JSON through JsonStreamStringify, which slices on
// byte boundaries and corrupts multi-byte UTF-8 in non-ASCII layer names. The
// importer then rejects the file. Swap it for JSON.stringify in place.
function ensurePatched(dir) {
  const f = path.join(dir, "models/Sketch/Sketch.js");
  if (!fs.existsSync(f)) return;
  const src = fs.readFileSync(f, "utf8");
  if (!/new JsonStreamStringify\(/.test(src)) return;
  try {
    fs.writeFileSync(
      f,
      src.replace(/new JsonStreamStringify\(([A-Za-z0-9_.]+)\)/g, "JSON.stringify($1)")
    );
    console.warn("[h2s] patched sketch-constructor UTF-8 bug -> " + f);
  } catch (e) {
    console.warn("[h2s] could not patch " + f + ": " + e.message);
    console.warn("[h2s] replace `new JsonStreamStringify(x)` with `JSON.stringify(x)` manually.");
  }
}

const rect = (x, y, w, h) => ({
  _class: "rect",
  x,
  y,
  width: w,
  height: h,
  constrainProportions: false,
});

function mapFont(ff, fw, cfg) {
  const weight = parseInt(fw, 10) || 400;
  const family = String(ff || "");
  const mono = (cfg.font && cfg.font.mono) || "Menlo";
  const cjk = (cfg.font && cfg.font.cjk) || "PingFangSC";

  if (/mono|Menlo|Courier|Consolas|code/i.test(family)) {
    return mono + (weight >= 600 ? "-Bold" : "-Regular");
  }
  const step =
    weight >= 800 ? "Heavy" : weight >= 600 ? "Semibold" : weight >= 500 ? "Medium" : "Regular";
  return cjk + "-" + step;
}

function align(a) {
  if (a === "center") return "center";
  if (a === "right" || a === "end") return "right";
  return "left";
}

function safeName(s, fallback) {
  const out = String(s || "")
    .replace(/\s+/g, "_")
    .replace(/[^\w\u4e00-\u9fa5.-]/g, "")
    .slice(0, 36);
  return out || fallback;
}

function main() {
  const manifestPath = process.argv[2];
  const outPath = process.argv[3];
  if (!manifestPath || !outPath) {
    console.error("usage: node build-sketch.cjs manifest.json out.sketch");
    process.exit(1);
  }

  const cfg = JSON.parse(fs.readFileSync(manifestPath, "utf8"));
  const canvas = cfg.canvas || {};
  const W = canvas.w || 1440;
  const H = canvas.h || 900;
  const BG = canvas.bg || "#ffffff";
  const gap = cfg.gap == null ? 160 : cfg.gap;
  const splitMin = cfg.splitMinSize == null ? 28 : cfg.splitMinSize;
  const splitMax = cfg.splitMaxChars == null ? 6 : cfg.splitMaxChars;
  const pages = cfg.pages || [];
  if (!pages.length) throw new Error("manifest.pages is empty");

  const { mod: SC, dir } = loadSC();
  ensurePatched(dir);
  const { Sketch, Page, Artboard, Text, Color, Bitmap } = SC;

  const baseDir = path.dirname(path.resolve(manifestPath));
  const resolveAsset = (p) => (path.isAbsolute(p) ? p : path.resolve(baseDir, p));

  const sketch = new Sketch();
  const page = new Page({ name: cfg.pageName || "Page 1" });
  sketch.addPage(page);

  let layerCount = 0;

  function emitText(parent, o) {
    const t = new Text({
      name: o.name,
      frame: rect(o.x, o.y, o.w, o.h),
      string: o.str,
      fontName: o.font,
      fontSize: o.fs,
      alignment: o.alignment,
      verticalAlignment: "top",
      color: o.color,
    });
    // Text() forwards a flat config into Style.TextStyle, but that path silently
    // falls back to Helvetica 16 black. Overwrite the encoded attributes directly.
    const enc = t.style && t.style.textStyle && t.style.textStyle.encodedAttributes;
    if (enc) {
      enc.MSAttributedStringFontAttribute = {
        _class: "fontDescriptor",
        attributes: { name: o.font, size: o.fs },
      };
      enc.MSAttributedStringColorAttribute = new Color(o.color);
    }
    t.textBehaviour = o.behaviour;
    if (o.kerning) {
      try {
        t.style.textStyle.kerning = o.kerning;
      } catch (e) {
        /* kerning is cosmetic */
      }
    }
    parent.addLayer(t);
    layerCount++;
  }

  pages.forEach((p, i) => {
    const textPath = resolveAsset(p.text);
    const bgPath = p.bg ? resolveAsset(p.bg) : null;
    const data = JSON.parse(fs.readFileSync(textPath, "utf8"));
    const ax = p.x == null ? i * (W + gap) : p.x;
    const ay = p.y == null ? 0 : p.y;

    const ab = new Artboard({
      name: p.name || "Page " + (i + 1),
      frame: rect(ax, ay, W, H),
      hasBackgroundColor: true,
      backgroundColor: new Color(p.bgColor || BG),
    });
    page.addArtboard(ab);

    if (bgPath && fs.existsSync(bgPath)) {
      ab.addLayer(new Bitmap({ name: "screen", filePath: bgPath, frame: rect(0, 0, W, H) }));
      layerCount++;
    } else if (p.bg) {
      console.warn("[h2s] missing background: " + bgPath);
    }

    for (const it of data.texts || []) {
      const str = String(it.t || "");
      if (!str.trim()) continue;

      const isVertical = !!it.vertical;
      const fsVal = Number(it.fs) || 16;
      const ls = parseFloat(it.ls) || 0;
      const font = mapFont(it.ff, it.fw, cfg);
      const color = it.color || "#ffffff";
      const cls = safeName(it.cls, "text");

      const tw = isVertical
        ? Math.max(Number(it.w) || 0, fsVal)
        : Math.max((Number(it.w) || 0) + 4, fsVal);
      const th = isVertical
        ? Math.max(Number(it.h) || 0, fsVal * 0.9)
        : Math.max((Number(it.h) || 0) + 2, fsVal * 1.3);

      // CJK headings of two or three glyphs can render with a collapsed advance
      // in some importers, overlapping their own characters. Emitting one Text
      // per glyph sidesteps the shaper entirely.
      const chars = Array.from(str);
      if (!isVertical && fsVal >= splitMin && chars.length >= 2 && chars.length <= splitMax) {
        const cw = (Number(it.w) || fsVal * chars.length) / chars.length;
        chars.forEach((ch, k) => {
          emitText(ab, {
            name: cls + "_" + k,
            x: (Number(it.x) || 0) + k * cw,
            y: Number(it.y) || 0,
            w: cw + 2,
            h: th,
            str: ch,
            font,
            fs: fsVal,
            color,
            alignment: "left",
            behaviour: 0,
          });
        });
        continue;
      }

      const singleLine = (Number(it.h) || fsVal) / (fsVal * 1.4) < 1.7;
      emitText(ab, {
        name: cls,
        x: Number(it.x) || 0,
        y: Number(it.y) || 0,
        w: tw,
        h: th,
        str,
        font,
        fs: fsVal,
        color,
        alignment: isVertical ? "center" : align(it.ta),
        behaviour: isVertical || singleLine ? 0 : 1,
        kerning: isVertical ? 0 : ls,
      });
    }
  });

  return sketch
    .build(outPath, 6)
    .then(() => {
      console.log(
        JSON.stringify({
          out: outPath,
          bytes: fs.statSync(outPath).size,
          pages: pages.length,
          layers: layerCount,
        })
      );
    })
    .catch((e) => {
      console.error(e);
      process.exit(1);
    });
}

main();
