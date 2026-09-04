@echo off
REM ============================================================
REM  _env.bat -- resolve the Python interpreter Live2Be uses.
REM  Result is written into %LIVE2BE_PY% for the launcher scripts.
REM  Priority: live2be conda env > other conda spots > PATH python.
REM
REM  NOTE: no `setlocal` here, otherwise the var would not reach
REM  the caller.
REM ============================================================
chcp 65001 >nul

set "LIVE2BE_PY="

REM 1) common live2be conda env (has fastapi/uvicorn/PyYAML)
if exist "%USERPROFILE%\miniconda3\envs\live2be\python.exe" set "LIVE2BE_PY=%USERPROFILE%\miniconda3\envs\live2be\python.exe"

REM 2) backup conda locations (miniconda/anaconda installed elsewhere)
if not defined LIVE2BE_PY if exist "C:\ProgramData\miniconda3\envs\live2be\python.exe" set "LIVE2BE_PY=C:\ProgramData\miniconda3\envs\live2be\python.exe"
if not defined LIVE2BE_PY if exist "%LOCALAPPDATA%\miniconda3\envs\live2be\python.exe" set "LIVE2BE_PY=%LOCALAPPDATA%\miniconda3\envs\live2be\python.exe"

REM 3) fallback: python from PATH (you must install deps yourself)
if not defined LIVE2BE_PY set "LIVE2BE_PY=python"

exit /b 0
