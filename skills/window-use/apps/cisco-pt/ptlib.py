# -*- coding: utf-8 -*-
"""ptlib.py — Cisco Packet Tracer 动作库（应用包，PC 端；跟着驱动跑，本机/远程场景通用）。

用法（任务脚本，经驱动 `script` 命令执行，继承 DPI-aware 进程）:
    import sys; sys.path.insert(0, AUTO + r"\\apps\\cisco-pt")   # AUTO 是驱动注入的全局
    import ptlib
    ptlib.probe()                       # 新 PC/新分辨率首跑: 坐标自检（只画准星，不点击）
    ptlib.place("cat.end", "icon.pc", LAYOUT_LAB2["PC12"])   # …见 坐标与配方.md

坐标体系（换分辨率不用重校，详见 坐标与配方.md）:
    ("r",  rx, ry)   比例坐标 0..1，按当前屏幕宽高解析 —— 画布/居中内容
    ("bl", px, dy)   贴底停靠: 左缘像素 px + 距底像素 dy —— 调色板
    ("c",  dx, dy)   屏幕中心偏移像素 —— 居中弹出的对话框/控制台（首跑需 probe 验证）
    ("tl", px, py)   左上固定像素
校准基准: PT 8.2.0 @1920x1080、100% DPI、最大化。
"""
import os
import time

import pyautogui
pyautogui.FAILSAFE = False
pyautogui.PAUSE = 0.25

import mss
import win32clipboard
from pywinauto import Desktop
from pywinauto.keyboard import send_keys
from PIL import Image, ImageDraw


def AUTO_DIR():
    return os.environ.get("WGUI_AUTO", r"C:\Users\master\ptauto")


def log(msg):
    # 注意: import ptlib 的模块命名空间拿不到驱动注入的全局，
    # 所以写自己的 ptlib.log（驱动 gui.log 仍有 START/DONE 主线记录）
    with open(os.path.join(AUTO_DIR(), "ptlib.log"), "a", encoding="utf-8") as f:
        f.write("[%s] %s\n" % (time.strftime("%H:%M:%S"), msg))


# ---------------- 坐标解析 ----------------

_SIZE = None

def screen_size():
    global _SIZE
    if _SIZE is None:
        with mss.mss() as s:
            # monitors[0]（虚拟桌面联合框），与 shot() 同一选择——旧版这里取
            # monitors[1]，幽灵屏尺寸不同则 resolve 的比例/中心坐标整体偏移
            m = s.monitors[0]
            _SIZE = (m["width"], m["height"])
    return _SIZE


def resolve(spec):
    if len(spec) == 2:                      # 纯 (x, y) = 当前分辨率绝对像素
        return int(spec[0]), int(spec[1])
    a = spec[0]
    W, H = screen_size()
    if a == "r":
        return int(spec[1] * W), int(spec[2] * H)
    if a == "bl":
        return int(spec[1]), H - int(spec[2])
    if a == "c":
        return W // 2 + int(spec[1]), H // 2 + int(spec[2])
    if a == "tl":
        return int(spec[1]), int(spec[2])
    raise ValueError("bad coord spec: %r" % (spec,))


# ---------------- 校准坐标表（1920x1080 实测） ----------------

