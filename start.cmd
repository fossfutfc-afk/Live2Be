@echo off
rem start - one-shot launcher for the local stack (LM Studio embed server + WebGUI).
rem Wrapper so a double-click / any shell works without touching ExecutionPolicy.
rem Usage: start.cmd [-Port 8000] [-NoEmbed] [-Cli] [-EmbedOnly]
setlocal
set "PS=pwsh"
where pwsh >nul 2>nul || set "PS=powershell"
"%PS%" -NoProfile -ExecutionPolicy Bypass -File "%~dp0start.ps1" %*
exit /b %errorlevel%
