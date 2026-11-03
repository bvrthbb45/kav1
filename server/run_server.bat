@echo off
REM Starts the warehouse sync server on 0.0.0.0:8000 (development checkout).
REM On the offline server PC use start_server.bat from the zip instead.
cd /d "%~dp0"
if exist "%~dp0python\python.exe" (
    "%~dp0python\python.exe" main.py
    goto :eof
)
if not exist .venv (
    echo First run: creating .venv and installing requirements - this needs internet.
    python -m venv .venv
    .venv\Scripts\python -m pip install -r requirements.txt
)
.venv\Scripts\python main.py
pause
