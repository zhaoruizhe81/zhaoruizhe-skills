# -*- coding: utf-8 -*-
"""win_gui_driver.py — 核心驱动（场景无关）：在本机或桌面会话里分发一条 GUI 命令。

调用姿势（两种等价）:
  python win_gui_driver.py <cmd> [args...]     # 本机直跑，命令走 argv（不再二次 shlex，
                                               # 反斜杠路径/含引号参数不会被吃）
  （无参数启动）                                # 读 <AUTO>/next_cmd.txt —— 远程投递用：
                                               # Mac 端 remote/pt.py send 重写该文件后触发计划任务。
                                               # 文件读后立即删除（防手工 /run 重放旧命令）。
每条命令结束写 START/DONE/FAIL 到 <AUTO>/gui.log（带日期，超 5MB 轮转 .old），
FAIL 自动存 error_<cmd>_<HHMMSS>.png。解析失败（next_cmd 缺失/空/引号不平衡）也记 FAIL parse
——旧版这里零痕迹死亡，远程只能干等超时。

单实例互斥：驱动进程持一个命名互斥体，上一个实例没退时新触发会立刻记 "FAIL busy"
并退出（schtasks IgnoreNew 的可观测版）。恢复：taskkill pythonw 后重触发，next_cmd.txt
未被消费，重跑会执行同一条命令。

部署: 放到 PC 固定目录；WGUI_AUTO（工作目录）、WGUI_TITLE_RE（目标应用窗口正则）
可用环境变量覆盖或改默认值。应用专属动作不要加在这里——写进 apps/<软件>/ 动作库，
经 `script` 命令执行（驱动全局函数注入脚本命名空间；驱动另把自身注册为 sys.modules['wgdrv']，
import 进来的应用库用 `import wgdrv` 桥接——注入函数对 import 的模块不可见，这是 wgdrv
存在的原因）。
"""
import os
import subprocess
import sys
import time
import traceback
import shlex
import ctypes

AUTO = os.environ.get("WGUI_AUTO", r"C:\Users\master\ptauto")
try:
    os.makedirs(AUTO, exist_ok=True)
except OSError:
    pass  # 默认路径不可写时，后续 log() 会再抛，但 import 期先别炸


def _crash(msg):
    """日志设施就绪前的兜底：import/早期失败也留痕，pythonw 下不再无声死亡。"""
    try:
        with open(os.path.join(AUTO, "driver_import_error.txt"), "a", encoding="utf-8") as f:
            f.write("[%s] %s\n" % (time.strftime("%Y-%m-%d %H:%M:%S"), msg))
    except OSError:
        pass


try:
    ctypes.windll.user32.SetProcessDPIAware()
except Exception:
    pass

try:
    import mss
    import mss.tools
    import pyautogui

    pyautogui.FAILSAFE = False
    pyautogui.PAUSE = 0.25

    import pywinauto  # noqa: F401  —— script 注入环境可直接用 pywinauto 名字
    from pywinauto import Desktop
except Exception as e:
    _crash("import failed: %r（部署清单见 脚本用法.md：pywinauto pyautogui mss pywin32）" % e)
    raise

SHOTS = os.path.join(AUTO, "shots")
SCRIPTS = os.path.join(AUTO, "scripts")
os.makedirs(SHOTS, exist_ok=True)
os.makedirs(SCRIPTS, exist_ok=True)

TITLE_RE = os.environ.get("WGUI_TITLE_RE", ".*Packet Tracer.*")


# ---------------- infrastructure ----------------

def log(msg):
    path = os.path.join(AUTO, "gui.log")
    try:
        if os.path.exists(path) and os.path.getsize(path) > 5 * 1024 * 1024:
            try:
                os.replace(path, path + ".old")
            except OSError:
                pass
    except OSError:
        pass
    with open(path, "a", encoding="utf-8") as f:
        f.write("[%s] %s\n" % (time.strftime("%Y-%m-%d %H:%M:%S"), msg))


def _grab(mon=None):
    with mss.mss() as s:
        # 统一 monitors[0]（虚拟桌面联合框）：这台 PC 有幽灵残帧显示器，
        # monitors[1] 会随机命中它（公#22，Lab5 实付半小时）——ptlib.shot 已改 [0]，驱动跟上。
        m = s.monitors[mon] if mon else s.monitors[0]
        img = s.grab(m)
        return img, m


def _save_png(img, path):
    """原子写：先落临时名再替换，远程轮询不会拉到半张 PNG。"""
    tmp = path + ".tmp"
    mss.tools.to_png(img.rgb, img.size, output=tmp)
    os.replace(tmp, path)


