# 远程场景：注册"提权版" session-0 计划任务桥（目标 PC 上执行一次）
# 与 create_task.ps1 的唯一区别：/rl HIGHEST —— 驱动进程及其子进程（cmd.exe / mmc.exe /
# 导航出的 GUI 窗口）全部以管理员运行，可以点服务管理器、管理员控制台等提权窗口。
# 原理：UIPI 规定低完整性级别进程无法向高完整性级别窗口发输入/读 UIA 树，
# 非提权驱动碰不动任何提权窗口；提权任务无 UAC 弹窗。
# 副产物：其 spawn 的 cmd 窗口标题带"管理员:"前缀（写实验报告时反而是需要的）。
#
# 何时用：任务涉及 services.msc、net start/stop、注册表、需要管理员的安装向导……
# 何时不用：普通应用（记事本/浏览器/PT）用基础版就够——最小权限原则。
# 安全备忘：这是一条本地静默提权通道——任何以同用户身份运行的进程写 next_cmd.txt
# + schtasks /run 即让驱动以 HIGHEST 执行任意代码（详见 远程坑.md §11）。
# 双桥注意：默认与基础版同名 PtGuiBridge，/f 重注册会互相顶掉；要并存就 -TaskName 换名
# （win135 约定 EnspBridge/EnspBridgeE 双名，见 远程坑.md §10）。
param(
    [string]$TaskName = "PtGuiBridge",                     # 桥任务名，与 pt.py --task 对应
    [string]$Pythonw   = "D:\software\miniconda\pythonw.exe",
    [string]$Driver    = "C:\Users\master\ptauto\win_gui_driver.py"
)

schtasks /create /tn $TaskName /tr "`"$Pythonw`" $Driver" /sc once /sd 2099-01-01 /st 00:00 /it /rl HIGHEST /f
if ($LASTEXITCODE -ne 0) {
    Write-Error "schtasks /create 失败 (exit=$LASTEXITCODE)——非提权会话注册 /rl HIGHEST 会被拒，先管理员运行本脚本"
    exit $LASTEXITCODE
}
schtasks /query /tn $TaskName /fo list

# 之后仍由 Mac 端 remote/pt.py send 触发，用法完全不变。
# 上一个 pythonw 实例未退出时：新版驱动会记 "FAIL busy"（可观测）；恢复仍是
# MSYS_NO_PATHCONV=1 cmd /c "taskkill /F /IM pythonw.exe" 后重新触发。
