@echo off
rem Kav1 - click-and-run wrapper for code_locator.py.
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
echo Finds where the server code handles roles / permissions / start-up seeding. Read-only.
echo Drag the server folder (the one with the 'app' folder) into the window when asked.
set "SCRIPT=%~dp0code_locator.py"
if not exist "%SCRIPT%" set "SCRIPT=%~dp0..\code_locator.py"
if not exist "%SCRIPT%" (
  echo Cannot find code_locator.py next to this file or one folder up.
  pause
  exit /b 1
)
%PY% "%SCRIPT%" --no-pause %*
echo.
pause