def shot(name):
    name = name.replace("/", "_")          # 文件名消毒（error 分支早就有，shot 补齐）
    img, m = _grab()
    path = os.path.join(SHOTS, name + ".png")
    _save_png(img, path)
    log("shot %s -> %dx%d" % (name, m["width"], m["height"]))


def crop(name, x1, y1, x2, y2):
    """区域放大 2x 截图，用于开眼校准坐标。坐标按主屏像素。"""
    import io
    from PIL import Image
    img, m = _grab()
    png = mss.tools.to_png(img.rgb, img.size)
    im = Image.open(io.BytesIO(png))
    # 用户坐标是虚拟屏坐标（主屏左上=0,0）；图内局部坐标 = 虚拟坐标 - monitor 偏移。
    # 旧版写成 + 偏移，主屏 left=0 时侥幸正确，非零偏移显示器下系统性裁错（2026-11-05 修复）。
    ox = m["left"] or 0
    oy = m["top"] or 0
    box = (int(x1) - ox, int(y1) - oy, int(x2) - ox, int(y2) - oy)
    c = im.crop(box)
    c = c.resize((c.width * 2, c.height * 2), Image.LANCZOS)
    path = os.path.join(SHOTS, name.replace("/", "_") + ".png")
    tmp = path + ".tmp"
    c.save(tmp)
    os.replace(tmp, path)
    log("crop %s box=%s" % (name, box))


def target_window():
    d = Desktop(backend="uia")
    return d.window(title_re=TITLE_RE, found_index=0)


# 兼容旧名（Packet Tracer 时期）
pt_window = target_window


def focus():
    w = target_window()
    w.set_focus()
    time.sleep(1.0)
    log("focused target window")


def maximize():
    w = target_window()
    w.maximize()
    time.sleep(1.5)
    log("maximized target window")


def click(x, y):
    pyautogui.click(int(x), int(y))
    log("click %s,%s" % (x, y))


def dclick(x, y):
    pyautogui.doubleClick(int(x), int(y))
    log("dclick %s,%s" % (x, y))


def rclick(x, y):
    pyautogui.rightClick(int(x), int(y))
    log("rclick %s,%s" % (x, y))


def move(x, y):
    pyautogui.moveTo(int(x), int(y))
    time.sleep(1.0)
    log("move %s,%s" % (x, y))


def drag(x1, y1, x2, y2):
    pyautogui.moveTo(int(x1), int(y1))
    pyautogui.dragTo(int(x2), int(y2), duration=0.8, button="left")
    log("drag %s,%s -> %s,%s" % (x1, y1, x2, y2))


def press(key):
    pyautogui.press(key)
    time.sleep(0.6)
    log("press %s" % key)


def typewrite(text):
    if not text.isascii():
        log("WARN type 含非 ASCII 字符: pyautogui 只映射 ASCII 键位，映射外字符静默不按"
            "——中文/特殊符号一律走 paste(clip+^v)")
    pyautogui.write(text, interval=0.02)
    time.sleep(0.4)
    log("type %r" % text)


def typeln(text):
    typewrite(text)
    pyautogui.press("enter")
    time.sleep(0.5)
    log("typeln %r" % text)


# ---------------- v2 辅助（2026-10-14 MySQL 8.0 + Navicat Lite 实战沉淀） ----------------

def set_clip(text):
    """写剪贴板(CF_UNICODETEXT)。含 @ 等特殊字符/中文的输入一律走它。
    剪贴板被其他进程短暂占用是高频瞬态错误：OpenClipboard 带重试；
    CloseClipboard 放 finally——旧版异常后剪贴板保持打开，锁死到进程退出。"""
    try:
        import win32clipboard
    except ImportError:
        import pyperclip
        pyperclip.copy(text)
        log("clip %d chars" % len(text))
        return
    last = None
    for _ in range(5):
        try:
            win32clipboard.OpenClipboard()
            try:
                win32clipboard.EmptyClipboard()
                win32clipboard.SetClipboardText(text, win32clipboard.CF_UNICODETEXT)
            finally:
                win32clipboard.CloseClipboard()
            log("clip %d chars" % len(text))
            return
        except Exception as e:
            last = e
            time.sleep(0.3)
    raise RuntimeError("set_clip failed after retries: %r" % last)


