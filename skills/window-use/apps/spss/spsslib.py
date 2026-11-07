# -*- coding: utf-8 -*-
"""spsslib.py — IBM SPSS Statistics 动作库（应用包，PC 端；2026-10-25 中心极限定理实验实战沉淀）。

用法（任务脚本，经驱动 `script` 命令执行，继承 DPI-aware 进程）:
    import sys; sys.path.insert(0, AUTO + r"\\apps\\spss")
    import spsslib as sp
    sp.launch_with_sps(r"C:\\...\\exp.sps")          # 冷启动带语法（每轮新实例，见 SP#7）
    sp.clear_startup_popups()                        # 先清"错误报告/会话管理"再等窗口（SP#8）
    sp.run_syntax("exp", wait_s=120, shotname="run1")  # 等使能 → ^a^r → 等输出 → 截图
    sp.shoot_data_view("[smp]", shotname="dv")       # 数据窗口截图（可先切 数据视图 标签）
    sp.page_viewer(pages=4, shot_prefix="pg")        # 查看器内容窗格翻页截图（SP#9）

铁律（详见 踩坑.md SP#7-SP#9 与 坐标与配方.md）:
- stats.exe 每次 Popen 都是全新实例、数据集不共享 → 多步语法合并一个 .sps 一次 ^a^r 跑完
- 强杀后恢复弹窗是自绘窗口（非 #32770，UIA 按钮抓不到），且出现在语法窗口可使能**之前**，
  顺序必须"先清弹窗、后等窗口"
- 查看器大纲点击会自动滚动导致坐标漂移、UIA TreeItem 枚举为 0 → 多对象截图走内容窗格翻页
"""
import os
import subprocess
import time

import pyautogui
pyautogui.FAILSAFE = False
pyautogui.PAUSE = 0.25

import mss
import mss.tools
import win32gui
from pywinauto import Desktop

STATS_EXE = r"C:\Program Files\IBM\SPSS\Statistics\27\stats.exe"
AUTO_DIR = os.environ.get("WGUI_AUTO", r"C:\Users\master\ptauto")

# 启动/异常恢复阶段会出现的 SPSS 弹窗 → 已知"取消"坐标（1920x1080 实测，SP#6/SP#8）
# 坐标唯一事实源：clear_startup_popups 与 kill_popups_v2 共用这一份
# （旧版字典里"错误报告"存着已过期的老版坐标 (1221,808)，点不中新版弹窗——SP#18/坐标与配方.md）
POPUP_KEYWORDS = ("错误报告", "会话管理")          # 需要主动清的两种（标题含关键词即命中）
POPUP_CANCEL_COORDS = {
    "错误报告": (1257, 809),  # 新版（带"共同体验计划"按钮）2026-10-25 实测；老版 (1221,808) 已过期
    "会话管理": (958, 733),
    "保存提示": (960, 551),   # 关查看器时的"是否保存"，点"否"
    "打开数据": (1210, 603),
}

# 数据编辑器左下角"数据视图/变量视图"标签（窗口最大化、1920x1080 实测）
DATA_TAB_COORDS = {"data": (40, 987), "var": (110, 987)}

# 查看器内容窗格的"空白"点击点（拿键盘焦点用，别点在图表/表格上）
VIEWER_BLANK = (1400, 500)


def log(msg):
    # import 进来的模块命名空间拿不到驱动注入的全局，写自己的 spsslib.log
    with open(os.path.join(AUTO_DIR, "spsslib.log"), "a", encoding="utf-8") as f:
        f.write("[%s] %s\n" % (time.strftime("%H:%M:%S"), msg))


# ---------------- 基础原语 ----------------

def shot(name):
    """全屏截图 → <AUTO>/shots/<name>.png（与驱动 shot 同目录同名规则）。"""
    d = os.path.join(AUTO_DIR, "shots")
    os.makedirs(d, exist_ok=True)
    path = os.path.join(d, name + ".png")
    with mss.mss() as s:
        # 抓 monitors[0]（虚拟桌面联合框）——这台 PC 有幽灵残帧显示器，monitors[1]
        # 随机命中它（公#22，ptlib Lab5 实付半小时的坑；旧版这里原样抄回已修的坑）
        m = s.monitors[0]
        img = s.grab(m)
        mss.tools.to_png(img.rgb, img.size, output=path)
    log("shot %s" % name)
    return path


def click(x, y):
    pyautogui.click(int(x), int(y))


def top_windows():
    out = []
    for w in Desktop(backend="win32").windows():
        try:
            out.append((w, w.window_text() or ""))
        except Exception:
            continue
    return out


def find_window(subkey, enabled=True, timeout=60):
    """按标题子串找顶层窗口；enabled=True 时还要求 is_enabled（SPSS 冷启动窗口先出现后使能）。"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        for w, t in top_windows():
            if subkey in t:
                try:
                    if not enabled or w.is_enabled():
                        return w
                except Exception:
                    pass
        time.sleep(3)
    return None


def popup_titles():
    """当前可见的 SPSS 恢复类弹窗（按标题关键词，兼容自绘窗口——SP#8）。"""
    hits = []
    for _w, t in top_windows():
        for k in POPUP_KEYWORDS:
            if k in t:
                hits.append(t)
    return hits


def clear_startup_popups(rounds=6):
    """强杀/崩溃后重启的两连弹：检测到就按已知坐标点"取消"，清完返回残留（应为空列表）。"""
    for _ in range(rounds):
        hits = popup_titles()
        if not hits:
            return []
        for k in POPUP_KEYWORDS:
            if any(k in t for t in hits):
                x, y = POPUP_CANCEL_COORDS[k]
                log("clear popup %s at (%d,%d)" % (k, x, y))
                click(x, y)
                time.sleep(2.5)
                break
    return popup_titles()


