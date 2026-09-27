@echo off
setlocal
REM Installs the warehouse sync server as a startup task and opens the firewall.
REM Asks for Administrator permission (UAC) automatically when needed.
cd /d "%~dp0"

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

echo [1/4] Checking bundled Python...
"%~dp0python\python.exe" -c "import fastapi, uvicorn, sqlalchemy, pydantic" || (
    echo [ERROR] Bundled Python or libraries are missing. Re-extract the zip.
    pause
    exit /b 1
)

echo [2/4] Opening TCP port 8000 in Windows Firewall...
netsh advfirewall firewall delete rule name="Warehouse Sync Server" >nul 2>&1
netsh advfirewall firewall add rule name="Warehouse Sync Server" dir=in action=allow protocol=TCP localport=8000 profile=any >nul

echo [3/4] Registering startup task (runs as SYSTEM, no login needed)...
schtasks /Create /TN "WarehouseSyncServer" /TR "\"%~dp0run_service.bat\"" /SC ONSTART /RU SYSTEM /RL HIGHEST /F >nul || (
    echo [ERROR] Could not create the scheduled task.
    pause
    exit /b 1
)

echo [4/4] Starting the server...
call "%~dp0stop_server.bat" >nul 2>&1
schtasks /Run /TN "WarehouseSyncServer" >nul
timeout /t 4 /nobreak >nul
"%~dp0python\python.exe" "%~dp0tools\healthcheck.py"

echo.
echo Done. The server starts automatically on every boot.
echo Logs: %~dp0logs\server.log
pause
