---
name: pe-dynamic
version: 1.0.0
description: "Use when a task requires DYNAMIC analysis of a Windows PE sample: running it under a debugger (x64dbg) or instrumentation (Frida hooks), monitoring file/registry/network/process behavior, bypassing anti-debug, unpacking to OEP, and producing an evidence-based behavior report. Requires a Windows target environment (VM or physical). Chinese triggers: 动态逆向, 行为分析, 跑起来看看, hook, 挂钩, 注入, 断点, 调试, 脱壳, 找OEP, 监控行为, 沙箱, 恶意样本行为. Do NOT use for pure static analysis (use winpe-static), or when no Windows target environment is available — say so and propose setting one up first."
allowed-tools: Bash, Read, Write, Glob, Grep
keywords: 动态逆向, x64dbg, frida, hook, 注入, 调试, 断点, 脱壳, OEP, 行为监控, procmon, wireshark, fakenet, 沙箱, 反调试, ScyllaHide, MITRE, ATT&CK
---

# pe-dynamic — Windows PE 动态逆向工作流

核心思想：**让样本在受控靶场里真实地跑，用探针记录它做的每一件事，必要时改变它的行为（断点/补丁/hook），最后给出可验证的行为报告。**
工作流与方法论提取自以下权威来源（动态部分）：

- **dariushoule/x64dbg-skills**（MIT）— trace 跟踪分析、状态快照/差分、trace 找 OEP（含反调试规避）、牺牲进程跑 shellcode、YARA 内存扫描、漏洞狩猎流程
- **Sarks0/binary-mcp**（Apache 2.0）— x64dbg/WinDbg 调试链路、"样本不可执行于工具层"、隔离 VM 纪律、原始调试命令白名单思想
- **masriyan/claude-code-cybersecurity-skill**（MIT）— 反调试/反虚拟机检测清单与对策、emulation-first 分诊
- **Frida 官方文档**（frida.re）— Interceptor 注入模式、spawn/attach 语义
- **Mandiant FLARE-VM / FakeNet-NG**（开源）— 靶场工具链与网络假响应
- **MITRE ATT&CK** — 行为标注框架

---

## 0. 执行环境（硬前提，不满足就停下来先说）

- 本技能**直接运行在 Mac mini 本机上**（agent 与技能同机，无远程中转，命令本地执行）。
- 动态分析需要一个 Windows 靶场，两个合法选项：
  - **VM 路线**（默认，分析可疑样本）：**同一台 Mac mini 上的虚拟机**（VMware Fusion/UTM 的 Win11 ARM）——样本跑在 VM 里，宿主与 VM 经虚拟网卡（host-only）和共享文件夹交换文件与探针连接
  - **实体机路线**（反 VM 检测/内核目标）：`windowpc`
- 红线：样本**只存在于 VM 快照之内**，宿主（Mac mini 本体）绝不执行样本。
- **靶场就绪检查**（开工前逐项确认）：
  - [ ] 快照点 `clean+tools` 存在且已回滚到该点
  - [ ] x64dbg + Automate 插件（RPC 可达）/ frida-server 在跑
  - [ ] Procmon、Wireshark 或 FakeNet-NG、Process Hacker 可用
  - [ ] 网络为 host-only/隔离，FakeNet 假 DNS/网关就位
- 靶场没有就明确告知用户"需要先搭环境"，给出附录 A 清单，**不要在宿主机上跑任何样本**。

## 1. 纪律（每条不可违反）

1. **只在快照内跑样本**；每次分析完回滚。快照之外绝无样本。
2. 靶场网络默认隔离；需要观察真实 C2 行为时**先征求用户同意**并说明暴露后果。
3. 靶场内**不登录任何个人账号**（微信/邮箱/网盘），不放真实个人文件。
4. 永久 patch 文件前先复制原文件并记录 SHA-256；改完记录改动字节。
5. 只分析自有/授权样本；不把样本或行为记录上传在线服务（同 winpe-static 红线）。
6. 原始调试器命令一律白名单化执行（binary-mcp 安全模型）：不确定的命令先问。

## 2. 证据契约

