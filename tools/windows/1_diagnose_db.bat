@echo off
rem Kav1 - click-and-run wrapper for diagnose_db.py.
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
echo Safe to run while the server is up. Makes a backup, changes nothing.
echo The report is shown as several pages - photograph each one, press Enter for the next.
set "SCRIPT=%~dp0diagnose_db.py"
if not exist "%SCRIPT%" set "SCRIPT=%~dp0..\diagnose_db.py"
if not exist "%SCRIPT%" (
  echo Cannot find diagnose_db.py next to this file or one folder up.
  pause
  exit /b 1
)
%PY% "%SCRIPT%" --no-pause %*
echo.
pause
