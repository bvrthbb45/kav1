@echo off
setlocal EnableExtensions
REM Olympus server update (patch). Replaces program files only:
REM the database (warehouse.db), backups, logs and your Excel files are
REM never touched or deleted. A copy of the database and of the old program
REM files is saved in backups\ first.
cd /d "%~dp0"

net session >nul 2>&1
if errorlevel 1 (
    echo Requesting Administrator permission...
    powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Process -FilePath '%~f0' -Verb RunAs" || (
        echo [ERROR] Administrator permission is required. Right-click update.bat and choose "Run as administrator".
        pause
    )
    exit /b
)

set "PATCH=%~dp0patch"
if exist "%PATCH%\main.py" goto have_patch
REM The update files were copied straight into the server folder (and
REM update.bat with them): they are already in place, so only back up,
REM check and restart.
if exist "%~dp0python\python.exe" if exist "%~dp0main.py" if exist "%~dp0app\main.py" (
    echo The update files are already in the server folder: %~dp0
    set "TARGET=%~dp0"
    set "INPLACE=1"
    goto have_patch
)
REM update.bat was opened from inside the zip (Windows copies only that one
REM file to a temp folder) or moved away from its "patch" folder: find the
REM update zip in the usual places and extract it ourselves.
echo Looking for Olympus-Server-Update.zip ...
set "PATCH="
for /f "usebackq delims=" %%p in (`powershell -NoProfile -ExecutionPolicy Bypass -Command "$dirs=@('%~dp0','%~dp0..','%~dp0..\..',[Environment]::GetFolderPath('Desktop'),[Environment]::GetFolderPath('CommonDesktopDirectory'),(Join-Path $env:USERPROFILE 'Downloads'),(Join-Path $env:USERPROFILE 'Desktop'),(Join-Path $env:USERPROFILE 'OneDrive\Desktop')); $z=$dirs | Where-Object { $_ -and (Test-Path $_) } | ForEach-Object { Get-ChildItem -LiteralPath $_ -Filter 'Olympus-Server-Update*.zip' -File -ErrorAction SilentlyContinue } | Sort-Object LastWriteTime -Descending | Select-Object -First 1; if ($z) { $d=Join-Path $env:TEMP 'OlympusUpdate_extract'; Remove-Item -LiteralPath $d -Recurse -Force -ErrorAction SilentlyContinue; Expand-Archive -LiteralPath $z.FullName -DestinationPath $d -Force; $m=Get-ChildItem -LiteralPath $d -Recurse -Filter main.py -File | Where-Object { $_.Directory.Name -eq 'patch' } | Select-Object -First 1; if ($m) { $m.DirectoryName } }"`) do set "PATCH=%%p"
if defined PATCH if exist "%PATCH%\main.py" (
    echo       Using: %PATCH%
    goto have_patch
)
echo [ERROR] The update files were not found.
echo         Right-click Olympus-Server-Update.zip, choose "Extract All",
echo         then open the extracted OlympusUpdate folder and run update.bat there.
pause
exit /b 1

:have_patch

echo [1/6] Finding the installed server...
if defined INPLACE goto have_target
set "TARGET="
REM The folder the startup task runs from (set by install.bat).
for /f "usebackq delims=" %%d in (`powershell -NoProfile -Command "try { $x=[xml](schtasks /Query /TN WarehouseSyncServer /XML 2>$null | Out-String); Split-Path ($x.Task.Actions.Exec.Command.Trim([char]34)) } catch {}"`) do set "TARGET=%%d"
if defined TARGET if not exist "%TARGET%\python\python.exe" set "TARGET="
if not defined TARGET (
    echo The installed server folder was not found automatically.
    echo Enter the folder that contains start_server.bat and warehouse.db
    set /p "TARGET=Folder: "
)

