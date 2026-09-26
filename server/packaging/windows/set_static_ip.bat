@echo off
setlocal
REM Sets 192.168.42.100/24 on the USB-tethering (RNDIS) network adapter.
REM Connect a tethered phone first so the adapter exists. Run as Administrator.
net session >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Please run this script as Administrator.
    pause
    exit /b 1
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
