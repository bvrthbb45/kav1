@echo off
rem Kav1 - DRY RUN: checks everything (database, copy test, patches) and writes NOTHING
setlocal
set "PY="
where py >nul 2>nul && set "PY=py -3"
if not defined PY where python >nul 2>nul && set "PY=python"
if not defined PY (
  echo Python 3.8+ was not found.
  pause
  exit /b 1
)
%PY% "%~dp0install_update.py" --dry-run
