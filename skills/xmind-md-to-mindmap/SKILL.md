---
name: xmind-md-to-mindmap
description: Convert Markdown into an XMind-style mind map PNG (and optional .xmind) from the command line by reusing XMind web's own converter and official renderer (snowmonster). Use when the user wants to turn markdown into a mind map / 脑图 / 思维导图 image, export .md to PNG or .xmind, or reproduce XMind's official rendering without opening the website. Supports headings, nested/ordered task lists, blockquotes (as notes), GFM tables (spreadsheet), images, code blocks, math, and inline rich text.
---

# XMind Markdown → 思维导图图片

用官网 `app.xmind.cn` 自己的 **Markdown 转换器 + 官方布局渲染引擎（snowmonster）**，命令行把 `.md`
输出成 **官网同款** 思维导图 PNG（可选同时导出 `.xmind`）。免登录、无需打开网站。

## 什么时候用
- 用户要「Markdown 转思维导图/脑图图片」「把 md 导成导图 PNG」「导出 .xmind」。
- 需要接近 XMind 官网导出效果，而不是自己画图。

## 前置条件
- 本机有 **Google Chrome / Chromium**（脚本按路径自动查找，或设 `CHROME_PATH`）。
- **playwright-core**：首次使用在本 skill 目录执行 `npm i`（只装 playwright-core，不下载浏览器，脚本用系统 Chrome）；或全局安装 / 用 `PLAYWRIGHT_CORE` 指定路径。
- 能访问 `app.xmind.cn`（每次运行会拉取官网 chunk）。

## 快速开始
```bash
node scripts/md2mindmap.mjs input.md                 # -> input.png
node scripts/md2mindmap.mjs input.md -o out.png
node scripts/md2mindmap.mjs input.md --xmind out.xmind
node scripts/md2mindmap.mjs - -o out.png < input.md      # 读 stdin
node scripts/md2mindmap.mjs input.md --width 2000 --height 1200
node scripts/md2mindmap.mjs input.md --headful           # 调试：显示浏览器
```
输出：PNG 绝对/相对路径打印到 stdout，进度信息在 stderr。

## 原理（一句话）
无头 Chrome 打开官网**公开登录页**当运行时宿主（有 `window.Manifests`/Vue 等全局，但有登录墙），
在页面里动态 `import` 官方 chunk 并调用：
`importMarkdownV3(md) → .xmind` → `openDocWithInject → doc` → `renderThumbnail(doc,{size}) → PNG`。
官网 chunk 名带内容哈希，脚本会**自动从 entry 解析最新文件名**。
完整调用链、导出符号、登录墙与 postMessage 协议、chunk 发现流程、排错：见
[`references/pipeline.md`](references/pipeline.md)。

## 关键选项
- `-o/--out`：输出 PNG 路径（默认 = 输入同名的 `.png`）。
- `--xmind`：额外导出 `.xmind`。
- `--width/--height`：输出像素（默认 1600×1000）。宽高比越接近内容比例，留白越少。
- `--headful`：非无头，排错用。
- 环境变量：`CHROME_PATH`、`XMIND_ORIGIN`、`PLAYWRIGHT_CORE`、`MD2MM_DEBUG=1`、
  `MD2MM_MARKDOWN_V3`/`MD2MM_IMPORT_FILE`/`MD2MM_SNOWMONSTER`、`MD2MM_NO_DISCOVER=1`。

## 注意
- **没有公开的 md→图片 HTTP 接口**：官网转换是纯前端；本工具是直接复用其前端转换器+渲染器。
- Markdown 里的 `![]()` 若是**外链图片**，官网渲染不会内嵌（节点会留空）。
- 官方发版改了 chunk/全局导致渲染为 null 时：`MD2MM_DEBUG=1` 看解析结果，或用 `MD2MM_*` 手动指定。
