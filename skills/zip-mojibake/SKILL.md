---
name: zip-mojibake
description: 诊断、修复、重新打包中文 ZIP 文件名乱码。当用户提到 zip 解压后中文文件名变成 `½ªÉºÉº` / `Ê¯¶«¾ý` / `Àîê×³½` / `???` / `????.zip` 这类 Latin-1 看待 GBK 字节的典型乱码,收到 Windows/国产压缩工具(Bandizip 旧版、好压、快压等)打的中文 zip,或反过来要把带中文文件名的目录打包发给 Windows 用户希望对方资源管理器不乱码时,务必使用本 skill。也包括 .rar/.7z 解压后乱码的诊断(修复输出仅针对 zip)。务必主动识别症状——不要等用户明确说"乱码",只要文件名出现上述 Latin-1 字符模式就触发。
---

# zip-mojibake

中文 ZIP 文件名乱码的诊断、修复、安全重打包。覆盖 Windows 国产压缩工具(Bandizip 旧版、好压、快压等)双重编码 bug 导致的"伪 UTF-8"乱码——这是中文圈最常见的乱码形态。

## 背景:为什么会乱码

ZIP 规范里文件名编码靠 **General Purpose Flag bit 11(0x800,叫 EFS)** 标志位声明:
- EFS = 0 → 文件名按 CP437 解码(或本地代码页)
- EFS = 1 → 文件名按 UTF-8 解码

国产压缩工具有个长期 bug:把 GBK 字节当成 Latin-1 字符,再重新编码成 UTF-8 字节,同时把 EFS 设为 1。结果字节在严格 UTF-8 解码下不报错(EFS=1 让解压工具信任它),但内容是错的——你看到的就是 Latin-1 视角的 GBK 字节。

**典型乱码模式**(看到这些就 99% 是双重编码):
- `½`、`Ê`、`À`、`Ã`、`Â`、`É`、`Î`、`Ô` 开头,后跟拉丁字母
- 中文姓名变成 4-6 个这种字符的串
- 同一个名字在 macOS `unzip` 显示为 `?`,在 Python `zipfile` 显示为 `½ªÉº` 等

## 三种工作模式

根据用户意图选一种:

### 1. 诊断模式

**触发**:用户问"为什么乱码" / "里面是什么文件" / "这是什么压缩包"。

```bash
python3 ~/.claude/skills/zip-mojibake/scripts/diagnose.py <zip路径>
```

输出每条目一行:`EFS | 原始字节十六进制 | UTF-8? | 双重编码? | GBK? | 推荐真名`。看完直接告诉用户原始真名 + 根因,不需要解压。

### 2. 修复解压模式

**触发**:用户要拿到正确文件 / "帮我把这个 zip 解压出来" / "文件名恢复正常"。

```bash
python3 ~/.claude/skills/zip-mojibake/scripts/extract_fixed.py <zip路径> [--out 输出目录] [--max-depth 3]
```

默认输出到 `<zip-stem>_recovered/`。**自动递归**:如果解出来的文件本身是 zip(嵌套场景),自动修复内层并展开,深度默认 3。**路径安全**:过滤 `..`、绝对路径、Windows 保留名(CON/NUL/AUX 等)。

### 3. 安全重打包模式

**触发**:用户要发给别人 / "我要打包发 Windows" / "重新压缩避免乱码"。

```bash
python3 ~/.claude/skills/zip-mojibake/scripts/repack_utf8.py <源目录或源zip> [--out 输出zip]
```

用 Python `zipfile` 写,文件名按合法 UTF-8 编码(EFS 自动设),路径分隔符统一 `/`,跳过 `.DS_Store` / `Thumbs.db`。写完用 Python 读回 `namelist` 自检中文是否正确。

## 关键规则(容易踩的坑)

1. **不要用 macOS 系统 `unzip` 验证修复结果**。它是 2009 年 Info-ZIP 老版,Apple 改的,根本没编译 UNICODE_SUPPORT,**无视 EFS 标志位**,即使字节是合法 UTF-8 + EFS=1,它也会显示成 `?`。这是 macOS 自带工具的 bug,不是 zip 的问题。
2. **验证用什么**:用 Python `python3 -m zipfile -l <zip>` 或 `python3 -c "import zipfile; print(zipfile.ZipFile('x.zip').namelist())"`。这两个都正确读 EFS。也可以用 Keka、The Unarchiver、Windows 资源管理器、7-Zip、WinRAR。
3. **重打包首选 Python `zipfile`**,不要用 macOS `zip` CLI 或 `ditto`(它们对中文处理不一致)。
4. **路径分隔符**:Windows 工具写的 zip 常用 `\`,跨平台解压会出问题,重打包时一律转 `/`。
5. **EFS=0 的纯 GBK 包也存在**(老 WinRAR、WinZip 早期版本),识别特征:EFS=0 且 GBK 解码成功 → 直接按 GBK 解,不要走双重编码链。

## 失败兜底

`extract_fixed.py` 和 `diagnose.py` 的解码顺序:
1. EFS=1:试 `bytes.decode('utf-8').encode('latin-1').decode('gbk')`(双重编码还原)
2. EFS=1 上一步失败:试 `bytes.decode('utf-8')`(真 UTF-8)
3. EFS=0:试 `bytes.decode('gbk')`
4. 仍失败:试 `gb18030`(GBK 超集)
5. 仍失败:用 UTF-8 + `errors='replace'` 兜底,在 stderr 警告,文件名带 `_RECOVERFailed_` 前缀方便人工介入

## 不做的事

- 不修 .rar / .7z(`diagnose.py` 能借入分析乱码模式,但修复输出仅 zip)
- 不做 CJK 全套(仅中文;日文 Shift-JIS / 韩文 EUC-KR 不在本 skill 范围)
- 不做图形界面或独立 CLI 工具(仅服务 Claude 自己调用)
