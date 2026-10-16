@echo off
REM Started by the scheduled task. Runs the server and appends output to logs\server.log.
cd /d "%~dp0"
if not exist logs mkdir logs
set PYTHONIOENCODING=utf-8
set PYTHONUTF8=1
"%~dp0python\python.exe" "%~dp0main.py" >> "%~dp0logs\server.log" 2>&1
