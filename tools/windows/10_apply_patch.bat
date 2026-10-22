@echo off
rem Kav1 - click-and-run wrapper for code_patch.py.
rem Drag a *.patch.json file onto this .bat (or run it and follow the prompts).
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
set "SCRIPT=%~dp0code_patch.py"
if not exist "%SCRIPT%" set "SCRIPT=%~dp0..\code_patch.py"
if not exist "%SCRIPT%" (
  echo Cannot find code_patch.py next to this file or one folder up.
  pause
  exit /b 1
)
set "PATCH=%~1"
if not defined PATCH (
  echo Drag the *.patch.json file into this window, then press Enter:
  set /p "PATCH=> "
)
%PY% "%SCRIPT%" --patch %PATCH%
