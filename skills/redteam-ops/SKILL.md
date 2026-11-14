---
name: redteam-ops
description: 红队渗透作业的分阶段编排与判据库，覆盖信息收集、资产梳理、漏洞扫描、突破、WebShell 落地、隧道、内网横向、提权八段链路，内置隧道/突破/扫描器三组选型判断与"什么算成功"的验收口径。Use when 需要做渗透测试、红队演练、打点、子域枚举、端口扫描、目录爆破、指纹识别、Nday 检测、弱口令爆破、未授权访问利用、反弹 Shell、WebShell 管理、内网穿透、SOCKS5 隧道、内网横向移动、域内提权，或需要判断某一步是否真的成功、某工具何时不该用、被封后如何降级时。
---

# 红队渗透作业编排

23 个工具域的知识已按阶段合并为 5 份 reference。本文件只放**编排、选型与判据**——具体命令在 reference，不要在正文里找。

## 先读这一条：宿主适配

原文出自 DSH 宿主，正文中出现 130+ 处 `redteam_*` 工具调用（`redteam_asset_add`、`redteam_score_hit` 等）。**这些工具在当前环境不存在，不要调用。**

它们的真实作用是"记账"，等价替换：

| 原文写法 | 实际做法 |
|---|---|
| `redteam_asset_add` / `asset_link` | 追加到 `runs/assets.jsonl`（一行一资产，含 provenance） |
| `redteam_credential_add` | 追加到 `runs/creds.jsonl` |
| `redteam_tunnel_add` / `session_check` | 追加到 `runs/tunnels.jsonl` |
| `redteam_score_hit` | 追加到 `runs/findings.jsonl`，附证据路径 |
| `redteam_asset_test` | 直接跑连通性命令，把输出存 `runs/proof/` |

每个工具的具体参数签名（必填字段、幂等键、可选值）见 `references/50-tool-contract.md`。

路径 `$DSH_HOME/redteam/toolkit/**`、`<你的VPS_IP>`、`DISPLAY=:10.0` 同理：一律替换为当前机器的真实值，不要照抄。遇到未替换的占位符 → 该条命令不可直接执行。

## 运行前自检

**已装（2026-11-14 实测可用）**

`/opt/homebrew/bin`：`nmap` 7.993 `masscan` 1.3.2 `ffuf` 2.1.0 `feroxbuster` 2.14.0 `gobuster` 3.8.2 `hydra` 9.7 `hashcat` 8.0.0 `john` 1.9.0

`~/.local/bin`：`subfinder` v2.17.0 `dnsx` `naabu` `httpx` `nuclei` `katana` `gau` 2.2.4 `anew` `fscan` 2.2.2 `gogo` 2.15.0 `chisel` 1.12.0 `frpc`/`frps` 0.72.0 `suo5` 2.2.0

浏览器（`browser-automation` 用）：
`~/Library/Caches/ms-playwright/chromium_headless_shell-1248/chrome-headless-shell-mac-arm64/chrome-headless-shell`（156.0.8078.4，`--dump-dom` 已验证）。

**字典与模板**

`~/wordlists/`：`Discovery/common.txt` 4751 行、`dir-medium.txt` 220559、`raft-dirs.txt` 29999、`raft-files.txt` 17129、`api-endpoints.txt` 295；`Passwords/top10k.txt` 10001、`pwdb10k.txt` 10000；`Usernames/top-usernames.txt` 17。总量 2.5MB，按需扩充用 `git clone --depth 1` 拉完整 SecLists。

nuclei 模板 **13,808 条**已就位。首次跑 `nuclei -tl` 为空时先 `nuclei -update-templates`。

**httpx 同名陷阱已解除**：`~/.local/bin` 在 PATH 第 5 位，压过 miniconda3 的第 13 位，`httpx` 现在解析到 ProjectDiscovery 版本。不要在 miniconda 环境里重排 PATH，否则会退回 Python 那个同名 CLI（`-l` 报 `No such option`）。

**仍需注意**

