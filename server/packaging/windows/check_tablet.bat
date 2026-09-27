@echo off
REM Shows whether a tablet is visible over USB for wired sync (ADB).
REM "device" = OK, "unauthorized" = approve the prompt on the tablet,
REM nothing listed = USB debugging off, driver missing, or (in a VM) USB not passed through.
cd /d "%~dp0"
"%~dp0adb\adb.exe" devices -l
pause
