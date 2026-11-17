# XMind Web「Markdown → 思维导图」逆向要点

本文件是 `xmind-md-to-mindmap` 的技术底稿，供排错与二次开发时按需阅读。完整版见同仓库
`xmind-md-reverse/XMind-Markdown导入逆向分析.md`（含逐节点 switch、标题算法、后处理、行号）。

## 目录
1. 核心调用链
2. 三个官方 chunk 的导出与作用
3. 为什么用「公开登录页」当运行时宿主
4. 服务端路由 `/markdown/:taskId` 与 postMessage 协议（要登录）
5. chunk 文件名自动发现
6. Markdown 语法 → 主题 映射速查
7. 排错

## 1. 核心调用链

```
Markdown 文本
  TextEncoder().encode(md)                        // 字节
  └─ mdmod.r.importMarkdownV3(bytes)              // -> .xmind 文件(ArrayBuffer)
       └─ ifm.o(xmind, true)  // openDocWithInject // -> { doc }（套默认主题、DataStructureVersion=3）
            └─ sm._(doc, {size:{width,height}})   // renderThumbnail // -> PNG(ArrayBuffer)
```
`sm.d(doc,{thumbnail})` 是 `packXmind`，能把 doc 重新打包成 `.xmind`（本 CLI 直接用 `importMarkdownV3` 的产物即可）。

## 2. 三个官方 chunk（导出符号）

| chunk | 导出别名（本工具用） | 真实名 | 作用 |
|---|---|---|---|
| `markdown_v3.chunk.*` | `r.importMarkdownV3` | `Kc` | Markdown 字节 → `.xmind`（ArrayBuffer） |
| `import-file.chunk.*` | `o` | `openDocWithInject`(x) | `.xmind` → `{doc,...}`，套默认主题/写版本 |
| `snowmonster-ext.chunk.*` | `_` | `renderThumbnail`(K) | doc → PNG（官方布局引擎） |
| `snowmonster-ext.chunk.*` | `d` | `packXmind`(le) | doc → `.xmind` 打包 |

- `renderThumbnail`(K，`snowmonster-ext.pretty.js` L408)：起离屏 editor → `exportSVGElementWithSize` 出整图 SVG → 光栅化成 PNG（默认 UPNG 编码）。
- `packXmind`(le，同文件 L647)：JSZip 打包 `content.json` + `Thumbnails/thumbnail.png`。

## 3. 为什么用「公开登录页」当运行时宿主

官方模块 `import` 时会依赖站点运行时全局（`window.Manifests` 图标清单、Vue、i18n 等）。
裸 HTML 页面直接 import 会报 `Cannot read properties of undefined (reading 'find')`。
用无头 Chrome 打开官网公开页 `https://app.xmind.cn/login`（未登录也不跳走，且有完整运行时），
再在其上下文 `import()` 官方 chunk 即可正常调用——**不需要登录**。

## 4. 服务端路由 `/markdown/:taskId` 与 postMessage 协议（要登录）

官网自己的转换页是个 iframe：`markdown.chunk.DtuI4T3O.js`。
- 子页 `postMessage({type:'ready', value:null, channel:taskId})` 给 `window.parent`；
- 父页发 `{type:'convert-markdown', value:<md文本>, channel:taskId}`；
- 子页回 `{type:'markdown-converted', value:{xmindFile, thumbnail}}` 或 `{type:'convert-markdown-failed', value:msg}`。
- 但该路由有登录守卫，未登录会 302/跳登录页，**不能当匿名 HTTP 接口**。所以本工具走 §3 方案。

## 5. chunk 文件名自动发现

官网 chunk 名带内容哈希会随发版变化。脚本流程：
1. 取 `${ORIGIN}/home` 的 HTML，正则找 `entry` 的 `<script src>`；
2. 拉 entry，收集所有 `markdown.chunk.<hash>.js`（多个候选：路由/导出等）；
3. 逐个拉取，挑出含 `importMarkdownV3` 的那个（即转换路由页 chunk）；
4. 从它里面正则提取 `markdown_v3.chunk.*` / `import-file.chunk.*` / `snowmonster-ext.chunk.*` 的最新文件名。

可用环境变量覆盖：`MD2MM_MARKDOWN_V3` / `MD2MM_IMPORT_FILE` / `MD2MM_SNOWMONSTER`；
`MD2MM_NO_DISCOVER=1` 关闭自动发现（用内置默认名）。

## 6. Markdown 语法 → 主题 映射速查

标题层级→主题层级；列表→子级（有序自动编号、`- [x]`→任务）；`> 引用`→备注；
`|表格|`→电子表格；`![]()`→图片主题（外部 URL 不内嵌会留空）；`[..](url)`→超链接；
`**粗**/*斜*/~~删~~`→富文本；` ```代码``` `→代码主题；`$$公式$$`→MathJax。
（细节见完整报告 §6–§8。）

## 7. 排错

- `缺少依赖 playwright-core`：`npm i playwright-core`，或 `PLAYWRIGHT_CORE=/abs/path`，或复用本项目 `xmind-md-reverse/node_modules`。
- 渲染返回 null / 空白：多为官方发版改了 chunk 名或运行时全局 → 用 `MD2MM_DEBUG=1` 看解析到的模块名，必要时手动设 `MD2MM_*`。
- 图片节点是空的：Markdown 里是外链图片，官网渲染不内嵌远程图；需要本地资源包时改用 `packXmind` 带 `stage` 的方案。
- 想要更高清：`--width 2400 --height 1500`（宽高比影响留白，尽量接近内容比例）。
