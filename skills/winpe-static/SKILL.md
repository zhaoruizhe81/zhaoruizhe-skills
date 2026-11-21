---
name: winpe-static
version: 1.0.0
description: "Use when a task requires STATIC analysis of a Windows PE file (exe/dll/sys): triage, PE headers, sections & entropy, packer detection, import-table threat categorization, strings/IOC extraction, pseudo-decompilation, and an evidence-based report — WITHOUT ever executing the sample. Chinese triggers: 静态逆向, PE分析, 帮我看看这个exe, 加壳检测, 脱壳判断, 导入表, 提取字符串, IOC, 恶意样本初判, 二进制分析. Do NOT use for dynamic debugging (x64dbg/Frida/断点), non-PE formats (ELF/Mach-O 固件), or when the user explicitly wants to run the sample."
allowed-tools: Bash, Read, Write, Glob, Grep
keywords: PE, static analysis, 静态逆向, 静态分析, pefile, radare2, rabin2, ghidra, entropy, 熵, 加壳, 壳检测, 导入表, IOC, strings, malware triage, 恶意样本, dnSpy, ilspy
---

# winpe-static — Windows PE 静态逆向工作流

只在**不执行样本**的前提下回答三个问题：**这是什么？有没有问题？值得不值得动态分析？**
工作流与方法论提取自以下权威开源项目（静态部分）：

- **Sarks0/binary-mcp**（Apache 2.0）— pefile 结构解析 → 熵分析 → 导入表分类 → Ghidra headless / ILSpyCmd 的静态引擎链路
- **masriyan/claude-code-cybersecurity-skill**（MIT）— 证据契约、triage 分级、反逆向特征库
- **horsicq/Detect-It-Easy 与 hasherezade 工作流** — 壳/编译器识别判据（节熵、节名特征、导入表稀疏度）
- **morluto/rea**（MIT）— "结论必须附证据与局限"的报告契约

---

## 0. 执行环境

- 本技能安装在**执行分析的机器上（Mac mini）**，所有命令**直接本地 Bash 执行**——无远程中转。
- 仅当用户主动要求时，才通过 ssh-skill 把命令转发到别的机器（如实体机 `windowpc`）。
- **开工前先探测工具**（一条命令合并探测，read-only）：

```bash
command -v rabin2 r2 strings file shasum; python3 -c "import pefile" 2>&1; python3 -c "import capstone" 2>&1
```

- 缺 Tier1 工具时**先报告缺什么、给出附录 A 的安装命令，征得用户同意后执行**。不要擅自安装。
- Tier2/Tier3 工具缺失不阻塞主流程：在报告里注明"未安装，无法执行 XX 检查"即可。

## 1. 样本纪律（每一条都不可违反）

1. **绝不执行样本**，包括"只跑一下看看"、"双击试试"。静态分析的命门。
2. 原件只读。分析一律在副本上进行：`~/re-sessions/<sha256前8位>/sample.ext`
3. 第一步就算 `shasum -a 256`，此后所有引用以 hash 为准（防"看错了文件"）。
4. **不得将样本或其片段上传到任何在线服务**（VirusTotal、聊天工具、网盘）。用户明确要求时提醒"这会把样本暴露给第三方"，同意后才可。
5. 网络抓包/动态行为不在本技能范围——发现用户想执行样本时，引导到动态分析路线（VM + x64dbg）。

## 2. 证据契约（报告里的每个结论都要归档为三档之一）

| 档位 | 含义 | 示例 |
|---|---|---|
| **观察** | 工具输出直接可查证 | "节 UPX0 熵 7.89" |
| **推断** | 由特征推出，附依据 | "疑似 UPX 壳：UPX0/UPX1 节名 + 导入仅 14 个函数" |
| **未验证** | 假设，明确说没验证 | "可能带 C2 通信（出现未解析域名）——需动态确认" |

禁止把推断写成观察。模糊就写模糊，置信度给出高中低。

---

## 3. 工作流（按序执行，每阶段保留原始输出到 session 目录 `notes/`）

### Phase 0 · 建档
```bash
mkdir -p ~/re-sessions/<sha前8>/notes && cp <样本> ~/re-sessions/<sha前8>/sample.ext
cd ~/re-sessions/<sha前8> && shasum -a 256 sample.ext && ls -l sample.ext && file sample.ext
```

