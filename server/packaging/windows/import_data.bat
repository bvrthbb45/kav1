@echo off
REM Loads users and items from CSV files (see data\users_template.csv and data\items_template.csv).
REM Usage: import_data.bat data\users.csv data\items.csv
REM Either file can be "-" to skip it.
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8
set PYTHONUTF8=1
set ARGS=
if not "%~1"=="" if not "%~1"=="-" set ARGS=%ARGS% --users "%~1"
if not "%~2"=="" if not "%~2"=="-" set ARGS=%ARGS% --items "%~2"
if "%ARGS%"=="" (
    echo Usage: import_data.bat users.csv items.csv
    pause
    exit /b 1
)
"%~dp0python\python.exe" "%~dp0seed.py" %ARGS%
pause
