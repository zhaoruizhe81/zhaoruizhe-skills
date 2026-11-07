# 远程场景：注册 session-0 计划任务桥（目标 PC 上执行一次）
# 用法: powershell -NoProfile -ExecutionPolicy Bypass -File create_task.ps1
#       换机部署用参数覆盖默认值: -TaskName XxxBridge -Pythonw D:\... -Driver C:\...
# 要点:
#   - 动作直接指向 pythonw.exe + 驱动脚本（无窗口；python.exe 会弹黑框抢焦点、污染截图）
#   - /sd 2099-01-01 让 "once" 触发器永不自燃（只给 /st 的话到点会自己跑一次，真实事故）
#   - /it 交互式令牌 = 运行在已登录用户的桌面会话（SSH 会话本身在 session 0 碰不到桌面）
#   - /create 失败会立刻报错退出（旧版照常跑 query，把旧任务打印出来伪装注册成功）
param(
    [string]$TaskName = "PtGuiBridge",                     # 桥任务名，与 pt.py --task 对应
    [string]$Pythonw   = "D:\software\miniconda\pythonw.exe",   # PC 上的无窗口 Python
    [string]$Driver    = "C:\Users\master\ptauto\win_gui_driver.py"  # 已部署的驱动绝对路径
)

schtasks /create /tn $TaskName /tr "`"$Pythonw`" $Driver" /sc once /sd 2099-01-01 /st 00:00 /it /f
if ($LASTEXITCODE -ne 0) {
    Write-Error "schtasks /create 失败 (exit=$LASTEXITCODE)——查权限/任务名/组策略，别信 query 输出"
    exit $LASTEXITCODE
}
schtasks /query /tn $TaskName /fo list

# 之后由 Mac 端 remote/pt.py send 触发:
#   schtasks /run /tn PtGuiBridge
# 验证桥是否通了: python3 remote/pt.py send shot verify1（投递+触发+轮询+拉图一条命令；
# 新驱动 next_cmd.txt 读后即删，裸 /run 只会记一条 FAIL parse，不再重放旧命令）
