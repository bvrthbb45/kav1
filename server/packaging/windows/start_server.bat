@echo off
REM Runs the server in this window (Ctrl+C to stop). Useful for testing.
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8
set PYTHONUTF8=1
"%~dp0python\python.exe" "%~dp0main.py"
pause
