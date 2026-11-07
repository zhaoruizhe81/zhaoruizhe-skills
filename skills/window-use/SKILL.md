---
name: window-use
description: Windows 桌面 GUI 自动化的工具与知识库（PC 本机直跑，或从 Mac 经 SSH 遥控 Windows 均可）：点击、输入、粘贴、截图、闭环验证任意桌面软件（Cisco Packet Tracer、Navicat、SSMS、网易云、安装向导…）。含常驻驱动、比例坐标+锚点、原子步进工作流（一次触发一个动作+一次验证）、按软件划分的应用包（apps/）、按症状索引的坑点速查表（公共坑 70 条 + 各 app 私有坑，报错串可直接 grep）。Use whenever the task involves making Windows desktop software act — automate, drive, click, type, paste, batch-operate, or screenshot any Windows app, even if the user never says "自动化": e.g. 远程操作 windowpc、在 PC 上做实验/装软件/配环境、批量截图、把桌面流程 E2E 走一遍 — locally or over SSH from macOS.
---

# window-use — Windows 桌面 GUI 自动化

把 agent 变成 Windows 桌面的手和眼，闭环推进。四条铁律：

1. **从不向没见过的界面盲发输入**——先截图取证再动手。
2. **撞墙先查坑，再动手修**——任何失败/怪象，第一个动作是对照下文"坑点速查表"+ grep 四类坑文件；
   命中就**按文档解法做，不自创**。这里 70 条公共坑 + 各 app 私有坑每条都是实付过 20 分钟到一整晚的学费，
   你遇到的怪事八成已有编号。**失败第 1 次就必须 grep；同一症状连续失败 2 次强制停**（展开见"失败处理阶梯"）。
3. **原子步进**——一次触发只做一个原子动作，做完立即验证，验证通过才走下一步。
   粒度由 app 包的粒度表定义（如 cisco-pt：连线一条/次）。违反的代价是实付过的：见 公#21。
4. **跑完必回写**——任务收尾（或一个阶段跑通）时，把这轮新付的学费沉淀回 skill 本身
   （见下文"skill 自优化闭环"）；失败阶梯走到第 3 次时，新坑当场就写（不等收尾）。
   不回写，下一个任务会把同样的坑原样再踩一遍。

> 反模式（铁律 2 专治）：点击落空 → 立刻改坐标 / 加 sleep / 换点击方式 / 换 UIA 匹配……
> 每一招都可能对应清单里一条编号明确的坑，自己重新发现一遍平均多花 20~50 分钟——
> 公#34 实付 25 分钟没读过界面报错原文，公#24 实付一整晚几十张空截图，公#22 追了半小时幽灵窗口。
> 改任何东西之前先自问一句：**这个症状我 grep 过坑文件了吗？**

## 本 skill 是什么

一套**长在 PC 上**的通用驱动 + 按软件划分的"应用包"（动作库/坐标表/配方/私有坑）。
在哪运行驱动，就能自动化那台机器的桌面——

- **场景一·本机直跑**：agent 就在那台 Windows 上（如 Windows 里的 ZCode），
  直接 `python win_gui_driver.py click 100 200`，无需任何桥接。
- **场景二·Mac 远程遥控**：经 SSH 投递。SSH 会话在 session 0 碰不到桌面，
  所以多一层"计划任务桥"把驱动投进桌面会话——`remote/` 目录只服务这个场景。

## 目录结构与两层模型

```
window-use/
├── SKILL.md                ← 你在这里（含坑点速查表）
├── scripts/
│   ├── win_gui_driver.py   ★核心驱动（场景无关，唯一必须部署到 PC 的通用件）
│   └── shots_gc.py         截图自动归档（超阈值打包 tar.gz；pt.py 每轮 pull 后自动跑）
├── remote/                 ★远程场景附件（本机直跑时用不上）
│   ├── pt.py               Mac 端遥控器：send/push/pushdir/pull/log/step（本地锁+新鲜度校验）
│   ├── create_task.ps1     session-0 计划任务桥注册（一次性，参数可覆盖）
│   ├── create_task_elevated.ps1  提权版桥（/rl HIGHEST，要点服务管理器/管理员 cmd 时用）
│   ├── shot.ps1            无 Python 的 PowerShell 截图兜底
│   └── 远程坑.md           §1-§11：桥接/schtasks/Git Bash/SFTP/GBK/提权/静默失败/win135/安全并发
├── 脚本用法.md             驱动命令表、script 注入协议、两种调用姿势、部署、校准
├── 踩坑清单.md             【公共坑】公#1-公#40 + 公S1-S7 + 公E1-E7 + 公M1-M12（共 70 条）
├── references/             旧项目（SSMS）深度沉淀存档
└── apps/                   ★应用层：一个软件一个包，"skill 的 skill"（树未列全，以 apps/ 实际目录为准）
    ├── cisco-pt/           Packet Tracer 8.2 包
    │   ├── ptlib.py        PT 动作库（比例坐标+锚点、probe 自检、place/wire/cli_config…）
    │   ├── 坐标与配方.md    校准坐标总表 + 常见操作配方 + Lab2/Lab5 全流程
    │   └── 踩坑.md         PT 私有坑
    ├── navicat/            Navicat Premium Lite 17 包
    │   ├── navlib.py       动作库（登录/开连接/建库/删库，含订阅弹窗自愈）
    │   ├── 坐标与配方.md    弹窗与树坐标总表 + 六个配方
    │   └── 踩坑.md         登录墙/周期弹窗/菜单坐标随行数漂移等私有坑（#1-#11）
    ├── sqldeveloper/       Oracle SQL Developer 24.3 包(2026-10-19 数据库实验1实战)
    │   ├── sqllab.py       动作库（填连接对话框/工作表执行SQL/数据页签增删改/SQL*Plus 控制台）
    │   ├── 坐标与配方.md    坐标总表(工具条/网格/标签) + 六个配方(含出错恢复)
    │   └── 踩坑.md         首启弹窗/zip布局/session0启动/粘贴错行回滚等私有坑
    ├── wps/                WPS Office 包(2026-10-17 项目六 WPS AI 策划书实战，Mac遥控windowpc)
    │   ├── 坐标与配方.md    AI五步配方(框架/细化/表格/校对/保存) + python-docx往返 + 坐标速查
    │   └── 踩坑.md         paste_at^a覆盖全文/会员墙/表格限制/标题劈裂/查找替换漂移等私有坑
    ├── excel/              Excel (Office 365) 包(录屏演示/表格自动化)
    │   ├── 坐标与配方.md    ffmpeg gdigrab 录屏配方 + 素材路径 + 坐标
    │   └── 踩坑.md         ffmpeg 0字节/缩略图坐标缩放/强杀恢复面板/字幕滤镜三连
    ├── ms-project/         MS Project 2024 包(2026-10-20 实战)
    │   ├── 坐标与配方.md    坐标总表 + 插列/筛选/基线/另存等配方
    │   └── 踩坑.md         proj#1-#14：F4开下拉/菜单单轮存活/行高漂移/数字IME/非最大化坐标偏移
    ├── spyder/             Spyder 6 包(2026-10-20 实战)
    │   ├── 坐标与配方.md    启动参数 + 实测坐标 + 分格运行/现成内核接入配方
    │   └── 踩坑.md         首启tour/内核自启失败绕过/autosave卡启动/Mac端CUA别碰
    ├── quartus/            Quartus II 13 + ModelSim 包(2026-10-20 实战)
    │   └── 坐标与配方.md    五步流水线 + 全套校准坐标 + do 模板（坑在 踩坑清单.md 公E/公M 段）
    ├── access/             Access 2016 包(2026-10-26/11-03 花店/图书销售系统实战)
    │   ├── acclib.py       动作库(boot/focus/dyn/DAO建库/VBE注入/两连拍，py_compile 已过)
    │   ├── 坐标与配方.md    功能区/图表向导全坐标 + R1-R6 配方
    │   └── 踩坑.md         A1-A14：COM 自举/CreateControl真签名/DAO要点/静默拒绝/模态两段式
    ├── spss/               SPSS 27 包(2026-10-22/25/26 三次实战)
    │   ├── spsslib.py      动作库(launch_chapter/kill_popups_v2/qtclick/run_syntax/page_viewer…)
    │   ├── 坐标与配方.md    校准坐标 + EXAMINE/t检验/直方图全链路配方 + 粒度表
    │   └── 踩坑.md         SP#1-18 合并.sps单实例/恢复弹窗多层队列且迟到/中文串宽/大纲漂移
    ├── devcpp/             Dev-C++ 5.11 包(2026-11-02 实战)
    │   ├── 坐标与配方.md    菜单/对话框坐标 + 快捷键 F9/F10 + 五个配方
    │   └── 踩坑.md         D1-D11 首启向导/焦点吞按键/GBK 中文源码/卡片对齐/桥脚本回传
    ├── huawei-ensp/        eNSP 包(2026-11-04 win135 实战)
    │   ├── 坐标与配方.md    win135 全坐标两套布局 + R1/R3/R4 配方 + 粒度表
    │   ├── 踩坑.md         N1-N21 手写拓扑丢PC线/冷启动假空白/截图不一致/telnet通道/VRP速记
    │   └── fix_topo.py     拓扑 XML 直改工具（改拓扑走 XML 勿 GUI 连线）
    ├── wireshark/          Wireshark 包(2026-11-05 win135 实战)
    │   ├── 坐标与配方.md    dumpcap+curl 无人值守抓包配方 + tshark 思考题四命令 + win135 全坐标
    │   └── 踩坑.md         W1-W4 Qt菜单UIA盲区(跨轮存活例外)/curl IPv6漏包/模板表格/Npcap
    └── oracle-db/          Oracle 数据库服务端(非 GUI)装配与排障
        └── 踩坑.md         静默安装 rsp/NLS_LANG 字符集/schema 前缀/外键删除顺序
```

