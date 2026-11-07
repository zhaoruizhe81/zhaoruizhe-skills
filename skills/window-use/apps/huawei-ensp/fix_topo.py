#!/usr/bin/env python3
"""eNSP .topo 修复器 — 手写拓扑加载后 PC↔交换机连线被静默丢弃的根治补丁。

根因（见 apps/huawei-ensp/踩坑.md N1）：加载器靠设备 slot 里的接口声明绑定线的
srcIndex/tarIndex；手写 topo 的 PC 没有 <interface> 声明 → 所有 PC 线静默丢弃
（交换机有声明所以 trunk 能活）。本工具：
  ① 给每台 model="PC" 补接口声明（写法照抄官方示例 Campus_Network.topo）：
     - 自闭合 dev（<dev ... />，手写件常见）→ 收口为 <dev ...><slot>声明</slot></dev>
     - 空 slot（<slot number="slot17" isMainBoard="1" />，eNSP 保存件常见）→ 展开注入
  ② 行尾统一 CRLF（eNSP 原生格式）
  ③ 打印 devices / lines / 接口声明 计数供核对
用法:
  python3 fix_topo.py <in.topo>            # 就地修复（自动备份 in.topo.bak）
  python3 fix_topo.py <in.topo> <out.topo> # 修到新文件
验收: 推到 PC 上用 eNSP 打开 → 保存回写 → 数新文件里 '<line ' 条数（N1）。
"""
import re
import sys
import shutil

# 注意：SLOT_DECL 内部只用 \n。注入发生在"归一到 \n"之后、"统一 CRLF"之前，
# 内嵌字面 \r\n 会被二次替换成 \r\r\n（2026-11-05 修复），行尾污染靠 XML 归一兜底才没炸。
SLOT_DECL = (
    '<slot number="slot17" isMainBoard="1">\n'
    '                <interface sztype="Ethernet" interfacename="GE" count="1" />\n'
    '            </slot>'
)


def fix_pc(dev, stats):
    if "<interface" in dev:
        stats["already"] += 1
        return dev
    if '<slot number="slot17" isMainBoard="1" />' in dev:
        stats["injected"] += 1
        return dev.replace('<slot number="slot17" isMainBoard="1" />', SLOT_DECL)
    # 自闭合 <dev ... /> —— 无 slot，收口后插入 slot
    m = re.search(r"\s*/>\s*$", dev)
    if m:
        stats["injected"] += 1
        body = dev[: m.start()]
        return body + ">" + SLOT_DECL + "\n        </dev>"
    sys.stderr.write("WARN: PC dev 结构异常，未改动:\n%s\n" % dev[:200])
    return dev


def fix(text):
    stats = {"injected": 0, "already": 0}

    def repl(m):
        dev = m.group(0)
        if 'model="PC"' not in dev:
            return dev
        return fix_pc(dev, stats)

    # 自闭合匹配必须放前面，且 [^>]* 保证不跨标签吞块（否则一个 match 吞掉多个 dev）
    text = re.sub(r"<dev\b[^>]*/>|<dev\b[^>]*>.*?</dev>", repl, text, flags=re.S)
    return text, stats


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    src = sys.argv[1]
    dst = sys.argv[2] if len(sys.argv) > 2 else src
    with open(src, "rb") as f:
        raw = f.read()
    # 记住源编码并按原编码写回（2026-11-05 修复：旧版 UTF-16 读入却一律 UTF-8
    # 写回，UTF-16 版 eNSP 读修复后的文件可能打不开）
    try:
        text = raw.decode("utf-8")
        enc = "utf-8"
    except UnicodeDecodeError:
        text = raw.decode("utf-16")  # 有些 eNSP 版本存 UTF-16
        enc = "utf-16"
    if text.startswith("\ufeff"):
        text = text.lstrip("\ufeff")
    text = text.replace("\r\n", "\n").replace("\r", "\n")  # 先归一再统一 CRLF
    text, stats = fix(text)
    text = text.replace("\n", "\r\n")
    if dst == src:
        shutil.copyfile(src, src + ".bak")
    with open(dst, "wb") as f:
        f.write(text.encode(enc))
    print("fixed -> %s (encoding=%s)" % (dst, enc))
    print("  PC 补接口声明: %d (本已声明: %d)" % (stats["injected"], stats["already"]))
    print("  <line 条数: %d" % text.count("<line "))
    print("  <interface 声明: %d" % text.count("<interface "))
    print("  设备数 <dev: %d" % text.count("<dev "))
    print("  CRLF 纯净: %s" % (text.count("\n") == text.count("\r\n")))
    if text.count("<line ") == 0:
        sys.stderr.write("WARN: 文件里没有连线——修复后仍需按 N1 验收流程确认\n")


if __name__ == "__main__":
    main()