- `masscan` 与 `nmap -sS` 需要 root（raw socket）。无 sudo 时用 `nmap -sT`。
- `nuclei` 在 arm64 上报 `sonic/ast only supports ... amd64` 并回退 `encoding/json`——功能正常，仅模板解析变慢。
- 冰蝎 / 哥斯拉仍未装（Java GUI 工具，本机无 GUI 自动化路径）。`webshell-toolkit` 里的文件管理能力需自备。
- `fscan` 的 `-h` 需带参数（`-h` 后必须跟值），看用法用 `fscan` 不带参数。

硬规则：阶段开始前先 `command -v <工具>`。缺工具 → **只输出规划与命令，明确标注「未执行（工具缺失）」**，不要重试、不要找替代品猜测行为、不要声称已完成。需用户提供的东西（VPS 地址/私钥、FOFA_KEY、字典）集中成一张缺项清单。

`references/` 已做环境适配：`$DSH_HOME`→`$RT_HOME`/`$RT_TOOLKIT`、`$REDTEAM_VPS_HOST` 与 `<你的VPS_IP>`→`$RT_VPS`、`DISPLAY=:10.0`→`$DISPLAY`、命令内 `<target>` 类尖括号→`$TARGET`（尖括号在 bash 里是重定向符）。

**仍保留 `redteam_*` 原样调用**（160 处）——不改写是有意的：改写会破坏原句可读性，且它们已在 `50-tool-contract.md` 完整映射。见到就当伪代码读。

## 阶段流水线

每段有进入条件与出口判据。**出口不满足不得进入下一段**——这是这套流程唯一必须遵守的纪律。

| 段 | 做什么 | reference | 出口判据 |
|---|---|---|---|
| L0 环境 | 确认 API key、VPS、工具是否在位 | `00-setup.md` | 缺失项已列入降级清单（降级也是交付物） |
| L1 侦查 | 铺资产面 | `10-recon.md` | 有域名/IP 清单 + 存活 URL 清单 |
| L2 梳理 | 指纹、C 段、证书关联 | `10-recon.md` | 资产之间存在可查询的关系，而非平铺列表 |
| L3 扫描 | Nday、目录、接口 | `20-scan.md` | 有可复现的命中（附请求/响应），不是"扫描器说高危" |
| L4 突破 | 口令、未授权、命令执行 | `30-exploit.md` | 拿到**真实会话或账号登录**，不是"发现弱口令" |
| L5 落地 | WebShell、载荷 | `30-exploit.md` | 有回显 + 能执行 `id` |
| L6 隧道 | 把可达性变成可用通道 | `40-internal.md` | `curl --socks5` 能穿过并拿到目标响应 |
| L7 内网 | 铺面、爆破、横向 | `40-internal.md` | 内网资产清单 + 凭据可用性验证 |
| L8 收口 | 证据归档、报告 | 全部 | 每条结论能指到一个证据文件 |

L1→L2→L3 对同一目标可小步循环；L4 之后一旦拿到新资产，回到 L2 重新梳理，不要线性推进。

## 三组选型（每张表都在回答"什么时候不用它"）

### 隧道（L6）

| 条件 | 选 | 不选的理由 |
|---|---|---|
| 已有能执行代码的 WebShell | suo5 | 非 WebShell 入口用不了，需冰蝎/哥斯拉马 |
| 仅命令执行、目标只出 HTTP | chisel | 不能出网时不可用；最易穿反向代理 |
| 需要长期稳定 + 端口直接映射 | frp | 需公网 VPS，自建成本高 |
| 只有本机可达、目标不主动外连 | 反弹 Shell 落地 | 隧道方案全部失效 |

三者的公共口径是 `entry_kind`：`target-outbound` / `target-http` / `target-agent` / `self-only`。**`self-only` 永远不算突破**——自己 VPS 上开的代理不是战果。

### 突破（L4）

| 线索 | 选 | 前提 |
|---|---|---|
| 有登录入口（后台/SSH/FTP/RDP/SMB/DB） | `credential-attack` | 需字典与限速，被封 >3 次换出口 |
| 暴露的数据库/中间件端口 | `unauth-exploit` | 6379/3306/1433/9200/27107/2375 直连 |
| 有 RCE 或命令注入 | `shell-handler` / `vps-reverse-shell` | 目标能回连 |
| 有上传点或文件写入 | `webshell-toolkit` | 必须落地**加密马**才算交付 |

