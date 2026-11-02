@echo off
rem Kav1 - click-and-run wrapper for permissions_restore.py.
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
echo Restores role permissions that disappeared after a server restart. Only ADDS missing links; backup first.
echo Drag the database in when asked, check the list, and type Y to confirm.
set "SCRIPT=%~dp0permissions_restore.py"
if not exist "%SCRIPT%" set "SCRIPT=%~dp0..\permissions_restore.py"
if not exist "%SCRIPT%" (
  echo Cannot find permissions_restore.py next to this file or one folder up.
  pause
  exit /b 1
)
%PY% "%SCRIPT%" --no-pause %*
echo.
pause
