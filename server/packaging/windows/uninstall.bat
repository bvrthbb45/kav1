@echo off
REM Removes the startup task and firewall rule. The database file is kept.
net session >nul 2>&1
if errorlevel 1 (
    REM Not elevated: relaunch this script through a UAC prompt.
    echo Requesting Administrator permission...
    powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Process -FilePath '%~f0' -Verb RunAs" || (
        echo [ERROR] Administrator permission is required. Right-click the file and choose "Run as administrator".
        pause
    )
    exit /b
)
call "%~dp0stop_server.bat"
schtasks /Delete /TN "WarehouseSyncServer" /F >nul 2>&1
netsh advfirewall firewall delete rule name="Warehouse Sync Server" >nul 2>&1
powershell -NoProfile -Command "Remove-Item -ErrorAction SilentlyContinue (Join-Path ([Environment]::GetFolderPath('CommonDesktopDirectory')) 'Warehouse Control Panel.lnk'); Remove-Item -ErrorAction SilentlyContinue (Join-Path ([Environment]::GetFolderPath('CommonDesktopDirectory')) 'Olympus Control Panel.lnk')" >nul 2>&1
echo Uninstalled. Data is still in %~dp0warehouse.db
pause