def find_window(specs, timeout=40):
    """多后端多条件轮询找窗口。specs=[(backend, {match_kwargs}), ...],
    返回第一个存在的窗口。win32 快但看不到 MMC/现代应用内部; uia 慢但全。"""
    end = time.time() + timeout
    last_err = None
    while time.time() < end:
        for backend, crit in specs:
            try:
                w = Desktop(backend=backend).window(**crit)
                if w.exists():
                    return w
            except Exception as e:
                last_err = e
        time.sleep(2)
    raise RuntimeError("window not found %r, last=%r" % (specs, last_err))


def win_titles(backend="win32"):
    out = set()
    for w in Desktop(backend=backend).windows():
        try:
            out.add(w.window_text() or "")
        except Exception:
            pass
    return out


def wait_new_console(before, timeout=30):
    """spawn 前后标题差集定位新控制台。标记 title 尚未打入前无法按标记找。"""
    end = time.time() + timeout
    while time.time() < end:
        for backend in ("win32", "uia"):
            try:
                for w in Desktop(backend=backend).windows():
                    t = w.window_text() or ""
                    if t and t not in before:
                        return w
            except Exception:
                pass
        time.sleep(1)
    raise RuntimeError("new console not found")


def console(mark):
    """开一个提权继承的管理员(或普通)控制台并打标题标记, 之后按标记定位。
    打完回读标题验证标记真的打上了（慢机器/焦点被抢时 title 会打进别的窗口，
    打不上就重试，仍失败则 FAIL——旧版盲打后直接返回，标题可能永远对不上）。"""
    before = win_titles("win32") | win_titles("uia")
    subprocess.Popen("cmd.exe", creationflags=0x10)  # CREATE_NEW_CONSOLE
    w = wait_new_console(before)
    for _ in range(3):
        time.sleep(1.5)
        w.set_focus()
        pyautogui.write("title " + mark, interval=0.02)
        pyautogui.press("enter")
        time.sleep(1.5)
        try:
            if mark in (w.window_text() or ""):
                break
        except Exception:
            pass
    else:
        raise RuntimeError("console %r: 标题标记未打上（重试 3 次后窗口标题仍不含标记）" % mark)
    log("console %s opened" % mark)
    return w


def raise_topmost(title_sub):
    """把标题含 title_sub 的窗口顶到 z 序顶层再聚焦。
    坐标点击前必调——否则点击落在叠在上面的别的窗口里。
    同名窗口多个时优先可见的（隐藏/历史同名窗口顶上去毫无意义）。"""
    import win32gui
    import win32con
    matches = [h for h, t in
               [(w.handle, w.window_text() or "") for w in Desktop(backend="win32").windows()]
               if title_sub in t]
    if not matches:
        raise RuntimeError("raise_topmost: no window %r" % title_sub)
    visible = [h for h in matches if win32gui.IsWindowVisible(h)]
    h = (visible or matches)[0]
    win32gui.SetWindowPos(h, win32con.HWND_TOPMOST, 0, 0, 0, 0,
                          win32con.SWP_NOMOVE | win32con.SWP_NOSIZE)
    win32gui.SetWindowPos(h, win32con.HWND_NOTOPMOST, 0, 0, 0, 0,
                          win32con.SWP_NOMOVE | win32con.SWP_NOSIZE | win32con.SWP_SHOWWINDOW)
    time.sleep(0.5)
    Desktop(backend="win32").window(handle=h).set_focus()
    time.sleep(0.8)
    log("raised %r" % title_sub)


def targeted_find(win, control_type, name_sub=None, exact=False):
    """定向 UIA 查询: 只遍历指定 control_type, 秒级返回。
    千万别对大窗口做全树遍历/print_control_identifiers(大列表要走几分钟,
    还会占住驱动实例让远程 /run 被 IgnoreNew 静默跳过)。
    返回元素后用 el.click_input() 点中心——UIA 元素中心是唯一稳定锚点,
    手算像素坐标会因工具栏布局漂移而点空(踩坑清单 公#16)。"""
    for el in win.descendants(control_type=control_type):
        n = ""
        try:
            n = el.element_info.name or ""
        except Exception:
            pass
        if name_sub is None:
            return el
        if (n == name_sub) if exact else (name_sub in n):
            return el
    return None


def paste_at(x, y, text, shotname=None):
    """坐标点输入框 -> 全选 -> 剪贴板粘贴。用于对话框/自绘编辑框。
    注意: 全程不碰任何窗口句柄 —— 模态对话框存在时对父窗口 set_focus
    会把键盘焦点从对话框抢走, ^v 落空(踩坑清单 公#17)。"""
    click(x, y)
    time.sleep(1.0)
    set_clip(text)
    pyautogui.hotkey("ctrl", "a")
    time.sleep(0.4)
    pyautogui.hotkey("ctrl", "v")
    time.sleep(1.5)
    if shotname:
        shot(shotname)


