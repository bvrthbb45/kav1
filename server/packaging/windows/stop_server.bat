@echo off
REM Stops whatever process is listening on port 8000.
schtasks /End /TN "WarehouseSyncServer" >nul 2>&1
for /f "tokens=5" %%p in ('netstat -ano ^| findstr /r /c:":8000 .*LISTENING"') do (
    taskkill /F /PID %%p >nul 2>&1 && echo Stopped server process %%p
)