COORDS = {
    # 组件面板类别行（贴底停靠 → bl）
    "cat.network":   ("bl",  20, 136),
    "cat.end":       ("bl",  56, 135),
    "cat.conn":      ("bl", 123, 136),
    "cat.misc":      ("bl", 157, 136),
    # 组件图标（选中所属类别后出现）
    "icon.pc":       ("bl", 229, 135),   # End Devices 面板的 PC（正规 PC，有 FastEthernet0）
    "icon.server":   ("bl", 310, 137),   # End Devices 面板的 Server-PT（Lab5 三级项目实测，FastEthernet0）
    "icon.auto":     ("bl", 229, 135),   # Connections 面板：自动选线（闪电）
    "icon.straight": ("bl", 309, 135),   # 铜质直通线
    "icon.cross":    ("bl", 349, 135),   # 铜质交叉线
    "icon.sw2960":   ("bl", 389, 140),   # 2960 交换机（在 Miscellaneous 面板！见 踩坑.md）
    "icon.rtrPT":    ("tl", 597, 940),   # Router-PT 通用路由器（Network Devices 面板，Lab4 校准）
    "icon.rtr2911":  ("tl", 384, 940),   # Cisco 2911（Network Devices 面板；**仅当子面板滚到最左**，
                                         #   滚动箭头 右(705,1004)/左(218,1004)，一下滚一项）
    "dlg.tab.physical": ("c", -306, -326),  # 设备对话框 Physical 标签（2911 装模块用）
    "icon.srlDCE":   ("tl", 509, 940),   # Serial DCE 线缆（Connections 面板；先点的端=DCE）
    "icon.srlDTE":   ("tl", 549, 940),   # Serial DTE 线缆
    "dlg.gw":        ("c",  200,  -80),  # IP Configuration: Default Gateway 输入框
    # 设备对话框（居中弹出 → c；新分辨率首跑 probe 验证此组）
    "dlg.tab.config":("c", -248, -326),  # Config 标签
    "dlg.tab.cli":   ("c", -190, -326),  # CLI（交换机）/ Desktop（PC）标签
    "dlg.close":     ("c",  327, -365),  # 对话框右上 X
    "dlg.settings":  ("c", -265, -273),  # 左树 Settings 节点
    "dlg.fe0":       ("c", -263, -215),  # 左树 FastEthernet0 节点
    "dlg.name":      ("c",  137, -236),  # Display Name 输入框
    "dlg.ipv4":      ("c",  200, -120),  # IP Configuration: IPv4 输入框
    "dlg.mask":      ("c",  200, -100),  # IP Configuration: 子网掩码输入框
    # 交换机 CLI 对话框（居中弹出）
    "cli.focus":     ("c",    0,  -90),  # 控制台空白处（点击给焦点）
    "cli.paste":     ("c",  261,  225),  # PT 控制台 Paste 按钮（控制台不认 Ctrl+V）
    # PC 桌面 → Command Prompt 控制台
    "pc.focus":      ("c",    0,  -90),
    # 确认删除对话框（居中小模态，UIA 拍平，只能像素点）
    "confirm.del":   ("c",  -14,   11),  # Delete 按钮
    # ---- Simulation 抓包(Lab5 实测;按钮 y 随事件列表高度漂移,点前先 fshot 核对) ----
    "sim.toggle":    ("tl", 1871, 907),  # 底部 Realtime/Simulation 切换(Simulation)
    "sim.play":      ("tl", 1781, 778),  # Auto Capture/Play(空列表时 y≈628)
    "sim.filters":   ("tl", 1698, 870),  # Edit Filters 按钮
    "sim.showall":   ("tl", 1835, 870),  # Show All/None
    "sim.evrow1":    ("tl", 1720, 228),  # 事件列表第一行(行距 20.3px)
    "sim.evscroll":  ("tl", 1907, 420),  # 事件列表竖滚动条(拖动翻页,滚轮无效)
    "sim.pdu_pgdn":  ("tl", 1207, 735),  # PDU 面板滚动条轨道底(点击=向下翻页)
    "sim.pdu_pgup":  ("tl", 1207, 335),  # 同上轨道顶
    "sim.pdu_x":     ("tl", 1226, 246),  # PDU Information 面板关闭 X
    # ---- Lab5 v2 仿真抓包专项(2026-10-20 校准,设备对话框必须全关) ----
    "sim.reset":     ("tl", 1687, 723),  # Reset Simulation(唯一清缓冲+时钟;面板上移 58px 时在 ~665)
    "sim.forward":   ("tl", 1820, 779),  # Capture/Forward 步进(0.65~0.9s/次)
    "sim.editfilt":  ("tl", 1755, 870),  # Edit Filters
    "filt.tab4":     ("tl", 825, 302),   # 过滤器对话框 IPv4 标签
    "filt.misc":     ("tl", 913, 302),   # Misc 标签
    "filt.arp":      ("tl", 813, 327),   # ARP 勾选(IPv4 页)
    "filt.dns":      ("tl", 813, 349),   # DNS 勾选(IPv4 页)
    "filt.http":     ("tl", 1016, 371),  # HTTP 勾选(Misc 页)
    "filt.tcp":      ("tl", 913, 569),   # TCP 勾选(Misc 页)
    "filt.close":    ("tl", 1106, 278),  # 过滤器对话框 X
    "buf.clear":     ("tl", 963, 559),   # Buffer Full → Clear Event List(清列表不清时钟!)
    "buf.viewprev":  ("tl", 1080, 559),  # Buffer Full → View Previous Events(保列表;唯一在用)
    "pdu.tab_osi":   ("tl", 723, 295),   # OSI 标签(注意 y=295,266 是标题栏)
    "pdu.tab_in":    ("tl", 836, 295),   # Inbound PDU Details(双击隔 0.8s)
    "pdu.tab_out":   ("tl", 982, 295),   # Outbound PDU Details
    "pdu.scroll_t":  ("tl", 1208, 345),  # 详情滚动起点
    "pdu.scroll_b":  ("tl", 1208, 740),  # 详情滚动终点
    "pc.webicon":    ("tl", 1188, 287),  # PC 对话框 Desktop→Web Browser
    "pc.url":        ("tl", 933, 271),   # 浏览器 URL 框
    "pc.go":         ("tl", 1166, 271),  # Go
    # ---- 服务器 Services 面板(Lab5;服务列表项从 (691,269) 起每项 +18px) ----
    "srv.svc_tab":   ("tl",  773, 214),  # 服务器对话框 Services 标签
    "srv.gw":        ("tl", 1075, 409),  # Config→Settings 的 Default Gateway 字段
    "srv.dhcp.on":   ("tl", 1079, 286), "srv.dhcp.gw":  ("tl", 1153, 340),
    "srv.dhcp.dns":  ("tl", 1153, 366), "srv.dhcp.ip4":  ("tl", 1227, 391),
    "srv.dhcp.max":  ("tl", 1153, 444), "srv.dhcp.save": ("tl", 1023, 522),
    "srv.dns.on":    ("tl",  953, 286), "srv.dns.name":  ("tl",  958, 340),
    "srv.dns.addr":  ("tl", 1038, 375), "srv.dns.add":   ("tl",  861, 403),
    "web.edit":      ("tl", 1022, 514),  # HTTP 面板 index.html 的 (edit)
    "web.content":   ("tl", 1000, 300),  # 主页编辑器内容框
    "web.save":      ("tl", 1245, 776), "web.overwrite": ("tl",  996, 539),
    # ---- PC Desktop 应用图标(单击只选中,再点一次才打开) ----
    "pc.ipcfg":      ("tl",  691, 287),  # IP Configuration
    "pc.cmd":        ("tl", 1080, 287),  # Command Prompt
    "pc.browser":    ("tl", 1188, 287),  # Web Browser
    "pc.dhcp_radio": ("tl",  647, 324),  # IP Configuration 内 DHCP 单选
    "browser.url":   ("tl",  933, 271),  # PC 浏览器 URL 框
    "browser.go":    ("tl", 1166, 271),
    "pc.sub_close":  ("tl", 1270, 250),  # 控制台/浏览器子窗 X
    # ---- 废弃键(留档勿用,校准漂移时别改错) ----
    "buf.prev":      ("tl", 1055, 558),  # [废弃] View Previous Events 旧校准,已被 buf.viewprev 取代
}

