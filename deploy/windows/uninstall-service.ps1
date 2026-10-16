<#
  我的世界开发者收益 QQ 机器人 —— Windows 服务卸载

  以【管理员身份】运行 PowerShell：
      powershell -ExecutionPolicy Bypass -File deploy\windows\uninstall-service.ps1

  作用：
      停止并删除开机自启的计划任务，清理生成的包装脚本。
      不会删除虚拟环境、配置文件和聊天缓存。
#>

$ErrorActionPreference = 'Stop'

$TaskName = 'MCDEV-RevenueBot'
$AppDir   = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path

Write-Host '============================================================'
Write-Host ' 我的世界开发者收益 QQ 机器人 · Windows 服务卸载'
Write-Host '============================================================'

# --- 检查管理员权限 ---
$isAdmin = ([Security.Principal.WindowsPrincipal] `
    [Security.Principal.WindowsIdentity]::GetCurrent()
).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    Write-Host '!! 请以管理员身份运行本脚本' -ForegroundColor Red
    exit 1
}

# --- 停止并删除计划任务 ---
$task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($task) {
    Write-Host '==> 停止计划任务...'
    Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    Write-Host '==> 删除计划任务...'
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
    Write-Host '已删除计划任务：' $TaskName
} else {
    Write-Host '未找到计划任务：' $TaskName '（可能尚未注册）'
}

# --- 清理包装脚本 ---
$Wrapper = Join-Path $AppDir 'deploy\windows\_run-bot.cmd'
if (Test-Path $Wrapper) {
    Remove-Item $Wrapper -Force
    Write-Host '已清理包装脚本：deploy\windows\_run-bot.cmd'
}

Write-Host ''
Write-Host '============================================================'
Write-Host ' 卸载完成'
Write-Host '============================================================'
Write-Host '  虚拟环境 .venv、配置文件 .env、缓存 .cache 均已保留。'
Write-Host '  如需彻底清理，可手动删除 .venv 目录。'
Write-Host ''
