# redteam_* 工具契约（53 个）

> 这些工具属于 DSH 宿主，**当前环境不存在**，不要调用。本表是字段契约，三个用途：
> 读 `references/` 里 130+ 处 `redteam_xxx(...)` 调用时对照参数；自己实现记账系统时复用字段名与幂等键；
> 判断哪些写入是幂等的。SKILL.md 里已给出 `runs/*.jsonl` 的等价替换。

## 四条硬约束（代码里写死的，不是建议）

- `credential_add` 要求口令/密钥**明文**写进 `secret_value`——不存明文就无法横向复用。
- `webshell_add` 只收冰蝎/哥斯拉**加密马**，普通一句话马不算交付。
- `session_check` 由 host 侧**真实发起 HTTP/TCP 连接**实测，再回写在线状态，不读库里的旧值。
- `agent_slot` 用真实运行中子会话数硬卡「同一靶标最多 3 个执行智能体」，超了直接拒绝。

另有两条口径：靶标绑定键是**会话根祖先 id**，子智能体沿 `parentSession` 继承（早期版本用全局当前靶标指针，是多会话串写的根源）；
`score_hit` 同一系统只按最高权限计一次（G1），先记低档后来提权记高档会自动顶掉。

## 幂等与覆盖

`asset_add` 为 upsert；`vuln_add` 带 `cve` 时按 `(asset_id, cve, target)` 幂等更新；`score_hit` 同条高档顶掉低档。
其余 `*_add` 多为追加式，重复调用会产生重复行。

## 全表

`必填` 为空的工具所有参数都可省略，靠当前会话绑定的靶标工作。


### 靶标与会话

| 工具 | 必填 | 关键可选 | 作用 |
|---|---|---|---|
| `redteam_engagement_open` | `target` | `scope` | 打开或创建一次攻防演练靶标（按单位名称），并把**当前会话**绑定到该靶标（子智能体会自动继承） |
| `redteam_session_bind` | — | `engagement` | 把一个**已经存在**的靶标绑定到当前会话（多会话并行时用：每个会话绑自己的靶标，互不串写） |
| `redteam_session_info` | — | `output` | 查看**当前会话绑定的是哪个靶标**（会话 id、父会话、根会话、绑定链） |
| `redteam_preflight` | — | `include` | 平台技能与资源自检：逐个检查红队技能的必需环境变量（如 FOFA 测绘的 FOFA_KEY）、本机工具与二进制（suo5 / fscan /… |
| `redteam_agent_slot` | `action` | `label`, `key` | 执行智能体的并发闸门：同一靶标**最多同时 3 个**在跑（可用 REDTEAM_MAX_AGENTS 配置） |

### 资产库

| 工具 | 必填 | 关键可选 | 作用 |
|---|---|---|---|
| `redteam_asset_add` | `ip`, `provenance`, `names`, `ports` | `engagement`, `state`, `primary_name`, `tool`, `discovered_at`, `first_seen` | 把一个资产及其端口/服务/指纹写入资产库（幂等 upsert） |
| `redteam_asset_link` | `src_kind`, `src_id`, `dst_kind`, `dst_id`, `relation` | `engagement`, `confidence` | 在资产库中写入一条关系边（图谱与后续横向分析共用） |
| `redteam_asset_query` | — | `engagement`, `cidr`, `port`, `service`, `fingerprint`, `provenance` 等 11 项 | 检索资产库 |
| `redteam_asset_get` | `id` | `engagement` | 取单个资产的完整详情：全部端口与服务、指纹、采集溯源时间线、关系边 |
| `redteam_asset_stats` | — | `output` | 资产测绘概览：C 段数、资产数（存活）、开放端口、服务、指纹、被动/主动溯源条数，以及各 C 段的明细 |
| `redteam_asset_graph` | — | `engagement`, `cidr`, `maxNodes` | 导出资产图谱（C 段 → 资产 → 开放端口，含域名解析边），用于拓扑推理与横向移动路径规划 |
| `redteam_asset_timeline` | — | `engagement`, `limit` | 资产「发现时间」视图：按天聚合"哪天收了多少资产"（区分内网/外网），并列出最近发现的资产 |
| `redteam_domain_index` | — | `output` | 按域名维度聚合资产：每个域名关联了哪些 IP/资产 |
| `redteam_web_list` | — | `engagement`, `cidr`, `limit` | 列出 Web 资产（含可直接访问的 URL 与页面标题） |
| `redteam_asset_test` | — | `engagement`, `asset_id`, `ip`, `status`, `test`, `notes` 等 9 项 | 记录对某个资产的测试情况：本次做了什么测试（`test`，追加式）、还剩什么攻击面（`surface`，覆盖式）、当前测试状态、是否被 WA… |
| `redteam_asset_assess` | — | `engagement`, `asset_id`, `ip`, `priority`, `potential`, `reason` 等 7 项 | 给资产做「易打性评估」：预期能拿下哪些成果（账号权限/RCE/服务器权限/数据库权限/敏感数据/边界突破）、优先级多高、判断理由 |