# Lab2 布局参考（画布设备位 → r 比例；换实验自行改）
LAYOUT_LAB2 = {
    "PC12": ("r", 0.2188, 0.2778),   # 420,300
    "PC13": ("r", 0.2188, 0.5741),   # 420,620
    "PC14": ("r", 0.5729, 0.2778),   # 1100,300
    "PC15": ("r", 0.5729, 0.5741),   # 1100,620
    "SW4":  ("r", 0.3948, 0.4278),   # 758,462
    "SW5":  ("r", 0.3958, 0.6685),   # 760,722
    "SW6":  ("r", 0.5208, 0.7454),   # 1000,805
    "PC16": ("r", 0.3125, 0.7407),   # 600,800
}


def probe(names=None, out="coord_probe"):
    """坐标自检：把坐标表逐个画十字准星+序号存一张图（不点击）。新 PC/新分辨率首跑必做。
    返回 序号->名字 对照（写进 ptlib.log），拉回截图对照确认。"""
    names = list(names) if names else list(COORDS)
    with mss.mss() as s:
        img = s.grab(s.monitors[0])     # 幽灵显示器规避, 见 shot()
    im = Image.frombytes("RGB", img.size, img.rgb)
    dr = ImageDraw.Draw(im)
    mapping = []
    for i, n in enumerate(names):
        x, y = resolve(COORDS[n])
        dr.line([(x - 14, y), (x + 14, y)], fill=(255, 0, 0), width=2)
        dr.line([(x, y - 14), (x, y + 14)], fill=(255, 0, 0), width=2)
        dr.text((x + 5, y - 16), str(i), fill=(255, 255, 0))
        mapping.append("%d=%s" % (i, n))
    os.makedirs(os.path.join(AUTO_DIR(), "shots"), exist_ok=True)
    p = os.path.join(AUTO_DIR(), "shots", out + ".png")
    im.save(p)
    log("probe -> %s | %s" % (p, " ".join(mapping)))
    return " ".join(mapping)


# ---------------- 基础动作 ----------------

def shot(name):
    # 注意: 抓 monitors[0](整个虚拟桌面)。这台 PC 有一个幽灵显示器
    # (残帧显示器, 内容停留在几天前), monitors[1] 会随机命中它 ——
    # Lab5 实付: 半夜追了半小时"lab4_v1 幽灵窗口", 其实全是幻影屏。
    with mss.mss() as s:
        img = s.grab(s.monitors[0])
    d = os.path.join(AUTO_DIR(), "shots")
    os.makedirs(d, exist_ok=True)
    mss.tools.to_png(img.rgb, img.size, output=os.path.join(d, name + ".png"))
    log("shot " + name)


