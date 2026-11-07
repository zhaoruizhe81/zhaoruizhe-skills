> 存档：旧项目（SSMS 遥控）时期的完整沉淀，内容不再更新。现行三级坑规范见根目录 [踩坑清单.md](../踩坑清单.md) 与 [remote/远程坑.md](../remote/远程坑.md)；本目录保留深度战例与当时的应用特化经验。

# Driver Pattern: win_gui_driver.py 契约与实例

驱动脚本运行在目标 PC 的桌面会话里（经计划任务投递），是整个自动化唯一的"现场执行者"。Mac 端只负责改 `next_cmd.txt`、触发任务、轮询日志、下载截图。

## 文件布局（PC 端工作目录）

```
C:\Users\<user>\auto\
├── win_gui_driver.py   # 驱动（本模板）
├── next_cmd.txt        # 待执行子命令（编排端覆写）
├── gui.log             # 运行日志（START/DONE/FAIL 标记）
├── shots/              # 截图输出目录
└── *.sql / *.xlsx ...  # 任务数据文件
```

## 契约

1. 计划任务动作 = `pythonw.exe C:\Users\<user>\auto\win_gui_driver.py`（**无参数**）。
2. 驱动启动时：argv 有参数用 argv；否则读 `next_cmd.txt`（第一个词为子命令，其余为参数）。
3. 每条命令：`log("START ...")` → 执行 → `log("DONE ...")`；异常时 `log("FAIL ...")` + traceback + 错误现场截图 + exit 1。
4. 编排端（Mac）轮询 `gui.log` 最后一行出现 `DONE`/`FAIL` 为止，再拉取截图。

## 编排端轮询模板（Mac bash）

```bash
run() {  # usage: run <子命令> [参数...]
  python3 ssh_skill.py exec windowpc \
    "echo $* > /c/Users/master/auto/next_cmd.txt && \
     MSYS_NO_PATHCONV=1 cmd /c \"schtasks /run /tn <Task>\"" >/dev/null
  for i in $(seq 1 36); do
    sleep 5
    LINE=$(python3 ssh_skill.py exec windowpc \
      'tail -1 /c/Users/master/auto/gui.log' --no-progress 2>/dev/null | \
      python3 -c "import json,sys;print(json.load(sys.stdin)['data']['stdout'].strip())")
    case "$LINE" in DONE*|FAIL*) echo "$LINE"; break;; esac
  done
}
```

## 通用辅助函数（已实战验证）

见 `scripts/win_gui_driver.py`，要点：

- `log(msg)` / `shot(name)`：mss 全屏截图存 PNG，毫秒级。
- `set_clip(text)`：win32clipboard 写 CF_UNICODETEXT——所有含括号/中文的输入都走它。
- `dismiss()`：给主窗口焦点并按 ESC，取消残留菜单/编辑态。**每个会改变界面状态的命令开头都调它。**
- `_page_type(w)`：按窗口内 Text 元素给向导/对话框分类（状态机用）。
- `_paste_edit(ed, text)`：click_input → ^a → ^v。**替代 set_edit_text**（后者在 WPF 上抛 COMError）。
- `_wizard_next(w)`：按名称精确找 "Next >" 按钮点击。

## 目标应用命令示例（SSMS 实战节选）

```python
def cmd_newdb():
    sql = "-- 注释含学号姓名\nCREATE DATABASE [Sales叶梦池]"
    new_query_run(sql, wait=6)      # 新建查询→剪贴板粘贴→F5
    refresh_oe_node("数据库")        # 选中节点→Shift+F10→发加速键
    db = tree_item("数据库")
    db.collapse(); db.expand()      # 收起再展开=刷新
    shot("02_createdb")

def cmd_import_sheet3(row, dest):
    """向导状态机: 每步识别页面类型再分派"""
    wiz = launch_wizard_single_instance()   # 先清理旧实例
    for step in range(14):
        wiz = wizard_win(); wiz.set_focus()
        _wiz_dismiss_error(wiz)             # 先点掉可能存在的错误弹窗
        pt = _page_type(wiz)                # welcome/source/dest/copy/...
        if pt == "source":   configure_source(wiz)   # 选Excel+版本+路径
        elif pt == "dest":   configure_dest(wiz)     # 提供程序+服务器+认证+库
        elif pt == "tables": check_row_and_fix_dest(wiz, row, dest)
        elif pt == "complete": click_finish(wiz); time.sleep(20)
        elif pt == "success": break
```

## 实战教训清单

1. **欢迎页可能被跳过**：勾选过"不再显示此起始页"后，向导直接落在第一个配置页。导航必须基于页面识别，不能基于固定按键序列。
2. **配置不跨启动保留**：向导重开是全默认状态。每张表都要完整走一遍配置，或显式校验每个字段的当前值。
3. **向导打开数据文件是独占锁**：重跑前必须关闭所有旧实例（窗口+进程都查）。
4. **首启 CPU 打满**：等待阈值放宽（轮询 200 秒），产物文件出现与否作为完成信号，不要睡固定时长。
5. **UIA 树先 dump 后写匹配**：`print_control_identifiers(depth=3, filename=...)` 的输出决定一切控件定位策略。