def atomic_menu(rx, ry, ix, iy, shotname=None):
    """同一命令内: 右键(rx,ry) -> 截图取证 -> 左键点菜单项(ix,iy)。
    上下文菜单不保证跨命令保留(会被周期弹窗/激活变化关掉, 踩坑清单 公#18)。"""
    rclick(rx, ry)
    time.sleep(2)
    shot("dbg_menu_open")
    click(ix, iy)
    time.sleep(2.5)
    shot(shotname or "menu_result")


def svc_state(service="MySQL80"):
    """平行通道: sc query 读服务真状态。net start 报 1053 不代表失败——
    SCM 默认等 30s, 慢服务(如 InnoDB 初始化)会在后台继续启动到 RUNNING。"""
    p = subprocess.run(["sc", "query", service], capture_output=True,
                       creationflags=0x08000000)
    out = p.stdout.decode("gbk", errors="ignore")
    if "STOPPED" in out:
        return "STOPPED"
    if "RUNNING" in out:
        return "RUNNING"
    return "UNKNOWN"


def svcwait(state, service="MySQL80", timeout=120):
    end = time.time() + timeout
    while time.time() < end:
        st = svc_state(service)
        if st == state:
            log("svc %s = %s" % (service, state))
            return True
        time.sleep(2)
    raise RuntimeError("svc %s not %s, now=%s" % (service, state, svc_state(service)))


def nags_click(nag_xy_list):
    """点掉各已知弹窗按钮坐标。
    注意: 没有弹窗时这组点击会落在空白/画布上——并非绝对"无副作用"（可能改变
    选中态/焦点）。仅用于"已知弹窗会周期出现"的场景（踩坑清单 公#19），
    与 popup 检测配套的清理见各应用库的 kill_popups_v2（点了之后有复核）。"""
    for nx, ny in nag_xy_list:
        click(nx, ny)
        time.sleep(1)


def findtpl(tpl, out):
    """模板找图（需要 opencv 提供 confidence）。结果写 <AUTO>/tpl_result.txt，
    out 传 "-" 时不落盘只回显。"""
    path = os.path.join(AUTO, "tpl", tpl + ".png")
    box = pyautogui.locateOnScreen(path, confidence=0.80, grayscale=True)
    log("findtpl %s -> %s" % (tpl, box))
    if out != "-":
        with open(os.path.join(AUTO, "tpl_result.txt"), "w") as f:
            f.write(str(box))
    if box is None:
        raise RuntimeError("template not found: %s" % tpl)


def run_script(fname):
    """执行 <AUTO>/scripts/<fname>，驱动全局（click/shot/press/log/…）注入脚本命名空间。
    另把驱动自身注册为 sys.modules['wgdrv']：import 进来的应用库（navlib/sqllab 等）
    看不到脚本命名空间的注入函数（模块有自己的 globals），库内 `import wgdrv` 桥接。"""
    path = os.path.join(SCRIPTS, fname)
    with open(path, "r", encoding="utf-8-sig") as f:   # utf-8-sig 容忍 BOM
        code = f.read()
    sys.modules.setdefault("wgdrv", sys.modules[__name__])
    g = dict(globals())
    g["__file__"] = path
    g["__name__"] = "__main__"
    exec(compile(code, path, "exec"), g)
    log("script %s finished" % fname)


def cmd_winlist():
    with open(os.path.join(AUTO, "winlist.txt"), "w", encoding="utf-8") as f:
        for w in Desktop(backend="uia").windows():
            try:
                f.write("%r | class=%s\n" % (w.window_text() or "", w.element_info.class_name))
            except Exception:
                pass
    log("winlist dumped")


