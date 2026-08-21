@echo off
rem imgdesc - describe images with the local Qwen2.5-VL model.
rem Works from any directory; used by Claude Code or any shell tool.
rem Usage: imgdesc <image> [question] [--json] [--brief]
"C:\Users\johnf\miniconda3\envs\live2be\python.exe" "%~dp0imgdesc.py" %*
exit /b %errorlevel%
