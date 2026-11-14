> **环境约定（本文所有命令按此解析，不适用于上游 DSH 宿主）**
>
> | 变量 | 含义 | 本机取值 |
> |---|---|---|
> | `$RT_HOME` | 红队根目录 | 自定，如 `~/rt` |
> | `$RT_TOOLKIT` | 外部二进制目录 | 默认 `~/.local/bin` |
> | `$RT_SETUP` | 环境与配置目录 | 自定 |
> | `$RT_RUNS` | 证据根 | 默认 `./runs`（当前工作目录下，先 `mkdir -p runs`） |
> | `$RT_VPS` | VPS 地址 | 需自备 |
> | `$RT_IP` | 本机公网 IP | 需自备 |
> | `$RT_PUBKEY` | SSH 公钥路径 | 需自备 |
> | `$OAST_DOMAIN` | 外带/DNSLog 域名 | 需自备 |
>
> 本文中所有 `runs/` 均指 `$RT_RUNS`；所有 `redteam_*` 均为**记账接口，当前环境不存在**，
> 等价做法（写 `runs/*.jsonl`）与字段签名见 `50-tool-contract.md`。正文未改写的调用按伪代码读。
>
> 命令内的 `$TARGET` `$IP` `$PORT` `$USER` `$PASS` `$DOMAIN` `$DC_IP` `$HASH` `$NTHASH` `$DB` `$KEY` `$ID` `$TEMPLATE` 按本次目标填写；
> **不要写成 `<target>` 形式**——bash 会把尖括号当重定向符，随即报语法错误。

---

## redteam-setup

> 首次使用引导：引导填写 FOFA_KEY 与 VPS、用演练台环境适配补路径、给出降级口径。不替用户下载或安装工具。


# 首次使用引导（把环境一次配齐）

**触发条件**（满足任一即执行本技能，不要跳过）：
- `redteam_preflight` 返回里 `onboarding.complete=false`；
- preflight 有 `broken` 技能且原因是"缺环境变量"或"VPS 还是占位符"；
- 用户第一次进红队模式、或明确说"环境/工具没配好"。

**核心原则**：**一次性把话说完，一次要齐**。不要挤牙膏式反复找用户要东西。

**红线**：不要替用户下载或安装任何工具。缺什么就说清填到哪，由用户自己补。

## 一、先看本机有没有安装脚本

- **Windows，或没有** `$RT_SETUP.sh`（`onboarding.setup_script.exists=false`）→ 这是正常情况。打开 dsh-purge 演练台「环境适配」，填写工具路径或选整包文件夹自动分配，并填写 `FOFA_KEY`、`REDTEAM_VPS_HOST`、`REDTEAM_VPS_KEY`。
- **有** `$RT_SETUP.sh` → 让用户自己执行 `bash "$RT_SETUP.sh" --check` 看体检。不要由智能体执行 `--yes` 去下载二进制。

## 二、要用户提供什么（一次列清）

| 要什么 | 为什么必须 | 给到哪 | 没有会怎样 |
| --- | --- | --- | --- |
| **FOFA_KEY** | 资产测绘靠它铺开互联网资产；没有就只能靠 crt.sh 和子域枚举，边缘和未备案资产会漏 | 演练台「环境适配」，或 `$RT_HOME/.env` 里的 `FOFA_KEY` | 测绘降级，后面阶段都受影响 |
| **VPS 登录方式**（`user@ip` + 私钥路径） | 需要公网可控主机时才用得上 | `REDTEAM_VPS_HOST`、`REDTEAM_VPS_KEY`（私钥路径） | 拿不到需要落地的成果，进不了内网 |

列完后等用户补齐。只有用户明确说「就按现有条件做」才降级。

用户的 key 不要写进仓库、不要贴进报告。

FOFA key 在 <https://fofa.info> 个人中心。自测：`curl -s "https://fofa.info/api/v1/info/my?key=$FOFA_KEY"`，返回 `"error":false` 即有效。

VPS 连通只确认登录：`ssh -i <私钥> -o BatchMode=yes <user>@<ip> 'echo ok'`。

## 三、配置完再复核

有安装脚本时，完成标记由用户自己的 `--yes` 或手动写入。没有脚本时：

```bash
mkdir -p "$RT_HOME/redteam" && date -Is > "$RT_HOME/redteam/.setup-complete"
```

然后重新跑 `redteam_preflight`，确认 `onboarding.complete=true`。改了 `$RT_HOME/.env` 后要告诉用户重启 dsh，当前进程读不到新变量。

## 四、用户不提供某些资源时

| 缺什么 | 降级方案 | 必须说明的限制 |
| --- | --- | --- |
| FOFA_KEY | crt.sh、被动 DNS、子域枚举、备案信息 | 资产收集不完整 |
| VPS | 只做不需要落地的成果 | 进不了内网 |
| 本机工具 | 在「环境适配」补路径；补不上就缩小范围 | 对应技能不可用 |

降级决定要写进汇报。
