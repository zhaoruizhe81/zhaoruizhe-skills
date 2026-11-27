#!/usr/bin/env node
/**
 * h2s extract — pull text layers or a text-free background out of an HTML page.
 *
 * Boots a throwaway static server so the harness and the target page share an
 * origin (cross-origin iframe.contentDocument is null), then drives headless
 * Chrome. Chrome is spawned asynchronously: blocking the event loop inside the
 * listen callback would starve the very server Chrome is waiting on.
 *
 *   node extract.cjs text --page index.html --out p1.json
 *   node extract.cjs shot --page index.html --out bg-p1.png --scale 2
 */
const http = require("http");
const fs = require("fs");
const path = require("path");
const os = require("os");
const { execFile } = require("child_process");

const MIME = {
  ".html": "text/html; charset=utf-8",
  ".htm": "text/html; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".json": "application/json; charset=utf-8",
  ".png": "image/png",
  ".jpg": "image/jpeg",
  ".jpeg": "image/jpeg",
  ".webp": "image/webp",
  ".gif": "image/gif",
  ".svg": "image/svg+xml",
  ".woff": "font/woff",
  ".woff2": "font/woff2",
  ".ttf": "font/ttf",
};

const FLAGS = {
  "--root": "root",
  "--page": "page",
  "--out": "out",
  "--mode": "mode",
  "--w": "w",
  "--h": "h",
  "--scale": "scale",
  "--chrome": "chrome",
  "--root-sel": "rootSel",
  "--port": "port",
};

function parseArgs(argv) {
  const a = { root: ".", w: 1440, h: 900, scale: 1, rootSel: ".frame" };
  // Leading positional selects the mode: `extract.cjs shot --page ...`
  if (argv[0] === "text" || argv[0] === "shot") a.mode = argv[0];
  for (let i = 0; i < argv.length; i++) {
    const flag = argv[i];
    const key = FLAGS[flag];
    if (!key) continue;
    const value = argv[i + 1];
    a[key] = /^(--w|--h|--scale|--port)$/.test(flag) ? Number(value) : value;
    i++;
  }
  return a;
}

function findChrome(explicit) {
  if (explicit) return explicit;
  if (process.env.CHROME_PATH) return process.env.CHROME_PATH;
  const candidates = [
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    "/usr/bin/google-chrome",
    "/usr/bin/chromium",
    "/usr/bin/chromium-browser",
    "/snap/bin/chromium",
  ];
  for (const c of candidates) if (fs.existsSync(c)) return c;
  throw new Error("Chrome not found. Pass --chrome <path> or set CHROME_PATH.");
}

function serve(root, harnessPath) {
  const resolvedRoot = path.resolve(root);
  return http.createServer((req, res) => {
    const urlPath = decodeURIComponent(req.url.split("?")[0]);
    if (urlPath === "/__h2s.html") {
      res.writeHead(200, { "Content-Type": "text/html; charset=utf-8" });
      return res.end(fs.readFileSync(harnessPath));
    }
    const file = path.resolve(resolvedRoot, "." + urlPath);
    if (!file.startsWith(resolvedRoot)) {
      res.writeHead(403);
      return res.end("forbidden");
    }
    fs.readFile(file, (err, buf) => {
      if (err) {
        res.writeHead(404);
        return res.end("not found");
      }
      res.writeHead(200, {
        "Content-Type": MIME[path.extname(file).toLowerCase()] || "application/octet-stream",
      });
      res.end(buf);
    });
  });
}

function decodeEntities(s) {
  return s
    .replace(/&quot;/g, '"')
    .replace(/&#39;/g, "'")
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">")
    .replace(/&amp;/g, "&");
}

function main() {
  const a = parseArgs(process.argv.slice(2));
  const mode = a.mode || "text";
  if (!a.page) throw new Error("--page <relative.html> is required");
  if (!a.out) throw new Error("--out <path> is required");

  const chrome = findChrome(a.chrome);
  const harnessPath = path.join(__dirname, "harness.html");
  const userDataDir = path.join(os.tmpdir(), "h2s-" + process.pid + "-" + Date.now());
  fs.mkdirSync(a.out.replace(/[^/]+$/, "") || ".", { recursive: true });

  const server = serve(a.root, harnessPath);

  const cleanup = () => {
    server.close();
    fs.rmSync(userDataDir, { recursive: true, force: true });
  };

  server.listen(a.port || 0, "127.0.0.1", () => {
    const port = server.address().port;
    const pageUrl = a.page.startsWith("http") ? a.page : "/" + a.page.replace(/^\/+/, "");
    const qs = new URLSearchParams({
      url: pageUrl,
      mode,
      w: String(a.w),
      h: String(a.h),
      root: a.rootSel,
    });
    const target = `http://127.0.0.1:${port}/__h2s.html?${qs.toString()}`;

    const base = [
      "--headless=new",
      "--disable-gpu",
      "--hide-scrollbars",
      "--no-sandbox",
      "--allow-file-access-from-files",
      "--user-data-dir=" + userDataDir,
      "--virtual-time-budget=20000",
    ];
    const opts = { maxBuffer: 256 * 1024 * 1024, encoding: "utf8", timeout: 180000 };

    if (mode === "shot") {
      const args = base.concat(["--window-size=" + a.w + "," + a.h, "--screenshot=" + a.out]);
      if (a.scale && a.scale !== 1) args.push("--force-device-scale-factor=" + a.scale);
      args.push(target);
      return execFile(chrome, args, opts, (err) => {
        cleanup();
        if (err) {
          console.error("[h2s] chrome failed: " + err.message);
          process.exit(1);
        }
        console.log(JSON.stringify({ out: a.out, mode, bytes: fs.statSync(a.out).size }));
      });
    }

    execFile(chrome, base.concat(["--dump-dom", target]), opts, (err, stdout, stderr) => {
      cleanup();
      if (err) {
        console.error("[h2s] chrome failed: " + err.message);
        if (stderr) console.error(stderr.slice(0, 600));
        process.exit(1);
      }
      const m = stdout.match(/JSONMARK([\s\S]*?)JSONEND/);
      if (!m) {
        const title = (stdout.match(/<title>([^<]*)<\/title>/) || [])[1] || "unknown";
        console.error("[h2s] no payload in DOM; harness reported: " + title);
        process.exit(1);
      }
      let data;
      try {
        data = JSON.parse(decodeEntities(m[1]));
      } catch (e) {
        console.error("[h2s] payload was not valid JSON: " + e.message);
        process.exit(1);
      }
      fs.writeFileSync(a.out, JSON.stringify(data, null, 1));
      console.log(JSON.stringify({ out: a.out, mode, layers: data.texts.length }));
    });
  });
}

main();
