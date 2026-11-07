# -*- coding: utf-8 -*-
"""acclib — Access 2016 自动化动作库
沉淀自 2026-10-26 花店销售系统 / 2026-11-03 图书销售系统（第13/14章实验）两次实战。
配套文档：apps/access/踩坑.md（A1-A14）、apps/access/坐标与配方.md。

用法（桥端驱动 script 通道）：
    import sys; sys.path.insert(0, AUTO + r"\\apps\\access")
    import acclib as acc
    app = acc.boot(DB)
    ...
shot()/log() 由驱动注入到脚本全局，库函数一律通过参数传入（不隐式依赖）。
改完本文件必须 py_compile，并同步回 PC 的 AUTO/apps/access/。
"""
import os
import subprocess
import time

import win32com.client
import win32gui

# ---- 对象类型常量 ----
AC_TABLE = 0
AC_QUERY = 1
AC_FORM = 2
AC_NORMAL = 0
AC_DESIGN = 1
AC_SAVEYES = 1
AC_SAVENO = 2

# ---- 控件类型（实测校准，见踩坑.md A10；122=ToggleButton 不是图表框！）----
AC_LABEL = 100
AC_RECTANGLE = 101  # 2026-11-05 修正：旧版误写 108（那是 acBoundObjectFrame）
AC_LINE = 102
AC_IMAGE = 103
AC_BUTTON = 104
AC_OPTIONBUTTON = 105
AC_CHECKBOX = 106
AC_OPTIONGROUP = 107
AC_BOUNDOBJECTFRAME = 108
AC_TEXTBOX = 109
AC_LISTBOX = 110
AC_COMBO = 111
AC_SUBFORM = 112
AC_OBJECTFRAME = 114  # 图表/OLE 对象框
AC_TOGGLE = 122

DAO_PROGID = "DAO.DBEngine.120"


def dyn(c):
    """统一动态分发。gen_py 类型包装三连坑（A13）：Module 丢 InsertCode、
    图表框被错型 _ToggleButton、frm.Section() MEMBERNOTFOUND——全部绕开。
    兜底必须也走 dynamic：普通 Dispatch(c) 会经类型库重建 gen_py 包装，
    恰好复活本函数要绕开的东西（2026-11-05 修正假安全网）。"""
    import win32com.client.dynamic
    return win32com.client.dynamic.Dispatch(c._oleobj_ if hasattr(c, "_oleobj_") else c)


# ---------------- 会话管理（A1：每脚本全新会话，绝不跨脚本附着） ----------------

