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
if not exist "%PATCH%\main.py" (
    echo [ERROR] The "patch" folder is missing. Extract the whole zip and run update.bat from it.
    pause
    exit /b 1
)

echo [1/6] Finding the installed server...
set "TARGET="
REM The folder the startup task runs from (set by install.bat).
for /f "usebackq delims=" %%d in (`powershell -NoProfile -Command "try { $x=[xml](schtasks /Query /TN WarehouseSyncServer /XML 2>$null | Out-String); Split-Path ($x.Task.Actions.Exec.Command.Trim([char]34)) } catch {}"`) do set "TARGET=%%d"
if defined TARGET if not exist "%TARGET%\python\python.exe" set "TARGET="
if not defined TARGET (
    echo The installed server folder was not found automatically.
    echo Enter the folder that contains start_server.bat and warehouse.db
    set /p "TARGET=Folder: "
)
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
pushd "%TARGET%"
"%PY%" -c "import app.main" || (
    popd
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
