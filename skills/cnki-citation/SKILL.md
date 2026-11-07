---
name: cnki-citation
description: 检索中国知网(CNKI)文献并生成标准引文。支持主题/篇名/关键词/作者检索、按被引/时间排序,输出 GB/T 7714-2025、APA、MLA、BibTeX、EndNote 等格式引文,可批量落盘为参考文献文件。当用户需要写论文找参考文献、查知网文献、生成引用格式、核对引文、找某主题高被引文献时使用。基于逆向的官方接口(纯 HTTP,无需浏览器),内置签名算法。
---

# 知网文献引用 (CNKI Citation)

纯 Node.js(零依赖)的知网检索 + 引文导出工具。所有脚本在本技能 `scripts/` 目录下运行。

## 命令速查

```bash
cd <技能目录>/scripts

# 检索: 关键词 → 文献列表(题名/作者/期刊/被引/文献ID)
node search.js "教育数字化转型"              # 默认主题检索第1页(20条)
node search.js "大语言模型" 2                # 前2页(40条, 页间隔内置20-30秒)
node search.js "深度学习" --sort 被引        # 排序: 相关度|发表时间|被引|下载
node search.js "深度学习" --field TKA        # 字段: SU主题 TKA篇名 KY关键词 AB摘要 AU作者
node search.js "深度学习" --json             # 机器可读输出(含文献ID/abstractUrl)

# 查论文→引论文 闭环: 检索 + 取前N篇引文落盘
node search.js "教育数字化转型" 1 --sort 被引 --top 5 --cite 'GB/T 7714' --out refs.txt

# 单篇引文(已有文献ID时)
node get-citation.js <文献ID>                # 默认 GB/T 7714-2025 + MLA + APA
node get-citation.js <文献ID> BibTex EndNote
```

文献 ID 来源:`search.js` 输出的 `id:` 行(加密 ID,GetExport 用),或知网页面"CNKI AI阅读"链接的 `cid=` 参数值。列表页可见的明文短号(如 HZLG20260930008)**不能**用于引文接口。

## 典型工作流

1. **写论文找参考文献**:`search.js "主题词" 1 --sort 被引 --json` 看高被引经典 → 和用户确认选哪些 → `--top N --cite 'GB/T 7714' --out` 落盘,或逐篇 `get-citation.js`。
2. **核对引文**:对用户论文里的每篇文献跑 `get-citation.js`,比对作者/年卷期/DOI。
3. **BibTeX**(LaTeX 用户):`--cite BibTex` 或 `get-citation.js <ID> BibTex`。注意:网络首发文献可能返回"暂无数据",GB/T 7714 始终可用。

## 红线(实测边界,违反会触发风控)

- **检索接口(brief/grid)短间隔连续请求必触发图形验证码**,且状态粘性——等待无效,需在浏览器知网页面人工过验后才恢复。翻页间隔已内置 20-30 秒随机,不要调小;引文接口较宽松(2-3 秒/篇)。
- 单次会话建议 ≤2 页;更多页请让用户在浏览器里翻页后单页抓取,或分多次跑。
- 默认限速已内置,不要并行调用脚本。

## 会话与排障

- 会话凭据在 `scripts/.cookie`(浏览器 document.cookie),过期表现为突然返回 `-403`/`-1` 或验证码页。
- 修复方法:让用户在浏览器打开 kns.cnki.net 任意检索页 → DevTools Console 输入 `copy(document.cookie)` → 写入 `scripts/.cookie`。检索和引文**不需要登录态**,匿名过验会话即可。
- 环境变量 `CNKI_COOKIE` 可覆盖文件;`--cookie "<...>"` 参数可用于单次指定。
- 报"触发知网频控":等几分钟,并让用户在浏览器里正常翻一页检索结果(人工行为会释放会话),刷新 `.cookie` 后重试。

## 接口与签名细节

端点规格、QueryJson 结构、签名算法、HTML 解析字段等实现细节见 [references/api-notes.md](references/api-notes.md)。仅当工具失效需要修复(如知网改版、签名变更)时读取。
