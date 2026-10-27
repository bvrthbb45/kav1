@echo off
REM Copies the database to backups\warehouse_YYYYMMDD_HHMMSS.db (safe while the server runs).
cd /d "%~dp0"
set PYTHONUTF8=1
"%~dp0python\python.exe" -c "import sqlite3,datetime,os;os.makedirs('backups',exist_ok=True);d='backups/warehouse_'+datetime.datetime.now().strftime('%%Y%%m%%d_%%H%%M%%S')+'.db';s=sqlite3.connect('warehouse.db');t=sqlite3.connect(d);s.backup(t);t.close();s.close();print('Backup saved:',d)"
pause