**按需读，别全读**——路由表：

| 场景 | 读哪份 |
|---|---|
| **出了任何怪事**（点不中/按键丢/截图不对/桥没反应/陌生报错） | **先看本文"坑点速查表"定位坑号 → grep → 打开对应文件读该条全文。这步不许跳过** |
| 要发驱动命令/写应用脚本 | [脚本用法.md](脚本用法.md)（命令表 + script 注入协议） |
| 远程场景搭建或远程特有报错 | [remote/远程坑.md](remote/远程坑.md) |
| 驱动协议深度理解 / 旧项目战例 | [references/driver-pattern.md](references/driver-pattern.md)、[references/gotchas.md](references/gotchas.md)（存档） |
| 做 Packet Tracer 任务 | [apps/cisco-pt/坐标与配方.md](apps/cisco-pt/坐标与配方.md) + [apps/cisco-pt/踩坑.md](apps/cisco-pt/踩坑.md)，动作写脚本调 `ptlib` |
| 做 eNSP（华为网络模拟器）任务（拓扑/连线/启动设备/VLAN/PC ping 测试/截图） | [apps/huawei-ensp/坐标与配方.md](apps/huawei-ensp/坐标与配方.md)（win135 全坐标两套布局+R1 文件关联开拓拓/R3 telnet 平行通道/R4 PC ping 配方+粒度表）+ [apps/huawei-ensp/踩坑.md](apps/huawei-ensp/踩坑.md)（N1 手写拓扑丢 PC 线=PC 缺 slot 接口声明【静默】+N4 冷启动加载 2-5 分钟假空白+N6 进程/窗口模型+N10 截图与用户所见不一致排查链+N14 无模拟面板→数据抓包▶(Wireshark)+真实ping 配方+N15 右键菜单坐标+N16 PC 设置窗/改名+N17 VRP 命令速记+N21 step 自动拉图 DOWNLOAD-FAIL）+ [apps/huawei-ensp/fix_topo.py](apps/huawei-ensp/fix_topo.py)（改拓扑走 XML 直改勿 GUI 连线），2026-11-04 实战；win135 桥见 remote/远程坑.md §10 |
| 做 Navicat 任务（建/删库、登录、开连接、表设计器建表/主键/外键/CHECK/索引） | [apps/navicat/坐标与配方.md](apps/navicat/坐标与配方.md) + [apps/navicat/踩坑.md](apps/navicat/踩坑.md)（navicat #8-#11 表设计器/增量保存/索引外键检查页签），动作写脚本；windowpc 走 AUTO/MysqlLab 桥（remote/远程坑.md §9） |
| 做 SQL Developer 任务（连接、工作表执行 SQL、数据页签增删改、SQL*Plus） | [apps/sqldeveloper/坐标与配方.md](apps/sqldeveloper/坐标与配方.md) + [apps/sqldeveloper/踩坑.md](apps/sqldeveloper/踩坑.md)，动作写脚本调 `sqllab` |
| 做 WPS Office 任务（AI 写作、文档自动化、报告生成） | [apps/wps/坐标与配方.md](apps/wps/坐标与配方.md)（AI五步配方 + python-docx往返 + 坐标速查）+ [apps/wps/踩坑.md](apps/wps/踩坑.md)（paste_at^a覆盖全文/会员墙/表格限制，2026-10-17 实战） |
| 做 Excel 任务（表格自动化、录屏演示、字幕烧录、打开xlsx截图/公式视图） | [apps/excel/坐标与配方.md](apps/excel/坐标与配方.md)（ffmpeg gdigrab 录屏配方）+ [apps/excel/踩坑.md](apps/excel/踩坑.md)（0字节/坐标缩放/恢复面板/登录墙/分析数据绿栏/Ctrl+PgDn失效点标签/Ctrl+`公式视图需IME英文态/状态栏100%开缩放对话框/对话框收尾必关/切表延迟需验证/保存提示坐标逐次实测） |
| 做 MS Project 任务（进度计划/资源/基线/筛选/统计，mpp 自动化） | [apps/ms-project/坐标与配方.md](apps/ms-project/坐标与配方.md)（坐标总表+插列/筛选/基线/另存等配方）+ [apps/ms-project/踩坑.md](apps/ms-project/踩坑.md)（F4开下拉/菜单单轮存活/行高漂移/数字IME，2026-10-20 实战） |
| 做 Spyder/科学计算 IDE 任务（跑分格代码、内核排障、跑代码截图） | [apps/spyder/坐标与配方.md](apps/spyder/坐标与配方.md)（启动参数+实测坐标+分格运行/现成内核接入配方）+ [apps/spyder/踩坑.md](apps/spyder/踩坑.md)（首启tour弹窗/内核自启失败绕过/Mac端CUA别碰，2026-10-20 实战）；公共坑 公#32-34 |
| 做 Quartus/ModelSim EDA 代做任务（VHDL、RTL 图、波形仿真、报告三件套批量产出） | [apps/quartus/坐标与配方.md](apps/quartus/坐标与配方.md)（v1 五步流水线 + v2 六报告批量实战：编辑器直截/RTL/波形缩放对话框/裁剪拼报告，全套坐标，2026-10-20/10-28 两次实战）；坑在 踩坑清单.md 公E1-E7/公M1-M12/公#36-#39 |
| 装/排障 Oracle 数据库本身（静默安装、监听、sqlplus、字符集、schema） | [apps/oracle-db/踩坑.md](apps/oracle-db/踩坑.md) |
| 做 SPSS Statistics 任务（语法驱动跑统计输出、导出/截图、对话框坐标） | [apps/spss/坐标与配方.md](apps/spss/坐标与配方.md)（校准坐标+EXAMINE/置信区间/直方图/两独立样本t检验全链路配方+粒度表）+ [apps/spss/踩坑.md](apps/spss/踩坑.md)（SP#1-18：合并 .sps 单实例跑、恢复弹窗多层队列且晚于固定 sleep 出现（SP#18）、中文串宽按字节、RECODE 静默失败换 COMPUTE+IF、大纲漂移改翻页截图、GPL 不可用改传统 GRAPH、批量任务新鲜启动循环见配方D、t检验小输出整窗截图+本地裁剪见配方E）+ spsslib.py 动作库（launch_chapter/kill_popups_v2/qtclick/run_syntax/page_viewer/shoot_data_view），2026-10-22/25/26 三次实战 |
| 做 Access 任务（建库建表/有效性/查询/窗体/报表/切换面板自动化） | [apps/access/踩坑.md](apps/access/踩坑.md)（A1 COM 自举：GetActiveObject 必败+Access 随 pythonw 退出、每脚本全新会话；A2 CreateControl/CreateReportControl 真签名、RunCommand(37) 加报表页眉页脚节、(521) 开切换面板管理器；A3 makepy dyn() 包装；A4 DAO 属性入库后再挂/拒关联聚合 UPDATE/日期传字符串防 8h 偏移；A5 数据表验证规则静默拒绝无弹窗；A6 模态对话框两段式 GUI 驱动、Switchboard Items 表直填速成；A7 截图杂项+坐标；A8 COM/DAO 建库速成；A9 信任位置注册表法；A10 控件类型常量表(122=ToggleButton,114=ObjectFrame)；A11 MSGraph 图表窗体程序化嵌入已死→GUI 向导全坐标；A12 数据表列头空白→挂附加标签；A13 dyn() 必须动态分发(InsertLines兜底/frm.Detail)；A14 远程 Git Bash 路径转换走 .cmd 文件通道），2026-10-26/11-03 两次实战。动作库 [apps/access/acclib.py](apps/access/acclib.py)（boot/focus/dyn/DAO建库/查询幂等建/列头标签/事件按钮/VBE注入/两连拍，py_compile 已过）+ [apps/access/坐标与配方.md](apps/access/坐标与配方.md)（功能区/图表向导全坐标 + R1-R6 配方），2026-11-03 实战 |
| 做 Dev-C++ 5.11 代做任务（打开/编译/运行 C 程序、控制台交互截图、GBK 中文源码、卡片对齐） | [apps/devcpp/坐标与配方.md](apps/devcpp/坐标与配方.md)（菜单/对话框坐标+快捷键 F9/F10+五个配方）+ [apps/devcpp/踩坑.md](apps/devcpp/踩坑.md)（D1 首启向导/D2 F9 被菜单焦点吞/D5 Ctrl+F4 无效+Ctrl+O 不重载/D6 [Executing] 标题/D9 中文对齐，2026-11-02 实战） |
| 做 Wireshark 抓包分析任务（抓 TCP 踪迹、协议层截图、Wireshark Lab 思考题、Npcap 环境排障） | [apps/wireshark/坐标与配方.md](apps/wireshark/坐标与配方.md)（dumpcap+curl -4 无人值守抓包配方、tshark 思考题四条命令、win135 全坐标：菜单栏/报文行/详情树/Stevens 图三级菜单）+ [apps/wireshark/踩坑.md](apps/wireshark/踩坑.md)（W1 Qt 菜单 UIA 盲区且实测跨轮存活/W2 curl 走 IPv6 漏过滤器→dumpcap 0 字节/W3 模板表格 cells[2] 是标签/W4 Npcap 环境），2026-11-05 win135 实战 |
| 接入一个新软件 | 本表 + 脚本用法.md 的校准一节，产出新 `apps/<软件>/` 包 |

**知识点归位判断一条线**：换个软件/换本机远程场景还成立 → 通用层；
只因这个软件成立 → `apps/<软件>/`；只因"远程"这个场景成立 → `remote/`。
新软件只新增 apps/ 目录、新场景只新增对应附件目录，核心永不动——
买油翁：新软件付一次"开眼校准"成本，沉淀成包，之后同软件任务全部盲跑。

## 工作流：原子步进协议（一次一个动作，一步一验证）

**硬性规则：一次驱动触发 = 一个原子动作 + 一次验证。** 循环推进：

0. **开工前（每任务一次）**：读 `apps/<软件>/踩坑.md` 全文（多数 ≤12KB，1 分钟；
   cisco-pt 31KB 最大，可按症状段读）+
   扫一遍下文"坑点速查表"；远程场景加读 remote/远程坑.md §3 排障纪律。
   知道有哪些坑，才能在坑出现的瞬间认出它。
1. **净场**：断言目标应用单实例（`tasklist` 查重）、无残留弹窗/菜单——esc 清不掉
   已弹出的设备对话框（点它的 X，如 ptlib.`close_leftovers()`）；残留对话框会把下一次的
   坐标点击吸进对话框里，动作全打偏（Lab4 v2 实付：整套配置粘进了另一台设备）
2. **发一个原子动作**——一个脚本只做粒度表里的一份（粒度按 app 包定义，cisco-pt 见
   [apps/cisco-pt/坐标与配方.md](apps/cisco-pt/坐标与配方.md) 的粒度表；如连线=一条/次）
3. **验证**：等 gui.log DONE → 拉截图 → **看图确认**（必要时平行通道查真值）
4. 通过 → 下一个动作；**失败 → 立即进入下面的"失败处理阶梯"，禁止直接改参数重试**
5. **收尾回写**：整个任务跑完（或一个阶段稳定跑通）→ 执行下文"skill 自优化闭环"，
   然后才算结束

### 失败处理阶梯（第 4 步失败分支的展开，铁律 2 的落地）

| 触发 | 必做 |
|---|---|
| **失败第 1 次** | ① 取证：看 `error_*.png` / 拉全屏截图。② **查坑**：速查表扫对应症状桶 + 用报错关键词 grep 坑文件（命令见速查表开头）。③ 命中 → **按文档解法做，不自创**；确认未命中 → 才允许"净场后重试同一个动作，一次只改一个变量" |
| **失败第 2 次**（同动作同症状） | **强制停**。换关键词再 grep 一轮；打开 `apps/<软件>/踩坑.md` 全文找近似症状；**先 crop 放大读界面报错原文**（公#34：一切诊断从报错原文开始，无头手段只做平行验证），再写**只读诊断**（`winlist`/UIA dump/平行通道）拿证据——不许再盲改 |
| **失败第 3 次** | **禁止再试同一路径**。绕路：UIA↔像素、鼠标↔键盘、GUI↔平行通道（文件/API/SSH），或改用离线方案（如 WPS 的 python-docx 往返）。并把新坑**立即**写进对应坑文件 + 速查表加一行（不等收尾） |

改任何东西之前先回答一句：**这个症状我 grep 过坑文件了吗？** 没有 → 现在做，30 秒。

为什么是硬性规则（Lab4 实付的学费）：一个脚本里连续连线多条，第一条之后 B 端端口菜单
**必现不弹**，失败还污染现场让后续脚本诡异地"成功却无效"；同样的连线拆成"一次触发一条"
5/5 全成。多动作脚本中途失败时既无法归因是哪步坏的、也没有失败瞬间的截图。原子化的
代价只是远程场景每次触发 ~15s 驱动冷启动——相比排障时间，这是最便宜的保险。

补充：首次接触任何对话框/菜单先 `shot`/`crop` 取证；校准过的坐标可连续盲跑，
关键动作后仍截图留档。

**何时必须开眼**：新 PC/新分辨率首跑（`ptlib.probe()`）、没见过的对话框
（给应用包攒知识的时机）、需要留档的证据图。
**何时可以闭眼**：坐标表与配方文档里写明的标准动作——且仍按原子步进推进。

## 坑点速查表（失败时第一个看这里，公共坑 70 条 + app 私有坑，按症状索引）

按"**你看到的现象**"分桶，不是按原因分。命中后读该条原文再动手。

**引用格式**：`公#N`/`公S*`/`公E*`/`公M*` = [踩坑清单.md](踩坑清单.md)（**标题即编号，grep 引用串直接命中**；N=编号坑，S=静默安装段，E=EDA 段，M=ModelSim 段）；
`远§N` = [remote/远程坑.md](remote/远程坑.md) 第 N 节；
`pt/navicat/sqldev(sqldeveloper)/wps/excel/proj(ms-project)/spyder/access/oracle-db` = `apps/<对应名>/踩坑.md`（条目标题即编号，如 navicat #8、proj#1-#14）；
`SP#N` = apps/spss、`D#N` = apps/devcpp、`N#N` = apps/huawei-ensp、`W#N` = apps/wireshark 各自踩坑.md；
quartus 无私有坑文件，其坑在 踩坑清单.md 的 公E/公M 段。

