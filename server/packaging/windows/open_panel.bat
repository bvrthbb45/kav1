@echo off
REM Opens the control panel. Starts the server first if it is not running.
cd /d "%~dp0"
"%~dp0python\python.exe" "%~dp0tools\healthcheck.py" >nul 2>&1
if errorlevel 1 (
    echo Server is not running - starting it...
    schtasks /Run /TN "WarehouseSyncServer" >nul 2>&1
    if errorlevel 1 (
        set WAREHOUSE_OPEN_PANEL=0
        start "Warehouse Server" /min "%~dp0start_server.bat"
    )
    timeout /t 6 /nobreak >nul
)
set URL=http://127.0.0.1:8000/panel
REM An Edge "app" window looks like a regular Windows program; otherwise use the default browser.
reg query "HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\msedge.exe" >nul 2>&1
if errorlevel 1 (
    start "" "%URL%"
) else (
    start "" msedge --app=%URL% --window-size=1400,900
)
