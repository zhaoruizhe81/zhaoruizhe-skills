# 实测坑（26 条）

每条按 **表现 → 原因 → 避法** 写。按"下次做同类事会踩"的优先级排序，越靠前越贵。
贯穿全文的一句话：这个链路里最贵的不是写代码，是**静默失败** —— Power BI 丢字段不报错、计划任务假成功、锁屏只回一个拒绝访问。所以每一步都要有一个可观测验证点（文件校验、DAX 原文、截图、日志），不能靠"命令返回 0"判断成功。

## 一、PBIR / 报表结构

**1. 字段"消失"，Desktop 不报错**
表现：Y 轴空、提示"一个或多个字段出错"，但 `visual.json` 里字段明明还在。
原因：Desktop 遇到不认识的投影或角色，直接丢弃，不报错。
避法：字段丢了先怀疑**结构名**，不是数据。核对 `queryState.<Role>.projections[]` 里的角色名是否属于该视觉对象。

**2. 柱形图图例角色叫 `Series`，不叫 `Legend`**
表现：用 `Legend` 时图例不出现，多个类别还会被合并成一个总和 —— 看着像"数据错了"。
原因：角色名不符，Desktop 静默忽略该投影。
避法：`Category / Y / Series` 是柱/折线图三件套。判据是**图表标题自动变成「… (按月份和产品)」且图例出现多系列**；标题里没有"和X"就是分组没生效。

**3. `pages.json` 的 `pageOrder` 为空 → Desktop 拒绝加载**
表现：打开即弹阻断对话框「你的报表存在无法解决的问题 / 我们在报表定义中遇到一些问题，但无法解决它们」，问题列表写着「找不到 ActivePageN / 报表没有页面。报表必须具有一个页面」。点「继续」无效、对话框复现，只能点「关闭桌面」退出。
原因：`pbi report create` 生成的 PBIR 是空报表，`pagesMetadata` 的 `pageOrder` 为 `[]`，`activePageName` 也缺。
避法：代码生成必须自己建页并写入 `pageOrder: ["p1"]` + `activePageName: "p1"`。生成器强制写死，`check.py` 也断言这一点。

**4. PBIP 首次打开只有元数据，图全空**
表现：画布上视觉对象布局都在、标题轴图例都对，但数值全是「(空白)」，顶部黄条「某些表包含不完整数据或没有数据」。
原因：Import 模式的模型文件里没有缓存数据，Desktop 打开时不自动刷新。
避法：这不是错，点一次「立即刷新」，等 45–90 秒（会出现"正在计算/正在加载数据"对话框）。自动化流程必须显式加这一步，别 8 秒就判失败。

**5. 错误原文藏在 UI 后面**
表现：图表只说"请参阅详细信息"，链接点不开。
原因：Desktop 把 DAX/模型错误包在内部，UI 只给摘要。
避法：去 **DAX 查询视图**跑 `EVALUATE ...` 拿原文，或翻 `msmdsrv.log`。没有原文就别改代码。

**6. 改了 PBIR 文件，重启 Desktop 后改动没了**
表现：生成/编辑后重新打开，位置或字段回到旧值。
原因：Desktop 退出时用内存态回写 PBIR，覆盖磁盘。
避法：**改文件前先 `Stop-Process -Name PBIDesktop -Force`（或正常关闭并等进程退出）**，再改再开。

**7. 只拷 `.Report` 或只拷 `.SemanticModel`**
表现：打开报找不到数据集 / 字段全失效。
原因：`definition.pbir` 里是 `datasetReference.byPath.path = "../<Name>.SemanticModel"`，两者靠相对路径绑定。
避法：`.pbip` + `.Report` + `.SemanticModel` 三件一起走，且保持同级目录。

## 二、TMDL / 模型

**8. M 分区不写 `type table` / 不定型 → 数值列变文本**
表现：`SUM` 报「函数 SUM 不能使用 String 类型的值」；或列在 Desktop 里显示为文本、右对齐变左对齐。
原因：`#table({"a","b"}, {...})` 让 Power Query 自己推断，数值列可能推成 String。TMDL 里的 `dataType: double` **压不住**导入推断。
避法：一律显式定型，二选一：
- `#table(type table [年份 = Int64.Type, 数值 = number], {...})`
- 走 CSV：`Csv.Document(...)` → `Table.PromoteHeaders` → `Table.TransformColumnTypes(Promoted, {{"年份", Int64.Type}, {"数值", type number}})`

中文 CSV 还要 `Encoding=65001`，否则表头乱码导致列名对不上。

