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

## nuclei-scan

> nuclei 模板化漏洞扫描：13,000+ 模板覆盖 CVE/暴露面/配置缺陷/默认口令，Nday 与 1day 的主力检测手段


# nuclei（模板化漏洞检测）

`nuclei` 是漏洞发现阶段的**主力**：一条命令覆盖 CVE、暴露面、错误配置、默认口令、未授权访问。
本机模板库已就位（详见下方路径），**不要上网重新找 POC**。

## 本机二进制与模板

| 项 | 值 |
| --- | --- |
| 二进制 | `nuclei`（PATH，或 `$RT_TOOLKIT/nuclei/nuclei`） |
| 模板库 | `$RT_TOOLKIT/nuclei-templates` |
| 模板版本 | v10.4.9（更新于 2026-09-18；**超过 90 天未更新即视为过期**，先跑 `nuclei -update-templates`） |
| 配置 | `~/.config/nuclei/config.yaml`、`.templates-config.json` |

模板分布（写报告时按类引用）：`http/` 11,364（其中 `http/cves` 4,320、`http/misconfiguration` 981、
`http/vulnerabilities` 961、`http/exposures` 707、`http/default-logins` 307）、`cloud/` 663、`file/` 447、
`network/` 282、`dast/` 251。

**更新模板**：`nuclei -update-templates`（频率不超过每周一次；更新后先跑 `-tl` 确认没坏）。

## 基本用法

```bash
# 1) 单目标快速体检（先看会命中什么，不实际打）
nuclei -u https://target.example.com -severity critical,high,medium -rl 30 -c 15

# 2) 批量：从资产库导出的存活 URL 清单
nuclei -l runs/alive-urls.txt -severity critical,high -rl 50 -c 25 \
  -jsonl -o runs/nuclei-$(date +%m%d-%H%M).jsonl

# 3) 指定模板（已知组件版本 → 精确打击，命中率高、噪声小）
nuclei -u http://target:8080 -t http/cves/2021/CVE-2021-44228.yaml
nuclei -u http://target -t http/exposures/ -t http/default-logins/

# 4) 按标签（tags）批量
nuclei -l runs/alive-urls.txt -tags seeyon,weaver,panel,exposure -rl 20

# 5) 只列出会跑的模板（不发包，先评估覆盖面）
nuclei -l runs/alive-urls.txt -tags cve -tl
```

## 关键参数（本场景常用）

| 参数 | 作用 | 建议 |
| --- | --- | --- |
| `-rl` | 每秒请求上限 | 互联网侧 30–50；被 WAF 盯上后降到 5 |
| `-c` | 并发模板数 | 15–25，过高会打崩小站 |
| `-severity` | 只跑指定等级 | 演练只关心 `critical,high`（中低危不得分） |
| `-tags` / `-t` | 模板筛选 | 有指纹线索时优先用，别全量轰 |
| `-jsonl -o` | 结构化输出 | **必须落 `runs/`**，报告要引用 |
| `-proxy` | 走代理 | 降噪用 `cn-proxy-pool`；**内网目标走 suo5 隧道加 `-proxy socks5://127.0.0.1:1080`** |
| `-H` | 自定义头 | 带 Cookie/Token 测登录后功能点 |
| `-duc` | 禁用模板更新检查 | 批量跑时省时间 |
| `-stats -si 30` | 进度输出 | 长任务看进度 |

## 与知识库的配合（先查再打，禁止重复劳动）

动手前先 `redteam_poc_search`（按 CVE / 组件 / 版本 / 正文特征）——它一次查两层：**本机 POC 知识库 + 本机 nuclei 模板库**。
命中就用 `redteam_poc_get` 取全文或直接 `nuclei -t <模板>`；两层都没有才上网找，最后才手搓。

验证有效的新模板/EXP 用 `redteam_poc_add` 回填知识库（带 `category` + `engagement` + `asset_target` + `verified` + `verified_note`，脱敏本次靶标信息）。

## 降噪与自保（重要）

1. **默认 ignore 已排除危险标签**：`~/.config/nuclei/.nuclei-ignore` 里默认忽略 `dos`、`local`、`fuzz`、`bruteforce`、`txt-service`——
   **不要为了"打得更全"去掉这些忽略项**，DoS 类模板会打死生产系统，直接毁掉演练。
