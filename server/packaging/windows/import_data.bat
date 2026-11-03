@echo off
REM Loads soldiers, item types and items from an Excel file (or two CSV files).
REM Easiest: use the control panel, tab "Import and reports".
REM Usage: import_data.bat data.xlsx
REM        import_data.bat users.csv items.csv   (either file can be "-")
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8
set PYTHONUTF8=1
if "%~1"=="" (
    echo Usage: import_data.bat data.xlsx
    echo        import_data.bat users.csv items.csv
    pause
    exit /b 1
)
if /i "%~x1"==".xlsx" (
    "%~dp0python\python.exe" "%~dp0seed.py" --excel "%~1"
    pause
    exit /b
)
set ARGS=
if not "%~1"=="-" set ARGS=%ARGS% --users "%~1"
if not "%~2"=="" if not "%~2"=="-" set ARGS=%ARGS% --items "%~2"
"%~dp0python\python.exe" "%~dp0seed.py" %ARGS%
pause
