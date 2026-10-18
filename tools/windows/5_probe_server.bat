@echo off
rem Kav1 - click-and-run wrapper for probe_server.py.
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
echo Probes the RUNNING server for 60 seconds. Send GET requests only - changes nothing.
echo While it watches, use the system normally. Photograph each page of the result.
%PY% "%~dp0..\probe_server.py" %*
echo.
pause
