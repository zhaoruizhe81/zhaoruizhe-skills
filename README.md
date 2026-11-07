# zhaoruizhe-skills

个人 ZCode / Claude Code skill 合集。每个 `skills/` 下的子目录就是一个独立的 skill，包含必需的 `SKILL.md` 和可选的脚本/资源。

## 结构

```
zhaoruizhe-skills/
└── skills/
    ├── example-hello/      ← 一个 skill = 一个目录
    │   ├── SKILL.md        ← 唯一必需文件（frontmatter: name + description）
    │   └── scripts/        ← 可选：辅助脚本
    └── ...
```

## 安装方式

### 方式一：整个 clone 后手动拷贝

```bash
git clone https://github.com/zhaoruizhe81/zhaoruizhe-skills.git
cp -r zhaoruizhe-skills/skills/<skill-name> ~/.zcode/skills/
```

### 方式二：sparse-checkout 只取想要的 skill

```bash
git clone --filter=blob:none --no-checkout https://github.com/zhaoruizhe81/zhaoruizhe-skills.git
cd zhaoruizhe-skills
git sparse-checkout init --cone
git sparse-checkout set skills/<skill-name>
git checkout
cp -r skills/<skill-name> ~/.zcode/skills/
```

### 方式三：让 agent 用 skill-installer 安装

直接对 agent 说：

> 从 zhaoruizhe81/zhaoruizhe-skills 安装 skills/<skill-name>

安装后重启 ZCode 即可在 skill 列表中看到新 skill。

## 如何新增 skill

1. 在 `skills/` 下新建目录，目录名 = skill 名
2. 写一个 `SKILL.md`，头部必须包含 YAML frontmatter：

```markdown
---
name: my-skill
description: 一句话说清这个 skill 做什么、什么时候该用它（agent 靠这段决定是否加载）
---

# My Skill

这里写给 agent 的操作说明…
```

3. 可选：把辅助脚本放进同目录的 `scripts/`，在 SKILL.md 里写明用法
4. 提交并推送：`git add . && git commit -m "add my-skill" && git push`

## Skill 列表

| Skill | 说明 |
|---|---|
| [example-hello](skills/example-hello/) | 最小示例 skill，演示 SKILL.md 格式 |
| [cnki-citation](skills/cnki-citation/) | 检索中国知网(CNKI)文献并生成标准引文 |
| [docx](skills/docx/) | Word 文档创建、编辑与分析（来自官方 documents 插件，转载请注明原许可） |
| [er-svg-generator](skills/er-svg-generator/) | 陈氏 ER 图的生成、渲染与布局优化 |
| [flowchart-json-renderer](skills/flowchart-json-renderer/) | 从 JSON 生成黑白流程图（内置 Python 渲染器） |
| [graphviz-diagrams](skills/graphviz-diagrams/) | 创建、校验、渲染 Graphviz DOT/GV 图 |
| [jupyter-notebook](skills/jupyter-notebook/) | 创建/编辑 Jupyter 笔记本（.ipynb） |
| [kaggle](skills/kaggle/) | Kaggle 竞赛、数据集与 notebook 工作流 |
| [module-diagram](skills/module-diagram/) | 论文风格功能模块图 / WBS 树状图 |
| [ppt-master](skills/ppt-master/) | AI 驱动的可编辑 PPTX 生成工作流（含模板库，~120M） |
| [qq-mail](skills/qq-mail/) | QQ 邮箱发信（支持中文附件名）/收发件查询 |
| [skill-creator](skills/skill-creator/) | 创建高质量 skill 的指南与脚手架 |
| [skill-installer](skills/skill-installer/) | 从 GitHub 仓库安装 skill（含私有仓库支持） |
| [snippet-to-image](skills/snippet-to-image/) | 代码片段/终端输出渲染为 PNG 图片 |
| [springboot2-crud-codegen](skills/springboot2-crud-codegen/) | SpringBoot2 CRUD 代码生成器（黑盒 CLI） |
| [ssh-skill](skills/ssh-skill/) | SSH / SCP / SFTP 远程服务器操作 |
| [unsplash-download](skills/unsplash-download/) | 搜索并下载 Unsplash 图片 |
| [volcengine-seedream-imagegen](skills/volcengine-seedream-imagegen/) | 火山引擎 Seedream 文生图（Ark API） |
| [volcengine-tts](skills/volcengine-tts/) | 火山引擎豆包语音合成（Seed TTS） |
| [window-use](skills/window-use/) | 桌面 GUI 自动化工具与知识库 |
| [writing-skills](skills/writing-skills/) | 如何写好/验证 skill 的方法论 |
| [zip-mojibake](skills/zip-mojibake/) | 诊断与修复中文 ZIP 文件名乱码 |

> 注：`ppt-master`、`volcengine-*`、`skill-creator`、`zip-mojibake` 等在本地是通过符号链接安装的，本仓库存的是真实文件拷贝；含密钥的 `.env` 已全部剔除，使用前需按各自 `.env.example` / SKILL.md 说明自行配置。
