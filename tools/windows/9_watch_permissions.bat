@echo off
rem Kav1 - click-and-run wrapper for permissions_watch.py.
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
echo Watches the role permissions live (read-only) to catch the exact moment they disappear.
echo Start it, THEN restart the Kav1 server and log in. Ctrl+C to stop and see the summary.
set "SCRIPT=%~dp0permissions_watch.py"
if not exist "%SCRIPT%" set "SCRIPT=%~dp0..\permissions_watch.py"
if not exist "%SCRIPT%" (
  echo Cannot find permissions_watch.py next to this file or one folder up.
  pause
  exit /b 1
)
%PY% "%SCRIPT%" --no-pause %*
echo.
pause