# ---------------- 高层配方 ----------------

def launch_with_sps(sps_path):
    """Popen 打开 .sps（会新起实例——多步语法务必合并进一个文件，SP#7）。"""
    log("launch %s" % sps_path)
    return subprocess.Popen([STATS_EXE, sps_path])


def run_syntax(key, wait_s=120, shotname=None, timeout=240):
    """等语法窗口(标题含 key)使能 → ^a^r 全选运行 → 等 wait_s 输出 → 可选截图。
    冷启动前记得先 clear_startup_popups()（顺序不能反，SP#8）。"""
    w = find_window(key, enabled=True, timeout=timeout)
    if w is None:
        log("run_syntax FAIL: window %r not enabled" % key)
        return None
    w.set_focus()
    time.sleep(2)
    w.type_keys("^a^r")
    log("run_syntax: ^a^r sent, wait %ss" % wait_s)
    time.sleep(wait_s)
    if shotname:
        shot(shotname)
    return w


def shoot_data_view(key, tab=None, shotname="dataview", ctrl_home=True, timeout=30):
    """数据编辑器截图。key=标题子串（如 "[smp]"）；tab="data"/"var" 先点对应左下角标签。
    注意 ^home 复位不总生效（焦点问题），截图后应人工核对滚动位置。"""
    w = find_window(key, enabled=True, timeout=timeout)
    if w is None:
        log("shoot_data_view FAIL: %r not found" % key)
        return None
    w.set_focus()
    time.sleep(1)
    try:
        w.maximize()
    except Exception:
        pass
    time.sleep(1.5)
    if tab:
        x, y = DATA_TAB_COORDS[tab]
        click(x, y)
        time.sleep(1.5)
        if ctrl_home:
            pyautogui.hotkey("ctrl", "home")
            time.sleep(1.5)
    shot(shotname)
    return w


def page_viewer(pages=1, direction="pgdn", shot_prefix="pg", blank=VIEWER_BLANK, first_home=False):
    """查看器内容窗格翻页截图（大纲定位不可靠，SP#9）。
    direction: "pgdn"/"pgup"；blank=点哪里拿焦点（务必避开图表表格）。"""
    w = find_window("查看器", enabled=True, timeout=30)
    if w is None:
        log("page_viewer FAIL: viewer not found")
        return None
    w.set_focus()
    time.sleep(1)
    if first_home:
        pyautogui.hotkey("ctrl", "home")
        time.sleep(2)
    click(*blank)
    time.sleep(1)
    for i in range(pages):
        pyautogui.press(direction)
        time.sleep(1.5)
        shot("%s%d" % (shot_prefix, i + 1))
    return w


# ---------------- 2026-10-25 十任务实训沉淀 ----------------

def qtclick(x, y):
    """Qt/自绘窗口可靠点击：moveTo→mouseDown→mouseUp（普通 click 会被吞，公#11b）。"""
    import pyautogui
    pyautogui.moveTo(x, y)
    time.sleep(0.3)
    pyautogui.mouseDown()
    time.sleep(0.15)
    pyautogui.mouseUp()
    time.sleep(2)


def kill_popups_v2(rounds=8):
    """清恢复弹窗 v2：Qt 点击 → esc → alt+F4 三级递进（SP#11/SP#12）。
    坐标统一取 POPUP_CANCEL_COORDS（唯一事实源，旧版此处硬编码绕过字典双源漂移）。"""
    for _ in range(rounds):
        hits = popup_titles()
        if not hits:
            return True
        for k in POPUP_KEYWORDS:
            if any(k in t for t in hits):
                qtclick(*POPUP_CANCEL_COORDS[k])
                if not popup_titles():
                    break
                for w, t in top_windows():
                    if k in t:
                        try:
                            w.set_focus()
                            time.sleep(1)
                            import pyautogui
                            pyautogui.press("esc")
                            time.sleep(1.5)
                            if popup_titles():
                                pyautogui.hotkey("alt", "f4")
                            time.sleep(2)
                        except Exception:
                            pass
                        break
                break
    return not popup_titles()


def launch_chapter(sps_path, key, wait_s=85, shotname=None, run=True):
    """批量任务新鲜启动（配方 D，2026-10-25 十任务实战）：
    杀进程 → 清 autoRecovery → launch → 持续轮询清弹窗+等使能 → ^a^r → 等待。
    key=窗口标题子串（文件名去扩展名）。返回语法窗口句柄或 None。"""
    import subprocess, os
    subprocess.run(["taskkill", "/F", "/IM", "stats.exe"], capture_output=True)
    time.sleep(5)
    rec = os.path.expandvars(r"%AppData%\IBM\SPSS\Statistics\27\autoRecovery")
    # 路径加引号：%AppData% 展开含空格的用户名时旧版静默失效
    subprocess.run(["cmd", "/c", 'del /q /s "%s\\*"' % rec], capture_output=True)
    launch_with_sps(sps_path)
    time.sleep(12)
    w = None
    deadline = time.time() + 240
    while time.time() < deadline:
        kill_popups_v2(2)
        w = find_window(key, enabled=True, timeout=4)
        if w:
            break
    if w is None:
        log("%s blocked" % key)
        shot(key + "_blocked")
        return None
    if run:
        import pyautogui
        w.set_focus()
        time.sleep(2)
        pyautogui.hotkey("ctrl", "a")
        time.sleep(0.5)
        pyautogui.hotkey("ctrl", "r")
        log("%s ^a^r sent, wait %ss" % (key, wait_s))
        time.sleep(wait_s)
        if shotname:
            shot(shotname)
    return w
