@echo off
REM ============================================================
REM  IDE_GUI.bat -- Live2Be IDE GUI (real LLM, needs an API key)
REM
REM  Double-click to run -> the browser opens automatically.
REM  Close this window to stop the server.
REM
REM  Needs an API key in the project-root .env file.
REM  No API key / just demoing? Use IDE_GUI_mock.bat instead.
REM ============================================================
chcp 65001 >nul
cd /d "%~dp0\.."
call "%~dp0\_env.bat"

echo [Live2Be] Starting IDE GUI (real LLM)...
echo [Live2Be] Browser will open http://127.0.0.1:8000/
echo [Live2Be] Close this window to stop.

REM open the browser after a 2s delay (let uvicorn bind the port)
start "" /b cmd /c "timeout /t 2 /nobreak >nul & start http://127.0.0.1:8000/"

"%LIVE2BE_PY%" -m web

echo.
echo [Live2Be] Server stopped.
pause