2. **先探测后开火**：先用 `-severity critical,high` 跑一轮；命中后再对具体命中项深入，不要一上来全量。
3. **WAF/封禁处理**：被拦先降 `-rl` 到 5 并加 `--delay 1s`，换 UA（`-H "User-Agent: ..."`），
   必要时用技能 `cn-proxy-pool` 换出口；**同一目标累计被封 >3 次立刻放弃**（`redteam_asset_test` status=abandoned + blocked=true），转向下一个目标。
4. **生产系统避开业务高峰**：定时任务、批量任务类模板（如触发同步/重建索引的）先在测试/预发资产上验证。

## 输出与落库（强制）

跑完立刻落库，**不要攒到最后**：

1. 读 `runs/nuclei-*.jsonl`，逐条 `redteam_vuln_add`：
   - `title`（模板名 + 命中点）、`severity`、`cve`（模板带的 `classification.cve-id`）、`target`（**带端口**）、
     `evidence`（命中回显/响应特征/matched-at）、`confidence=confirmed`（nuclei 命中即为已确认存在于响应层面）、
     `gained`（通过它能拿到什么）、`agent=vuln-scan`。
2. **每条确认漏洞配一条 `redteam_http_evidence_add`**：请求行 + Host + 关键请求头 + 响应摘要（模板的 `curl-command` 字段可直接用）。
3. 每个关键动作 `redteam_chain_add`：`stage_code=recon` 或 `internet`，
   `tool` 写**实际命令原文**（例如 `nuclei -l runs/alive-urls.txt -severity critical,high -rl 50 -jsonl -o runs/nuclei-0918.jsonl`），
   `result` 写回显摘要（例如 `命中 3 条：CVE-2023-xxxx（critical）…`）。
4. 测完该资产立刻 `redteam_asset_test` 回写：`status`（testing/tested/no_surface/blocked）、`test`（追加式结论）、`surface`（还剩什么可测）。
5. **只记能得分的面**：与得分无关的信息泄露、版本暴露、CORS/CSRF、SSL 与响应头类问题**最多记一行排除结论**，不深挖、不重复跑。

## 常见坑

| 现象 | 原因 | 处理 |
| --- | --- | --- |
| 一条不命中 | 目标不是 HTTP，或模板被 ignore | 加 `-tl` 看实际跑了哪些模板；确认协议 `-t http/` vs `network/` |
| 大量 `could not resolve` | URL 清单里有死链 | 先用 `pd-httpx` 过滤存活：`pd-httpx -l all.txt -o alive-urls.txt -silent` |
| 命中一堆 low/info | severity 没限 | 演练加 `-severity critical,high,medium` |
| 目标被打挂 | 并发过高 / 跑了 dos 模板 | 降 `-rl`/`-c`；确认 ignore 文件没被动过 |
| 内网目标打不到 | 没走隧道 | 加 `-proxy socks5://127.0.0.1:<suo5端口>`（技能 `suo5-tunnel`） |

---

## dir-bruteforce

> 目录与文件爆破：后台入口、备份文件、配置泄露、源码与版本库暴露（ffuf/feroxbuster/dirsearch/gobuster）


# 目录与文件爆破（找入口的主力）

**实战里大部分入口不是 CVE 打进去的，是目录爆破扫出来的**：后台 `/admin`、备份 `www.zip`、配置 `.env`、
源码 `.git/`、接口文档 `swagger-ui.html`、上传点、调试页、actuator/druid 监控台。
本技能覆盖本机已就位的四个工具，**不要只用一个**——它们的字典与判定逻辑不同，互补。

## 本机工具

| 工具 | 路径 | 版本 | 特点 |
| --- | --- | --- | --- |
| **feroxbuster** | `feroxbuster`（PATH，或 `$RT_TOOLKIT/feroxbuster/`） | Rust，递归爆破最强，自动跟随目录层级，**首选** |
| **ffuf** | `ffuf`（PATH，或 `$RT_TOOLKIT/ffuf/`） | 最快、最灵活，支持多字典/vhost/参数 fuzz |
| **dirsearch** | `dirsearch`，或 `$RT_TOOLKIT/dirsearch/dirsearch` | Python，字典全、报告友好 |
| **gobuster** | `gobuster`（PATH，或 `$RT_TOOLKIT/gobuster/`） | 轻量稳定，dir/dns/vhost 三模式 |