**9. 多行 DAX 在 TMDL 里缩进丢失**
表现：度量值解析失败，或计算语义莫名错位。
原因：TMDL 靠缩进切分结构。`measure X =` 后面直接跟 DAX 时，首行不会自动进表达式体。
避法：`measure X =` 单独一行，DAX 每行 3 个 tab。生成器对首行自动补 `\t\t\t`。

**10. `DATEADD` 配整数年份列报错**
表现：`度量值 'Fin'[营收增长率] 中的计算错误:在对函数"DATEADD"的调用中指定的列不属于 DATE 类型`。
原因：`DATEADD` 要求真正的日期列；年份是 int64。
避法：用 `MAX` + `CALCULATE` 手算上一期：

```dax
VAR y = MAX(Fin[年份])
VAR cur = CALCULATE(SUM(Fin[营业收入]), Fin[年份] = y)
VAR prev = CALCULATE(SUM(Fin[营业收入]), Fin[年份] = y - 1)
RETURN DIVIDE(cur - prev, prev)
```

**11. 维度列被默认聚合，轴变成 `Sum of 年份`**
表现：X 轴刻度是 2020、2020…，标题「Sum of 年份」。
原因：Desktop 对数值列默认 `summarizeBy: sum`，投影里也默认套聚合。
避法：维度列 TMDL 写 `summarizeBy: none`；类别角色的投影**不加** `Aggregation`，改带 `"active": true`。

**12. `dataType` 与实际不符 → 静默空图**
表现：图表不报错但没有任何值。
原因：类型不匹配导致行被过滤或转换失败，错误只在 `msmdsrv.log`。
避法：生成后用 `pbi table schema <表>` 或 DAX `EVALUATE TOPN(5, <表>)` 复核每列真实类型。

## 三、pbi-cli 工具链（若使用）

**13. 模型层命令离线不可用**
表现：`pbi table list` 报 `Error: No active connection. Run 'pbi connect' first.`（exit 1）。
原因：`table/column/measure/partition/relationship` 都走 Analysis Services，必须连到**运行中的 Desktop**。
避法：离线生成模型只能自己写 TMDL。报表层（`report` / `visual` / `filters` / `bookmarks`）加 `-p --no-sync` 可离线写 PBIR，`visual bind` 会用 TMDL 目录做字段索引（输出里 `resolved_by: tmdl` 即证明走了离线索引）。

**14. Desktop 重启后 `pbi connect` 连不上**
表现：`Microsoft.AnalysisServices.ConnectionException ... SocketException ... 127.0.0.1:54970`。
原因：AS 引擎端口每次启动都变，`~/.pbi-cli/connections.json` 缓存了旧端口。
避法：`Remove-Item -Recurse -Force "$env:USERPROFILE\.pbi-cli"` 再 `pbi connect`，会打印 `Auto-detected Power BI Desktop on localhost:<新端口>`。

**15. `--no-sync` / `-p` 位置写错**
表现：命令把路径当子命令，报 `No such command`。
原因：`--no-sync` 与 `-p/--path` 是**组级选项**，必须写在子命令前。
避法：`pbi visual -p 'D:\x\Y.Report' --no-sync add --page p1 ...`。

**16. 冷启动慢到超时**
表现：一条命令 15–25 秒，串两条必被杀（60s 上限）。
原因：每次 `pbi.EXE` 冷启动都要加载 .NET 运行时与 pbi-cli-tool。
避法：批量构建写成后台 ps1（`Start-Process powershell -File ... -WindowStyle Hidden`）+ 日志轮询。热启动后 5 条 `visual update` 只要 2.7 秒。
## 四、数据层

**17. 宽表的分组表头没进映射表**
表现：资产负债表的"流动资产""非流动资产"等分组行没被识别，整段科目被归到上一个分组，图表标题全错。
原因：分组表头是合并单元格/单列标题，行数是对的但语义塌了。
避法：转完抽样打印「指标 → 分组」映射给人看，别只看行数对不对。

**18. 源表自相矛盾，先做恒等式校验**
表现：某公司"股东权益"和"流动负债"五年一模一样；用它反推的资产规模与披露的资产负债率冲突。
原因：手工台账错行、合并口径不一致。
避法：先跑 `资产 = 负债 + 权益`、用流入−流出反算现金流比率，对上了才允许用该列推导 ROE / 资产总计。矛盾数据不要拿来推导。

**19. 单位混用（亿/万/元）**
表现：总量级差 4 个数量级，图表比例全歪。
原因：不同年度/子公司口径不同。
避法：转换时统一到同一单位，并用原表能反算的比率做交叉验证（如现金流量比率 = 净现金流/营收，和披露值对上才证明换算对）。

