@echo off
REM Runs the server in this window and opens the control panel.
REM If the server is already running in the background, just opens the panel.
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8
set PYTHONUTF8=1
if not defined WAREHOUSE_OPEN_PANEL set WAREHOUSE_OPEN_PANEL=1
"%~dp0python\python.exe" "%~dp0main.py"
pause