**先 grep，再读全文**（在 skill 根目录 `~/.zcode/skills/window-use` 下）：

```bash
grep -rn -i -E "关键词1|关键词2|关键词3" 踩坑清单.md remote/远程坑.md apps/*/踩坑.md
```

关键词优先取：**报错原文片段**（`1053`、`vsim-3039`、`payload initialization`）、
**症状动词**（落空/没反应/吞/卡住/跳过/乱码/拼接）、**界面元素**（菜单/网格/下拉/剪贴板/截图）。
命中任何一条 → 打开对应文件读全文 → 按解法做。
上面 grep 无命中时，把 `apps/*/坐标与配方.md` 也扫进来（个别包有坑住在配方文档里）。

### 桶 1 · 点击/按键发了但没反应

| 你看到的 | 坑 | 一句话解法 |
|---|---|---|
| 屏幕上有弹窗/对话框在等按钮；菜单打不开、按键像消失、命令超时 | 公#8 proj#7 | 先截全屏找弹窗，UIA/坐标点掉再继续 |
| 菜单已弹出、坐标算对，click 毫无反应（Qt 系） | 公#11b pt | moveTo 悬停 → mouseDown/Up；点后扫描菜单是否消失 |
| 窗口在屏幕上、UIA 枚举不到、点击被吞（标题带"管理员:"） | 公#11c 远§4 | UIPI 隔离：taskkill 关它；要操作它就注册提权桥 |
| 菜单扫不到、点击落空、截图与 UIA 对不上的各种灵异 | 公#11d pt | 双实例：tasklist 查重，保住有进度的那个再杀多余 |
| esc 关掉菜单后按 F9 等功能键毫无反应（Dev-C++ 等） | devcpp D2 | 菜单栏焦点残留吞按键：先点编辑区拿焦点再按键 |
| 上一个脚本崩了之后，后续同类操作"成功却无效" | 公#11e 公#21 | 残留现场：开头双 esc 清场；一次只做一个动作 |
| 点击落在别的窗口上（目标被盖住） | 公#16 公E4 | 点前 `raise_topmost`；多余大窗口先最小化 |
| 上一轮脚本开的菜单，这一轮点菜单项落空 | 公#18 公#30 proj#2 | 开菜单→点项放**同一脚本**；菜单不跨驱动轮次（**例外**：Wireshark Qt 菜单实测跨轮存活，见 wireshark W1） |
| Wireshark 等 Qt 菜单 UIA 枚举不到 MenuItem（popup #32768 不出现） | wireshark W1 | 放弃 UIA，shot 读坐标点菜单；多级菜单可拆两轮（开菜单+截图 → 按图点项） |
| ribbon 组合框点不开 / 开了即关 | 公#30 proj#1 | `click 框 → press f4`；开完截图核对焦点没串 |
| 点了之后马上截图像没生效，于是又重点了一次 | 公#24 excel | ~1s 渲染延迟：sleep≥1.2s 再截；偶成偶空=时序不是坐标 |
| 键盘导航/type-ahead 对列表无效 | 公#16 | 先真实点击**某一行**拿焦点，点空白不算 |
| 滚轮滚不动网格 | proj#5 | click 任意单元格 → `press pgdn` |
| 每隔一两分钟弹"会话过期"/登录墙打断操作 | 公#19 navicat #1/#2 | `nags_click` 自愈循环；向用户要账号登录一次 |
| 黑色控制台窗口抢焦点、污染每张截图 | 远§1 | 桥的动作必须 pythonw.exe **无参数**，不是 .bat/python.exe |
| 悬挂的下拉/浮层收不掉：esc 无效或串焦点 | 公#28 公#30 | 非模态下拉 esc 安全；网格内悬挂下拉**点远处空白格**收；模态对话框严禁 esc |
| 第二轮 Popen stats.exe 报"文件不存在/变量未定义"、出现两个 stats.exe | spss SP#7 | SPSS 不单实例：多步语法合并成一个 .sps 同实例一次跑完，别再 Popen |
| SPSS 恢复弹窗多层队列、老取消坐标点不中、普通 click 被吞 | spss SP#11/SP#12 | Qt 点击(moveTo+mouseDown+mouseUp)→esc→altF4 三级递进；按钮位 crop 实测；等窗口期间持续轮询清弹窗（弹窗会迟到 30~60s） |
| eNSP 设备右键菜单项坐标随菜单开向（上翻/下开）和多选状态漂移，盲点点到框外只关菜单 | eNSP N15 | rclick 后必 shot 核对菜单位置再点；先点空白取消多选（选中态菜单含“删除”，误触会弹删除确认） |
| RECODE INTO 新变量静默不生成，后续 FORMATS 报未定义 | spss SP#14 | 别恋战：COMPUTE 新=1 + IF(x GT 切点) 新=2 + EXE 等价替换 |
| CLUSTER 树状图冰柱图全没、SAVE 群集变量未建 | spss SP#17 | ICICLE→VICICLE；Ward 配 SEUCLID（EUCLID 分组不可解释） |
| 表设计器网格点空白不加行;未提交新行上 ESC=撤销整行(数据消失) | navicat #8 | "添加字段"加行(先ESC清编辑态);新行用点击已有行提交,禁 ESC;类型格直接粘"CHAR(9)"全定义 |
| Navicat 添加字段连用触发内部错误崩溃(insert Index larger than COLList) | navicat #9 | 首存命名尽早+每加一字段 Ctrl+S 增量保存;崩溃报告可关,主程序或仍存活 |
| Navicat 索引页签下拉无 PRIMARY;主键按钮在格编辑态下无效 | navicat #11 | 主键回字段页签点行头选中后再点主键按钮;复合主键逐行追加 |
| Access 数据表输非法值不弹验证对话框，单元格红/粉框、铅笔标记、点哪都没反应 | access A5 | 静默拦截是常态不是故障：证据用字段属性特写+无效态截图+DAO 复查值，别恋战弹窗 |
| 一次 drag 中断后所有 click 都被当成 drag（按下拖走、界面乱点一气） | 公#3 | 左键卡死：每条命令前 mouseUp(left) 复位（驱动主入口已内置），先复位再诊断 |
| 菜单想用加速键/方向键导航，结果焦点漂移、猜错顺序点到危险项 | 公#7 | 菜单操作总则：打开后截图读位置、鼠标坐标点击；加速键跨版本/语言不可靠；菜单生命周期先读公#18 |
| 按键没反应就连环改坐标/换点击方式/换匹配 | 公#12 | 先截图：90% 的"按键没反应"一张截图就能定位（焦点在别处/弹窗挡住/菜单没开） |
| 同一症状连败，一轮里同时改坐标+等待+匹配好几个变量，无法归因 | 公#14 | 一次只改一个变量；反复失败先查坑，再跑只读诊断（winlist/UIA dump/截图）基于证据修 |
| 界面上明明有报错红框/弹窗，却绕道 SSH 查进程、命令行复现猜原因（无头惯性） | 公#34 | 一切诊断从 crop 放大界面报错原文开始；无头手段只做平行验证（公#13） |
| 第二轮 Popen 打开另一文件报"文件不存在/变量未定义"，tasklist 有两个该 exe 进程（通用版，不只 SPSS） | 公#35 | 多文档 GUI 二次 Popen=开全新实例不共享上下文：多步任务合并一个文件一次跑，或走窗口内打开菜单 |
| Dev-C++ 编译完底部只有标签条看不到日志，以为编译没执行 | devcpp D3 | 编译日志面板默认折叠：点「编译日志」标签展开 |
| Dev-C++ 编译/运行快捷键拿不准、按错没反应 | devcpp D4 | F9=编译 F10=运行 F11=编译运行；不确定先开「运行」菜单截图核对再 esc |
| eNSP 对设备图标合成双击连试多次只选中（变橙），配置/控制台窗口从不弹出 | eNSP N13 | 双击打不开是常态：右键设备→设置(PC)/CLI(交换机)开窗；开窗后按设备名动态定位窗口再取坐标 |
| eNSP 工具栏和右键菜单都找不到连线项；想连线却把设备拖得叠罗汉 | eNSP N5 | 连线走左侧面板「设备连线」类别点线缆图标；拖拽=移动设备不是连线；能改 XML 别 GUI 连线（fix_topo.py） |
| Navicat 偶发"有新的版本可用"更新弹窗抢焦点 | navicat #3 | 点"跳过此版本"，别点下载——版本一变全部坐标要重校 |
| SQL Developer 首启连弹"导入首选项"和"使用情况跟踪"对话框挡操作 | sqldeveloper #2 | 依次点 否→确定 点掉两连弹窗，再最大化（坐标见包） |
| SQL Developer 启动弹窗每次开机重现：遥测框+展开连接弹密码框 | sqldeveloper #11 | 启动序列固定：关遥测框(1103,604)→最大化→密码框 paste_at 密码+确定，别假设上次点过这次就没了 |
| SQL Developer 点工作表标签没切换，或点偏到关闭 X 把标签关了 | sqldeveloper #7 | 点标签后必 shot 验证真切换；标签 X 附近易误关，被关的工作表右键连接重开 |
| SQL Developer 切标签弹"是否保存更改"，点否连工作表标签一起被丢弃 | sqldeveloper #6 | 粘错行先点"取消编辑"再丢弃，别在确认框里把标签内容连工作表一起丢 |
| SQL Developer 树节点右键菜单跨轮存活（公#18 的 app 例外），菜单助记是 V 不是 N | sqldeveloper #13 | rclick+shot 取证后，下一轮直接点菜单项坐标；创建视图走"视图"右键→新建视图(V)，向导坐标见包配方G |
| Spyder 首启弹 "Welcome to Spyder!" tour 对话框挡住中栏 | spyder | 点 Dismiss 点掉再动别处；启动后 75s 内必现，先截图确认 |
| WPS 选中表格按 Delete 只清了内容剩空表壳 | wps | 右键→全选表格→Backspace 才删表对象；两相邻表之间必须保留段落 |
| WPS Ctrl+Shift+S 另存为没反应 | wps | 另存为快捷键是 F12 |

