---
name: packet-tracer-labs
description: 读取、改写、生成并验证 Cisco Packet Tracer 的 .pkt 实验拓扑文件，不需要手工在图形界面拖设备。用于这些场景：要做网络实验的 pkt（交换机/路由器/PC/服务器拓扑）、要改已有 pkt 的设备名或配置或 IP、要把实验拓扑交付给学生或客户、pkt 里的端口起不来或 ping 不通、要把 pkt 转成拓扑图、要批量生成同类实验文件。
---

# Packet Tracer 实验文件工程

`.pkt` 是加密容器 + 未公开 XML。容器早被逆向（见 `references/xml-structure.md`），
所以正确做法不是"打开 PT 手点"，而是**把 pkt 当结构化数据改，再回 PT 验收**。

## 0. 先选路线

| 情况 | 路线 |
|---|---|
| 目标版本是 6.x / 7.x，或已有同类实验文件 | **手术式修改**（推荐）：拿原生 pkt 当底稿，只改差异 |
| 目标版本是 8.x / 9.x，且能接受库默认模板 | **从零生成**：`Lab()` + `add_device()` |
| 只调版式、位置、配色 | `move()` 改坐标即可 |

版式差异是硬约束：库内置模板来自 9.0.1，直接生成的文件在 6.2 里可能打不开（缺 `UUID_STR` 等字段）。
**能手术就不要从零建。**

## 1. 环境

```bash
python3 -m venv .venv && .venv/bin/pip install packet-tracer-pkt-format
```

CLI 与库：

```bash
pkt info lab.pkt                    # 版本、加密、XML 大小
pkt unpack lab.pkt -o out/lab       # XML + configs/ + topology.json/dot
pkt export lab.pkt --format graphviz -o out/lab.dot
```

## 2. 手术式修改（主路线）

```python
import sys; sys.path.insert(0, "scripts")
import pkt_surgery as P

c   = P.load("source.pkt")          # 底稿：同版本的某个原生 pkt
xml = c.xml

P.devices(xml)                      # 先看清序号：LINK 的 FROM/TO 就是这里的 index
links = P.dump_links(xml)           # 现有链路整体导出，保留 mem 地址

xml = P.delete_device(xml, "Router0")                 # 删设备（自动清理物理 NODE）
xml = P.rename_device(xml, "Switch0", "SW1")          # 改名（同步 PHYSICAL + 物理节点）
xml = P.set_running_config(xml, "SW1", [...])         # 整份 RUNNINGCONFIG，含 sync_startup
xml = P.set_port_ip(xml, "PC1", "172.16.0.2", "255.255.0.0", "172.16.0.254")
xml = P.set_links(xml, edited_links)                  # 改完设备再重排链路
xml = P.move(xml, {"SW1": (960, 412), "PC1": (560, 417)})

P.save(xml, "out/实验六.pkt", c)
```

执行顺序很重要：**删/改设备 → 重排 LINKS → 调坐标 → 保存**。
链路里的 `FROM`/`TO` 是设备序号，删过设备就必须重建，否则线会连到别的设备上。

`set_running_config` 收的是纯命令行列表，不带提示符，`!` 分隔符自己写：

```python
["!", "hostname SW1", "!", "enable secret 123", "!",
 "interface Vlan1", " ip address 172.16.0.1 255.255.0.0", "!",
 "ip default-gateway 172.16.0.254", "!",
 "line vty 0 4", " password cisco123", " login", "!", "end"]
```

**不要**预置 `duplex full` / `speed 100`——PT 里会让该端口直接 `down/down`（详见验收章节）。

## 3. 从零生成（8.x / 9.x）

```python
from pkt_core import Lab
lab = Lab(); lab.prune_seed_devices()
sw = lab.add_device("2950-24", "SW1", 500, 300, ios_config=["hostname SW1", ...])
pc = lab.add_device("PC-PT", "PC1", 300, 300, pc_ip=("192.168.1.2", "255.255.255.0", "192.168.1.1"))
lab.link(sw, "FastEthernet0/1", pc, "FastEthernet0", kind="copper")
lab.save("out/lab.pkt")
```

已知问题：生成的 LINKS 用 `save-ref-id:` 引用，`pkt export` 出的 dot 可能没有 edge（设备本身正常）。
真在乎链路，回退到手术式修改。

## 4. 验收：必须在真 PT 里打开

代码跑通 ≠ 文件能用。完整流程、坐标、粘贴方式、密码输入、截图要求见
`references/pt-gui-automation.md`。最小验收：

1. PT 打开文件，无版本报错；
2. `show ip interface brief` 所有接线的口 `up / up`；
3. 交换机 ping 对端 4/5 以上；
4. 终端 ping 服务器 4/4。

## 5. 故障对照表

| 现象 | 原因 | 处理 |
|---|---|---|
| 某端口 `down/down`，同交换机其他口正常 | 配置里预置了 `duplex full` + `speed 100` | `no speed` / `no duplex`，并把这两行从预置配置里去掉 |
| 文件打不开 / 报版本错误 | 用 9.0.1 模板生成了 6.x 目标 | 改成同版本原生文件当底稿 |
| `pkt export` 的图上没有连线 | LINK 的 FROM/TO 序号与实际设备顺序不符，或 mem 地址是编的 | 用 `dump_links()` 取原值再改 |
| 打开后 PT 报结构错误 / 物理视图异常 | 删设备时漏删物理工作区的 NODE 叶节点 | 用 `delete_device()`，它同时清理 |
| 设备开机是关的 | `<POWER>` 非 true | 改 XML 或直接改模板 |
| 终端有 IP 但不通 | `<PORT_GATEWAY>` 与 `<GATEWAY>` 两处不一致 | `set_port_ip()` 会同时写这两处 |

## 6. 交付

一份实验通常交三样：`.pkt` 本体、规范示意图（白底矢量，标端口）、PT 实测截图（链路全绿、标题栏带文件名）。
出图方式见 `references/pt-gui-automation.md` 第 7 节。
