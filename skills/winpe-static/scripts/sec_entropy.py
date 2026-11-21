#!/usr/bin/env python3
"""PE 各节熵值计算 — 用法: python3 sec_entropy.py <文件>"""
import sys, math
import pefile
from collections import Counter

def entropy(b: bytes) -> float:
    if not b:
        return 0.0
    c = Counter(b)
    n = len(b)
    return -sum(v / n * math.log2(v / n) for v in c.values())

pe = pefile.PE(sys.argv[1])
print(f"{'节名':<12}{'虚拟大小':>14}{'原始大小':>14}{'熵':>9}  判读")
for s in pe.sections:
    name = s.Name.decode(errors="ignore").rstrip("\x00") or "(无名)"
    e = entropy(s.get_data())
    flag = ">>> 高熵(加壳/加密嫌疑)" if e > 7.2 else ""
    print(f"{name:<12}{s.Misc_VirtualSize:>14X}{s.SizeOfRawData:>14X}{e:>9.3f}  {flag}")
