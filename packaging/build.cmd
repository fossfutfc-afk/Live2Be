@echo off
rem Live2Be 打包入口（给 PowerShell 执行策略不友好的人用）。
rem
rem 为什么需要它: `.\build.ps1` 在某些机器的 PowerShell 里会被拦下
rem （"is not digitally signed. You cannot run this script on the current system"）。
rem 那是**执行策略**（AllSigned / 带下载标记的 RemoteSigned）拦的，不是脚本坏了。
rem 这里用 `-ExecutionPolicy Bypass` 只对**这一次调用**放行 —— 不改系统、不改用户策略。
rem
rem 用法:
rem   build.cmd                # 完整版（自带全部素材，约 267 MB）
rem   build.cmd -Slim          # 不带图的瘦身版
rem
rem 其余的开关原样传给 build.ps1。

setlocal
set "HERE=%~dp0"
set "PS=pwsh"
where pwsh >nul 2>nul
if errorlevel 1 set "PS=powershell"

"%PS%" -NoProfile -ExecutionPolicy Bypass -File "%HERE%build.ps1" %*
exit /b %errorlevel%
