# -*- coding: utf-8 -*-
"""navlib.py — Navicat Premium Lite 17 动作库（经驱动 script 注入使用）

部署: apps/navicat/ 整个目录推到 PC 的 <AUTO>/apps/navicat/
用法(任务脚本里):
    sys.path.insert(0, AUTO + r"\\apps\\navicat")
    import navlib
    navlib.open_conn()                  # 打开已保存的连接（默认首行；传 row=(x,y) 指定行）
    navlib.create_db("gradem")         # 图形界面新建数据库
    navlib.delete_db((90, 174))        # 图形界面删除数据库(勾永久删除)

坐标基准: 1920x1080、窗口最大化、Navicat Premium Lite 17.3.11 简体中文。
换分辨率/语言/版本先跑 navlib.probe() 开眼重校。
依赖驱动 v2 辅助: raise_topmost/paste_at/atomic_menu/nags_click——经下方 wgdrv 桥接入。
"""
import time

# ---- 驱动原语桥（2026-11-05 P0 修复）----
# 驱动注入的函数只存在于"脚本命名空间"，import 进来的模块有自己的 globals，看不见注入
# ——旧版全库函数因此必炸 NameError。新版驱动 run_script 已把自身注册为
# sys.modules["wgdrv"]，这里显式导入并把驱动全局铺平进本模块命名空间。
try:
    import wgdrv as _drv
except ImportError:
    raise ImportError(
        "navlib 依赖 wgdrv 桥：请用新版 win_gui_driver 的 script 通道运行任务脚本"
        "（驱动自注册 sys.modules['wgdrv']），不能在普通 python 里直接 import navlib")

globals().update({k: v for k, v in vars(_drv).items()
                  if not k.startswith("_") and k not in globals()})

# ---- 已校准坐标(最大化窗口) ----
NAG_OK      = (958, 548)     # "订阅会话已过期"小提示 的 确定
LOGIN_CLOSE = (1324, 311)    # "注册/登录"大框 右上角 X
LOGIN_ID    = (1150, 467)    # Navicat ID(电子邮箱)输入框
LOGIN_PW    = (1150, 498)    # 密码输入框
LOGIN_BTN   = (1150, 562)    # 登录按钮
LOGIN_DONE  = (1252, 693)    # 登录成功后的 确定
UPDATE_SKIP = (798, 616)     # "有新的版本可用" 的 跳过此版本
CONN_ROW    = (70, 155)      # 左树第一个连接项(我的连接下方)
DB_ROW0_Y   = 174            # 第一个数据库行 y(连接展开后)
DB_ROW_H    = 20             # 数据库行高(字母序排列)
DB_ROW_X    = 90
NEWDB_NAME  = (1040, 402)    # 新建数据库对话框 数据库名称输入框
NEWDB_OK    = (1056, 686)    # 新建数据库对话框 确定
DEL_CHECK   = (878, 527)     # 删除确认框 "我了解此操作具永久性"复选框
DEL_OK      = (917, 563)     # 删除确认框 删除(勾选后才可点)
DEL_CANCEL  = (999, 563)     # 删除确认框 取消

NAGS = [NAG_OK, LOGIN_CLOSE, UPDATE_SKIP]   # 已知弹窗按钮

# 上下文菜单项相对"右键点"的偏移（Windows 上下文菜单跟随光标弹出——
# 旧版 delete_db 用绝对坐标点菜单项，右键非首行时菜单整体下移、绝对坐标点中另一项
# 或点空关菜单）。以 CONN_ROW(70,155) + 新建数据库项(135,319) 校准得出。
# 注意：目标行贴近屏幕底边时菜单可能上翻(eNSP N15 同款)，此时偏移失效——
# 点菜单项前先看 atomic_menu 自动存的 dbg_menu_open 截图核对菜单位置。
MENU_OFFSET = (65, 164)


def _front():
    raise_topmost("Navicat")
    time.sleep(1.0)


