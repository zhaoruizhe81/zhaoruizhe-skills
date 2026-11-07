# 全屏截图（PowerShell 版，无需 Python；必须在桌面会话中运行——用计划任务 /it 投递）
# 用法: powershell -NoProfile -ExecutionPolicy Bypass -File shot.ps1 [-Out C:\path\out.png]
# 2026-11-05 修复: 默认输出原为字面 "C:\Users\<user>\auto\shot.png"（< > 是文件名非法
# 字符，无 -Out 直跑必炸）→ 改 $env:USERPROFILE；补 DPI 感知（否则高 DPI 缩放机器截图
# 被虚拟化裁剪）；GDI 对象 try/finally Dispose；临时文件原子替换。
param(
    [string]$Out = "$env:USERPROFILE\auto\shot.png"
)
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
Add-Type -TypeDefinition @"
using System;
using System.Runtime.InteropServices;
public class DpiHelper {
    [DllImport("user32.dll")] public static extern bool SetProcessDPIAware();
}
"@
[DpiHelper]::SetProcessDPIAware() | Out-Null
$b = [System.Windows.Forms.SystemInformation]::VirtualScreen
$dir = Split-Path -Parent $Out
if ($dir -and -not (Test-Path $dir)) { New-Item -ItemType Directory -Path $dir -Force | Out-Null }
$bmp = $null; $g = $null
try {
    $bmp = New-Object System.Drawing.Bitmap($b.Width, $b.Height)
    $g = [System.Drawing.Graphics]::FromImage($bmp)
    $g.CopyFromScreen($b.X, $b.Y, 0, 0, $bmp.Size)
    $tmp = "$Out.tmp"
    $bmp.Save($tmp, [System.Drawing.Imaging.ImageFormat]::Png)
    Move-Item -Force $tmp $Out
    Write-Output ("OK " + (Get-Date -Format "yyyy-MM-dd HH:mm:ss"))
} finally {
    if ($g) { $g.Dispose() }
    if ($bmp) { $bmp.Dispose() }
}