### 桶 2 · 点击落点偏了 / 落错位置

| 你看到的 | 坑 | 一句话解法 |
|---|---|---|
| 高 DPI 屏上点击系统性偏移 | 公#4 | 自定义脚本别丢 `SetProcessDPIAware()`（驱动已内置） |
| 手算像素坐标连点三次不中；工具栏一变整体漂移 | 公#16 | UIA 能暴露的控件用 `targeted_find` 点元素中心 |
| 按 Read 显示的缩略图（1440×810）算坐标脱靶 | 公E5 | 坐标一律按 mss 真实分辨率（1920×1080）算，Read 会缩放 |
| 按几步前截图算的行 y 点到相邻行 | 公#31 proj#4 | 行高随换行 27↔54px 跳变；点前用**当前截图**现算 |
| 换文件/插列之后按旧列头坐标点错 | 公#28 proj#10 | 布局每次动作后整体漂移；先 shot 现算 |
| 打开文件后所有坐标整体偏 | proj#11 | 窗口可能没最大化：先点最大化按钮再 shot 确认 |
| 坐标点进了残留对话框（配置粘到别的设备） | 公#11e | 净场：点掉 esc 清不掉的对话框（`close_leftovers`） |
| 屏幕上有对话框但 `Desktop.windows()` 枚举不到 | 公#5 | 内嵌子面板被拍平：主窗口 `descendants` 找；或退化像素 |
| Access 数据表双击列边界想自动调宽，结果整列被选中、日期列仍显示#### | access A7 | 列宽走 DAO 挂 `ColumnWidth`(twips) 属性后再开视图，别用双击 |
| 顶层窗体/分割窗体数据表列头空白（子窗体却正常） | access A12 | 给每个 TextBox 挂附加标签（CreateControl parent=控件名），标签 Caption=列头 |
| Access COM 建图表：CreateControl(122) 得到切换按钮；Class+Action 嵌入报“并未包含OLE对象”；VBA 也失败 | access A10/A11 | 114=ObjectFrame；MSGraph 程序化嵌入在 2016 已死，唯一活路=GUI 图表向导（完整坐标在 A11） |
| pywinauto/win32com gen_py 包装丢方法（Module.InsertCode/图表.Class），frm.Section() 报找不到成员 | access A13 | dyn() 用 dynamic.Dispatch；Module 用 InsertLines(1,code) 兜底；Section 换 frm.Detail.Height |
| 点菜单坐标偏移误触发"插入任务"，网格顶部冒出无名任务行、WBS 全体重排 | proj#14 | 单击最左行号选中整行→delete 直接消失（无确认框），删后核对相邻行名称 |
| eNSP 拓扑窗口位置/布局每轮都不同，复用上一轮记忆坐标点错 | eNSP N11 | 窗口按 topo 存的几何还原，最大化/非最大化两套布局差几百像素：每轮动作前 shot 现算 |
| Navicat 右键菜单项/删库点错行——树行 y 随建删按字母序漂移 | navicat #4 | 菜单项=右键锚点+固定偏移，但树行 y 不是常数：动手前截图数行再算 y |
| SQL Developer 数据页签添加行后按旧 y 点单元格，值粘错行 | sqldeveloper #5 | 新行位置随新增行数变：先 shot 确认行号再点格（工具栏坐标见包） |
| SQL Developer 连接树行 y 与上次记忆差 20px+，点中相邻节点 | sqldeveloper #12 | 动手前 crop 放大读行位置现算，别用记忆坐标 |
| WPS 查找替换对话框布局随结果面板展开漂移，paste_at 点空、替换戳进表格单元格 | wps | 弃 GUI 修文本走 python-docx 往返：保存→拉回→改→推回重开（推回前先关旧文档选不保存） |
| WPS ribbon 按钮（帮我写）按历史坐标点到相邻按钮——启用过校对等文档级功能后选项卡增删、按钮移位 | wps | 跨阶段操作前必须重新截图定位按钮，别迷信历史坐标 |
| WPS AI 生成内容插错位置：标题被劈成两半、拒答语插进文档开头 | wps | 帮我写写在当前光标处：插入前先点到标题之后的正文空段落，完成后核对标题完整性 |
| Excel Alt+F4 保存确认框"不保存"按钮位置每次都不同，老坐标脱靶 | excel | shot→crop 放大按钮区实测坐标→点击→再 shot 验证 |

