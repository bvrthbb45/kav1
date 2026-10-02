@echo off
REM Shows whether a tablet is visible over USB for wired sync (ADB).
REM "device" = OK, "unauthorized" = approve the prompt on the tablet,
REM nothing listed = USB debugging off, driver missing, or (in a VM) USB not passed through.
REM The control panel (open_panel.bat) shows the same check step by step, in Hebrew.
cd /d "%~dp0"
echo Starting ADB (the first time can take up to 20 seconds)...
"%~dp0adb\adb.exe" start-server
echo.
"%~dp0adb\adb.exe" devices -l
echo.
echo device       = OK, the tablet is connected and approved
echo unauthorized = approve "Allow USB debugging" on the tablet screen
echo (empty list) = USB debugging is off, Samsung driver missing, or VirtualBox did not pass the tablet
pause
