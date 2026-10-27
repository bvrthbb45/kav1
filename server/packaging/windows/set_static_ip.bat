@echo off
setlocal
REM Sets 192.168.42.100/24 on the USB-tethering (RNDIS) network adapter.
REM Connect a tethered phone first so the adapter exists. Run as Administrator.
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
echo Network adapters:
netsh interface show interface
echo.
set /p ADAPTER=Type the adapter name exactly as shown above (e.g. Ethernet 2): 
netsh interface ipv4 set address name="%ADAPTER%" static 192.168.42.100 255.255.255.0 || (
    echo [ERROR] Failed. Check the adapter name.
    pause
    exit /b 1
)
echo Static IP 192.168.42.100 set on "%ADAPTER%".
pause