def wshot(name, title_sub="Packet Tracer"):
    """按窗口表面抓图（PrintWindow），绕开 mss 屏幕拷贝的陈旧帧问题
    （windowpc 实测：远程会话合成器不重绘被遮挡区域，mss 会把几分钟前的旧
    画面当"现状"——Lab5 三级项目实付学费）。窗口找不到时 raise，不落 silently。"""
    d = Desktop(backend="win32")
    for w in d.windows():
        if title_sub in (w.window_text() or ""):
            img = w.capture_as_image()
            if img is None:
                raise RuntimeError("capture_as_image returned None for %r" % title_sub)
            p = os.path.join(AUTO_DIR(), "shots", name + ".png")
            img.save(p)
            log("wshot " + name)
            return p
    raise RuntimeError("window with title %r not found" % title_sub)


def repaint(title_sub="lab5.pkt"):
    """最小化再还原目标窗口，强制 DWM 整窗重绘——这台 PC 的 mss 截屏
    在无鼠标移动/无窗口切换时会拿到几分钟前的旧帧（Lab5 实付），截图前必调。"""
    import win32gui, win32con
    for w in Desktop(backend="win32").windows():
        if title_sub in (w.window_text() or ""):
            h = w.handle
            win32gui.ShowWindow(h, win32con.SW_MINIMIZE)
            time.sleep(0.9)
            win32gui.ShowWindow(h, win32con.SW_RESTORE)
            time.sleep(1.4)
            return True
    raise RuntimeError("window %r not found for repaint" % title_sub)


def fshot(name, title_sub="lab5.pkt"):
    """repaint + shot：这台机器上唯一可信的验证截图。"""
    repaint(title_sub)
    shot(name)


def mouse_reset():
    pyautogui.mouseUp(button="left")   # 失败 drag 会卡死左键，一切动作前复位


def set_clip(text):
    """写剪贴板。占用冲突带重试；CloseClipboard 进 finally——异常后剪贴板
    保持打开会锁死到进程退出（与驱动版 set_clip 同一修复，2026-11-05）。"""
    last = None
    for _ in range(5):
        try:
            win32clipboard.OpenClipboard()
            try:
                win32clipboard.EmptyClipboard()
                win32clipboard.SetClipboardText(text, win32clipboard.CF_UNICODETEXT)
            finally:
                win32clipboard.CloseClipboard()
            return
        except Exception as e:
            last = e
            time.sleep(0.3)
    raise RuntimeError("set_clip failed after retries: %r" % last)


def elname(el):
    try:
        return el.element_info.name or ""
    except Exception:
        return ""


def click_at(spec, delay=1.2):
    x, y = resolve(spec) if isinstance(spec, tuple) else spec
    mouse_reset()
    pyautogui.click(x, y)
    time.sleep(delay)
    return x, y


# ---------------- QMenu 菜单（PT 的端口选择/右键菜单都是 Qt QMenu） ----------------

def find_qmenu():
    d = Desktop(backend="uia")
    for w in d.windows():
        try:
            if w.element_info.class_name == "QMenu":
                return w
        except Exception:
            pass
    return None


def menu_click(exact, shotprefix="menu_miss"):
    """在当前打开的 QMenu 里按名称精确点击菜单项（自动滚动由 UIA 处理）。"""
    m = find_qmenu()
    if m is None:
        raise RuntimeError("no QMenu opened")
    items = m.descendants(control_type="MenuItem")
    for i in items:
        if elname(i).strip() == exact:
            i.click_input()
            time.sleep(0.8)
            return
    shot(shotprefix + "_" + exact.replace("/", "_").replace(" ", "_")[:30])
    raise RuntimeError("item %r not in menu, have: %s" % (exact, [elname(i).strip() for i in items][:8]))


# ---------------- 配方 ----------------

def palette(cat, icon):
    """选中组件放置工具（注意: 放置工具是一次性的，每放一台重新选）。"""
    click_at(COORDS[cat], delay=1.0)
    click_at(COORDS[icon], delay=0.8)


def place(cat, icon, canvas_spec):
    palette(cat, icon)
    click_at(canvas_spec, delay=1.0)


def open_device(dev_spec, tab="config"):
    """单击画布设备 → 打开其对话框并切标签。tab: config | cli(交换机) | desktop(PC)。"""
    click_at(dev_spec, delay=1.5)
    click_at(COORDS["dlg.tab.config" if tab == "config" else "dlg.tab.cli"], delay=1.2)


def close_dialog():
    click_at(COORDS["dlg.close"], delay=1.0)


def paste_field(spec, text):
    """对话框输入框: 先按 Shift 切 IME 到 EN（中文态会拦 Ctrl+V，随机失效），
    三击全选 → 剪贴板粘贴。"""
    pyautogui.press('shift')          # IME -> EN（公共坑：中文态拦 ^v）
    time.sleep(0.2)
    x, y = resolve(spec)
    mouse_reset()
    pyautogui.tripleClick(x, y)
    time.sleep(0.3)
    set_clip(text)
    pyautogui.hotkey("ctrl", "v")
    time.sleep(0.3)


