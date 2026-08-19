@echo off
REM ============================================================
REM  IDE_CLI.bat -- Live2Be IDE command-line interface
REM
REM  Double-click to run -> interactive text mode in this window.
REM  Needs an API key (project-root .env).
REM  For a no-key demo, use IDE_GUI_mock.bat instead.
REM ============================================================
chcp 65001 >nul
cd /d "%~dp0\.."
call "%~dp0\_env.bat"

echo [Live2Be] Starting IDE CLI...
echo [Live2Be] Type /exit (or Ctrl-C) to quit.

"%LIVE2BE_PY%" -m fetch.agent

echo.
echo [Live2Be] Exited.
pause
