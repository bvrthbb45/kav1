@echo off
rem Kav1 - DRY RUN: checks everything (database, copy test, patches) and writes NOTHING
setlocal EnableDelayedExpansion
set "PY="
py -3 --version >nul 2>&1
if not errorlevel 1 set "PY=py -3"
if not defined PY (
  python --version >nul 2>&1
  if not errorlevel 1 set "PY=python"
)
if not defined PY if exist "%~dp0python_path.txt" set /p PY=<"%~dp0python_path.txt"
if not defined PY (
  echo Python was not found automatically on this computer.
  echo Drag python.exe ^(the one the Kav1 server uses^) into this window, then press Enter.
  set /p "PYIN=> "
  call :unquote
  if not exist "!PYIN!" (
    echo That file does not exist. Nothing was done.
    pause
    exit /b 1
  )
  set "PY="!PYIN!""
  echo !PY!>"%~dp0python_path.txt"
)
%PY% "%~dp0install_update.py" --dry-run %*
if errorlevel 1 pause
goto :eof

:unquote
set "PYIN=%PYIN:"=%"
goto :eof