## 一、feroxbuster（首选：递归 + 自动过滤）

```bash
feroxbuster -u https://target.example.com \
  -w "$RT_TOOLKIT/wordlists/raft-large-directories.txt" \
  -x php,asp,aspx,jsp,html,js,zip,tar.gz,bak,sql,txt,xml,json,config \
  -d 3 -t 30 --rate-limit 80 --timeout 10 \
  --filter-status 404 --filter-size 0 \
  -o runs/ferox-target.txt --json -o runs/ferox-target.json
```

要点：`-d 3`（递归深度）别开太大；`--rate-limit` 交给服务器喘气；`-x` 后缀表必须带**备份与配置类**。

## 二、ffuf（最快，多字典 / vhost / 参数）

```bash
# 目录与文件（两轮：先目录，再按命中的目录加后缀）
ffuf -u https://target/FUZZ -w $RT_TOOLKIT/wordlists/raft-medium-directories.txt \
  -mc 200,204,301,302,307,401,403,500 -fc 404 -t 40 -rate 80 -timeout 10 \
  -o runs/ffuf-dir.json -of json

# 敏感文件（备份/配置/源码/密钥）
ffuf -u https://target/FUZZ -w $RT_TOOLKIT/wordlists/quickhits.txt \
  -mc all -fc 404 -t 40 -o runs/ffuf-quick.json -of json

# vhost 虚拟主机发现（同 IP 多站点，边缘资产常从这里出来）
ffuf -u https://target/ -H "Host: FUZZ.example.com" \
  -w $RT_TOOLKIT/wordlists/subdomains-top1million-20000.txt \
  -fs 0 -mc all -t 50 -o runs/ffuf-vhost.json -of json
```

## 三、dirsearch（字典全，适合补漏）

```bash
$RT_TOOLKIT/dirsearch/dirsearch \
  -u https://target.example.com -e php,asp,aspx,jsp,zip,bak,txt,sql,json \
  --random-agent -t 30 --delay 0.1 --exclude-status 404 \
  -r -R 3 --format json -o runs/dirsearch-target.json
```

## 四、gobuster（轻量兜底）

```bash
gobuster dir -u https://target -w $RT_TOOLKIT/wordlists/common.txt \
  -x php,asp,aspx,jsp,zip,bak -t 30 -k -o runs/gobuster-target.txt
```

## 字典（放在 `$RT_TOOLKIT/wordlists`，没有就换已有词表）

| 用途 | 路径 |
| --- | --- |
| 大目录字典 | `$RT_TOOLKIT/wordlists/raft-large-directories.txt` |
| 中目录字典 | `$RT_TOOLKIT/wordlists/raft-medium-directories.txt` |
| 常见文件 | `$RT_TOOLKIT/wordlists/common.txt` |
| 敏感文件（quickhits） | `$RT_TOOLKIT/wordlists/quickhits.txt` |
| 子域（vhost 用） | `$RT_TOOLKIT/wordlists/subdomains-top1million-20000.txt` |

字典目录：`$RT_TOOLKIT/wordlists`。**缺字典时**用 `redteam_credential_list` 里已收集的
单位词（品牌名、拼音缩写）自造小字典——针对性字典命中率往往高于通用大字典。

## 重点目标（扫到就要跟到底）

| 命中 | 下一步 |
| --- | --- |
| `/admin`、`/manage`、`/login`、后台路径 | 交给账号权限路线：默认口令/弱口令（技能 `credential-attack`） |
| `.git/`、`.svn/`、`.env`、`config.php.bak`、`www.zip`、`web.rar` | **源码与配置泄露**：拉下来找数据库连接串、密钥、硬编码账号 → `redteam_credential_add` |
| `swagger-ui.html`、`/v2/api-docs`、`/openapi.json` | 提取全量接口清单 → 未授权与越权探测（技能 `unauth-exploit`） |
| `actuator`、`druid`、`/console`、`/jmx` | 未授权监控台，常直通 RCE 或数据库 |
| 上传点、导入、备份恢复、模板/报表设计 | 交给漏洞利用角色串 getshell 链 |
| `.ssh/`、`id_rsa`、`*.pem`、`*.jks` | 私钥泄露 → 直接尝试登录（`ssh -i`） |