与 winpe-static 相同的三档标注：**观察**（工具日志可查证）/ **推断**（由行为特征推出，附依据）/ **未验证**（待验证假设）。动态报告的每条行为必须带证据来源（Procmon 事件行 / Frida send 输出 / Wireshark 包号 / trace 地址段）。

---

## 3. 工作流

### Phase 0 · 接入方式决策
| 场景 | 接入方式 | 命令形态 |
|---|---|---|
| 从头观察完整行为 | **spawn**（推荐） | `frida -f sample.exe -l scripts/hook_common_apis.js`（spawn 后自动恢复执行）；或 x64dbg automate spawn 并挂起在入口 |
| 已在跑的进程 | **attach** | `frida -n <进程名> -l scripts/hook_common_apis.js`；x64dbg attach |
| 纯 shellcode/无 PE 载荷 | **牺牲进程**（x64dbg-skills 方法） | x64dbg 起 `timeout.exe` → 分配内存写入 shellcode → 转跳执行 |
| 想看"不改程序"的宏观行为 | **三线监控**（Phase 1） | Procmon + Wireshark/FakeNet + Process Hacker |

位数匹配：32 位样本用 32 位工具链（frida/x64dbg32），64 位用 64 位——启动前先确认（winpe-static 的 Phase 1 结论直接复用）。

### Phase 1 · 三线宏观监控（先开监控，再放样本）
- **文件/注册表线**：Procmon → Filter 定位样本 PID 及其子进程 → 关注：落盘文件（尤其 %AppData%/%Temp%/计划任务）、Run 键、服务创建、种子文件复制
- **网络线**：隔离网内用 **FakeNet-NG**（假 DNS/HTTP 让样本以为联网成功，行为不中断）或 Wireshark 抓包 → 记录 IP/域名/端口/协议特征/载荷摘要
- **进程线**：Process Hacker 观察：子进程链、线程起点（远程线程=注入嫌疑）、句柄打开（其他进程=交叉进程操作）
- 三线日志全部落盘到 session 目录 `notes/`。

### Phase 2 · Frida 注入路线（行为 API 探针）
- 配套脚本 `scripts/hook_common_apis.js`：hook 文件/网络/注册表/进程/注入/加密共 15+ 个关键 API，打印参数摘要
- 用法见脚本头部注释；在 VM 内执行；若 frida-server 跑在 VM 而宿主想直连，可用 `frida -H <VM的IP> -f …`（同机虚拟网卡，无外发流量）
- 观察要点：样本**自己的**调用 vs 库的常规调用（按调用栈区分，`Thread.backtrace`）
- 静态阶段（winpe-static Phase 3）标记过的危险 API——这里逐个验证"是否真的被调用、参数是什么"

### Phase 3 · x64dbg 调试路线（微观验证与改变行为）
- **断点验证静态推断**：对静态标出的可疑函数下断（如 `VirtualAllocEx`），命中后回溯调用栈定位触发代码
- **trace 跟踪**（x64dbg-skills 方法）：trace into/over N 步或到条件（如 `cip` 进入新节）→ 分析指令日志：热点、API 调用序列、循环
- **状态快照/差分**：全内存+寄存器落盘 → 两时刻 diff → 自动叙述"这期间它改了什么"
- **改变行为三式**：改寄存器/标志（绕过判断）、NOP 掉校验跳转、改内存数值——每次改动记录地址+原字节+新字节
- **内存 YARA 扫描**：对快照内存按 packer/crypto/anti-debug 规则扫描（x64dbg-skills `/yara-sigs` 思路，规则库 Yara-Rules + citizenlab）

### Phase 4 · 反反调试预案（静态发现 → 动态对策）
| 静态看到的 API/特征 | 动态对策 |
|---|---|
| IsDebuggerPresent / PEB BeingDebugged | **ScyllaHide** 插件一键隐匿（或手动清 PEB.BeingDebugged） |
| NtQueryInformationProcess (DebugPort/DebugObjectHandle) | ScyllaHide 对应选项 |
| CheckRemoteDebuggerPresent / DebugActiveProcess 自检 | 同上 + 对返回值下断改写 |
| GetTickCount/rdtsc/Sleep 时间差 | ScyllaHide timing 选项；或断在比对处改跳转 |
| GetThreadContext 查 DR0-3（硬件断点检测）| 改用软件/内存断点 |
| FindWindow/EnumWindow 找调试器窗口类名 | ScyllaHide 窗口隐藏；或改窗口标题 |
| 自校验 CRC（校验自身代码段）| 先定位比对点，patch 前备份、记改动 |
| 输出调试字符串探针 (OutputDebugString) | ScyllaHide 拦截 |