def rename_device(dev_spec, name):
    open_device(dev_spec, "config")
    time.sleep(0.5)
    paste_field(COORDS["dlg.name"], name)
    time.sleep(0.5)
    pyautogui.press("enter")     # QLineEdit 回车提交（直接点 X 会丢弃未提交编辑）
    time.sleep(0.8)
    close_dialog()


def delete_device(dev_spec):
    """删除画布设备: 单击选中（会弹对话框）→ 关掉 → DEL → 点确认框 Delete。
    ⚠ DEL 后固定 1.0s 即盲点确认框——确认框未弹出时（设备未选中/DEL 被吃）该点击
    落在画布中心附近。关键删除动作前先 shot 确认确认框真的在（对照 sim_buffer_dialog
    的像素检测思路）。"""


def fe_anchor(cx, cy):
    """点设备后扫描其右侧弹出的端口菜单，返回第一个黄色 FE 插头图标的 (x,y)。
    菜单未弹出/扫描不到返回 None。用像素定位，不依赖 UIA（UIA 枚举 QMenu 时好时坏）。"""
    from PIL import Image
    import mss
    bx, by = cx + 5, max(150, cy - 50)
    box = {"left": bx, "top": by, "width": 420, "height": 300}
    with mss.mss() as s:
        img = s.grab(box)
        im = Image.frombytes("RGB", img.size, img.rgb)
    px = im.load()
    pts = []
    for i in range(0, im.width, 2):
        for j in range(0, im.height, 2):
            r, g, b = px[i, j][:3]
            if r > 200 and g > 160 and b < 90:      # FastEthernet 插头的黄色
                pts.append((i, j))
    if len(pts) < 8:
        return None
    pts.sort(key=lambda p: p[1])
    top = [p for p in pts if p[1] - pts[0][1] <= 14]   # 最上面的连续黄簇
    ax = sum(p[0] for p in top) // len(top)
    ay = sum(p[1] for p in top) // len(top)
    return (bx + ax, by + ay)


def port_click(cx, cy, off, label):
    """点击菜单中 FE 基准项下方 off*20px 处的端口项（0=第一个 FE 口）。
    关键两条：① moveTo 悬停后再按下-释放（Qt 菜单忽略瞬移点击）；
    ② 点击后验证菜单已从屏幕消失（消失才代表选中；点空只会关菜单不选中）。
    ⚠ 判据的边界：off 越界/菜单布局变化时点中菜单空白区同样会"消失"并返回 True，
    本函数不验证连线真的生成——off 序号必须先靠截图核实，连线后以画布/配置复核。"""
    for _ in range(4):
        a = fe_anchor(cx, cy)
        if not a:
            pyautogui.click(cx, cy); time.sleep(2)   # 菜单没弹，重新点设备
            continue
        tx, ty = a[0] + 45, a[1] + 20 * off
        pyautogui.moveTo(tx, ty, duration=0.25); time.sleep(0.25)
        pyautogui.mouseDown(); time.sleep(0.12); pyautogui.mouseUp()
        time.sleep(1.2)
        if fe_anchor(cx, cy) is None:
            return True
    log("port %s FAILED" % label)
    return False


_WIRE_DONE = False


def wire(icon, a_spec, a_port_off, b_spec, b_port_off, cat="cat.conn", force=False):
    """连线（慢点击版，Lab4 实战验证）：选线型 → 点 A 设备 → port_click 选 A 口 →
    点 B 设备 → port_click 选 B 口 → esc 收尾。
    a_port_off/b_port_off: 端口在菜单中的序号（0=第一个 FE 口，20px 一项）。
    例：PC=FastEthernet0 用 0；2960 的 Fa0/1、Fa0/2 用 0、1；Router-PT 的
    Fa0/0、Fa0/1、S2/0、S3/0 用 0、1、2、3。串口线用 icon.srlDCE（先点的端=DCE）。

    铁律：一个脚本只连一条线（原子步进，见 踩坑.md"批量连线必炸 B 端"）——
    批量调用时第二条起 B 端端口菜单必现不弹。第二次调用直接 raise；
    连下一条线请另起一次脚本触发。确要强连传 force=True（不推荐）。"""
    global _WIRE_DONE
    if _WIRE_DONE and not force:
        raise RuntimeError(
            "wire() 一条线一次触发（原子步进铁律，见 踩坑.md 批量连线坑）；"
            "连下一条请另起一次脚本触发，或 force=True 强连")
    _WIRE_DONE = True
    for attempt in range(3):
        pyautogui.press("esc"); time.sleep(1)      # 清残留菜单/状态
        palette(cat, icon); time.sleep(0.6)
        ax, ay = resolve(a_spec)
        click_at((ax, ay), 1.5)
        if not port_click(ax, ay, a_port_off, "A"):
            pyautogui.press("esc"); time.sleep(1); continue
        time.sleep(0.8)
        bx, by = resolve(b_spec)
        click_at((bx, by), 2.0)
        if not port_click(bx, by, b_port_off, "B"):
            pyautogui.press("esc"); time.sleep(1); continue
        time.sleep(1)
        pyautogui.press("esc"); time.sleep(0.8)
        return True
    raise RuntimeError("wire failed after 3 attempts (see ptlib.log)")


