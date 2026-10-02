# Warehouse sync server

FastAPI + SQLite backend for the offline-first warehouse Android app.
All client-facing messages are in Hebrew.

## Run

```bat
cd server
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\python seed.py --demo        REM optional demo data
.venv\Scripts\python main.py               REM serves on 0.0.0.0:8000
```

`run_server.bat` does the same (creates the venv on first run).

Environment overrides: `WAREHOUSE_HOST`, `WAREHOUSE_PORT`,
`WAREHOUSE_DATABASE_URL` (default: `server/warehouse.db`).

### Headless Windows 11 setup

1. Give the USB-tether (RNDIS) network adapter the static IP `192.168.42.100`, mask `255.255.255.0`.
2. Open the port: `netsh advfirewall firewall add rule name="Warehouse Sync" dir=in action=allow protocol=TCP localport=8000`
3. Start on boot without a logged-in user: Task Scheduler → *Create Task* → trigger *At startup*,
   action `server\run_server.bat`, *Run whether user is logged on or not*.

## Loading users and items

```bat
.venv\Scripts\python seed.py --users users.csv --items items.csv
```

CSV headers: `user_id,full_name,unit` and `qr_id,name` (UTF-8, Excel "CSV UTF-8" works).
The same can be done over HTTP with `POST /api/admin/users` and `POST /api/admin/items`
(JSON arrays). Existing ids are updated; item status is never reset.

## Control panel and wired sync

Open `http://127.0.0.1:8000/panel` on the server PC (the offline package adds a
"Warehouse Control Panel" desktop shortcut). It shows, live: server status,
inventory counts, a step-by-step check of the USB/ADB tablet link (Windows sees
the Samsung device, driver OK, USB debugging on, prompt approved, app
installed, last sync), connected tablets, a sync/event log, recent actions,
items and users, plus "sync now" and "restart ADB" buttons. The panel and its
`/api/panel/*` endpoints answer only requests from the PC itself unless
`WAREHOUSE_PANEL_REMOTE=1`.

Wired sync (`app/usb_sync.py`) runs when `adb` is found (`adb/adb.exe` next to
the server, `WAREHOUSE_ADB`, or PATH; disable with `WAREHOUSE_USB_SYNC=0`). Every
3 s it touches `agent.alive` on each authorized tablet, so the app can show that
the server sees it, and syncs when the app's manual sync button wrote
`sync.request`, or every 60 s otherwise.

## API

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/sync/push` | Upload pending device transactions |
| GET | `/api/sync/pull` | Full current state of items and users |
| GET | `/api/health` | Liveness check |
| POST | `/api/admin/users`, `/api/admin/items` | Bulk upsert |

`POST /api/sync/push` body:

```json
{"device_id": "…", "transactions": [
  {"tx_id": "uuid", "qr_id": "ITEM-0001", "user_id": "1000001",
   "action_type": "BORROW", "timestamp": 1700000000000}
]}
```

- The whole batch is written in one DB transaction; a database error rolls it all back (HTTP 500).
- `tx_id` is generated on the device, so re-sending a batch is safe: known ids are reported as accepted again.
- Transactions with an unknown item/user/action are rejected individually with a Hebrew reason;
  the rest of the batch is still stored.
- An item's `current_status` (`AVAILABLE` / `BORROWED`) follows its latest action **by device
  timestamp**, so a device that syncs late cannot overwrite a newer action from another device.

## Tests

```bat
pip install -r requirements-dev.txt
python -m pytest tests
```

## Offline Windows package

`packaging/build_offline_zip.sh` (run on any Linux/macOS machine with internet) produces
`WarehouseServer-win64-offline.zip`: portable Python 3.11, all dependencies pre-installed and the
scripts in `packaging/windows/` (`install.bat`, `set_static_ip.bat`, `import_data.bat`, …).
Instructions for the target machine are in `packaging/windows/README_HE.txt`.