CMD = {
    "shot": lambda *a: shot(a[0]),
    "crop": lambda *a: crop(a[0], *a[1:]),
    "click": lambda *a: click(*a),
    "dclick": lambda *a: dclick(*a),
    "rclick": lambda *a: rclick(*a),
    "move": lambda *a: move(*a),
    "drag": lambda *a: drag(*a),
    "press": lambda *a: press(a[0]),
    "type": lambda *a: typewrite(" ".join(a)),
    "typeln": lambda *a: typeln(" ".join(a)),
    "focus": lambda *a: focus(),
    "maximize": lambda *a: maximize(),
    "findtpl": lambda *a: findtpl(*a),
    "script": lambda *a: run_script(a[0]),
    "winlist": lambda *a: cmd_winlist(),
    # --- v2 ---
    "clip": lambda *a: set_clip(" ".join(a)),
    "paste": lambda *a: paste_at(a[0], a[1], a[2], a[3] if len(a) > 3 else None),
    "console": lambda *a: console(a[0]),
    "raise": lambda *a: raise_topmost(" ".join(a)),
    "menu": lambda *a: atomic_menu(a[0], a[1], a[2], a[3],
                                   a[4] if len(a) > 4 else None),
    "svcwait": lambda *a: svcwait(a[0], a[1] if len(a) > 1 else "MySQL80",
                                  int(a[2]) if len(a) > 2 else 120),
}

# 参数个数校验（旧版 lambda *a 一律吞参：paste 多打一个词会把第 4 个词当截图名，
# click 多一个参数 TypeError——静默错行为和裸崩各占一半，这里统一前置校验）
ARITY = {
    "shot": (1, 1), "crop": (5, 5), "click": (2, 2), "dclick": (2, 2),
    "rclick": (2, 2), "move": (2, 2), "drag": (4, 4), "press": (1, 1),
    "type": (1, 99), "typeln": (1, 99), "focus": (0, 0), "maximize": (0, 0),
    "findtpl": (2, 2), "script": (1, 1), "winlist": (0, 0),
    "clip": (1, 99), "paste": (3, 4), "console": (1, 1), "raise": (1, 99),
    "menu": (4, 5), "svcwait": (1, 3),
}

_MUTEX_NAME = "Global\\WGuiDriverSingleInstance"


def _acquire_mutex():
    """返回 (handle, is_busy)。上个实例没退时 is_busy=True——IgnoreNew 的可观测版。"""
    h = ctypes.windll.kernel32.CreateMutexW(None, False, _MUTEX_NAME)
    ERROR_ALREADY_EXISTS = 183
    return h, ctypes.windll.kernel32.GetLastError() == ERROR_ALREADY_EXISTS


if __name__ == "__main__":
    try:
        _mutex, busy = _acquire_mutex()
    except Exception:
        busy = False
    if busy:
        try:
            log("FAIL busy: 上一个驱动实例还在运行（本次有日志，不再 IgnoreNew 式静默跳过）。"
                "恢复: taskkill /F /IM pythonw.exe 后重新触发；next_cmd.txt 未消费，重跑执行同一条命令")
        except Exception:
            pass
        sys.exit(2)

    try:
        if len(sys.argv) > 1:
            args = sys.argv[1:]          # argv 已是分好的词，不再二次 shlex
        else:
            p = os.path.join(AUTO, "next_cmd.txt")
            with open(p, encoding="utf-8-sig") as f:
                raw = f.read()
            try:
                os.remove(p)             # 读后即删：手工 /run 不再重放旧命令
            except OSError:
                pass
            args = shlex.split(raw)
    except Exception as e:
        try:
            log("FAIL parse: %r —— next_cmd.txt 缺失/为空/引号不平衡都会走到这里"
                "（部署验证请用 pt.py send，别裸 /run）" % e)
        except Exception:
            pass
        sys.exit(1)

    if not args:
        try:
            log("FAIL parse: next_cmd.txt 为空")
        except Exception:
            pass
        sys.exit(1)

    cmd = args[0]
    if cmd not in CMD:
        log("FAIL unknown cmd %r (可用: %s)" % (cmd, " ".join(sorted(CMD))))
        sys.exit(1)
    lo, hi = ARITY.get(cmd, (0, 99))
    if not (lo <= len(args) - 1 <= hi):
        log("FAIL arity %s: got %d args, expect %d..%d" % (cmd, len(args) - 1, lo, hi))
        sys.exit(1)

    log("START %s %s" % (cmd, " ".join(str(x) for x in args[1:])[:120]))
    try:
        # 任何动作前先复位鼠标键：一次失败的 drag 会让左键保持按下，
        # 之后所有 click 都被当成 drag（真实事故）。
        pyautogui.mouseUp(button="left")
        CMD[cmd](*args[1:])
        log("DONE %s" % cmd)
    except Exception as e:
        log("FAIL %s : %r" % (cmd, e))
        log(traceback.format_exc())
        try:
            shot("error_%s_%s" % (cmd.replace("/", "_"), time.strftime("%H%M%S")))
        except Exception:
            pass
        sys.exit(1)