## 降噪与自保

1. **必须先过滤 404 的软 404**：先请求一个不存在的随机路径，看返回状态码与响应长度，用它做 `--filter-size` / `-fs`。
2. **限速**：`-rate 80` / `--delay 0.1` / `-t 30` 起步；被 WAF 拦（大量 403/429）先降到 5–10 req/s。
3. **别碰危险路径**：`/logout`、`/reboot`、`/shutdown`、`/delete*`、`/reset*` 这类会改状态的不要爆破，
   字典里遇到也要排除（会造成业务中断，且演练记分不认）。
4. **被封 >3 次放弃**该资产（`redteam_asset_test` status=abandoned + blocked=true），转下一个。
5. **内网目标走隧道**：feroxbuster `--proxy socks5://127.0.0.1:1080`、ffuf `-x socks5://127.0.0.1:1080`
   （技能 `suo5-tunnel`）。

## 输出与落库（强制）

1. **隐藏路径本身不是得分项**，但**每个拿到东西的路径都要落库**：
   - 找到后台/上传点/接口文档 → 记进该资产 `redteam_asset_test` 的 `surface`（追加式），交给漏洞发现/利用的下一个动作；
   - 泄露源码/配置/密钥/凭据 → `redteam_credential_add`（`source=配置泄露`，`tool` 写路径与命令，明文写 `secret_value`）；
   - 未授权可访问的接口/监控台 → 直接 `redteam_vuln_add`（含 `evidence` 回显）+ `redteam_http_evidence_add`。
2. 每个关键动作 `redteam_chain_add`：`stage_code=internet`（或 `internal`），
   `tool` 写实际命令原文（例如 `feroxbuster -u https://target -w raft-large-directories.txt -x php,zip,bak -d 3 --rate-limit 80`），
   `result` 写命中摘要（例如 `命中 /admin/、/backup/www.zip、/.env`）。
3. 跑完立刻 `redteam_asset_test` 回写 `status`/`test`/`surface`——不写状态后面的人一定重复扫。
4. 字典与结果文件一律放 `runs/`（报告要能复现）。

---

## cn-proxy-pool

> 国内免费 HTTP/SOCKS5 代理池：抓取、验活、按需轮换；只用命令级代理参数，绝不改动本机网络与代理配置


# 国内免费 IP 代理池

免费代理不稳定，定位是**降低被封风险**而不是隐藏身份。关键目标优先用自有出口或 suo5 隧道。

## ⛔ 铁规则：不许动本机的网络与代理配置

使用代理**只允许在单条命令上临时指定**，任何情况下都不要修改本机配置。以下操作一律禁止：

| 禁止 | 说明 |
|---|---|
| 设系统代理 | GNOME/KDE 网络设置、`gsettings set org.gnome.system.proxy …`、`networksetup -setwebproxy`、Windows `netsh winhttp set proxy` |
| 写全局环境变量 | 修改 `/etc/environment`、`/etc/profile`、`/etc/profile.d/*`、`~/.bashrc`、`~/.bash_profile`、`~/.profile`、`~/.zshrc` 里的 `http_proxy` / `https_proxy` / `all_proxy` / `no_proxy` |
| 改工具全局配置 | `~/.curlrc`、`~/.wgetrc`、`~/.npmrc`、`/etc/apt/apt.conf.d/*proxy*`、`/etc/pip.conf`、`~/.docker/config.json`、`~/.gitconfig` 的 proxy 项 |
| 改 proxychains 全局配置 | 不修改 `/etc/proxychains4.conf`、`~/.proxychains/proxychains.conf`；确需用时用 `-f` 指向 `runs/` 下的临时配置，用完删除 |
| 动系统网络 | iptables/nftables 规则、路由表、DNS（`/etc/resolv.conf`）、NetworkManager、起停 VPN/tun 设备 |
| 持久化 export | 不在 shell 里 `export http_proxy=…` 让它留在会话里；要传就**内联**在该条命令前 |