_WIRE_UIA_DONE = False


def wire_uia(icon, a_spec, a_port, b_spec, b_port, cat="cat.conn", attempts=3):
    """UIA 按端口名连线（2911 等千兆口设备必须用这个：Gi 插头不是黄色，
    wire() 的 fe_anchor 像素扫描找不到锚点）。点 A 设备 → QMenu 里按精确名点 A 口 →
    点 B → 点 B 口。A/B 端端口名写错/被占用（不在菜单里）→ menu_click raise，
    attempts 内重试，全失败 raise（不会瞎点）。串口线 icon.srlDCE 先点端=DCE。

    铁律与 wire() 相同：一个脚本只连一条线（2026-11-05 补上缺失的二次调用闸门——
    旧版只有 wire() 有闸门，wire_uia 可在一个脚本里连跑多条，恰是"批量连线必炸
    B 端"踩坑场景本身）。"""
    global _WIRE_UIA_DONE
    if _WIRE_UIA_DONE:
        raise RuntimeError(
            "wire_uia 一条线一次触发（原子步进铁律，同 wire()）；"
            "连下一条请另起一次脚本触发")
    _WIRE_UIA_DONE = True
    for _attempt in range(attempts):
        pyautogui.press("esc"); time.sleep(1)
        palette(cat, icon); time.sleep(0.6)
        ax, ay = resolve(a_spec)
        click_at((ax, ay), 1.5)
        try:
            menu_click(a_port, "menuA_miss")
        except RuntimeError as e:
            log("A-port menu fail: %s" % e)
            continue
        bx, by = resolve(b_spec)
        click_at((bx, by), 2.0)
        try:
            menu_click(b_port, "menuB_miss")
        except RuntimeError as e:
            # B 端与 A 端同等重试（旧版 B 端裸调用，一次失败就炸整个 attempts 循环，
            # 与 docstring 契约相反——2026-11-05 修复）
            log("B-port menu fail: %s" % e)
            pyautogui.press("esc"); time.sleep(1)
            continue
        time.sleep(1)
        pyautogui.press("esc"); time.sleep(0.8)
        return True
    raise RuntimeError("wire_uia failed after %d attempts (see ptlib.log)" % attempts)


def close_leftovers():
    """脚本开头净场：关掉上一轮可能残留的设备对话框 + esc 清菜单。
    必做——残留对话框会让下一次的画布点击落在对话框内部（Lab4 v2 实付：
    整台路由器的配置被粘进另一台设备）。esc 对已弹出的设备对话框无效，必须点 X。
    ⚠ 这是"盲点 X 位置"：没有对话框残留时该点击落在画布上方区域，可能选中恰好
    在那里的设备——净场自带制造残留的理论可能。净场后建议 shot 核对一次再发关键动作。"""
    x, y = resolve(COORDS["dlg.close"])
    mouse_reset()
    pyautogui.click(x, y)
    time.sleep(1.0)
    pyautogui.press("esc")
    time.sleep(0.6)


def _cli_click_paste(line, delay):
    set_clip(line + "\n")
    x, y = resolve(COORDS["cli.paste"])
    mouse_reset()
    pyautogui.click(x, y)
    time.sleep(delay)


def router_cli_config(dev, lines, shotname=None, slow=("ip route", "clock"),
                      save=True, verify=None):
    """路由器 Console 配置一台（粒度表：一台/次）。与交换机 cli_config 的区别：
    ① 先 close_leftovers() 净场；② 初始配置对话框守卫（no + 空行）+ enable 进特权
    （模式会漂，直接 conf t 会 % Invalid）；③ slow 里的关键词行慢速粘贴（1.7s，
    快了会丢参数，如 AD 值）；④ save 后默认跟一条 verify 命令（如 show ip route
    static）留证。完成后截图，不关对话框（看图后由下一步净场）。"""
    close_leftovers()
    click_at(dev, 1.8)
    x, y = resolve(COORDS["dlg.tab.cli"])
    mouse_reset()
    pyautogui.click(x, y)
    time.sleep(1.5)
    x, y = resolve(COORDS["cli.focus"])
    mouse_reset()
    pyautogui.click(x, y)
    time.sleep(0.8)
    _cli_click_paste("no", 1.5)        # 初始配置对话框守卫 "Continue with configuration
                                       # dialog? [yes/no]"——直接回车默认进 setup，
                                       # 整段配置会粘进向导；无对话框时多一个 no，无害
    _cli_click_paste("", 1.5)          # 冲残留 --More-- / Press RETURN
    _cli_click_paste("enable", 1.2)
    _cli_click_paste("configure terminal", 1.2)
    for ln in lines:
        d = 1.7 if any(k in ln for k in slow) else 0.8
        _cli_click_paste(ln, d)
    _cli_click_paste("end", 1.2)
    if save:
        _cli_click_paste("copy running-config startup-config", 1.5)
        _cli_click_paste("", 2.0)      # 确认目的文件名
    if verify:
        _cli_click_paste(verify, 3.0)
        _cli_click_paste("", 1.0)      # 冲一行 --More--
        time.sleep(2.0)
    if shotname:
        shot(shotname)