### Phase 1 · 分类（是什么）
- `file`：确认 PE/MS-DOS、位数（PE32/PE32+）。
- pefile 快查：machine、subsystem（GUI/Console/驱动 sys）、linker 版本、编译时间戳（**常被伪造**，仅作弱证据）。
- **CLR header 存在 → 是 .NET 程序**：转向 .NET 路线（Tier3 的 ilspycmd 全量反编译比原生分析高效百倍），本流程 Phase 5 的原生代码分析可跳过。
- PE 有数字签名目录 → 记录签名者（只读证书表，不联网验签）。

### Phase 2 · 结构与壳检测（有没有壳）
```bash
rabin2 -I sample.ext                       # 基本信息
rabin2 -S sample.ext                       # 节表（注意：-S 不出熵列，-SS 是 segments 不是熵！）
python3 scripts/sec_entropy.py sample.ext  # 每节熵值——配套脚本，见下方"脚本说明"
rabin2 -ee sample.ext                      # TLS callback（PE 上随构造/析构入口一起列出）
rabin2 -i sample.ext                       # 导入表
rabin2 -e sample.ext                       # 入口点
rabin2 -H sample.ext                       # 头部标志 (NX/ASLR/Canary)
```

> **脚本说明**：`scripts/` 目录与本文件同文件夹，含 `sec_entropy.py`（节熵）和
> `wide_strings.py`（UTF-16LE 字符串）。开工前先把 scripts/ 上传到目标机 session 目录。
> 原因：macOS 的 BSD `strings` 没有 `-e` 参数；`rabin2 -S` 无熵列，熵必须自己算才准。
**加壳判据**（满足越多，置信度越高，逐条记入报告）：
| 判据 | 阈值/特征 |
|---|---|
| 单节熵 | 可执行节 > 7.2 高度可疑；> 7.8 几乎必然加壳/加密 |
| 节名 | UPX0/UPX1、.aspack、.adata、.themida、.winlice、.enigma1/.enigma2、MPRESS1/2 |
| 导入表稀疏 | 导入函数总数 < 20 且集中在 LoadLibraryA/GetProcAddress/VirtualAlloc |
| 节属性矛盾 | 虚拟大小 >> 原始大小（内存解压型壳）；RWX 同节 |
| 入口异常 | EP 位于第一/最后一节而非 .text |
| overlay | 文件尾有额外数据块（嫁接/隐藏载荷常见位） |
- TLS callback 数量 > 0 → 单独记录（壳与反调试常用，EP 之前执行）。
- 结论写法示例："**推断：UPX 加壳（高置信）**——节名 UPX0/UPX1 + EP 在 UPX1 + 导入 14 项。可用 `upx -d` 尝试脱壳后再走 Phase 5。"（UPX 类公开壳可建议官方工具脱壳；非公开壳留待动态。）

### Phase 3 · 导入表威胁分类
用 pefile 展开完整导入表，按下表打标签（同一 API 可多标签）：
| 类别 | 特征 API |
|---|---|
| 反调试 | IsDebuggerPresent, CheckRemoteDebuggerPresent, NtQueryInformationProcess, OutputDebugString, FindWindow(OLLYDBG/tdidbg) |
| 反虚拟机 | RegQueryValueEx(SYSTEM\\CurrentControlSet\\Services\\Disk\\Enum), cpuid 指令, GetSystemFirmwareTable, WMI 查询 |
| 进程注入 | WriteProcessMemory, CreateRemoteThread, NtMapViewOfSection, SetWindowsHookEx, QueueUserAPC |
| 网络 | ws2_32 系列, WinHttp*/InternetOpen*, getaddrinfo, DnsQuery |
| 持久化 | RegSetValueEx(…Run 键), CreateService, SchTasksAPI, WMI |
| 加密/勒索 | CryptEncrypt, BCryptEncrypt, CryptAcquireContext, CryptoAPI+高熵字符串 |
| 键盘记录 | GetAsyncKeyState, GetKeyboardState, SetWindowsHookEx(LOW_LEVEL) |
| 隐蔽执行 | CreateProcess + 倒序命令行, COM/ShellExecute,回调函数执行 |

