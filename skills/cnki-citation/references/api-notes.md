# CNKI 接口与签名实现笔记

逆向自知网 KNS8 平台(2026-10 验证有效)。仅当工具失效需要修复时读取。

## 目录

1. [端点规格](#端点规格)
2. [GetExport 签名算法](#getexport-签名算法)
3. [检索 QueryJson 结构](#检索-queryjson-结构)
4. [结果 HTML 解析字段](#结果-html-解析字段)
5. [风控行为汇总](#风控行为汇总)

## 端点规格

均为主域 `kns.cnki.net`,HTTP 头需带 `user-agent`(现代 Chrome UA)与有效会话 cookie。

### 检索列表(无需签名)

```
POST /kns8s/brief/grid
Content-Type: application/x-www-form-urlencoded; charset=UTF-8
X-Requested-With: XMLHttpRequest
Referer: https://kns.cnki.net/kns8s/defaultresult/index?classid=WD0FTY92&korder=SU&kw=<词>

boolSearch=true
QueryJson=<见下节,URL编码>
pageNum=1 & pageSize=20 & CurPage=1
sortField=(空=相关度|PT发表时间|CF被引|DFR下载) & sortType=(DESC)
dstyle=listmode & productStr= & aside=(主题：关键词) & searchFrom=资源范围：总库
subject= & language= & uniplatform=
```

流程:先 GET 检索页 `/kns8s/defaultresult/index?classid=WD0FTY92&korder=SU&kw=<词>`(建立会话,收 Set-Cookie),再 POST。响应为**服务端渲染 HTML 片段**;若含 `vericodeForm` 则是频控验证码。

### 引文导出(需签名头)

```
POST /dm8/API/GetExport
Content-Type: application/x-www-form-urlencoded; charset=UTF-8
X-Requested-With: XMLHttpRequest
Origin: https://kns.cnki.net

filename=<加密ID> & displaymode=GBTREFER,MLA,APA & uniplatform=NZKPT & language=CHS

timestamp: <毫秒时间戳>
nonce: <见签名>
signature: <见签名>
appID: LoginWap
ClientID: <Ecp_ClientId cookie 原值>
```

响应 JSON:`{code:1, data:[{key:"GB/T 7714-2025 格式引文", mode:"GBTREFER", value:["[1]...", ...]}, ...]}`。引文文本含 `<br>` 需替换;行首自带 `[1]` 编号可按需去除。

displaymode 可选:`GBTREFER`(GB/T 7714-2025) `REFER`(CAJ-CD) `MLA` `APA` `BibTex` `EndNote` `NoteExpress` `Refworks` `NEW`(查新)。网络首发文献的 BibTex 可能"暂无数据"。

## GetExport 签名算法

逆向自 `my.cnki.net/realNameOauthDialog/js/common.js` 的 `createSign`(以浏览器内 `createSign.toString()` 为准——CDN 文件与运行时真身的盐值差一个字符 r,运行时真值为 `t8b52yrsoyx66f35tk0p4nubrmrcglv5`)。

```js
timestamp = Date.now()                                        // 毫秒,数字
nonce     = Math.sin(timestamp).toString().substr(6)          // sin 值字符串第6位起
signature = md5(
  timestamp + nonce +
  "t8b52yrsoyx66f35tk0p4nubrmrcglv5" +      // 盐值
  sortedParams +                            // 实测传空串 "" 即可通过
  Ecp_ClientId                              // cookie 原值
).replace(/ /g, "")
```

`sortedParams` 规范(页面原逻辑):取某 URL 的 query,按 key 小写序排序,拼成 `key1=value1key2=value2...`(无分隔符,值 decodeURIComponent)。**实测服务端不校验该部分,传空即可**;页面真实行为是对"加载时最后一次 createSign 调用的 URL 参数"签名(通常是 get_user_member_info 的 `IdenId=<LID>SourceType=login`)。

页面机制:`createSign(url)` 为下一个请求注册 jQuery 全局 `ajaxSend` 处理器,闭包捕获当次计算的签名;多个处理器叠加、后注册覆盖。同会话内签名头曾被观察到重复使用(每页面加载只算一次)。

签名实现:`scripts/sign.js`(Node crypto md5,`CNKI_CLIENT_ID` 环境变量传入 ClientID)。

## 检索 QueryJson 结构

```json
{
  "Platform": "", "Resource": "CROSSDB", "Classid": "WD0FTY92", "Products": "",
  "QNode": { "QGroup": [{
      "Key": "Subject", "Title": "", "Logic": 0,
      "Items": [{ "Field": "SU", "Value": "<关键词>", "Operator": "TOPRANK", "Logic": 0, "Vector": "", "Title": "主题" }],
      "ChildItems": []
  }]},
  "ExScope": 1, "SimpTrad": "0", "SearchType": 2, "Rlang": "CHINESE",
  "KuaKuCode": "YSTT4HG0,LSTPFY1C,EMRPGLPA,JUP3MUPD,MPMFIG1A,WQ0UVIAA,BLZOG7CK,PWFIRAGL,NN3FJMUV,NLBO1Z6R",
  "Expands": {}, "View": "changeDBCh", "SearchFrom": 1
}
```

Field 取值:`SU`主题 `TKA`篇名 `KY`关键词 `AB`摘要 `AU`作者 `LY`来源 `FT`全文 `FI`基金(Title 随之变)。URL 检索入口:`/kns8s/defaultresult/index?classid=WD0FTY92&korder=<Field>&kw=<词>`。

分页上限 300 页 × 每页最大 50 条;`<em>总条数</em>` 与 `data-pagenum="300"` 在响应 HTML 中。

## 结果 HTML 解析字段

响应为固定模板 `table.result-table-list`,每行 `<tr>` 内:

| td class | 内容 | 提取要点 |
|---|---|---|
| `seq` | checkbox | `input.cbItem[value]` = 加密文献ID(GetExport 用) |
| `name` | 题名 | `a.fz14` 文本;先剥 `<!--注释-->`、`B.marktip`(网络首发)、`i.freeIdent`(免费) |
| `author` | 作者 | 多个 `a.KnowledgeNetLink` 文本 |
| `source` | 来源期刊 | `p > a` 文本 |
| `date` / `data` | 发表时间 / 数据库类型 | 纯文本 |
| `quote` / `download` | 被引 / 下载数 | 数字,可能为空 |
| `operat` | 操作列 | `a.icon-collect[data-filename][data-dbname]` = 明文短号+库代码(**不能**用于 GetExport);`a.icon-airead[href]` 的 `cid=` 参数 = 加密ID 的另一来源 |

## 风控行为汇总

| 行为 | 后果 | 解除 |
|---|---|---|
| 全新匿名会话直接访问 | 302 到 `/verify/home?captchaType=blockPuzzle`(腾讯滑块) | 浏览器过验 |
| 随机自造 Ecp_ClientId | GetExport 返回 -403 | 用服务端认的 clientid(浏览器 cookie) |
| brief/grid 短间隔连发 | 响应变 `vericodeForm` 图形验证码页 | 粘性,等待无效;浏览器人工过验释放 |
| GetExport 高频 | 风控松,2-3 秒/篇连打多次正常 | — |
| 登录态过期 | 页面右上角"个人登录";检索/引文不受影响 | 需要下载全文时重新登录 |

Ecp_ClientId 格式:32 位 hex + 9 位 base62,由知网服务端体系认定;本地生成仅作为无 cookie 时的降级(通常会 -403)。会话 cookie 收割:浏览器 `document.cookie` 仅含非 HttpOnly 部分,已够用;若需完整 cookie(含 KNS2COOKIE)须用 Playwright `context.cookies()`。
