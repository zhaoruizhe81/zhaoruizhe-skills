---
name: example-hello
description: 最小示例 skill，向用户打招呼并演示 SKILL.md 格式。当用户想看"一个 skill 长什么样"或测试 skill 安装是否生效时使用。
---

# Example Hello

这是一个最小可用的 skill 示例，只做一件事：向当前用户问好并报告环境信息。

## 步骤

1. 用 Bash 运行 `whoami && date` 获取当前用户和时间
2. 输出一句问候，例如：`你好 <用户名>！现在是 <时间>，你的 example-hello skill 已正常工作。`

## 说明

- 本 skill 无任何依赖和脚本，仅演示结构
- `name` 必须与目录名一致
- `description` 写清楚触发场景，agent 靠它决定何时加载本 skill