### 桶 3 · 输入的内容错 / 丢 / 变汉字

| 你看到的 | 坑 | 一句话解法 |
|---|---|---|
| Enter 变汉字；单字母快捷键弹拼音候选 | 公#1 公M6 | 动作前 `press shift` 切 EN；文本一律剪贴板 |
| `PC12`→`PC2`、括号被吃、带空格命令连写 | 公#2 公E3 | `set_clip + ^v`；组合键用 `hotkey` 不用 `press`/`typewrite` |
| 纯数字 type 无痕失败 | proj#6 | 数字也中 IME 的招，一律剪贴板 |
| 对话框输入框粘贴"成功"回头是空的 | 公#17 | 模态期间别 set_focus：用 `paste_at`（点→^a→^v 不碰句柄） |
| 粘贴变成"原值+新值"拼接 | proj#3 proj#12 | 先进编辑态 ^a 再 ^v；粘贴后裁剪该格验证 |
| 整篇文档被提示词覆盖 | wps | `paste_at` 的 ^a 落在正文：瞬态控件同脚本内操作；出事立刻 Ctrl+Z |
| 控制台 `--More--` 把下一行当翻页键吃掉 | 公#9 | 长输出后先贴 q/回车冲掉分页 |
| 网格内嵌编辑器粘贴无痕失败，2-3 步后才发现 | 公#28 | 改键盘方向键定位+回车；每步裁剪目标区验证 |
| SPSS DATA LIST 中文行整行静默变系统缺失 | spss SP#10 | 字符串宽度按字节=字数×3+余量；跑完先查频数表缺失数 |
| Ctrl+S 无报错但文件没落盘 | wps | 对话框开着时保存静默失败；用**远端 mtime** 验证 |
| 写进 Access 的日期比预期早 8 小时（10-18 变 10-17 16:00） | access A4 | pywin32 把 naive datetime 按 UTC 平移：日期一律传 "YYYY/MM/DD" 字符串 |
| dclick 任务名打开"任务信息"又取消，格子停在空编辑态，稍后粘贴/回车把名字写丢 | proj#13 | 重新 click 该格→^v 正确名字→enter 并截图核对；粘贴目标行必须先 shot 核实 |
| Dev-C++ 打开 Mac 生成的源文件中文注释/字符串乱码 | devcpp D8 | Dev-C++ 5.11 默认 ANSI(GBK)：Mac 侧 UTF-8 写→encode('gbk')+CRLF 再 push |
| Dev-C++ 控制台 scanf 交互不知道怎么喂输入；运行结束停在「请按任意键继续」 | devcpp D10 | 数字直接打（IME 英态）；中文 set_clip+ctrl+v 一行一次；结束 press enter 关窗，截图赶在关窗前 |
| VRP/PC 配 IP 时 210.051.x.x 这类前导 0 网段被拒/配不上 | eNSP N19 | 前导 0 去掉（051→51）；重拍顺序：先连通性 ping（脏态）→清态出初始态证据→抓包；清交换机 MAC 表必须在预热 ping 之后 |

### 桶 4 · UIA 找不到 / 查询很慢

| 你看到的 | 坑 | 一句话解法 |
|---|---|---|
| 控件显示"选择"但 `window_text()` 返回空 | 公#6 | winlist/dump/截图三者对齐后再写匹配 |
| `print_control_identifiers`/`descendants()` 跑几分钟不返回 | 公#15 | 只做定向 `descendants(control_type=…)`；远程还会连带 IgnoreNew 假死 |
| find_window 匹配 Dev-C++ 报 ElementAmbiguous（2 个元素） | devcpp D7 | 主窗口用全模式 'xxx.c - Dev-C++'；MDI 子窗口才是短模式 |
| 运行中 raise 主窗口报 no window | devcpp D6 | 标题插了 [Executing]：改匹配 'xxx.exe' 控制台或收尾先关控制台 |
| 提权窗口 UIA 不可见、点击被吞 | 公#11c 远§4 | 见桶 1；根因 UIPI |
| 控件查找/点击偶成偶败，同一脚本时灵时不灵（应用还没就绪） | 公#11 | 冷启动时间差异：轮询特征控件/产物文件出现再动作，不固定 sleep |
| Navicat 树项/菜单项想用 UIA 定位但枚举不可靠/没验证过 | navicat #6 | Qt 界面 UIA 支持一般：主窗口能找，树项/菜单项走校准坐标+截图闭环；要升级 UIA 先 probe 验证 |

### 桶 5 · 截图不对 / 截图在说谎

