#!/usr/bin/env python3
"""Packet Tracer .pkt 外科手术工具箱。

核心思路：不要从零生成 .pkt，而是拿一个**目标版本的原生 .pkt 当底稿**，
只改需要改的部分（设备名、配置、IP、链路、坐标），这样版本字段天然对齐。

依赖: pip install packet-tracer-pkt-format
"""
from __future__ import annotations

import json
import re
import sys
import pathlib

from pkt_core.codec.container import decode, encode_bytes

DEV_RE = re.compile(rb"<DEVICE>.*?</DEVICE>", re.S)
NAME_RE = re.compile(rb'<NAME translate="true">([^<]*)</NAME>')


# ---------- 读 ----------

def load(path: str | pathlib.Path):
    """返回 container（含 .xml / .format_name / .version 等）。"""
    return decode(str(path))


def version(xml: bytes) -> str:
    m = re.search(rb"<VERSION>([^<]*)</VERSION>", xml)
    return m.group(1).decode() if m else "?"


def devices(xml: bytes) -> list[dict]:
    """按 PT 内部顺序列出设备。索引即 LINK 里 FROM/TO 用的序号。"""
    out = []
    for i, m in enumerate(DEV_RE.finditer(xml)):
        blk = m.group(0)
        name = NAME_RE.search(blk).group(1).decode()
        model = re.search(rb'<TYPE customModel="([^"]*)"', blk)
        addr = re.search(rb"<DEV_ADDR>([^<]*)</DEV_ADDR>", blk)
        out.append({
            "index": i,
            "name": name,
            "model": model.group(1).decode() if model else "?",
            "dev_addr": addr.group(1).decode() if addr else "?",
        })
    return out


def block_of(xml: bytes, name: str) -> bytes:
    for m in DEV_RE.finditer(xml):
        if NAME_RE.search(m.group(0)).group(1).decode() == name:
            return m.group(0)
    raise KeyError(f"没有设备 {name}")


# ---------- 写 ----------

def replace_block(xml: bytes, name: str, new_block: bytes) -> bytes:
    old = block_of(xml, name)
    return xml.replace(old, new_block, 1)


def rename_device(xml: bytes, old: str, new: str) -> bytes:
    """同时改 ENGINE/NAME、PHYSICAL 路径末段、SYS_NAME、物理工作区叶节点。"""
    blk = block_of(xml, old)
    b = re.sub(rb'(<NAME translate="true">)[^<]*(</NAME>)',
               rb"\g<1>" + new.encode() + rb"\g<2>", blk, count=1)
    # <PHYSICAL>Rack,Main Wiring Closet,旧名</PHYSICAL> —— 只换最后一段
    b = re.sub(rb'(<PHYSICAL translate="true">[^<]*),([^<,]*)</PHYSICAL>',
               rb"\g<1>," + new.encode() + rb"</PHYSICAL>", b, count=1)
    b = re.sub(rb"(<SYS_NAME>)[^<]*(</SYS_NAME>)",
               rb"\g<1>" + new.encode() + rb"\g<2>", b, count=1)
    xml = replace_block(xml, old, b)
    xml = xml.replace(f'<NAME translate="true">{old}</NAME>'.encode(),
                      f'<NAME translate="true">{new}</NAME>'.encode())
    return xml


def delete_device(xml: bytes, name: str) -> bytes:
    """删设备块 + 物理工作区里对应的机架叶节点（漏删会留下孤儿节点）。"""
    xml = xml.replace(block_of(xml, name), b"", 1)
    xml = re.sub(rb"[ \t]*<DEVICE>\s*</DEVICE>\n?", b"", xml)
    needle = f'<NAME translate="true">{name}</NAME>'.encode()
    pos = xml.find(needle)
    while pos != -1:
        s = xml.rfind(b"<NODE>", 0, pos)
        e = xml.find(b"</NODE>", pos) + len(b"</NODE>\n")
        xml = xml[:s] + xml[e:]
        pos = xml.find(needle)
    return xml


def set_running_config(xml: bytes, name: str, lines: list[str],
                       sync_startup: bool = True) -> bytes:
    """整体替换 RUNNINGCONFIG；sync_startup=True 时 STARTUPCONFIG 写成同一份
    （等价于已经 copy run start，打开就是掉电后状态）。"""
    ind = "      "
    blk = block_of(xml, name)
    inner = "".join(f"{ind}<LINE>{ln}</LINE>\n" for ln in lines).encode()
    rc = f"{ind}<RUNNINGCONFIG>\n".encode() + inner + f"{ind}</RUNNINGCONFIG>".encode()
    blk = re.sub(rb"[ \t]*<RUNNINGCONFIG>.*?</RUNNINGCONFIG>", rc, blk, count=1, flags=re.S)
    if sync_startup:
        sc = f"{ind}<STARTUPCONFIG>\n".encode() + inner + f"{ind}</STARTUPCONFIG>".encode()
        blk = re.sub(rb"[ \t]*<STARTUPCONFIG\s*/>|[ \t]*<STARTUPCONFIG>.*?</STARTUPCONFIG>",
                     sc, blk, count=1, flags=re.S)
    return replace_block(xml, name, blk)