### 扫描器分工（L3/L7）

| 场景 | 用 | 不要用 |
|---|---|---|
| 已知组件版本，找现成 POC | nuclei | 内网大网段用它是浪费噪声预算 |
| 内网 /16 /12 大网段铺面 | gogo（智能模式） | 不要先用 fscan，它噪声大 |
| 已知目标，定向爆破与未授权 | fscan | 不要用它铺大网段 |
| 模板 POC 内外网都要 | nuclei 外网、`gogo -e/-E` 内网 | 两者能力重叠，别对同一目标跑两遍 |

内网顺序固定：**gogo 铺面 → fscan 定向 → 横向**。反了就是拿噪声换覆盖率。

## 全局红线

这几条来自演练计分口径，不是道德建议——违反后成果作废。

- **只有凭据不算拿到账号**。必须用该凭据真实登录一次并留在证据里。
- **`self-only` 不算突破**。自建代理、自己 VPS 上的隧道不计入战果。
- 同一系统/主机/库**只按最高权限计一次**。同端口刷多个账号不累加。
- 同一服务被封 **>3 次**：换出口 IP，仍不行就放弃并记录，不要硬怼。
- **不看回显不算成功**。"我以为通了"是最常见的假成果。
- WebShell 落地后**立刻建隧道**，不要先做别的。
- 凭据、key 不入仓库；证据落 `runs/`，不落 VPS 系统盘。

## 已知不可靠的命令

原文档有已验证的执行缺陷，下面几条按现状不要直接跑：

- `10-recon.md` 的 httpx 流水线已修（原 `<<'PY'` 内 `$D` 不展开，会去找字面 `runs/httpx-$D.jsonl`）。
- `10-recon.md` 的接口提取已修（原单引号内 `\'` 提前闭合导致 `bash: syntax error near unexpected token`）。
- `02`/`recon-pipeline` 声称含 `katana`，实际未安装，抓页面走 `browser-automation`。
- `passive-recon` 的落库工具名已修正为 `redteam_asset_add`。
- `chisel-tunnel`/`frp-tunnel` 把阶段码 `boundary` 当得分点 id 写，实际得分点是 `boundary-logical`/`boundary-strong`/`boundary-physical`/`boundary-supply`。
- `webshell-toolkit` 正文含明文示例口令，照抄即为弱口令，必须现场生成。
- `kimi-webbridge`（2026-09 实测）、`nuclei-scan`（模板 v10.4.9）、`fofa-recon`（限额）三篇把时间点写死，外部产品改版即失效，用前自查。

## Reference 路由

| 文件 | 覆盖 | 何时读 |
|---|---|---|
| `references/00-setup.md` | redteam-setup | 首次使用、环境不全、用户说"工具装一下" |
| `references/10-recon.md` | passive-recon, fofa-recon, recon-pipeline, active-scan, web-fingerprint, asset-correlation, browser-automation, kimi-webbridge | L1/L2，或需要不接触目标拿情报 |
| `references/20-scan.md` | nuclei-scan, dir-bruteforce, cn-proxy-pool | L3，或扫描被 WAF 拦 |
| `references/30-exploit.md` | credential-attack, unauth-exploit, shell-handler, vps-reverse-shell, webshell-toolkit | L4/L5，需要打通第一个 shell |
| `references/40-internal.md` | suo5-tunnel, chisel-tunnel, frp-tunnel, gogo-intranet, fscan-intranet, lateral-movement | L6/L7，已进内网 |
| `references/50-tool-contract.md` | 53 个 `redteam_*` 的字段契约 | 读到 130+ 处 `redteam_xxx(...)` 调用不知该传什么时；或要自建记账系统 |

只读当前阶段那一份。跨阶段引用（如扫描被封要查代理池）按需再开，不要一次全读。

## 来源与许可

正文由 `dsh-purge v1.1.40`（commit `3bc63be`，MIT，Copyright (c) 2026 小杨）的 23 篇技能合并而成，
合并时修正了 3 处执行缺陷，其余内容保持原样。上游 dual-use 声明见原项目 `src/docs/redteam-upstream-DISCLOSURE`。