def kill_access():
    subprocess.call(["taskkill", "/F", "/IM", "MSACCESS.EXE"],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(1.5)


def boot(db, exclusive=False, warnings=False):
    """自举：杀残留 → DispatchEx → 打开库。脚本结束时 pythonw 退出，Access 随之消亡。"""
    kill_access()
    app = win32com.client.DispatchEx("Access.Application")
    app.Visible = True
    app.OpenCurrentDatabase(db, exclusive)
    app.DoCmd.SetWarnings(warnings)
    time.sleep(1.0)
    return app


def focus():
    """最大化 + 置前（截图前必调）。找不到可见 Access 窗口时 raise 而非静默 no-op
    （旧版回调缺 return True 枚举停在第一个窗口，Access 非顶层时静默跳过——
    随后截图拍到别的窗口还以为拍到了 Access）。"""
    hwnd = [None]

    def cb(h, _):
        if "Access" in win32gui.GetWindowText(h) and win32gui.IsWindowVisible(h):
            hwnd[0] = h
        return True  # 缺这行 EnumWindows 会在第一个窗口后中止枚举

    win32gui.EnumWindows(cb, None)
    if not hwnd[0]:
        raise RuntimeError("focus: 没找到可见的 Access 窗口（先 boot()）")
    win32gui.ShowWindow(hwnd[0], 3)
    try:
        win32gui.SetForegroundWindow(hwnd[0])
    except Exception:
        pass
    time.sleep(1.2)


def trust(path_dir, key="LocAccAuto"):
    """A9 信任位置（免黄色安全条）。subprocess list 传参，尾随反斜杠安全。"""
    subprocess.call(
        ["reg", "add",
         r"HKCU\Software\Microsoft\Office\16.0\Access\Security\Trusted Locations\%s" % key,
         "/v", "Path", "/t", "REG_SZ", "/d", path_dir.rstrip("\\") + "\\", "/f"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


# ---------------- DAO（A8：建库/建表/关系/数据全程零 GUI） ----------------

def dao(db):
    return win32com.client.Dispatch(DAO_PROGID).OpenDatabase(db)


def mkfield(td, name, typ, size=None):
    f = td.CreateField(name, typ)
    if size is not None:
        f.Size = size
    td.Fields.Append(f)


def mktable(db, name, fields, pk):
    """fields: [(字段名, DAO类型, size或None)]；typ: 3=Integer 4=Long 5=Currency
    8=Date 10=Text(要size) 11=OLE 12=Memo"""
    td = db.CreateTableDef(name)
    for fn, ft, fs in fields:
        mkfield(td, fn, ft, fs)
    idx = td.CreateIndex("PrimaryKey")
    idx.Primary = True
    idx.Fields.Append(idx.CreateField(pk))
    td.Indexes.Append(idx)
    db.TableDefs.Append(td)
    db.TableDefs.Refresh()


def mkrel(db, name, t1, t2, field):
    """t1.字段 → t2.字段 参照完整性（A8：Attributes=0）。"""
    rel = db.CreateRelation(name)
    rel.Table = t1
    rel.ForeignTable = t2
    rel.Attributes = 0
    rf = rel.CreateField(field)
    rf.ForeignName = field
    rel.Fields.Append(rf)
    db.Relations.Append(rel)


def ins(db, tbl, cols, rows):
    rs = db.OpenRecordset(tbl)
    for row in rows:
        rs.AddNew()
        for c, v in zip(cols, row):
            if v is not None:
                rs.Fields(c).Value = v
        rs.Update()
    rs.Close()


def set_colwidth(db, tbl, field, twips):
    """A7：日期列 #### 的预防（Append 前字段不存在属性会静默失败，包 try）。"""
    try:
        f = db.TableDefs(tbl).Fields(field)
        f.Properties.Append(f.CreateProperty("ColumnWidth", 3, twips))
    except Exception:
        pass


def create_query(db, name, sql):
    """幂等建查询（存在先删）。"""
    try:
        db.QueryDefs(name).Delete()
        db.QueryDefs.Refresh()
    except Exception:
        pass
    db.CreateQueryDef(name, sql)
    db.QueryDefs.Refresh()


# ---------------- 窗体 ----------------

def del_object(app, objtype, name):
    try:
        app.DoCmd.Close(objtype, name, AC_SAVENO)
    except Exception:
        pass
    try:
        app.DoCmd.DeleteObject(objtype, name)
    except Exception:
        pass


def save_as(app, tmp_name, final_name):
    """新建窗体落盘（花店实战验证模式，无另存为对话框）。"""
    app.DoCmd.Close(AC_FORM, tmp_name, AC_SAVEYES)
    app.DoCmd.Rename(final_name, AC_FORM, tmp_name)


def attach_headers(app, form_name, field_names, col_w=1600):
    """A12 列头空白修复：按 ControlSource 找 TextBox，逐个挂附加标签。
    返回 {字段: 控件名} 映射。须在 OpenForm(窗体, AC_DESIGN) 后调用。"""
    frm = dyn(app.Forms(form_name))
    cs = frm.Controls
    mapping = {}
    for i in range(cs.Count):
        c = dyn(cs.Item(i))
        try:
            if int(c.ControlType) == AC_TEXTBOX:
                src = str(c.ControlSource)
                if src in field_names:
                    mapping[src] = str(c.Name)
        except Exception:
            continue
    for i, f in enumerate(field_names):
        if f in mapping:
            lbl = dyn(app.CreateControl(form_name, AC_LABEL, 0, mapping[f], "",
                                        i * col_w, 0, col_w - 100, 340))
            lbl.Caption = f
    return mapping


def _has_proc(mod, name):
    """模块里是否已存在名为 name 的过程（add_events 幂等守卫用）。"""
    try:
        n = mod.CountOfLines
    except Exception:
        return False
    pat = "Sub %s(" % name
    for ln in range(1, n + 1):
        try:
            if pat in mod.Lines(ln, 1):
                return True
        except Exception:
            continue
    return False


def add_events(app, form_name, btn_acts, shot=None):
    """给命令按钮挂 [Event Procedure]（A13：Module 丢 InsertCode → InsertLines 兜底）。
    幂等（2026-11-05 修复）：已存在的 _Click 过程跳过——重跑/重试时旧版会重复注入
    触发 VBA "Ambiguous name" 全挂；兜底 InsertLines 改为追加到模块末尾——插第 1 行
    会把 Option Compare Database 顶到过程之后（VBA 要求 Option 在最前）→ 编译错误。
    btn_acts: [(按钮控件名, VBA事件体一行, 如 'DoCmd.GoToRecord , , acNext')]"""
    frm = dyn(app.Forms(form_name))
    mod = dyn(frm.Module)
    for nm, act in btn_acts:
        if _has_proc(mod, "%s_Click" % nm):
            continue
        code = ("Private Sub %s_Click()\r\n  On Error Resume Next\r\n  %s\r\nEnd Sub\r\n"
                % (nm, act))
        try:
            mod.InsertCode(code)
        except Exception:
            mod.InsertLines(mod.CountOfLines + 1, code)
    for nm, _ in btn_acts:
        dyn(frm.Controls(nm)).OnClick = "[Event Procedure]"


def find_control(app, form_name, control_type, source=None):
    """按类型(+ControlSource)查找控件，返回 dyn 句柄（自动名控件 Text12 之类找不着名时用）。"""
    frm = dyn(app.Forms(form_name))
    cs = frm.Controls
    for i in range(cs.Count):
        c = dyn(cs.Item(i))
        try:
            if int(c.ControlType) == control_type and (source is None
                                                       or str(c.ControlSource) == source):
                return c
        except Exception:
            continue
    return None


# ---------------- VBE 注入（A11/A13：要用 Access 原生常量/DeleteControl 时） ----------------

def run_vba(app, code, func_name):
    """注入标准模块函数并运行；重复注入前自动清旧 Module*。返回函数返回值。"""
    vbe = dyn(app.VBE)
    comps = vbe.ActiveVBProject.VBComponents
    for i in range(comps.Count, 0, -1):
        cp = dyn(comps.Item(i))
        try:
            if int(cp.Type) == 1 and str(cp.Name).lower().startswith("module"):
                comps.Remove(cp)
        except Exception:
            continue
    comp = dyn(comps.Add(1))
    dyn(comp.CodeModule).AddFromString(code)
    return app.Run(func_name)


# ---------------- 查询实验标准两连拍 ----------------

def shots_design_result(app, qname, base_name, shot, log=None):
    """设计视图 + 数据表结果两张截图。shot/log 为驱动注入函数，须显式传入。
    渲染延迟已按 公#24 留足（每步 ≥2.5s）。"""
    app.DoCmd.OpenQuery(qname, AC_DESIGN)
    time.sleep(2.5)
    focus()
    shot(base_name + "_design")
    app.DoCmd.Close(AC_QUERY, qname, AC_SAVENO)
    time.sleep(0.8)
    app.DoCmd.OpenQuery(qname, AC_NORMAL)
    time.sleep(2.5)
    shot(base_name + "_result")
    app.DoCmd.Close(AC_QUERY, qname, AC_SAVENO)
    if log:
        log("ACC_SHOTS_DONE " + base_name)
