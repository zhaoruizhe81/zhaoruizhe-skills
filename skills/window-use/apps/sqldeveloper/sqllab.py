"""sqllab — SQL Developer(Oracle)动作库。2026-10-19 实验1实战沉淀,单轮实测。
驱动 script 注入环境用:
    import sys; sys.path.insert(0, AUTO + r"\\apps\\sqldeveloper")
    import sqllab as sq
注入环境已提供: click/dclick/rclick/press/shot/crop/set_clip/paste_at/raise_topmost/log
以及 pyautogui——经下方 wgdrv 桥接入（注入函数对 import 的模块不可见，这是桥存在的原因）。
全部函数默认操作最大化主窗口(1920x1080 实测);sqllab 无 probe 自检,
换分辨率/换机需重新校准本表坐标与 坐标与配方.md 全表。
"""
import time

# ---- 驱动原语桥（2026-11-05 P0 修复，同 navlib）----
try:
    import wgdrv as _drv
except ImportError:
    raise ImportError(
        "sqllab 依赖 wgdrv 桥：请用新版 win_gui_driver 的 script 通道运行任务脚本"
        "（驱动自注册 sys.modules['wgdrv']），不能在普通 python 里直接 import sqllab")

globals().update({k: v for k, v in vars(_drv).items()
                  if not k.startswith("_") and k not in globals()})

# —— 实测坐标(详见 坐标与配方.md)——
C = dict(
    conn_plus=(17, 121),            # 连接面板 + 新建连接
    ws_tab_y=99,                    # 顶层文档标签条 y
    run_stmt=(359, 122),            # 运行语句(查询结果网格)
    run_script=(382, 122),          # 运行脚本(F5,脚本输出)
    tbl_tab_data=(394, 121),        # 表定义:数据页签
    grid_edit=(370, 143), grid_undo=(395, 143), grid_add=(407, 143),
    grid_del=(437, 143), grid_commit=(458, 143), grid_rollback=(490, 143),
    ws_paste=(700, 250),            # 工作表粘贴点
    row1_y=186, row_h=21,           # 网格第1行 y、行高
    dlg_no=(1026, 557), dlg_yes=(926, 557),
)


def row_y(n):
    """数据页签网格第 n 行的 y 坐标(1 起)。加行后行数变化,重算。"""
    return C["row1_y"] + C["row_h"] * (n - 1)


def fill_connection(name, user, password, service="FREEPDB1"):
    """在新建连接对话框里填全部字段并勾选保存口令、选服务名。"""
    paste_at(1063, 317, name)
    paste_at(1063, 451, user)
    paste_at(1063, 479, password)
    click(1239, 479)
    click(860, 647)
    time.sleep(1)
    paste_at(1145, 647, service)
    time.sleep(1)


def test_save_connect(wait=15):
    """连接对话框:测试→保存→连接。调用前先 shot 确认'状态: 成功'。"""
    click(1125, 739)
    time.sleep(6)
    shot("conn_test")
    click(923, 739)
    time.sleep(4)
    click(1222, 739)
    time.sleep(wait)
    shot("conn_done")


def paste_sql(sql, paste_xy=None, shot_name=None):
    """把 SQL 文本粘进当前活动的工作表。调用方必须先确认活动标签是工作表(踩坑8)。
    ⚠ paste_at 内部先 Ctrl+A 全选再粘（公#17 同源）——对同一工作表二次调用会
    整体覆盖前一次内容，无法追加；要追加请换新工作表标签或先手动清空。"""
    x, y = paste_xy or C["ws_paste"]
    paste_at(x, y, sql)
    time.sleep(2)
    if shot_name:
        shot(shot_name)


def run_script(wait=10, shot_name="ws_run"):
    """点运行脚本(F5),等执行,截图。执行秒数按脚本量给足。"""
    click(*C["run_script"])
    time.sleep(wait)
    shot(shot_name)


def run_stmt(wait=10, shot_name="ws_stmt"):
    """Ctrl+Enter 运行当前语句,出查询结果网格(比点绿三角稳)。"""
    import pyautogui
    pyautogui.hotkey("ctrl", "enter")
    time.sleep(wait)
    shot(shot_name)


def grid_add_row(values, row_n, shot_prefix="gridadd", commit=True):
    """数据页签:添加一行并按 values 逐列填值(从第1列起),提交。
    row_n = 新行的行号(添加后 shot 确认再调本函数,或先调 grid_add_empty)。"""
    click(*C["grid_add"])
    time.sleep(3)
    _fill_row(values, row_n, shot_prefix)
    if commit:
        grid_commit_row(shot_prefix + "_commit")


def grid_add_empty(shot_name="grid_row"):
    """只加一个空行,返回后必须 shot 确认新行行号再 _fill_row。"""
    click(*C["grid_add"])
    time.sleep(3)
    shot(shot_name)


def _fill_row(values, row_n, shot_prefix):
    import pyautogui
    xs = [460, 560, 660]  # 第1/2/3列实测;更多列先 crop 校准
    if len(values) > len(xs):
        raise ValueError("_fill_row 最多支持 %d 列（当前 %d 个值）——更多列先 crop 校准 xs"
                         % (len(xs), len(values)))
    for i, v in enumerate(values):
        click(xs[i], row_y(row_n))
        time.sleep(1)
        set_clip(str(v))
        pyautogui.hotkey("ctrl", "v")
        time.sleep(1)
    shot(shot_prefix + "_typed")


def grid_commit_row(shot_name="grid_commit"):
    click(*C["grid_commit"])
    time.sleep(6)
    shot(shot_name)


def grid_delete_row(row_n, shot_prefix="griddel"):
    """选中第 row_n 行行头→删除→提交→截图(行头 x=387)。"""
    click(387, row_y(row_n))
    time.sleep(2)
    shot(shot_prefix + "_sel")
    click(*C["grid_del"])
    time.sleep(3)
    grid_commit_row(shot_prefix + "_commit")


def grid_cancel_edits(shot_name="grid_cancel"):
    """回滚数据页签未提交编辑;弹'是否保存更改'时点否。"""
    click(*C["grid_undo"])
    time.sleep(3)
    click(*C["dlg_no"])
    time.sleep(3)
    shot(shot_name)


def plus_console(title, connect_str, statements, each_wait=4, shot_name="sqlplus"):
    """开控制台跑 SQL*Plus:启动 cmd(驱动桌面会话,窗口可见)、最大化、
    登录、逐条粘贴执行 statements,最后全屏截图。
    控制台窗口用轮询等待（最多 15s）——cmd 创建慢于固定 sleep 时旧版直接
    RuntimeError 且现场已污染；等待失败raise前现场未动。"""
    import subprocess
    import pyautogui
    subprocess.Popen('cmd /k title %s' % title, shell=True)
    raised = False
    deadline = time.time() + 15
    while time.time() < deadline:
        try:
            raise_topmost(title)
            raised = True
            break
        except RuntimeError:
            time.sleep(1)
    if not raised:
        raise RuntimeError("控制台窗口 %r 15s 内未出现（cmd 创建失败或被策略拦截）" % title)
    time.sleep(1)
    pyautogui.hotkey("win", "up")
    time.sleep(2)
    click(900, 400)
    time.sleep(1)
    set_clip(connect_str)
    pyautogui.hotkey("ctrl", "v")
    pyautogui.press("enter")
    time.sleep(8)
    for s in statements:
        set_clip(s)
        pyautogui.hotkey("ctrl", "v")
        pyautogui.press("enter")
        time.sleep(each_wait)
    shot(shot_name)