### Phase 4 · 字符串与 IOC
```bash
strings -a -n 6 sample.ext > notes/str_ascii.txt
python3 scripts/wide_strings.py sample.ext > notes/str_utf16.txt  # 宽字符串必查（BSD strings 无 -e 参数）
rabin2 -zz sample.ext >> notes/str_bin.txt              # -zz 扫全文件原始字符串；-z 只扫 data 节，加壳样本会漏
```
- 重点捞：URL/域名/IP、邮箱、注册表路径、互斥体（Global\\、Local\\）、文件路径、钱包地址、错误提示文案（可判定来源国别/作者习惯）、PDB 路径（**泄露原始工程结构，高价值**）。
- ASCII+UTF16 全都乱码、可读串近乎为零 → 印证 Phase 2 加壳结论。

### Phase 5 · 原生代码深度（样本未加壳时）
```bash
r2 -q -A -c 'afl' sample.ext > notes/functions.txt      # 自动分析+函数列表
r2 -q -A -c 'pdf @ entry0' sample.ext                   # 入口反汇编
r2 -q -A -c 'pdc @ <函数地址>' sample.ext                # 伪 C 反编译（radare2 内置）
```
- 优先看：WinMain/main、TLS callback、DllMain、Phase 3 危险 API 的交叉引用（`r2 -q -A -c 'axt @ sym.imp.<api>'`）。
- 识别加密常量（在数据里搜这些前缀）：AES S-box（637C777BF26B6FC5…）、SHA-256 K 表（428A2F98…）、MD5 初始化（67452301…）、ChaCha/Salsa 魔串 "expand 32-byte k"、TEA/XTEA delta（9E3779B9）→ 推断内置加密能力。注意：RC4 没有魔数常量，别按名字搜它。

### Phase 6 · 重型反编译（可选，Tier3 装了才做）
- Ghidra headless 全量导出伪代码：
  `analyzeHeadless <项目目录> <项目名> -import sample.ext -postScript /path/to/decompile_all.java`
- .NET 程序：`ilspycmd sample.ext -o notes/ -p`（全工程转 C#）。
- 未装 → 报告注明"建议安装 Ghidra 以获得函数级伪代码"，不要现场硬装不问人。

### Phase 7 · 报告（固定模板）
```markdown
# PE 静态分析报告 · <原名> · sha256:<hash前16位>
**一句话结论**：<是什么/干什么的/危险等级>（标注档位）
## 文件信息
大小/类型/位数/子系统/编译器线索/签名状态
## 壳与结构
加壳判定（置信度+逐条判据）/ 可疑节 / TLS / overlay
## 行为画像（静态可证的）
按 Phase 3 标签归纳：能连网?能注入?能加密文件?有持久化?有反调试?
## 关键发现
- [观察] …
- [推断] …（依据：…）
- [未验证] …
## IOC 表
hash / url / ip / 域名 / 互斥体 / 注册表路径 / PDB 路径
## 下一步建议
值得动态分析吗？若值得：哪个点值得先断（API/入口），建议 VM 路线还是实体机路线
```

---

## A. 工具分层与安装清单（在目标机器执行前先征得同意）

| 层 | 工具 | 用途 | 安装 |
|---|---|---|---|
| **Tier1 必需** | radare2 (rabin2/r2)、pefile、capstone | 结构/导入/反汇编 | `brew install radare2`；`pip3 install pefile capstone` |
| Tier1 系统自带 | strings/file/shasum/otool | 字符串/分类/hash | 无需安装 |
| **Tier2 推荐** | yara-python、Detect It Easy(CLI)、upx | 规则扫描/壳识别/公开壳验证脱壳 | `pip3 install yara-python`；DIE 官方 macOS 构建；`brew install upx`（`upx -d` 可解 UPX 类壳，作为加壳推断的验证手段） |
| **Tier3 可选重型** | Ghidra headless、ilspycmd、retdec | 全量伪代码/.NET 反编译 | `brew install --cask ghidra`（需 `temurin` JDK）；`dotnet tool install -g ilspycmd` |

## B. 边界（什么时候不用本技能）
- 要跑起来、下断点、看真实网络行为 → 动态路线（VM + x64dbg-automate，另技能）
- ELF/Mach-O/固件 → 不在本技能范围，别硬套
- 样本在远程 Windows 机（windowpc）上 → 本技能同样适用，只是执行环境换成对应 SSH 别名
