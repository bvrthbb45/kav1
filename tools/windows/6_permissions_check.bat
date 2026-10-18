@echo off
rem Kav1 - click-and-run wrapper for permissions_check.py.
rem Looks for Python in: the project venv, the "py" launcher, then PATH.
setlocal
set "PY="
if exist "%~dp0..\..\.venv\Scripts\python.exe" set "PY=%~dp0..\..\.venv\Scripts\python.exe"
if not defined PY where py >nul 2>nul && set "PY=py -3"
if not defined PY where python >nul 2>nul && set "PY=python"
if not defined PY (
  echo Python 3.8+ was not found. Install it or create the venv - see README.md.
  pause
  exit /b 1
)
echo Run this BEFORE restarting the server, then again AFTER. Read-only; makes a backup first.
echo It saves a snapshot of every role's permissions and shows what changed since the last one.
set "SCRIPT=%~dp0permissions_check.py"
if not exist "%SCRIPT%" set "SCRIPT=%~dp0..\permissions_check.py"
if not exist "%SCRIPT%" (
  echo Cannot find permissions_check.py next to this file or one folder up.
  pause
  exit /b 1
)
%PY% "%SCRIPT%" --no-pause %*
echo.
pause
