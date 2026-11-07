---
name: qq-mail
description: 通过QQ邮箱发送邮件（含中文附件名）、查询已发送/收件箱、验证邮件是否送达。凡涉及QQ邮箱SMTP/IMAP发信——"帮我发封邮件""把这个文件发给XX""发带附件的邮件""确认邮件到了没""查一下已发送"——即使没明说QQ邮箱，只要发件方是QQ邮箱就使用本技能。
---

# QQ邮箱发信与查询

## 前置条件

QQ邮箱需开启 SMTP/IMAP 服务并持有**授权码**（16位字母，QQ邮箱网页版 设置→账号→开启IMAP/SMTP服务生成）。
授权码不是QQ密码。凭据来源优先级：命令行参数 > 环境变量 `QQ_MAIL_ADDRESS` / `QQ_MAIL_AUTH_CODE` > 配置文件 `~/.config/qq_mail/config.json`。

## 工具与用法

统一使用打包好的脚本（纯标准库，无需安装依赖）：

```bash
SCRIPT=~/.agents/skills/qq-mail/scripts/qq_mail.py

# 发送（支持多个附件，中文文件名不乱码，自动重试3次）
python3 $SCRIPT send --to someone@example.com --subject "主题" \
  --body "正文" --attach 文件1.docx 文件2.pdf [--dry-run]

# 批量给多人发不同内容：用脚本片段循环调用 send（每组间隔3秒防频率限制）

# 查询
python3 $SCRIPT check-sent --days 1 [--contains 关键字]
python3 $SCRIPT check-inbox --days 1 [--contains 关键字]

# 投递链路自测（发给自己再验证到达，用于"邮件到底发没发出去"的排查）
python3 $SCRIPT selftest
```

`--dry-run` 先演练确认再真发。对外发送属于不可撤回操作：**正式发送前必须先让用户确认收件人、内容和方式**。

## 必须知道的坑（都是实际踩过的）

1. **SMTP发送不会写「已发送」副本**。网页版发信才自动存；脚本用 `smtplib` 发完后必须通过 IMAP `APPEND` 到 `"Sent Messages"` 补一份（脚本已内置），否则用户在QQ邮箱网页看不到已发送记录，会以为没发出去。
2. **IMAP文件夹名带空格必须加引号**：`select('"Sent Messages"')`，不带引号会返回 BAD。
3. **IMAP不能用中文条件搜索**：`search('SUBJECT', '中文')` 直接 ascii 编码崩溃。正确做法是 `SINCE <英文日期>` 拉取后本地解码过滤（脚本已内置）。
4. **中文主题/附件名必须用 `Header(..., 'utf-8').encode()`** 编码，直接塞字符串会乱码或报错。
5. **批量发送要限速**：每封间隔≥3秒，附件总量大时更慢些，否则触发QQ频率限制。失败自动重试3次已内置。
6. **验证送达**：SMTP `sendmail` 返回成功＝QQ已接手投递；若无退信基本已送达（自测邮件30秒内可达）。查「已发送」为空不代表没发出去——见第1条。

## 安全

- 授权码是敏感凭据：不要写入SKILL.md或任何会分享的文件；不要在输出中回显；config.json 权限保持 600。
- 用完或怀疑泄露时，提醒用户去QQ邮箱设置删除旧授权码重新生成。
