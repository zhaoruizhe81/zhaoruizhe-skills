# zip-mojibake

> Claude Code Skill — 诊断、修复、安全重打包中文 ZIP 文件名乱码。

## 这是什么

一个 [Claude Code](https://docs.claude.com/en/docs/claude-code) 的 skill,专门处理中文 ZIP 文件名乱码——尤其是 Windows 国产压缩工具(Bandizip 旧版、好压、快压等)双重编码 bug 导致的"伪 UTF-8"乱码,这是中文圈最常见的乱码形态。

## 三种工作模式

1. **诊断** —— 指出乱码根因 + 原始真名,不解压
2. **修复解压** —— 把乱码 zip 解压成正确文件名(自动递归嵌套 zip,过滤路径穿越)
3. **安全重打包** —— 把目录/zip 重打为标准 UTF-8 包,发给 Windows 用户不乱码

## 用法

把本目录放到 `~/.claude/skills/zip-mojibake/`,之后让 Claude 处理乱码 zip 即可,Claude 会自动调用本 skill 的脚本:

```bash
python3 ~/.claude/skills/zip-mojibake/scripts/diagnose.py      <zip>   # 诊断
python3 ~/.claude/skills/zip-mojibake/scripts/extract_fixed.py <zip>   # 修复解压
python3 ~/.claude/skills/zip-mojibake/scripts/repack_utf8.py   <dir>   # 安全重打包
```

完整说明见 [SKILL.md](SKILL.md)。

## 为什么会乱码(一句话)

ZIP 用 General Purpose Flag bit 11(EFS)声明编码;国产压缩工具把 GBK 字节当 Latin-1 再转成 UTF-8 并设 EFS=1,导致严格 UTF-8 解码不报错但内容是错的——你看到的就是 Latin-1 视角的 GBK 字节(如 `½ªÉºÉº`)。