| 你看到的 | 坑 | 一句话解法 |
|---|---|---|
| 截图是几天前的旧窗口旧拓扑，窗口枚举却正常 | 公#22 | 残帧显示器：抓 `monitors[0]`；截前最小化再还原强制重绘；真伪以 API 为准 |
| 点击后立即截图是空面板/上一事件的内容 | 公#24 | 见桶 1：sleep≥1.2s 再截 |
| "拍完了"后来发现全是没开面板的空画布 | 公#25 | 每批拉回立即裁关键区验收，按内容命名；拍的图默认是嫌疑人 |
| SPSS 查看器大纲点击几叶后坐标全体漂移、Home 重置无效、UIA TreeItem=0 | spss SP#9 | 弃大纲定位：点内容区空白拿焦点后 pgdn/pgup 逐屏截图，Mac 端裁剪 |
| pull 失败后换名重拉，拉回几天前的旧图 | 公#29 | 文件名带日期戳；关键判断前核对任务栏时钟 |
| shots 目录历史文件撞名（w1.png 几个月前的旧图），新截图没存成就拉回旧图 | access A7 远§2.4 | 每任务独立前缀；拉回核对 mtime；按内容验收 |
| 全屏图上勾选框看着没勾 | excel | crop 放大再判，别重点（会把已勾的取消） |
| SSH 里截屏全黑 / 脚本"成功"屏幕却没动静 | 远§1 | session 0：一切 GUI 经计划任务桥（`/it`） |
| 打开 xlsx 弹"登录以验证你的订阅"模态框、主窗口 find_window 全超时 | excel 登录墙/绿栏/Ctrl+PgDn 节 | esc 关弹窗再找窗口；"分析数据"绿栏点"稍后使用"；Ctrl+PgDn 切表会静默失效改点标签（坐标见 excel 包） |
| eNSP 主窗被别的窗（Windows 系统设置也叫“设置”）遮挡、SetForegroundWindow 拉错窗；对主窗 SW_RESTORE 会变非最大化全盘坐标作废 | eNSP N16 | 枚举窗口按精确标题区分；用 SW_MAXIMIZE 不用 SW_RESTORE；弹窗层叠偏移，矩形一律 GetWindowRect 动态取 |
| eNSP 设备 GUI 控制台是全会话镜像流，残留旧窗/旧缓冲会拍出旧数据（如旧 IP 的 ARP 表） | eNSP N18 | 拍证据前按精确标题关掉该设备全部旧窗；开新窗用前后 hwnd diff 验证；crop 前确认最新命令输出完整 |
| Ctrl+` 切公式视图没反应；Ctrl+滚轮缩放无效；点击突然全被吞 | excel IME 前提/缩放/对话框收尾 节 | Ctrl+` 需先 shift 切英文IME；缩放走状态栏"100%"开对话框选档；点击被吞=上一脚本开了对话框没关，先 esc 清场再动作；切表后 sleep5+shot 验证 |
| 强杀 SPSS 后"错误报告服务/会话管理"挡路且 #32770 枚举不到、等窗口使能超时 | spss SP#8 | 按标题含"错误报告/会话管理"检测，先点已知取消坐标再等窗口 is_enabled，顺序不能反；弹窗可能晚于固定 sleep 出现→popup_titles 轮询清，取消键坐标按 crop 实测（spss SP#11/SP#12） |
| 界面显示成功就下了结论，结果不对/证据存疑 | 公#13 | 平行通道验证 ground truth：配置文件/数据库/API 才是真相，GUI 显示成功 ≠ 真成功 |
| Navicat 建/删库后靠树截图判断成败，容易看走眼 | navicat #5 | 看左下角"N 数据库"计数 ±1，加 SSH 旁路 SHOW DATABASES 双通道验证 |

### 桶 6 · 脚本/驱动卡死、桥没反应

| 你看到的 | 坑 | 一句话解法 |
|---|---|---|
| 脚本永不返回、gui.log 停在 START、send 全超时 | 公#32 | 长活进程 `Popen`+重定向文件，绝不 `run(capture_output)`；恢复：taskkill pythonw → /run |
| `/run` 回"成功"但 gui.log 没有新 START | 远§4 远§6 | IgnoreNew：上个 pythonw 未退；杀掉重触发；**成败只看 gui.log 新增行** |
| `/run` 后 20~25 秒没动静 | 远§4 | 任务计划服务启动延迟；轮询预算给够（pt.py 默认 240s） |
| 只 push 新脚本直接 /run，跑的是旧脚本 | 远§6 | 先覆写 next_cmd.txt 或走 pt.py send；核对 START 行是预期脚本（新版驱动 next_cmd 读后即删，裸 /run 不再重放；旧桥 mysql_lab 不享受） |
| send 秒回 OK 但什么都没发生 | 远§7 | 旧 DONE 行误匹配；pt.py 触发前清空 gui.log 并回读确认为空 + START 守卫，别自己裸解析 gui.log |
| eNSP 桥每轮 step 末尾自动拉截图恒 DOWNLOAD-FAIL（拉图竞态），脚本其实已跑完 | eNSP N21 | 忽略该 FAIL，随后单独 pull 即可；成败只看 gui.log DONE 与手动 pull |
| sed 批量生成的驱动脚本静默写坏/替换未生效，推上去才炸 | 公#40 | 参数化脚本用 heredoc 整段生成；py_compile + grep 校验后再 push |
| 想在超时后立刻重发同一条命令 | 远§3 | 先截图看现场——可能已生效，重发=二次点击 |
| `Start-Process` 起的 GUI 进程在、窗口没有 | 远§1 | session 0 派生全不可见；经桥 Popen 启动 |
| `nohup … &` 返回成功但进程消失、日志 0 字节 | 公S2 远§1 | 会话退出杀子进程树；长任务走 schtasks 或 `Start-Process -WindowStyle Hidden` |
| `LastTaskResult=2147946720` | 公#32 | 同驱动卡死恢复流程（新实例起不来=旧实例没退） |
| 一台 PC 多套桥（ptauto/PtGuiBridge 与 AUTO/MysqlLab 并存）不知用哪套 | 远§9 | ls 候选目录看 gui.log/shots mtime，优先最近验证过、与应用匹配的专用桥 |
| schtasks 启动 GUI 的 bat 缺 `start`：任务永久"正在运行"，之后 /run 回显成功却再不启动 | 公#37 | bat 内 `start "" 程序`；每次 /end+/run；起没起看 tasklist/gui.log |
| 远程 Git Bash 吃 `/create` `/f` 等斜杠参数，本地 export MSYS_NO_PATHCONV 无效 | 公#36 | export 写在远程命令字符串第一句 |
| GetActiveObject 找不到 Access/Office 实例(-2147221021)，上次打开的 Office 也没了 | access A1 | COM 实例不进 ROT 且随 pythonw 退出：每脚本自举 taskkill→DispatchEx→OpenCurrentDatabase，不跨脚本附着 |
| 连续 CreateForm/Close/Rename 几轮后第 3~4 次 CreateForm 无限挂起，之后 /run 全被 IgnoreNew 跳过 | access A1 | 一个脚本一个全新会话只建一个对象；挂起先 taskkill pythonw 再查现场 |
| DoCmd.OpenQuery(参数查询)/RunCommand(521) 不返回，驱动脚本 TIMEOUT | access A6 | 模态对话框阻塞 COM：两段式——触发(预期超时)→taskkill pythonw 留对话框→纯 GUI 脚本驱动（勿再 boot 重启） |
| script 注入脚本里 print() 的输出看不见，像没执行/想回传数据 | devcpp D11 | pythonw 无控制台：用 log()（进 gui.log，pt.py log 拉回）或写文件后 pull；shot 名与脚本不同名就手动 pull |

### 桶 7 · SSH / 传输报错

| 你看到的 | 坑 | 一句话解法 |
|---|---|---|
| `C:\Users\…` 到远端变 `C:Usersmaster` | 公#26 远§2 | 远端一律正斜杠 `/c/Users/…`；复杂命令 `printf … \| ssh host cmd` |
| `/F` 变 `F:/`、`/run` 变 `C:/Program Files/Git/run`、报"无效参数" | 远§2 | `MSYS_NO_PATHCONV=1`；taskkill 包一层 `cmd /c "…"` |
| `unrecognized arguments` / exit 5 / 参数拆散 | 远§2 | 内嵌引号提前闭合外层；禁止嵌套两层，写进 .ps1 文件上传执行 |
| `cmd /c "tasklist /FI \"...\""` 只回显 banner 像执行了其实没跑 | 远§2·spss SP#15 | Git Bash 双层引号被吞：用 `tasklist \| grep -i 名`，别用 /FI |
| SFTP upload 绝对路径失败 | 远§2 | 只收 home 相对路径：`ptauto/x.txt` |
| 裸 scp 报 /c/... No such file（ssh 命令却正常） | 远§9 | SFTP 不走 shell：路径用 Windows 风格 `windowpc:C:/Users/...` |
| 输出一串 `????` 乱码 | 远§2 | `\| iconv -f GBK -t UTF-8`；判定靠文件/日志，别解析中文输出 |
| `kex_exchange_identification` / download_failed 偶发 | 远§7 | pt.py 已带 2 次重试；兜底 base64 走 exec 通道 |
| download 连续失败而 exec 正常 | 远§6 | SFTP 子系统挂了：PC 起 `http.server` 用 curl 拉 |
| `cp *.docx` 报 target is not a directory | wps | `~$xxx.docx` 锁文件混进 glob：用 `[!~]*.docx` |
| exec base64 大文件只拿到前一段、`truncated: true` | 远§7 | exec stdout ~500KB 截断：大文件走 PC 起 http.server + curl 拉，md5 对照 |
| schtasks `/tr` 带引号路径报错 | 远§1 | 动作=单一无参脚本路径；带引号命令写 .ps1 |
| PowerShell Start-Process 带内嵌 `2>$null`/`$_` 的长命令回显正常但静默没起 | 远§2.2 | 写 .ps1 上传 `-File` 执行；起服务后 netstat 计数验证，别信回显 |
| printf 写 bat 吃 \a \b \f 转义，bat 变控制符程序不启动 | 公#38 | heredoc 写 bat + sed 补 CRLF |
| curl -s 拉图 404/断连不写文件也不报错，目录全空才发现 | 远§2.3 | `-s` 改 `-sS`；每批拉完 ls 验证文件数和大小（100KB+=正常，335B=404） |
| 脚本里 open 推上去的文件报找不到（文件其实传到了别的目录） | sqldeveloper #4 | push 落在 <AUTO>/scripts/：脚本里 open 用 C:\Users\master\ptauto\scripts\<name> 全路径 |

