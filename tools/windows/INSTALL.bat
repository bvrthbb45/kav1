@echo off
rem Kav1 - double-click to install the update (see README.txt)
setlocal
set "PY="
where py >/dev/null 2>/dev/null && set "PY=py -3"
if not defined PY where python >/dev/null 2>/dev/null && set "PY=python"
if not defined PY (
  echo Python 3.8+ was not found.
  pause
  exit /b 1
)
%PY% "%~dp0install_update.py" %*
