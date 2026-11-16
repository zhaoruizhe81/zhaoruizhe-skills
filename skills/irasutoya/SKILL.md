---
name: irasutoya
description: 检索、列举并下载 いらすとや(irasutoya.com)免费商用插画。当需要日系扁平插画素材、给 PPT/报告/网页/公众号配图、按日文关键词找"某某的插画"、按官方分类翻图、批量下载 PNG、或需要指定尺寸/方形裁切时使用。纯 HTTP 直连逆向出的 Blogger JSON feed,无需浏览器、无第三方依赖。
---

# いらすとや 接口封装

站点是 **Blogger(blogspot)托管**,所以不用解析 HTML —— 后台就是个 GData feed。
以下全部经实测验证(2026-11 抓取),脚本: `scripts/irasutoya.py`。

## 逆向结果:真正在用的三个接口

| 用途 | 端点 |
|---|---|
| 全文搜索 | `GET https://www.irasutoya.com/feeds/posts/default?alt=json&q=KEYWORD&max-results=N&start-index=M` |
| 按官方标签 | `GET https://www.irasutoya.com/feeds/posts/default/-/LABEL?alt=json` |
| 单篇文章 | `GET https://www.irasutoya.com/feeds/posts/default/POST_ID?alt=json` |

返回结构要点(踩过的坑,别猜):

- 条目在 `feed.entry`(不是 `entries`),字段值都在 `{"$t": "..."}` 里。
- `openSearch$totalResults` **是假的**,它等于你请求的 `max-results`。真实总数只能靠翻页到底。
  实测:`q=猫` 全翻 = 318 篇;标签 `猫` = 233 篇;站点官方标签共 239 个。
- 翻页靠 `start-index`(1 起),每页实测可到 500,脚本用 150 稳一点。
- `q` 的关键词语义是 **AND 全匹配,且只索引正文可见文字**:`猫 溶ける` → 1 条;
  `猫 暑い` → 0 条(因为"暑い"没出现在含猫的正文里)。所以**召回靠标签,精度靠 q**。
- 图片域名固定 `blogger.googleusercontent.com/img/b/<ID>/<尺寸段>/<文件名>`。
  **尺寸段可任意改写**,不需要签名:
  `s1600`(长边 1600,超过原图则给原图)、`s800`、`w1200`、`s400-c`(400×400 方形裁切)、`s72-c`。
- 正文里同一张图出现两次(`<a href>` 大图 + `<img src>` 缩略),按文件名去重取大即可;
  `thumbnail_*`、`banner_*`、`sidebar_*`、`body_background` 是模板垃圾,必须滤掉。
- 单篇文章的 `postId` 不在 feed 里,得从文章页 HTML 抠 `'postId': '4414480386979278786'`(脚本已做)。

## 命令

在 skill 目录内运行:`python3 scripts/irasutoya.py <cmd>`。

```bash
# 搜索(日文关键词;多个词是 AND,慎用)
python3 scripts/irasutoya.py search 猫 -n 5

# 搜索并直接下载(每篇最多 3 张,长边 1200)
python3 scripts/irasutoya.py search 会議 -n 3 --download out/meeting --per-post 3 --size w1200

# 按官方标签翻(召回最全)
python3 scripts/irasutoya.py label 動物キャラ -n 20 --all

# 看全部官方标签 / 过滤
python3 scripts/irasutoya.py labels --grep 天気

# 单篇详情(URL 或 postId 都行),看清所有变体
python3 scripts/irasutoya.py post https://www.irasutoya.com/2025/07/blog-post.html --download out/melt

# 机器可读
python3 scripts/irasutoya.py search 猫 -n 5 --json
```

常用开关:`--size`(默认 `s1600`)、`--json`、`--no-images`、`--download DIR`、
`--per-post K`、`--dl-posts K`、`--flat`(不按标题建子目录)、`--all`(翻完所有页)。

## 输出结构

```
out/<文章标题>/<原文件名>.png
```
文件名保持站点原名(如 `chara_girl_cat.png`),方便追溯;已存在且非空则跳过,可重复跑。

## 使用规则(硬性)

- 个人/法人商用免费、可修改、无需申请。
- **同一件作品用 20 张以内无需署名**;超过 20 张须注明 `イラスト：いらすとや` 或链接。
- 禁止把素材打包转售/当作图库再分发。

## 排错

- 返回 0 条:关键词用日文,且改成单个词;英文几乎无索引(`cat` → 1 条)。
- 下载到的图偏小:站点原图上限就是长边约 1000–1600,`s1600` 已给原图,再大无意义。
- 官方标签名必须日文精确匹配(如 `動物キャラ`、`会社`、`祝日`),用 `labels` 先查。