**正确姿势**（全部是命令级、一次性的）：

```bash
P=$(shuf -n1 runs/live-proxies.txt)

# 方式一：工具自带的代理参数（首选）
curl -s --proxy "http://$P" --max-time 15 -I "https://target.example.com/"
nuclei -u https://target.example.com/ -proxy "http://$P" -rate-limit 20
sqlmap -u "https://target.example.com/item?id=1" --proxy="http://$P" --batch --random-agent
ffuf -u https://target.example.com/api/FUZZ -w wordlist.txt -x "http://$P" -rate 20

# 方式二：只对这条命令内联环境变量（不 export，进程结束即失效）
http_proxy="http://$P" https_proxy="http://$P" curl -s --max-time 15 "https://target.example.com/"

# 方式三：只支持原始 TCP 的工具 → 用 suo5 SOCKS5 隧道（技能 suo5-tunnel），
#        不要为它去改系统代理；proxychains 用临时配置文件：
proxychains4 -f runs/proxychains.tmp.conf -q nmap -sT -Pn -p 80,443 10.0.0.5
```

## 一、抓取（多源合并）
```bash
mkdir -p runs && cd runs
curl -s --max-time 20 "https://www.89ip.cn/tqdl.html?api=1&num=50&port=&address=%E4%B8%AD%E5%9B%BD&isp=" \
  | grep -oE '([0-9]{1,3}\.){3}[0-9]{1,3}:[0-9]{2,5}' >> raw-proxies.txt
curl -s --max-time 20 "http://www.ip3366.net/free/?stype=1" \
  | grep -oE '([0-9]{1,3}\.){3}[0-9]{1,3}</td>[[:space:]]*<td>[0-9]{2,5}' \
  | sed -E 's#</td>[[:space:]]*<td>#:#' >> raw-proxies.txt
curl -s --max-time 20 "https://raw.githubusercontent.com/proxifly/free-proxy-list/main/proxies/countries/CN/data.txt" \
  | grep -oE '([0-9]{1,3}\.){3}[0-9]{1,3}:[0-9]{2,5}' >> raw-proxies.txt
sort -u raw-proxies.txt -o raw-proxies.txt && wc -l raw-proxies.txt
```

## 二、验证（并发测活，留下能用的）
```bash
cat > runs/check_proxy.py <<'PY'
import concurrent.futures, sys, urllib.request
TARGET = "http://www.baidu.com"   # 仅测连通性，不携带任何敏感数据
def ok(proxy):
    try:
        op = urllib.request.build_opener(urllib.request.ProxyHandler({"http": "http://" + proxy, "https": "http://" + proxy}))
        with op.open(TARGET, timeout=6) as r:
            return proxy if r.status == 200 else None
    except Exception:
        return None
with open(sys.argv[1]) as f:
    cands = [l.strip() for l in f if l.strip()]
with concurrent.futures.ThreadPoolExecutor(max_workers=50) as ex:
    for res in ex.map(ok, cands):
        if res: print(res, flush=True)
PY
python3 runs/check_proxy.py runs/raw-proxies.txt > runs/live-proxies.txt
wc -l runs/live-proxies.txt
```

## 三、轮换与限速
- 每个请求随机取一个代理；失败自动剔除并换下一个。
- 目标侧仍要限速（`-rate-limit` / `--delay`），代理只是换出口 IP，不是加速器。
- 记录每个出口 IP 的成败，同一目标连续 3 次被封就按漏洞检测提示词里的规则**放弃该目标**。

## 四、注意事项
- **不要通过免费代理传输凭据、Cookie、上传的 shell**——免费代理可能记录流量。
- 测活只测连通性，不要用真实业务请求去测。
- 高频爆破前确认目标没有账号锁定策略；触发锁定前主动停手。
- 用完清掉 `runs/` 下的临时配置（如 `proxychains.tmp.conf`），不要在系统里留下任何代理痕迹。
- 仅在授权演练范围内使用。
