@echo off
REM Removes the startup task and firewall rule. The database file is kept.
net session >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Please run this script as Administrator.
    pause
    exit /b 1
)
call "%~dp0stop_server.bat"
schtasks /Delete /TN "WarehouseSyncServer" /F >nul 2>&1
netsh advfirewall firewall delete rule name="Warehouse Sync Server" >nul 2>&1
echo Uninstalled. Data is still in %~dp0warehouse.db
pause
