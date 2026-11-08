---
name: magpie-browser
description: 当需要操作用户本人的真实 Chrome 浏览器（经 Magpie Browser 扩展，共享其登录态、Cookie 和已打开的标签页）时使用：列出/新建/切换/关闭标签页、导航、抓取无障碍快照、点击/输入/按键/悬停/选择/滚动/拖拽/上传、等待文本或 URL、执行 JS、读取页面文本与控制台、处理弹窗、截图、录制 GIF。凡 "用我的浏览器"、"操作我的 Chrome"、"在浏览器里帮我点/填/截图"、"打开这个网站看看"、或 chrome-devtools 隔离环境拿不到的已登录页面，都显式调用本技能。
---

# Magpie Browser

通过 **Magpie Browser** MCP 驱动用户自己的真实 Chrome 浏览器（浏览器侧装 Magpie 扩展）。它共享用户已登录的会话、Cookie 和标签页，因此能操作 chrome-devtools 这类隔离环境访问不到的页面。副作用落在用户真实可见的浏览器上，做可逆、克制。

## 显式调用

- 触发口号（任一即可让 agent 加载本技能）：`用 magpie-browser`、`用我的浏览器`、`操作我的 Chrome`、`在浏览器里…`。
- 工具本体只有一个：`browser`，由 `action` 决定行为。
  - 本 harness 命名空间：`mcp__magpie__magpie-browser__browser`
  - 其他 runtime：MCP server `magpie` → 子服务 `magpie-browser` → 工具 `browser`
- 每个 action 都可带 `screenshot: true`（在回答里附一张窗口小图）和 `tab`（目标标签页 id，如 `t123`；省略=本会话自己的标签页，无则新建一个在用户页面后台）。

## 何时用 / 何时不用

- **用**：需要用户登录态、其 Cookie、其真实标签页、其账号下的数据；需要把操作结果给用户看一眼。
- **不用**：全新的、无登录态的隔离自动化 → 用 `chrome-devtools` MCP（`mcp__chrome-devtools__*`），别污染用户浏览器。

## Action 参考

| 分组 | action | 关键参数 | 作用 |
|---|---|---|---|
| 会话/标签 | `browsers` | — | 列出已连接的浏览器 |
| | `use_browser` | `browser`(id 或名字) | 切换目标浏览器 |
| | `tabs` | — | 列出标签页 |
| | `tab_new` | `url`, `front` | 新建标签页；仅当用户要看时才 `front:true` |
| | `tab_select` | `tab` | 切到某标签页 |
| | `tab_close` | `tab` | 关闭某标签页 |
| 导航 | `navigate` | `url` | 打开地址 |
| | `back` / `forward` / `reload` | `tab` | 前进/后退/刷新 |
| 读取 | `snapshot` | `interactive`, `ref`, `maxChars` | 无障碍树 + 可操作元素 `ref`（`e1`,`e2`…）|
| | `text` | `maxChars` | 页面可见文本 |
| | `evaluate` | `script`, `ref` | 在页面执行表达式/函数 |
| | `console` | `level`(`all`/`errors`/`network`), `limit` | 控制台消息 |
| | `screenshot` | `ref`, `fullPage`, `png` | 截图（整页或某元素）|
| 交互 | `click` | `ref`, `double`, `button`(`left`/`right`/`middle`), `modifiers` | 点击 |
| | `type` | `ref`, `text`, `clear`, `submit`, `slowly` | 键入（`slowly` 用于自动补全）|
| | `press` | `key`, `ref` | 按键/组合键（`Enter`,`Control+a`）|
| | `hover` | `ref` | 悬停 |
| | `select` | `ref`, `values` | 下拉选择（按 value 或 label）|
| | `scroll` | `direction`, `amount`, `ref` | 滚动；带 `ref` 无方向=滚入视野 |
| | `drag` | `from`, `to` | 拖拽（两个 ref）|
| | `upload` | `ref`, `paths` | 上传文件（本机绝对路径）|
| 等待 | `wait` | `text`, `textGone`, `url`, `seconds`, `timeout` | 等文本/消失/URL/固定秒数 |
| 弹窗 | `dialog` | `accept`(bool), `promptText` | 接受/取消 alert/confirm/prompt |
| 录制 | `record_start` / `record_stop` | — | 把每步后的窗口图录成 GIF，返回下载链接 |

## 核心循环

1. `browsers` —— 确认目标浏览器在线（输出里 `*` 那台是默认）。
2. `tabs` / `tab_new` / `tab_select` —— 定位到正确的标签页（记下 `t#########`）。
3. `snapshot(interactive=true)` —— 拿到 `ref`（如 `e12`）。
4. 用该 `ref` 操作：`click` / `type` / `select` / …（加 `screenshot:true` 便于核对）。
5. 页面变了就**重新 `snapshot`**，再取新 `ref` 做下一步。
6. 用 `text` / `console` / `screenshot` 读结果、向用户汇报。

## 铁律

- **ref 是一次性的**：只来自最新一次 `snapshot`；任何改变 DOM 的操作后必须重抓，旧 ref 会失效或指错元素。
- **先快照后动作**：没拿 `ref` 别 `click`/`type`。
- **能等就别睡**：优先 `wait(text=...)`/`wait(url=...)`，别写死 `seconds`。
- **截图给人看**：用户要"看看结果"或需要核对时，加 `screenshot:true` 或 `action:"screenshot"`。
- **克制副作用**：只关本技能自己开的标签页；用户原有标签页、登录态别乱动；`tab_new` 默认后台（`front:false`）。
- **弹窗先处理**：出现 alert/confirm/prompt 用 `dialog` 收口，别让流程卡住。
- **上传要真路径**：`upload` 的 `paths` 是本机绝对路径。

## 常见错误

| 错误 | 修复 |
|---|---|
| 操作后复用上一个 `ref` | 每次动手前重抓 `snapshot` |
| 拿 chrome-devtools 打开已登录站点 → 空白/未登录 | 改走 magpie-browser |
| 用固定 `seconds` 等加载 | 用 `wait(text=...)` / `wait(url=...)` |
| 新建页抢焦点打扰用户 | `front:false`（默认后台）|
| 用户看不到发生了什么 | 关键步加 `screenshot:true` |
| 拖拽传选择器而非 ref | `from`/`to` 都传快照里的 ref |

## 最小示例

```
browser(action="browsers")
browser(action="tab_new", url="https://example.com", front=false)   # 回 t2093613278
browser(action="snapshot", interactive=true, tab="t2093613278")     # 得 ref=e1/e2…
browser(action="click", ref="e1", screenshot=true, tab="t2093613278")
browser(action="snapshot", interactive=true, tab="t2093613278")     # 页面变了→重抓
browser(action="tab_close", tab="t2093613278")
```

## 与 magpie 其他服务的关系

`magpie` MCP 下还有 `huggingface`（搜模型/数据集/论文）——与本技能无关，别混用。本技能只负责 `magpie-browser` 的 `browser` 工具。