原则：**先上 ScyllaHide 全家桶，命中哪个再精细化**；每次绕过都记录"检测点地址 + 绕过方式"。

### Phase 5 · 加壳样本 → 脱壳回静态（与 winpe-static 的闭环）
1. 静态判定加壳（winpe-static Phase 2 结论）→ 本阶段目标：**到达 OEP，dump 出可静态分析的明文 PE**
2. trace 找 OEP（x64dbg-skills `/find-oep` 方法）：启发式 = 执行流从壳节切到代码节 / 栈恢复模式（pushad+popad）/ 编译器入口特征（PUSH EBP 系）/ IAT 大批量填充完成
3. 到达 OEP 后：状态快照留证 → **Scylla** dump 进程 + IAT 重建 → 得 `dump.exe`
4. `dump.exe` 交回 **winpe-static** 重跑：字符串、导入表、伪反编译全部重生
5. UPX 等公开壳优先用官方 `upx -d` 验证（干净快速），失败再走 trace 路线

### Phase 6 · 漏洞狩猎（可选，样本是攻击载荷时）
按 x64dbg-skills `/vuln-hunter` 流程：枚举导入按攻击面分类（网络/文件/注册表）→ 危险函数交叉引用排序可达性 → 对可疑函数构造畸形输入观察崩溃 → PoC 脚本（Python）演示影响。仅授权研究场景做。

### Phase 7 · 报告（固定模板，与 winpe-static 配对）
```markdown
# PE 动态行为报告 · <原名> · sha256:<hash前16位>
**一句话结论**：<它实际做了什么/危害等级>（档位标注）
## 运行环境
VM/实体机 · 快照点 · 隔离方式 · 工具版本
## 行为时间线
t+0s 启动 → t+2s … （每条附证据：Procmon行/Frida输出/包号）
## 三线明细
文件系统：创建/写入/删除清单
注册表：键值操作清单
网络：IP/域名/协议/载荷摘要（FakeNet 假响应需注明"未真实外联"）
进程：子进程/注入/持久化
## 反分析对抗
遇到的检测点 + 绕过方式（地址级记录）
## MITRE ATT&CK 映射
T1547.001 注册表Run键 / T1055 进程注入 / T1071 应用层C2 / T1082 系统发现 …
## 静态对照
winpe-static 的推断哪些被证实 / 哪些证伪 / 哪些仍未验证
## IOC 实测表
真实 C2、落盘路径、互斥体、持久化键值（FakeNet 环境下标注"未实测外联"）
```

---

## A. 靶场工具分层（装在 Windows 靶场；先征求用户同意）

| 层 | 工具 | 用途 | 来源 |
|---|---|---|---|
| **Tier1 必需** | x64dbg + Automate 插件 + ScyllaHide + Scylla | 调试/隐匿/脱壳 | x64dbg 官方发布 + dariushoule/x64dbg-automate |
| Tier1 必需 | Sysinternals（Procmon/Procexp/TCPView） | 三线监控 | 微软官方（免费闭源） |
| Tier1 必需 | Wireshark 或 FakeNet-NG | 网络观察/假响应 | 开源（Mandiant） |
| **Tier2 推荐** | frida-tools、CAPA、yara | 注入探针/能力判定/扫描 | 开源（`pip install frida-tools`；CAPA 为 Mandiant 出品） |
| **Tier3 可选** | WinDbg（Windows SDK）、CAPE 沙箱 | 内核态调试/自动化沙箱 | 微软 / 开源 |

## B. 边界
- Win11 ARM 模拟层对**内核态**（驱动/反作弊）行为分析支持有限 → 内核目标走实体机路线
- 反 VM 强目标 → 实体机 `windowpc`，VM 线直接放弃并注明
- 宿主机（macmini 本体/笔记本）绝对不执行样本
- 纯静态问题 → 用 winpe-static，别把样本跑起来
