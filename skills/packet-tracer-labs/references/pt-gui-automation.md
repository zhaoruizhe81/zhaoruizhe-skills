# PT GUI 实测与验收（Windows 8.2）

改完 .pkt 不算完，必须在真实 PT 里打开确认。以下是已在 Windows 10/11 + PT 8.2.0、1920×1080 上跑通的流程。

## 1. 文件怎么进 Windows

Mac 侧起下载服务器（在产物目录下）：

```bash
python3 -m http.server 8777
```

Windows 侧拉取（中文文件名正常工作）：

```powershell
Invoke-WebRequest -Uri 'http://<MAC_IP>:8777/lab.pkt' -OutFile "$env:USERPROFILE\Desktop\实验.pkt" -UseBasicParsing
```

反向（截图回传）用 PUT 服务，见 `scripts/recv_server.py`：

```powershell
Invoke-WebRequest -Uri 'http://<MAC_IP>:8778/up?name=shot.png' -Method Put `
  -InFile "$env:USERPROFILE\Desktop\ptshot\s1.png" -UseBasicParsing -TimeoutSec 25
```

## 2. 打开文件的固定套路

1. `File → New`，弹「unsaved changes」点 **No** —— 目的是释放同名文件的锁。
2. 覆盖桌面上的 .pkt（文件被 PT 打开时无法写入）。
3. `File → Open` → 文件名框粘完整路径 → 发 `VK_RETURN`（别点"打开"按钮）。
4. 等 **30–45 秒**让 STP 收敛，端口指示灯由橙变绿。

菜单坐标（PT 8.2 最大化、1920×1080）：`File (22,33)`、`New (40,53)`、`Open... (50,74)`、
保存提示 `No (1035,549)`、文件名框 `(460,489)`。

## 3. CLI 自动化：三条硬规则

**① 交换机 CLI 不认 Ctrl+V。**
只能用设备对话框右下角的 `Paste` 按钮，坐标 `(1251,763)`。剪贴板文本末尾带 `\n` 会自动回车执行。

**② `Password:` 提示下 Paste 无效。**
IOS 屏蔽密码粘贴，必须发真实键盘事件：

```powershell
Add-Type -MemberDefinition '[DllImport("user32.dll")] public static extern void keybd_event(byte bVk, byte bScan, uint dwFlags, System.UIntPtr dwExtraInfo);' -Name K -Namespace N
[N.K]::keybd_event(0x0D,0,0,[UIntPtr]::Zero); Start-Sleep -Milliseconds 90; [N.K]::keybd_event(0x0D,0,2,[UIntPtr]::Zero)
```

密码本身用 `SendKeys` 的 `SendWait("123{ENTER}")`。

**③ `terminal length 0` 在 2950 12.1 上不支持**（报 `% Invalid input detected`），`show interfaces status` 也不支持。
遇到 `--More--` 就先贴一个 `q` 冲掉，再发下一条命令。

## 4. PC 的 Command Prompt

右键 → 菜单里选 `Paste`（菜单项全屏坐标约 `(970,455)`）→ 再 `keybd_event` 发回车。
不要用 `SendKeys` 打整串命令，会丢前缀并多出字符。

## 5. 验收标准（缺一不可）

| 检查 | 命令/动作 | 通过标志 |
|---|---|---|
| 配置加载 | `show running-config` | hostname、密码、接口、VLAN、vty 全在 |
| 端口状态 | `show ip interface brief` | 所有接线的口 `up / up` |
| 二层学习 | `show mac-address-table` | 能看到终端 MAC |
| 三层连通 | 交换机 `ping 对端IP` | ≥4/5（首包 ARP 正常丢） |
| 端到端 | PC 里 `ping 服务器IP` | 4/4、0% loss |

## 6. 踩过的坑

**强制 duplex/speed 会让端口 down。** 在 running-config 里预置
`interface f0/1` + `duplex full` + `speed 100`，PT 里该口 `down/down`，链路不通；
执行 `no speed` / `no duplex` 立刻 `changed state to up`。
结论：**预置配置里不要留这两行**，教材要求演示时让人自己在 CLI 里敲一遍看回显即可。

**截图别用裁剪。** 带 `region` 的截图会出现残帧/旧画面，判断状态一律拍全屏，然后再本地裁掉任务栏（1920×1080 → 1920×1035）。

**坐标会随布局漂移。** 设备位置由 .pkt 里的 `<X>/<Y>` 决定，改过布局就要重新截图量坐标，不要复用记忆值。

## 7. 出图交付

实验报告要两张图：

1. **规范示意图** — 白底矢量，标设备名、端口、Console 配置线。手写 SVG 后 `rsvg-convert -z 1.4` 出 PNG，比 graphviz 好控制（graphviz 标签总压线）。
2. **PT 实测截图** — 真实界面，标题栏带文件名，链路全绿，裁掉任务栏。