def cli_paste(line):
    """向交换机 CLI 粘贴一行（剪贴板带换行自动回车）。控制台不认 Ctrl+V，只能点 Paste 按钮。"""
    set_clip(line + "\n")
    x, y = resolve(COORDS["cli.paste"])
    pyautogui.click(x, y)
    time.sleep(0.6)


def cli_config(lines, flush=2, save=True, shotname=None):
    """交换机 CLI 批量配置。flush: 先贴空行冲掉残留; save: copy run start（含回车确认）。"""
    x, y = resolve(COORDS["cli.focus"])
    pyautogui.click(x, y)
    time.sleep(0.5)
    for _ in range(flush):
        cli_paste("")
        time.sleep(1.5)
    for ln in lines:
        cli_paste(ln)
    if save:
        cli_paste("copy running-config startup-config")
        cli_paste("")          # 确认默认目的文件名
        time.sleep(1.5)
    if shotname:
        time.sleep(2.0)
        shot(shotname)


def pc_paste(text):
    """PC Command Prompt: 右键 → Paste 菜单粘贴（不回车）。IME 开着也没关系（走剪贴板）。"""
    set_clip(text)
    d = Desktop(backend="uia")
    for _attempt in range(3):
        pyautogui.press("esc"); time.sleep(0.5)
        x, y = resolve(COORDS["pc.focus"])
        pyautogui.rightClick(x, y)
        time.sleep(1.2)
        m = find_qmenu()
        if m is None:
            continue
        for i in m.descendants(control_type="MenuItem"):
            if elname(i).strip() == "Paste":
                i.click_input()
                time.sleep(0.8)
                return
    raise RuntimeError("Paste menu not found")


def pc_run(text):
    """粘贴一行并回车执行（回车必须用 send_keys，裸 Enter 会被中文 IME 吃成汉字）。"""
    pc_paste(text)
    send_keys("{ENTER}")
    time.sleep(0.5)


def pc_ping(dev_spec, target, wait=6):
    """在 PC 的 Command Prompt 里 ping（假设已打开控制台）。结果靠截图判读。"""
    x, y = resolve(dev_spec)
    pyautogui.click(x, y)
    time.sleep(0.8)
    pc_run("arp -d")            # 换过设备后清残留 ARP（PT 常见假丢包）
    time.sleep(2)
    pc_run("ping " + target)
    time.sleep(wait)


# ---------------- Simulation 抓包 + 服务器/PC 配置(Lab5 v2 沉淀,2026-10-20) ----------------
# 硬事实: ①缓冲 ~48 条,被过滤协议也占名额,满即弹 Buffer Full(每次点击必弹);
#         ②PDU 面板只显示选中行,点击后渲染 ~1s,立即截图=空/旧;标签行 y≈295;
#         ③纯 ACK 行只渲染 L2(无首部表);④列表滚轮无效,滚动条轨道拖拽=翻页;
#         ⑤Clear 只清列表不清时钟,清缓冲必须 Reset Simulation。详见踩坑.md Lab5 v2 专项。

def sim_buffer_dialog():
    """Buffer Full 弹窗是否在(蓝色 i 图标像素;标题条暗像素会被画布虚线误判)。"""
    with mss.mss() as s:
        g = s.grab({"left": 795, "top": 488, "width": 30, "height": 30})
        im = Image.frombytes("RGB", g.size, g.rgb)
    px = im.load()
    blue = sum(1 for i in range(0, im.width, 2) for j in range(0, im.height, 2)
               if px[i, j][2] > 150 and px[i, j][0] < 110 and px[i, j][1] < 160)
    return blue > 30


def sim_dismiss_buffer(keep_list=True):
    """关 Buffer Full 弹窗。keep_list=True 用 View Previous Events(保已捕获行)。"""
    x, y = resolve(COORDS["buf.viewprev"] if keep_list else COORDS["buf.clear"])
    pyautogui.click(x, y); time.sleep(0.9)


