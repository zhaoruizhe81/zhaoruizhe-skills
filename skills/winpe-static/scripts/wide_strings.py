#!/usr/bin/env python3
"""UTF-16LE 宽字符串提取（macOS 自带 strings 无 -e 参数，故用本脚本）
用法: python3 wide_strings.py <文件> [最小长度=6]
输出: <文件内偏移>  <字符串>
"""
import sys, re

data = open(sys.argv[1], "rb").read()
minlen = int(sys.argv[2]) if len(sys.argv) > 2 else 6
for m in re.finditer(rb"(?:[\x20-\x7e]\x00){%d,}" % minlen, data):
    print(f"{m.start():#010x}  {m.group().decode('utf-16-le')}")