def set_port_ip(xml: bytes, name: str, ip: str, mask: str, gw: str) -> bytes:
    """终端设备（PC/Server）的网卡静态 IP。只动第一个 <PORT> 块。"""
    blk = block_of(xml, name)
    m = re.search(rb"<PORT>.*?</PORT>", blk, re.S)
    port = m.group(0)
    for tag, val in (("IP", ip), ("SUBNET", mask), ("PORT_GATEWAY", gw)):
        t = tag.encode()
        pat = rb"<" + t + rb"\s*/>|<" + t + rb">[^<]*</" + t + rb">"
        port = re.sub(pat, f"<{tag}>{val}</{tag}>".encode(), port, count=1)
    blk = blk[:m.start()] + port + blk[m.end():]
    if b"<GATEWAY>" in blk:
        blk = re.sub(rb"<GATEWAY>[^<]*</GATEWAY>",
                     f"<GATEWAY>{gw}</GATEWAY>".encode(), blk, count=1)
    else:
        blk = re.sub(rb"(</SYS_NAME>\n)",
                     rb"\1     <GATEWAY>" + gw.encode() + rb"</GATEWAY>\n", blk, count=1)
    return replace_block(xml, name, blk)


# ---------- 链路 ----------

def dump_links(xml: bytes) -> list[dict]:
    """导出当前链路为可编辑 JSON（保留 mem 地址，改拓扑时直接改这个）。"""
    m = re.search(rb"<LINKS>(.*?)</LINKS>", xml, re.S)
    if not m:
        return []
    out = []
    for lm in re.finditer(rb"<LINK>.*?</LINK>", m.group(1), re.S):
        b = lm.group(0)

        def g(tag):
            mm = re.search(rb"<" + tag + rb">([^<]*)</" + tag + rb">", b)
            return mm.group(1).decode() if mm else ""

        ports = re.findall(rb"<PORT>([^<]*)</PORT>", b)
        out.append({
            "from": int(g(rb"FROM")), "from_port": ports[0].decode() if ports else "",
            "to": int(g(rb"TO")), "to_port": ports[1].decode() if len(ports) > 1 else "",
            "length": g(rb"LENGTH"),
            "from_dev_mem": g(rb"FROM_DEVICE_MEM_ADDR"),
            "to_dev_mem": g(rb"TO_DEVICE_MEM_ADDR"),
            "from_port_mem": g(rb"FROM_PORT_MEM_ADDR"),
            "to_port_mem": g(rb"TO_PORT_MEM_ADDR"),
            "cable_type": (re.findall(rb"<TYPE>([^<]*)</TYPE>", b) or [b""])[-1].decode(),
        })
    return out


def set_links(xml: bytes, links: list[dict]) -> bytes:
    """整体替换 <LINKS>。links 条目字段见 dump_links()。"""
    chunks = []
    for l in links:
        chunks.append(f"""   <LINK>
    <TYPE>eCopper</TYPE>
    <CABLE>
     <LENGTH>{l.get('length', '1')}</LENGTH>
     <FROM>{l['from']}</FROM>
     <PORT>{l['from_port']}</PORT>
     <TO>{l['to']}</TO>
     <PORT>{l['to_port']}</PORT>
     <FROM_DEVICE_MEM_ADDR>{l.get('from_dev_mem', '0')}</FROM_DEVICE_MEM_ADDR>
     <TO_DEVICE_MEM_ADDR>{l.get('to_dev_mem', '0')}</TO_DEVICE_MEM_ADDR>
     <FROM_PORT_MEM_ADDR>{l.get('from_port_mem', '0')}</FROM_PORT_MEM_ADDR>
     <TO_PORT_MEM_ADDR>{l.get('to_port_mem', '0')}</TO_PORT_MEM_ADDR>
     <GEO_VIEW_COLOR>#000000</GEO_VIEW_COLOR>
     <TYPE>{l.get('cable_type', 'eStraightThrough')}</TYPE>
    </CABLE>
   </LINK>
""")
    body = "<LINKS>\n" + "".join(chunks) + "  </LINKS>"
    return re.sub(rb"<LINKS>.*?</LINKS>", body.encode(), xml, count=1, flags=re.S)


# ---------- 布局 ----------

def move(xml: bytes, positions: dict[str, tuple[float, float]]) -> bytes:
    """改逻辑视图坐标。屏幕坐标 ≈ 逻辑坐标（实测 y 有固定偏移属正常）。"""
    def repl(m):
        blk = m.group(0)
        name = NAME_RE.search(blk).group(1).decode()
        if name not in positions:
            return blk
        x, y = positions[name]
        i = blk.find(b"<LOGICAL>")
        head, tail = blk[:i], blk[i:]
        tail = re.sub(rb"<X>[^<]*</X>", f"<X>{x}</X>".encode(), tail, count=1)
        tail = re.sub(rb"<Y>[^<]*</Y>", f"<Y>{y}</Y>".encode(), tail, count=1)
        return head + tail

    return DEV_RE.sub(repl, xml)


def save(xml: bytes, dst: str | pathlib.Path, cont) -> pathlib.Path:
    p = pathlib.Path(dst)
    p.write_bytes(encode_bytes(xml, cont.format_name))
    return p


# ---------- CLI ----------

def main(argv: list[str]) -> None:
    if len(argv) < 3:
        print("用法:\n  pkt_surgery.py info <in.pkt>\n  pkt_surgery.py links <in.pkt>")
        return
    cmd, src = argv[1], argv[2]
    cont = load(src)
    if cmd == "info":
        print(f"file    : {src}")
        print(f"version : {version(cont.xml)}")
        for d in devices(cont.xml):
            print(f"  [{d['index']}] {d['name']:<12} {d['model']}")
        print(f"links   : {len(dump_links(cont.xml))}")
    elif cmd == "links":
        print(json.dumps(dump_links(cont.xml), indent=2, ensure_ascii=False))
    else:
        print(f"未知命令 {cmd}")


if __name__ == "__main__":
    main(sys.argv)