def sim_step(n=1, guard=True):
    """Capture/Forward 步进 n 个事件。会话结束后多按会跳进 OSPF 领地+吃缓冲,别贪。"""
    x, y = resolve(COORDS["sim.forward"])
    for _ in range(n):
        pyautogui.click(x, y); time.sleep(0.65)
        if guard and sim_buffer_dialog():
            sim_dismiss_buffer()
            return False
    return True


def _pdu_panel_open():
    """PDU 面板是否开着(红色 X 按钮 (1226,238) 像素;标题暗像素会被画布误判)。"""
    with mss.mss() as s:
        g = s.grab({"left": 1214, "top": 228, "width": 24, "height": 22})
        im = Image.frombytes("RGB", g.size, g.rgb)
    px = im.load()
    red = sum(1 for i in range(0, im.width, 2) for j in range(0, im.height, 2)
              if px[i, j][0] > 170 and px[i, j][1] < 130 and px[i, j][2] < 130)
    return red > 6


def sim_select_row(y, tries=2):
    """点击事件列表 y 行并确保面板打开。渲染 ~1s:每次点击后等 1.2s 再判定。"""
    for t in range(tries):
        click_at(("tl", 1720, y), 1.2)
        time.sleep(1.2)
        if _pdu_panel_open():
            return True
    return False


def sim_pdu_tab(name):
    """切换 PDU 面板标签。name: "osi"/"in"/"out"。双击隔 0.8s(渲染慢,单击常丢)。"""
    key = {"osi": "pdu.tab_osi", "in": "pdu.tab_in", "out": "pdu.tab_out"}[name]
    x, y = resolve(COORDS[key])
    pyautogui.click(x, y); time.sleep(0.7)
    pyautogui.click(x, y); time.sleep(1.0)


def sim_pdu_scroll():
    """详情区拖到底(渲染后等 1s)。"""
    x1, y1 = resolve(COORDS["pdu.scroll_t"])
    x2, y2 = resolve(COORDS["pdu.scroll_b"])
    pyautogui.moveTo(x1, y1, duration=0.3)
    pyautogui.dragTo(x2, y2, duration=0.8); time.sleep(1.0)


def sim_capture(y, name, tabs=("osi", "in", "out", "bot")):
    """目标行四连拍: OSI 全屏 / Inbound 表 / Outbound 表 / 滚动到底。
    渲染延迟 1.2s 起步——快了全是废片(踩坑.md Lab5 v2)。"""
    if not sim_select_row(y):
        log("sim_capture: row %d panel not open" % y)
    shots = []
    if "osi" in tabs:
        shot(name + "_osi"); shots.append(name + "_osi")
    if "in" in tabs:
        sim_pdu_tab("in"); shot(name + "_t1"); shots.append(name + "_t1")
    if "out" in tabs:
        sim_pdu_tab("out"); shot(name + "_t2"); shots.append(name + "_t2")
    if "bot" in tabs:
        sim_pdu_scroll(); shot(name + "_bot"); shots.append(name + "_bot")
    return shots


def sim_reset():
    """清缓冲+时钟。前置: 关全部设备对话框(否则面板上移 58px 点不中)。"""
    x, y = resolve(COORDS["sim.reset"])
    pyautogui.click(x, y); time.sleep(2.0)


def sim_page(down=True):
    """事件列表翻页: 滚动条轨道拖拽(滚轮/方向键均不可靠)。"""
    x = resolve(COORDS["sim.evscroll"])[0]
    y1, y2 = (640, 350) if down else (350, 640)
    pyautogui.moveTo(x, y1, duration=0.3)
    pyautogui.dragTo(x, y2, duration=0.5); time.sleep(0.7)


def pc_dhcp(dev_spec, wait=15, shotname=None):
    """PC 通过 DHCP 获取地址(Desktop→IP Configuration→DHCP 单选,等租约)。"""
    close_leftovers()
    click_at(dev_spec, 2.0)
    click_at(COORDS["dlg.tab.cli"], 1.5)
    click_at(COORDS["pc.ipcfg"], 1.5)
    click_at(COORDS["pc.dhcp_radio"], 1.0)
    time.sleep(wait)               # 等 DORA,应出现 "DHCP request successful"
    if shotname:
        shot(shotname)


def save_pkt():
    """保存当前 .pkt(esc 清态 → 画布抢焦点 → Ctrl+S)。阶段完成必调（公#23 强杀前必存）。
    ⚠ 两点如实说明（2026-11-05 修正）：① 本函数不知道工程路径，mtime 核实做不了，
    调用方拉截图核对保存提示条消失才算数——旧 docstring 承诺 mtime 核实系未实现；
    ② 画布中心抢焦点的点击若恰好落在设备上会打开其对话框，Ctrl+S 就被对话框吞掉；
    ③ 首次保存弹原生"另存为"对话框，本函数不处理。"""