### 漏洞库

| 工具 | 必填 | 关键可选 | 作用 |
|---|---|---|---|
| `redteam_vuln_add` | `title`, `severity` | `engagement`, `asset_id`, `cve`, `status`, `target`, `source` 等 10 项 | 记录一条漏洞发现（漏洞检测角色） |
| `redteam_vuln_query` | — | `engagement`, `severity`, `status`, `cve`, `asset_id`, `cidr` 等 8 项 | 检索漏洞库：按严重级、状态、CVE、资产、C 段或关键词过滤 |
| `redteam_vuln_update` | `id` | `engagement`, `status`, `severity`, `evidence`, `confidence`, `gained` 等 7 项 | 更新漏洞状态/严重级/证据（例如验证后置为 confirmed、利用成功后置为 exploited、误报置为 false-positive） |

### 凭据与访问

| 工具 | 必填 | 关键可选 | 作用 |
|---|---|---|---|
| `redteam_credential_add` | `host` | `engagement`, `username`, `secret_type`, `secret_value`, `secret_ref`, `privilege` 等 11 项 | 记录一条凭据（漏洞利用/内网渗透角色） |
| `redteam_credential_list` | — | `engagement`, `host`, `username` | 列出已收集的凭据（含明文 secret_value），用于凭据复用与横向移动 |
| `redteam_access_add` | `host`, `method` | `engagement`, `username`, `privilege`, `asset_id`, `session_ref`, `note` 等 7 项 | 记录一次成功获得的访问会话（横向移动起点） |
| `redteam_access_list` | — | `engagement`, `host` | 列出已获得的访问会话 |

### WebShell 与隧道

| 工具 | 必填 | 关键可选 | 作用 |
|---|---|---|---|
| `redteam_webshell_add` | `url` | `engagement`, `shell_type`, `pass_key`, `privilege`, `secret_ref`, `asset_id` 等 8 项 | 登记一个已上线的 WebShell |
| `redteam_webshell_list` | — | `engagement`, `status`, `asset_id` | 列出已登记的 WebShell（含在线状态与最后检查时间） |
| `redteam_webshell_update` | `id` | `engagement`, `status`, `privilege`, `note`, `check_note` | 更新 WebShell 状态（被删/掉线/权限变化）或补充说明 |
| `redteam_tunnel_add` | `kind`, `listen` | `engagement`, `entry`, `reach`, `entry_kind`, `webshell_id`, `asset_id` 等 10 项 | 登记一条内网隧道 |
| `redteam_tunnel_list` | — | `engagement`, `status` | 列出已登记的内网隧道（含状态、监听地址、可达网段、entry_kind 与 legit 判定） |
| `redteam_tunnel_update` | `id` | `engagement`, `status`, `listen`, `reach`, `entry`, `entry_kind` 等 8 项 | 更新隧道状态（关闭/失效/更换监听地址）或补 entry_kind 判定 |
| `redteam_sessions` | — | `output` | 一屏总览当前所有可复用入口：已上线的 WebShell、可用的内网隧道（含监听地址与可达网段）、凭据、访问会话，并给出在线/离线统计 |
| `redteam_session_check` | — | `engagement`, `timeoutMs` | 实测所有 WebShell 与隧道的连通性（由 host 侧真实发起 HTTP / TCP 连接），并把在线/离线状态回写数据库 |

### 得分与报告

