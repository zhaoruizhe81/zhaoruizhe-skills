# .pkt 容器与 XML 结构

## 1. 容器层

```
.pkt  --[字节反转 + XOR]-->  Twofish-EAX --[XOR(len-i)]--> qCompress --> UTF-8 XML
      key = 0x89 ×16, iv = 0x10 ×16（PT 4.1–9.x 通用）
```

`pkt_core.codec.container.decode(path)` 一步解到底，返回对象带 `.xml`、`.format_name`、版本信息。
回写用 `encode_bytes(xml, cont.format_name)`——**注意本机安装版没有 `original=` 参数**，
直接写 `encode_bytes(xml, fmt)` 即可。

## 2. 根结构

```xml
<PACKETTRACER5>
  <VERSION>6.2.0.0052</VERSION>
  <NETWORK>
    <DEVICES><DEVICE>…</DEVICE>…</DEVICES>
    <LINKS><LINK>…</LINK>…</LINKS>
  </NETWORK>
  <PHYSICALWORKSPACE>…</PHYSICALWORKSPACE>
  <SHAPETESTS/>
  …
</PACKETTRACER5>
```

`<DEVICE>` 块之间**不嵌套**，可以安全地用 `<DEVICE>.*?</DEVICE>` 非贪婪切分。

## 3. DEVICE 块

```xml
<DEVICE>
  <ENGINE>
    <TYPE customModel="2950-24" …>Switch</TYPE>
    <NAME translate="true">SW1</NAME>
    <POWER>true</POWER>
    <SYS_NAME>SW1</SYS_NAME>
    <GATEWAY>…</GATEWAY>              <!-- 终端有，交换机无 -->
    <RUNNINGCONFIG><LINE>…</LINE></RUNNINGCONFIG>
    <STARTUPCONFIG/>                  <!-- 空 = 没保存过 -->
    <MODULE>…<PORT>…</PORT>…</MODULE>
  </ENGINE>
  <WORKSPACE>
    <LOGICAL>
      <X>960.0</X><Y>412.0</Y><DEV_ADDR>201996400</DEV_ADDR>
    </LOGICAL>
  </WORKSPACE>
</DEVICE>
```

要点：

- `RUNNINGCONFIG` 是 `<LINE>` 数组，**每行一条、不带提示符**，`!` 也要自己写。
- 想让文件"打开即掉电后状态"，把 `STARTUPCONFIG` 写成与 `RUNNINGCONFIG` 相同的内容。
- `<LOGICAL>` 里的 `<X>/<Y>` 是逻辑视图坐标，改布局就改这两个值；只在 `<LOGICAL>` 之后替换第一次出现，否则会误伤别处的 X/Y。
- `POWER` 必须是 `true`，否则设备开机就是关的。

## 4. 端口与 IP（PC / Server）

终端 IP 在第一个 `<PORT>` 内：

```xml
<PORT>
  <IP>172.16.0.2</IP>
  <SUBNET>255.255.0.0</SUBNET>
  <PORT_GATEWAY>172.16.0.254</PORT_GATEWAY>
  <PORT_DNS>0.0.0.0</PORT_DNS>
  <PORT_DHCP_ENABLE>false</PORT_DHCP_ENABLE>
</PORT>
```

未配置时是自闭合形式 `<IP/>`、`<SUBNET/>`，替换时必须同时兼容 `<TAG/>` 和 `<TAG>值</TAG>` 两种写法。
默认网关在同一设备块里还有一份 `<GATEWAY>`（位置在 `</SYS_NAME>` 之前）；有的设备模板缺这个标签，缺就插在 `</SYS_NAME>` 之后。

## 5. LINKS

```xml
<LINK>
  <TYPE>eCopper</TYPE>
  <CABLE>
    <LENGTH>1.95782</LENGTH>
    <FROM>2</FROM>          <!-- 设备序号，从 0 开始，按 DEVICES 顺序 -->
    <PORT>FastEthernet0</PORT>
    <TO>0</TO>
    <PORT>FastEthernet0/1</PORT>
    <FROM_DEVICE_MEM_ADDR>191596912</FROM_DEVICE_MEM_ADDR>
    <TO_DEVICE_MEM_ADDR>201996400</TO_DEVICE_MEM_ADDR>
    <FROM_PORT_MEM_ADDR>198098936</FROM_PORT_MEM_ADDR>
    <TO_PORT_MEM_ADDR>199529404</TO_PORT_MEM_ADDR>
    <GEO_VIEW_COLOR>#000000</GEO_VIEW_COLOR>
    <TYPE>eStraightThrough</TYPE>   <!-- 内层才是电缆类型 -->
  </CABLE>
</LINK>
```

- `FROM`/`TO` 是**设备序号**，删设备后其余设备的序号会顺移，链路必须跟着重排。
- 交换机 2950-24 的 Console 端口**不在 PORT 列表里**，直接写字符串 `Console` 即可。
- 电缆类型：`eStraightThrough` 直通、`eCrossOver` 交叉、`eRollOver` 配置线（PC 的 `RS 232` ↔ 交换机 `Console`）。
- mem 地址是 PT 内部的随机端口标识。**改已有链路时沿用原值最稳**；从旧文件里 dump 出来改，别自己编。

## 6. 物理工作区（最容易漏的一处）

```
<PHYSICALWORKSPACE><HOMERACK><CHILDREN><NODE>…<NAME translate="true">SW1</NAME>…</NODE>
```

删设备只删 `<DEVICE>` 块，会在物理工作区留下孤儿 NODE，文件结构被破坏。
正确做法：删 DEVICE 块后，按设备名定位 `<NAME translate="true">设备名</NAME>`，向上找最近的 `<NODE>`、向下找 `</NODE>`，整块删掉。
改名同理——设备块内的 `<PHYSICAL>Rack,Main Wiring Closet,旧名</PHYSICAL>` 末段和物理 NODE 的 NAME 都要同步。

## 7. 版本差异

| 项 | PT 6.2 | PT 8.2 / 9.x |
|---|---|---|
| `UUID_STR` | 无 | 有 |
| `PHYSICAL_CPUR` | 无 | 有 |
| LINKS 的 FROM/TO | 纯数字 | 纯数字 / `save-ref-id:` 两种 |
| 官方模板 | 需自备底稿 | 库内置 9.0.1 seed |

结论：**库的 `Lab()` 直接生成的是 9.0.1 文件，交给 6.2 打不开的风险真实存在。**
要 6.2 就用 6.2 的原生文件当底稿做手术；要 9.x 才用 `Lab()` 从零建。

## 8. 闭环校验

改完必须验，别只看代码跑通：

```bash
pkt info out/new.pkt                 # 版本/加密/XML 大小
pkt export out/new.pkt --format graphviz -o out/new.dot   # 设备与链路数量对不对
pkt unpack out/new.pkt -o out/new    # 看 configs/SW1.cfg 是否符合预期
```

`export` 出图里没有 edge，通常是 LINK 的 FROM/TO 序号与实际设备顺序对不上，或 mem 地址是编的。
最终验收只有一个标准：**在目标版本的 PT 里打开，端口指示灯变绿，ping 通。**