def probe():
    """开眼自检: 清弹窗 -> 前置最大化 -> 截图。新 PC/新分辨率先跑这个重校坐标。
    注意：临时把驱动 TITLE_RE 指向 Navicat 再 maximize（旧版直接 maximize 走默认
    TITLE_RE=Packet Tracer，会去最大化 PT 而不是 Navicat），用完恢复。"""
    nags_click(NAGS)
    _front()
    old = getattr(_drv, "TITLE_RE", None)
    try:
        _drv.TITLE_RE = "Navicat"
        maximize()
    except Exception:
        pass
    finally:
        if old is not None:
            _drv.TITLE_RE = old
    time.sleep(2)
    nags_click(NAGS)
    shot("navicat_probe")


def db_row_y(index):
    """第 index 个(0 起,字母序)数据库行的 y 坐标。行数以截图为准。"""
    return DB_ROW0_Y + index * DB_ROW_H


def dismiss_nags(rounds=2):
    """清周期弹窗(订阅过期/登录框/更新提示), 每轮间隔给弹窗留出现时间。"""
    for _ in range(rounds):
        nags_click(NAGS)
        time.sleep(1.5)


def login(email, password):
    """Navicat ID 登录(免费版不登录不给用; 会话过期也会引到这个流程)。
    凭证找用户要, 别硬绕。注意登录后周期弹窗仍会出现（navicat 踩坑 #2），
    dismiss_nags/nags_click 循环仍需常开。"""
    dismiss_nags()
    click(*LOGIN_CLOSE)                 # 关掉可能开着的登录大框, 重新走一遍确定入口
    time.sleep(1)
    nags_click([NAG_OK])
    time.sleep(1.5)
    paste_at(*LOGIN_ID, email)
    paste_at(*LOGIN_PW, password)
    click(*LOGIN_BTN)
    time.sleep(10)                      # 网络往返
    shot("navicat_after_login")
    click(*LOGIN_DONE)                  # 成功页的 确定(失败页该坐标是空白, 无副作用)
    time.sleep(1.5)
    nags_click(NAGS)


def open_conn(row=CONN_ROW, expect_dbs=None):
    """双击打开左树连接(树展开)。
    expect_dbs 参数保留但未实现自动校验（状态栏"N 数据库"计数需截图判读），
    打开后以 navicat_conn_opened 截图为准。"""
    dismiss_nags()
    _front()
    dclick(*row)
    time.sleep(5)
    shot("navicat_conn_opened")


def create_db(name, conn_row=CONN_ROW):
    """图形界面新建数据库: 右键连接 -> 新建数据库... -> 填名 -> 确定。
    原子性: 右键和点菜单项必须同一命令内(atomic_menu), 对话框可跨命令保留。"""
    dismiss_nags()
    _front()
    atomic_menu(conn_row[0], conn_row[1],
                conn_row[0] + MENU_OFFSET[0], conn_row[1] + MENU_OFFSET[1],
                "nav_newdb_menu")       # 新建数据库...
    time.sleep(1.5)
    paste_at(*NEWDB_NAME, name, "nav_newdb_typed")
    click(*NEWDB_OK)
    time.sleep(3)
    shot("navicat_db_created")


def delete_db(row_xy, shot_prefix="nav_del"):
    """图形界面删除数据库: 右键库 -> 删除数据库 -> 勾'永久删除' -> 删除。
    row_xy 用 db_row_y(index) 按字母序算, 或截图确认后传入。
    菜单项按右键点+MENU_OFFSET 相对定位（菜单跟随光标弹出）；row_xy 贴近屏幕
    底边时菜单可能上翻，先看 <shot_prefix>_menu 截图核对再确认后续步骤。"""
    dismiss_nags()
    _front()
    atomic_menu(row_xy[0], row_xy[1],
                row_xy[0] + MENU_OFFSET[0], row_xy[1] + MENU_OFFSET[1],
                shot_prefix + "_menu")  # 删除数据库
    time.sleep(1.5)
    click(*DEL_CHECK)                   # 勾"我了解此操作具永久性", 删除按钮才激活
    time.sleep(1)
    shot(shot_prefix + "_confirm")
    click(*DEL_OK)
    time.sleep(3)
    shot(shot_prefix + "_done")


def view_db(row_xy):
    """点选某数据库行: 左侧选中 + 右侧属性面板(字符集/排序规则)即'查看状态'。"""
    dismiss_nags()
    _front()
    click(*row_xy)
    time.sleep(2)
    shot("navicat_db_status")