| 工具 | 必填 | 关键可选 | 作用 |
|---|---|---|---|
| `redteam_score_list` | — | `output` | 查看得分目标面板：所有得分点（名称/分类/分值/是否已拿下/命中证据）与总分进度 |
| `redteam_score_hit` | `evidence` | `engagement`, `code`, `point_id`, `point_name`, `points`, `target` 等 13 项 | 记录一次得分 |
| `redteam_score_point_save` | `name` | `engagement`, `id`, `code`, `category`, `points`, `description` 等 7 项 | 新增或修改得分点（分值/名称/分类/说明/启用） |
| `redteam_score_report` | — | `engagement`, `limit`, `markdown` | 攻击得分链路复现报告：只收录"拿到了分"的成果（没得分的漏洞不进报告），每一项都尽量附上可直接粘贴进 Yakit Repeater 复现的原… |
| `redteam_report` | — | `output` | 生成成果报告（Markdown）：只收录**已验证/已利用且中危以上**的成果漏洞（每条附可粘贴进 Burp/Yakit 的原始请求）、攻击… |
| `redteam_report_targets` | — | `engagement`, `target` | 按目标查看成果报告（每个 IP / URL / C 段一份）：成果漏洞（含可粘贴进 Burp/Yakit 的原始请求）、已获权限、凭据、攻击… |

### 攻击链与攻击面

| 工具 | 必填 | 关键可选 | 作用 |
|---|---|---|---|
| `redteam_chain_add` | `stage`, `title` | `engagement`, `detail`, `tool`, `result`, `asset_id`, `vuln_id` 等 15 项 | 记录一个攻击链步骤 |
| `redteam_chain` | — | `output` | 读取完整攻击链（按步骤顺序），用于汇报与检查链路是否闭合（入口 → 权限 → 内网突破） |
| `redteam_attack_path` | — | `engagement`, `cidr`, `maxNodes` | 导出攻击图谱：资产拓扑 + 漏洞节点 + 已控制资产（meta.owned） |
| `redteam_attack_chain` | — | `output` | 攻击链：按攻击面位置串起来的五个阶段 —— ① 信息收集（互联网侧）→ ② 互联网资产权限 → ③ 边界突破（搭隧道）→ ④ 内网资产权限 … |

### POC 知识库

| 工具 | 必填 | 关键可选 | 作用 |
|---|---|---|---|
| `redteam_poc_search` | — | `q`, `cve`, `component`, `kind`, `category`, `engagement` 等 12 项 | 先查"现成的"两层：① **知识库**（本机沉淀的通用 POC/EXP，跨靶标共享，按"已验证 → 复用次数"排序）② **本机 nucle… |
| `redteam_poc_get` | — | `id`, `code` | 取一条知识库 POC/EXP 的**完整内容**（正文 + 用法 + 验证记录 + 落盘路径），可直接照用或改造成目标专用脚本 |
| `redteam_poc_add` | `title` | `kind`, `category`, `cve`, `component`, `versions`, `severity` 等 21 项 | 把**通用可复用**的 POC/EXP 落进知识库（跨靶标共享） |
| `redteam_poc_list` | — | `kind`, `verified` | 列出知识库里的 POC/EXP（可按 kind/source/component/verified 过滤，不带条件就是全部） |
| `redteam_poc_update` | — | `id`, `code`, `patch`, `verified`, `verified_note` | 更新知识库条目：补验证结论（verified + verified_note）、修正影响版本、补用法或正文、改标签 |
| `redteam_poc_use` | — | `id`, `code`, `used_on` | 记一次知识库 POC/EXP 的复用（用在哪个靶标/目标） |

### 证据与攻击文件

| 工具 | 必填 | 关键可选 | 作用 |
|---|---|---|---|
| `redteam_http_evidence_add` | `request` | `engagement`, `vuln_id`, `asset_id`, `label`, `method`, `url` 等 10 项 | 保存一条 HTTP 证据：原始请求与响应 |
| `redteam_attack_file_add` | `target`, `name`, `evidence` | `engagement`, `kind`, `description`, `content`, `path`, `asset_id` 等 8 项 | 保存一个**实际生效**的攻击文件（脚本/POC/EXP/字典）到目标文件夹，供复用与交付 |
| `redteam_attack_file_list` | — | `engagement`, `target` | 列出已保存的攻击文件（按目标文件夹分组） |

### 角色提示词

| 工具 | 必填 | 关键可选 | 作用 |
|---|---|---|---|
| `redteam_roles` | — | `output` | 列出红队角色及其职责标题（信息收集 / 漏洞检测 / 漏洞利用 / 内网渗透） |
| `redteam_role_prompt` | `role` | `engagement` | 取出某个红队角色当前生效的系统提示词，只供查看 |
| `redteam_role_prompt_reset` | — | `engagement`, `role` | 把角色系统提示词恢复为内置默认（新版模板） |
