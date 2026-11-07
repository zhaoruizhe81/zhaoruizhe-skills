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
| [example-hello](skills/example-hello/) | 示例：演示 SKILL.md 的最小格式 |