### 桶 8 · 安装 / 服务 / 进程管理

| 你看到的 | 坑 | 一句话解法 |
|---|---|---|
| `net start` 报"错误 1053" | 公#20 远§4 | 不是失败：`svcwait("RUNNING")` 轮询 sc query 真状态 |
| `payload initialization failed… corrupt`（MD5 却对） | 公S1 | BitRock 不能从只读挂载卷跑：先拷到本地盘 |
| "请求的操作需要提升" | 公S3 | schtasks `/rl HIGHEST //it` 注册即提权，无 UAC 弹窗 |
| grep 日志完成标记误报完成/提前返回 | 公S4 | Transcript -Append 命中旧行：改**文件存在性探测** |
| 安装器 `-Wait` 提前返回、实际还在装 | 公S5 | 以目标文件出现为准轮询，别信脚本顺序 |
| NSIS 安装器想省 GUI 逐页点击；装完找不到主程序（名字对不上） | 公S6 | `file` 探测 NSIS → 提权桥 script 通道 `Popen([exe,"/S"])+DEVNULL` 轮询产物目录；主 exe 按安装目录真名搜，安装器名≠产品名 |
| 新版 Wireshark 报 "Unable to load Npcap (wpcap.dll)"；npcap /S 弹 "Silent installation is only supported in Npcap OEM" | 公S7 | WinPcap 残留 + 免费版不支持静默：提权桥 GUI 三轮点装（卸 WinPcap→Npcap 向导默认项→`tshark -D` 验证），装完免重启 |
| dumpcap 抓包 pcap 0 字节但 curl 下载成功 | 公S7 附 | curl 走了 IPv6 而 `host <IPv4>` 过滤器全漏：加 `-4` 强制 IPv4，用 `-w %{remote_ip}` 核对与过滤器一致 |
| 强杀后重开弹"恢复文件"挡路 | 公#10 excel | UIA 读按钮全名点掉；Excel 走 `win.close()`+不保存，更彻底：删 %AppData% Excel 恢复目录与 UnsavedFiles 两处缓存 |
| 杀一个进程连带 GUI 全没了 | 公#33 | 同运行时家族按映像名杀是无差别：按 PID，先 tasklist 查 |
| 强杀后阶段成果清零 | 公#23 | 每阶段 Ctrl+S + mtime 验证落盘后才许杀 |
| ffmpeg 强杀后 ts 0 字节 | excel | `-flush_packets 1` |
| Spyder 启动卡在 "Recover from autosave" | spyder | 先删 `~/.spyder-py3/autosave/*.py` 再启动 |
| 远程 shutdown 发出后 ~20s 探测还在线，误判没生效想重发 | 远§8 | 断连窗口 20~40s：等 ≥40s 再探或 ping+ssh 双通道；重发无害只是叠加计时 |
| 观察类实验做完要关 Project，走保存对话框会把实验态写进磁盘文件 | proj#9 | 直接 taskkill /F /IM WINPROJ.EXE 保磁盘干净（改前确认磁盘已有保存过的干净版，mtime 核对） |
| eNSP 走 GUI 打开对话框开拓扑：保存提示/半加载状态/窗口布局不可控 | eNSP N3 | 杀三进程（eNSP_Client/eNSP_Switch/eNSP_VBoxServer）后 cmd /c start "" xxx.topo 文件关联启动 |
| 装 eNSP 前上网搜安装包白耗时间；FileVersion 与 ProductVersion 并存被当两个版本 | eNSP N12 | 装前先摸磁盘现成安装包（一键静默装脚本就绪）；1.2.00.510 与 1.3.00.100 是同一套件的两个版本号 |
| SQL Developer 启动报 Unable to open ... bin\sqldeveloper.conf，或 Popen 起不来 | sqldeveloper #1 | unzip 半途损坏改用 Python zipfile.extractall 重解压；Popen cwd 必须是内层 sqldeveloper\sqldeveloper |
| Oracle 静默安装十几分钟没动静不知装没装完；Free 版找不到"DBCA 建库"入口 | oracle-db | 完成标志=setup.log 出现 Installation success or error status: 0（服务 RUNNING 判活更早）；rsp 参数不得留空；无自建库入口以 FREEPDB1 建用户替代 |
| 改了 Spyder 配置文件（spyder.ini）重启后改动悄悄丢失 | spyder | Spyder 退出时回写配置会覆盖你的修改：改前确认所有 Spyder 进程已退 |

### 桶 9 · EDA / 录屏 / 具体报错串 / 工具行为限制