## 五、远程 Windows 自动化

**20. `BitBlt: 拒绝访问` = 机器锁屏/在登录界面**
表现：截图工具报拒绝访问，命令行一切正常。
原因：不是权限问题，是 session 0 碰不到交互桌面。
避法：确认 `explorer.exe` 在 session 1、`LogonUI` 是否在跑。GUI 进程（PBIDesktop）**只能从 session 1 起**；通过 ssh 起 GUI 进程会"启动即死"，25 秒后进程数=0 且无任何报错。

**21. 计划任务 `/run` 返回"成功"不等于跑了**
表现：`schtasks /run` 成功，但目标程序没起。
原因：`/run` 只表示任务已提交。
避法：只认日志 —— 有没有新的 START 行、目标进程在不在。GUI 桥的成败只认日志与截图。

**22. Git Bash 吃斜杠参数**
表现：`schtasks /query` 变成 `C:/Program Files/Git/query`，报「无效语法/选项」。
原因：MSYS 路径转换。
避法：带 `/` 的 Windows 命令走 `MSYS_NO_PATHCONV=1` + `cmd /c`，或整条命令写进 `.ps1` 再执行（`MSYS_NO_PATHCONV=1` 对 `ssh host "cmd"` 内的参数仍可能失效，最稳是 ps1）。

**23. 远程点击必须"截图 → 定位 → 点击 → 再截图"**
表现：点错位置 —— 刷新点到了"最近使用的源"、新建视觉对象点到了图上、视图点到了建模。
原因：Ribbon 随上下文切换位置变化，鼠标事件偶发丢失（返回 error 但屏幕没动）。
避法：绝不记忆坐标，每次先截图看当前布局；点击失败原地重试一次即成功，别换坐标。

**24. 含中文的 `.ps1` 必须存 UTF-8 with BOM**
表现：脚本里的中文变成乱码，字符串比较/路径全错。
原因：PowerShell 5.1 读 `.ps1` 默认按 ANSI。
避法：`(printf '\xef\xbb\xbf'; cat x.ps1) > x_bom.ps1` 再传。输出乱码用 `| iconv -f gbk -t utf-8 -c` 修。

**25. PowerShell 5.1 传参给 native exe 会吃掉双引号**
表现：`pbi dax execute 'EVALUATE ROW("rows", 1)'` 报「函数 ROW 要求列名作为实参号 1」。
原因：PS 5.1 在把参数交给 native exe 时重新拼命令行，内层双引号丢失。
避法：把查询/长参数写进文件（`.dax`、`.json`），用 `--file` 传。

## 六、交付与打包

**26. 用 macOS 自带 `unzip` 验证中文包会误判**
表现：`unzip -l` 显示中文全是 `?`，看着像打包坏了。
原因：它不认 EFS 标志位，合法 UTF-8 也显示问号。
避法：用 Python `zipfile` 写包，再用 `namelist()` 读回自检；查看用 7-Zip / WinRAR / Windows 资源管理器。同时断言 `namelist()` 里没有 `\` 分隔符（那是 Windows 下压缩工具写出的非法条目）。

## 附：Office 出图（报表归档环节）

- **PPT `add_picture` 同时给宽高会拉伸**：换图后宽高比变化（1.46 → 1.97）图就变形。按宽高比算 fit 尺寸再居中。
- **Power BI 导出的 PDF，画布不等于整页**：真实画布约 `(18,18)-(978,558)`、缩放 0.75，外面还有边距。按整页比例裁剪会切掉标题首字。用 `page.get_drawings()` 找最大白色矩形拿真实画布，别用 `page.rect`。
- **截图分辨率一开始就定高**：220dpi 裁出的图放进 Word 会被放大发虚，420dpi 才够。PDF 是矢量的，可以重渲染不损失。

## 验收清单（贴在每次交付前）

1. 生成器打印 `OK <path>`；`check.py` 退出码 0 且视觉对象数量与 spec 一致
2. `pages.json` 有非空 `pageOrder` + `activePageName`
3. 所有 visual 的 `queryState` 非空，且**没有出现 `Legend` 角色**
4. TMDL partition 里有 `Table.TransformColumnTypes`
5. Desktop 打开无错误对话框，页标签名与 spec 一致
6. 点「立即刷新」后，**用明细手算对账**每个卡片/比率的数值
7. 带 `Series` 的图表标题含「和<分组列>」且图例出现多系列
