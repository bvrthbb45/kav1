@echo off
REM Adds 3 demo users and 3 demo items (safe to run more than once).
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8
set PYTHONUTF8=1
"%~dp0python\python.exe" "%~dp0seed.py" --demo
pause