:have_target
set "TARGET=%TARGET:"=%"
if "%TARGET:~-1%"=="\" set "TARGET=%TARGET:~0,-1%"
if not exist "%TARGET%\python\python.exe" (
    echo [ERROR] "%TARGET%" is not an Olympus server folder ^(python\python.exe is missing^).
    pause
    exit /b 1
)
if not exist "%TARGET%\main.py" (
    echo [ERROR] "%TARGET%" is not an Olympus server folder ^(main.py is missing^).
    pause
    exit /b 1
)
echo       Server folder: %TARGET%
set "PY=%TARGET%\python\python.exe"
set PYTHONUTF8=1
for /f %%t in ('call "%PY%" -c "import datetime;print(datetime.datetime.now().strftime('%%Y%%m%%d_%%H%%M%%S'))"') do set "TS=%%t"

echo [2/6] Stopping the server...
schtasks /End /TN "WarehouseSyncServer" >nul 2>&1
for /f "tokens=5" %%p in ('netstat -ano ^| findstr /r /c:":8000 .*LISTENING"') do taskkill /F /PID %%p >nul 2>&1
timeout /t 2 /nobreak >nul

echo [3/6] Backing up the database...
if exist "%TARGET%\warehouse.db" (
    "%PY%" -c "import sqlite3,os,sys;t=sys.argv[1];os.makedirs(os.path.join(t,'backups'),exist_ok=True);d=os.path.join(t,'backups','warehouse_before_update_'+sys.argv[2]+'.db');s=sqlite3.connect(os.path.join(t,'warehouse.db'));b=sqlite3.connect(d);s.backup(b);b.close();s.close();print('      Saved:',d)" "%TARGET%" "%TS%" || (
        echo [ERROR] Could not back up the database. Nothing was changed.
        goto restart
    )
) else (
    echo       No database yet - nothing to back up.
)

if defined INPLACE (
    echo [4/6] Files already copied - skipping.
    echo [5/6] Checking the updated server...
    goto check
)
echo [4/6] Saving the current program files...
set "OLD=%TARGET%\backups\program_before_update_%TS%"
robocopy "%TARGET%\app" "%OLD%\app" /E /XD __pycache__ /NJH /NJS /NFL /NDL /NP >nul
for %%f in (main.py seed.py requirements.txt VERSION.txt) do if exist "%TARGET%\%%f" copy /y "%TARGET%\%%f" "%OLD%\" >nul
echo       Saved: %OLD%

echo [5/6] Installing the update (database and data are kept)...
REM No /MIR: robocopy only adds and overwrites, it never deletes anything.
robocopy "%PATCH%" "%TARGET%" /E /XF warehouse.db warehouse.db-wal warehouse.db-shm /XD backups logs /NJH /NJS /NFL /NDL /NP
if errorlevel 8 (
    echo [ERROR] Copying the update failed. To roll back, copy the files from
    echo         %OLD%
    echo         back into %TARGET%
    goto restart
)
:check
pushd "%TARGET%"
"%PY%" -c "import app.main" || (
    popd
    if defined INPLACE (
        echo [ERROR] The server does not start with these files. Copy the folders
        echo         app and the file main.py from the update into %TARGET% again.
        goto restart
    )
    echo [ERROR] The updated server does not start. Rolling back the program files...
    robocopy "%OLD%" "%TARGET%" /E /NJH /NJS /NFL /NDL /NP >nul
    goto restart
)
popd

:restart
echo [6/6] Starting the server...
schtasks /Query /TN "WarehouseSyncServer" >nul 2>&1
if errorlevel 1 (
    echo       No startup task - run start_server.bat in %TARGET% to start the server.
) else (
    schtasks /Run /TN "WarehouseSyncServer" >nul
    timeout /t 5 /nobreak >nul
    if exist "%TARGET%\tools\healthcheck.py" "%PY%" "%TARGET%\tools\healthcheck.py"
)
echo.
if exist "%TARGET%\VERSION.txt" type "%TARGET%\VERSION.txt"
echo Done. Your data was not changed; a database backup is in %TARGET%\backups
pause
