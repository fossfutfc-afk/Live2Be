@echo off
REM ============================================================
REM  IDE_GUI_mock.bat -- Live2Be IDE GUI (MOCK mode)
REM
REM  No API key needed. Uses the built-in StubLLM to run the full
REM  demo flow: think -> propose -> approve -> execute -> done.
REM  Writes to a temp dir, never touches the real config.
REM
REM  Great for: first-time walkthrough, demos, or verifying the
REM  flow without a key.
REM ============================================================
chcp 65001 >nul
cd /d "%~dp0\.."
call "%~dp0\_env.bat"

echo [Live2Be] Starting IDE GUI (MOCK mode, no API needed)...
echo [Live2Be] Browser will open http://127.0.0.1:8000/
echo [Live2Be] Close this window to stop.

set "IDE_MOCK=1"

start "" /b cmd /c "timeout /t 2 /nobreak >nul & start http://127.0.0.1:8000/"

"%LIVE2BE_PY%" -m web

echo.
echo [Live2Be] Server stopped.
pause
