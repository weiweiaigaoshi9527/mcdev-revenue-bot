<#
  我的世界开发者收益 QQ 机器人 —— Windows 服务注册（计划任务方式）

  以【管理员身份】运行 PowerShell：
      powershell -ExecutionPolicy Bypass -File deploy\windows\install-service.ps1

  作用：
      注册一个开机自启的计划任务（无需第三方工具），
      开机后自动在后台运行机器人，崩溃后自动重启。

  卸载：
      powershell -ExecutionPolicy Bypass -File deploy\windows\uninstall-service.ps1
#>

$ErrorActionPreference = 'Stop'

$TaskName = 'MCDEV-RevenueBot'
$AppDir   = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$Python   = Join-Path $AppDir '.venv\Scripts\python.exe'
$BotPy    = Join-Path $AppDir 'bot.py'

Write-Host '============================================================'
Write-Host ' 我的世界开发者收益 QQ 机器人 · Windows 服务注册'
Write-Host '============================================================'
Write-Host "项目目录：$AppDir"

# --- 检查管理员权限 ---
$isAdmin = ([Security.Principal.WindowsPrincipal] `
    [Security.Principal.WindowsIdentity]::GetCurrent()
).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    Write-Host '!! 请以管理员身份运行本脚本' -ForegroundColor Red
    exit 1
}

# --- 检查虚拟环境 ---
if (-not (Test-Path $Python)) {
    Write-Host '==> 未找到虚拟环境，正在创建...'
    python -m venv (Join-Path $AppDir '.venv')
    & $Python -m pip install --upgrade pip
    & $Python -m pip install -r (Join-Path $AppDir 'requirements.txt')
}
Write-Host "Python  ：$Python"

# --- 配置文件 ---
$EnvFile = Join-Path $AppDir '.env'
if (-not (Test-Path $EnvFile)) {
    Copy-Item (Join-Path $AppDir '.env.example') $EnvFile
    Write-Host '已生成 .env（请填写 MCDEV_COOKIE 等配置）'
}

# --- 包装脚本：设置环境变量后启动 ---
$Wrapper = Join-Path $AppDir 'deploy\windows\_run-bot.cmd'
$WrapperContent = @"
@echo off
cd /d "$AppDir"
set PYTHONIOENCODING=utf-8
set MPLBACKEND=Agg
"$Python" "$BotPy"
"@
Set-Content -Path $Wrapper -Value $WrapperContent -Encoding OEM

# --- 注册计划任务 ---
$action  = New-ScheduledTaskAction -Execute $Wrapper -WorkingDirectory $AppDir
$trigger = New-ScheduledTaskTrigger -AtStartup
$trigger.Delay = 'PT30S'
$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -RestartCount 999 `
    -RestartInterval (New-TimeSpan -Minutes 1) `
    -ExecutionTimeLimit ([TimeSpan]::Zero) `
    -StartWhenAvailable

if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
}

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -RunLevel Highest `
    -Description '我的世界开发者收益 QQ 机器人（NoneBot2）' | Out-Null

Write-Host ''
Write-Host '============================================================'
Write-Host ' 注册完成'
Write-Host '============================================================'
Write-Host "  立即启动 ： Start-ScheduledTask -TaskName $TaskName"
Write-Host "  停止任务 ： Stop-ScheduledTask  -TaskName $TaskName"
Write-Host "  查看状态 ： Get-ScheduledTask   -TaskName $TaskName | Format-List"
Write-Host "  取消自启 ： .\deploy\windows\uninstall-service.ps1"
Write-Host ''
Write-Host '  前台调试（不注册服务时可直接双击 start.bat）'
Write-Host ''