| 你看到的 | 坑 | 一句话解法 |
|---|---|---|
| vsim-3039 "supports only a single HDL" | 公E1 | tb 与设计同语言；先 `vsim -c` console 版看真报错 |
| "Errors occured during modelsim simulation" / fs.do 找不到 | 公E2 | qsim 的 do 拷到 modelsim 目录；或全走 ModelSim 自写 tb |
| 第二个 `vsim -do` 静默不执行、旧窗口纹丝不动 | 公M1 | ModelSim 单实例：先 `taskkill vsim.exe vsimk.exe` |
| vsim-3479 warning / 激励被舍入 | 公M2 | 一律 `-t 1ns` |
| `run -all` 永不结束（SSH 调 console 直接卡死） | 公M3 | tb 有自由时钟：固定时长 `run 200 ns` |
| 修完 bug 重跑结果没变、误判修复无效 | 公M4 | check.do 开头先 `vcom` 重新编译，否则验的是旧结果 |
| examine 读出怪数字、误判设计有 bug | 公M5 | 采样点落在每组 DONE 后的静止窗口内 |
| "No help for wave zoomrange"；zoom full 后时间轴远大于仿真段 | 公M7 公M9 | f=Zoom Full 只缩到 WLF 全程；精确缩放走右键 Zoom Range... 对话框（开框→填→OK 同一轮内完成，跨轮即消失），或把 run 拉到 ~1000ns |
| Quartus Files 面板按字母序双击多文件 → 拍到张冠李戴的代码 | 公E6 | 行序=.qsf 添加顺序，先拍一张验证；行 y=130 起 +22 |
| vcom 全成功、vdir 有实体，vsim 仍报 vsim-3170 Could not find | 公M10 | cp 复制的 tb 实体名没改；vdir 核对库内实体名 |
| 端口叫 rol：Quartus 编译过，ModelSim vcom 报 near "rol" | 公M11 | rol/sll/srl 是 VHDL-93 保留字；BSD sed 不认 \b 用 perl 改名 |
| 强杀后 ModelSim 白屏挂死（vsim.exe 几 MB 不动）或秒退 | 公M12 | 清工程目录 vsim.wlf transcript wlft* 再启；排障期去掉 onerror quit |
| 截图自动去白边失效，trim 后仍是整幅 | 公E7 | 右下"激活 Windows"水印 (1600-1905,935-990)；裁剪底边 ≤928 |
| 驱动脚本里 paste(...) 报 NameError 整步失败 | 公#39 | 注入的是 paste_at；或 set_clip+click+ctrl+a/ctrl+v |
| VHDL 仿真前段全是 U/X 算术警告 | 公M8 | 寄存器声明处 `:= (OTHERS => '0')` 初始化 |
| `No such filter: 'ass'` / `No option name near` / `Unable to open sub.srt` | excel | 换 full build；`subtitles=filename=` 显式键名；绝对路径转义 |
| `crop() takes 5 positional arguments but 7 were given` | excel | crop 写进脚本内执行，不经 pt.py send 传参 |
| Mac computer-use 对某 app 全拒绝（键盘/点击/a11y 只读） | spyder | 别在 Mac 死磕：走本 skill 遥控 Windows PC |
| CreateControl 报 `invalid literal for int() with base 10: '控件名'` | access A2 | 真签名没有 ControlName 位：CreateControl(窗体,类型,节,Parent,ColumnName,L,T,W,H)，控件名自动生成 |
| 报表建控件报"找不到引用的窗体'报表1'" / "您所输入的节数无效" | access A2 | 报表必须用 CreateReportControl；报表页眉/页脚节默认不存在，设计视图下 RunCommand(37) 添加后再放控件 |
| makepy 句柄设 `lbl.Caption` 报 AttributeError / `rpt.Section` 找不到成员 | access A3 | 控件 dyn() 转动态绑定；Section 走 typed `app.Reports(名).Section(0)` |
| DAO 挂字段属性 Append 报 3219 无效操作 | access A4 | InputMask 等自定义属性必须 TableDefs.Append 之后经 db 句柄 CreateProperty+Append |
| Jet UPDATE 报 3073 操作必须使用可更新的查询 | access A4 | 不支持关联聚合子查询 UPDATE：Python 算好逐行简单 UPDATE |
| 新建报表主体节高 5952 缇、两条记录隔半页；页面页脚 =Sum() 显示#错误 | access A2 | Section(0).Height=420 压回；Sum 只能放报表页脚（先 RunCommand(37) 加节） |
| PT 手工 ip ospf cost 配了不生效 / 多区域路由不显示 O IA | pt | PT 限制：改 `bandwidth` 才重算 cost；O IA 标记 PT 不显示，以配置+ping 取证（cisco-pt 踩坑.md Lab5 专项） |
| PT reload 卡在 Save? [yes/no] 把后续输入当回答吃掉 | pt 远§7 | 先 no 再空行冲提示（cisco-pt 踩坑.md Lab5 专项） |
| PT fshot 报 window 'lab5.pkt' not found；截图是几天前旧桌面 | pt 远§7 公#22 | fshot 默认子串写死，改用 send shot；残帧先 repaint |
| eNSP 手写 .topo 加载后 PC↔交换机的线全部静默消失（无报错） | eNSP N1 | PC 缺 slot 接口声明，加载器静默丢线；用 fix_topo.py 补声明或照官方示例写 topo |
| 更新项目(100% 完成)后"关键"列全变否，误判筛选器/操作故障 | proj#8 | 这是 Project 重算浮动时间的真实状态不是 bug：报告以操作时点截图为准 |
| 手写 .topo 加载丢数据/行为异常（格式细节没对齐官方） | eNSP N2 | 行尾 CRLF、版本串照抄本机保存文件；权威格式 本机保存topo>官方示例>猜；slot 接口声明缺了必炸（N1/fix_topo.py） |
| eNSP 交换机/路由器取证走 GUI 慢还踩 Qt 菜单坑；PC 想走 telnet 却没有 | eNSP N7 | 交换机/路由器有 telnet 127.0.0.1:<com_port> 平行通道直连 VRP（Python socket 剥 IAC）；PC(simpc) 无 telnet 走 GUI ping |
| eNSP 改了设备配置不生效；取证 cfg 与设备实际配置对不上 | eNSP N8 | 设备启动自动加载 <topo目录>/<设备ID>/vrpcfg.cfg：改这个文件或 GUI 敲；拓扑旁的参考 cfg 会骗人 |
| eNSP 设备刚启动就 ping 不通/连通性测试失败 | eNSP N9 | 图标橙=启动中(每台 10~30s)：启动后等 60~90s（STP 收敛+VRP 起来）再测；框选启动的橡皮筋起止点必须在空白画布 |
| 替换了截图 PNG，docx 报告里仍是旧图 | eNSP N20 | 图片生成时已嵌入 word/media/：改证据后重跑整份文档生成脚本再后处理+目检；生成脚本存档复用 |
| CREATE DATABASE MyDB 建出来是 mydb，残留旧库让建库报 1007 | navicat #7 | Windows MySQL 库名不区分大小写：动手前 SSH 旁路 SHOW DATABASES 摸底清理 |
| script 注入脚本里 clip(...) 报 NameError | sqldeveloper #3 | 环境注入的是 set_clip 没有 clip：set_clip(文本)+hotkey ctrl+v |
| sqlplus 跑含中文的 .sql 报 ORA-01756 / 中文乱码 | sqldeveloper #9 oracle-db #1 | export NLS_LANG=AMERICAN_AMERICA.AL32UTF8；控制台显示乱码只影响显示不影响存储 |
| 建表没带 schema 前缀，表落到 SYSTEM 查不到 | oracle-db #2 | 一律带 yggl. 前缀；误建 drop table system.<表> cascade constraints 清理 |
| 删表报 ORA-02292（外键约束阻止删除） | oracle-db #3 | 先子表(Salary)后主表(Employees)删 |
| 对象建完找不到落在哪个容器/用户；all_tables 查不到 | oracle-db #4 | cdb_objects where object_name='<大写名>' 一眼定位；查前 alter session set container=FREEPDB1 |
| sqlplus 命令行连接失败，密码里带 # | oracle-db #5 | 连接串里密码用双引号包住 |
| char(n) 默认按字节计长，UTF-8 一个汉字 3 字节，插 5 字姓名报 ORA-12899 | oracle-db #6 | 中文值长度≤n/3 个汉字；根治=建表用 char(n char)/varchar2(n char) 字符语义 |
| pyautogui 发 Win+Alt+R 录屏没反应，Videos\Captures 不生成文件 | excel | 该 PC Game Bar 被精简：直接用 ffmpeg gdigrab 录屏，更可控 |
| openpyxl 写完公式打开没值/想找 recalc 工具重算 | excel | openpyxl 只写公式串无缓存值：真 Excel 打开自动重算，直接在真 Excel 截图验证（公式视图=过程证据） |
| WPS AI 校对/纠错点「开始修改」弹会员墙；Ctrl+A 全选后让 AI 生成=全文被报告覆盖 | wps | 校对走 WPS AI 侧边栏（文档问答），回复不碰文档；选区上只发起改写类需求且先备份 |
| Spyder 控制台红框 An error occurred while starting the kernel，一直 Connecting to kernel | spyder | 先 crop 红框读报错原文（公#34 的实付案例）；绕过=独立 Popen 起内核→Consoles→Connect to existing kernel |

上表没有的 → 走 grep；grep 也没有 → 按"失败处理阶梯"第 2/3 次规则拿证据、换路，
并把新坑回写（见"skill 自优化闭环"）。

## skill 自优化闭环（第四条铁律的展开）

每次运行结束后，花几分钟回答一个问题：**这轮有哪些付出过时间的东西，下次还会再遇到？**
有 → 按下面的路由写回 skill，才允许收工。

| 这轮学到的是 | 写到哪 |
|---|---|
| 换软件、本机/远程都成立的失败模式 | [踩坑清单.md](踩坑清单.md)（公共坑，带编号） |
| 只因这个软件成立 | `apps/<软件>/踩坑.md`（症状 → 原因 → 解法 三段式） |
| 新校准的坐标/锚点/配方 | `apps/<软件>/` 动作库 COORDS + 坐标与配方.md |
| 同一骨架在 ≥2 个任务脚本里重复出现 | 收编成动作库函数（实付例：`wire_uia`、`router_cli_config`、`close_leftovers`） |
| 驱动/遥控器本身的缺陷或竞态 | 修代码 + 在 远程坑.md/踩坑清单.md 记录因果（实付例：pt.py 的 START 守卫、SFTP 重试） |
| 文档与现实不符 | 直接改文档（坐标漂移、端口命名规则变了等） |
| **新坑写进任何坑文件之后** | **同步在本文"坑点速查表"对应症状桶加一行**——索引不更新 = 下次失败还是搜不到 |

**质量线**（防止清单烂掉）：

- 只写**这轮实测过的**（真踩到/真跑通的），不写猜测和"应该吧"；每条注明症状与实付代价。
- 公共坑保持"症状 → 原因 → 解法"；过时条目直接改删，别让清单膨胀成流水账。
- 改了 `.py` 必须 `py_compile`，并尽量用一条无害命令实弹验证；改完把动作库同步回 PC 的 AUTO 目录。
- **截图/日志等任务产物永不回写 skill 目录**——pt.py 默认落 `~/.zcode/window-use/shots`
  （skill 内路径一律被重定向），目录超 200MB 自动归档（scripts/shots_gc.py，先打包校验再删原图）。
  172MB 证据图沉淀进 skill 的学费（2026-11-05 清理实付）不允许再犯。
- 细节进 references/ 和 app 包，本文件只留工作流与路由表。
- app 包的粒度表若被实测推翻（比如某动作批量必炸/某动作其实可批量），当场改粒度表。

## 快速开始

本机直跑：
```
python win_gui_driver.py shot s1            # 截图
python win_gui_driver.py click 960 540      # 点击
python win_gui_driver.py script t1.py       # 执行应用包脚本
```
Mac 远程：部署一次 `remote/create_task.ps1`（见 脚本用法.md 部署清单），
之后 `remote/pt.py step <动作脚本.py>` 一轮轮原子步进（push→执行→拉截图，一条命令一轮）；
`send/push/pull/log` 也可单独使唤。

## 应用包使用（以 cisco-pt 为例）

1. 读 `apps/cisco-pt/坐标与配方.md` 拿坐标表和配方（+ 踩坑.md 全文，见工作流第 0 步）
2. 把 `apps/` 目录部署到 PC 的 AUTO 目录下
3. 任务脚本里 `sys.path.insert(0, AUTO + r"\apps\cisco-pt"); import ptlib`
4. 新 PC/新分辨率首跑 `ptlib.probe()` 自检坐标，之后用
   `place/wire/wire_uia/cli_config/router_cli_config/pc_ping…` 组装任务
