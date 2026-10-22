# Kav1 Visitor Management System
<div align="center">
  
![Kav1](https://github.com/user-attachments/assets/6bcebb1b-bc3e-4e3b-b4d5-faece9b61698)<svg width="500" height="500" xmlns="http://www.w3.org/2000/svg">
 <g>
  <rect rx="60" id="svg_11" height="500" width="500" y="0" x="0" stroke-width="0" stroke="#000" fill="#000000"/>
  <rect transform="rotate(45 210 325)" stroke-width="0" id="svg_13" height="50" width="200" y="300" x="110" stroke="#000" fill="#fff"/>
  <rect transform="rotate(-45 210 175)" stroke-width="0" id="svg_15" height="50" width="200" y="150" x="110" stroke="#000" fill="#fff"/>
  <rect transform="rotate(90 100 250)" stroke-width="0" id="svg_19" height="50" width="300" y="225" x="-50" stroke="#000" fill="#fff"/>
  <rect transform="rotate(90 400 250)" stroke-width="0" id="svg_20" height="50" width="300" y="225" x="250" stroke="#000" fill="#fff"/>
 </g>

</svg>

</div>


Kav1 is a visitor management system for controlled environments (guard posts,
sites, offices): register visitors, mark who is **inside / outside**, keep an
audit log of every entry, exit and change, and see the same live list on every
workstation. It is designed to run **fully offline on a local network**, with
no cloud dependency.

- **Server** — FastAPI + SQLAlchemy + SQLite, REST API and a WebSocket that
  tells clients to refresh.
- **Client** — PySide6 (Qt) desktop application for Windows, talking to the
  server over HTTP/WebSocket.

> Current version: see [`VERSION`](VERSION) · history in [`CHANGELOG.md`](CHANGELOG.md)

## Contents
[Architecture](#architecture) · [Tech stack](#tech-stack) · [Requirements](#system-requirements) ·
[Offline Windows deployment](#offline-windows-deployment) · [Running](#running) ·
[Configuration](#configuration) · [Project structure](#project-structure) ·
[Database schema](#database-schema) · [REST API](#rest-api) ·
[Database maintenance](#database-maintenance-tools) · [Versioning](#versioning) · [License](#license)

## Architecture

```
 workstation A            workstation B                 server machine
┌──────────────┐        ┌──────────────┐        ┌────────────────────────────┐
│ Kav1 client  │        │ Kav1 client  │  HTTP  │ uvicorn + FastAPI          │
│ (PySide6)    │◄──────►│ (PySide6)    │◄──────►│  routes.py → crud.py       │
└──────▲───────┘   WS   └──────▲───────┘   WS   │  SQLAlchemy → SQLite file  │
       └── "sync" push ────────┴───────────────►│  (local_database.db)       │
                                                 │  visitor_logs/*.log (CSV)  │
                                                 └────────────────────────────┘
```
Any change (entry/exit/create/edit/delete) is written to the DB and to a daily
text log, then the server broadcasts `sync` on `/ws`; every client reloads the
"currently inside" list.

## Tech stack

| layer      | technology |
|------------|------------|
| API server | Python 3.11, FastAPI, Uvicorn, WebSockets |
| ORM / DB   | SQLAlchemy, SQLite (single file), Alembic (migrations), Pydantic |
| Client     | PySide6 (Qt for Python) |
| Packaging  | PyInstaller → Inno Setup installer (`kav1.iss`, `build_windows.bat`) |
| CI         | GitHub Actions: `black --check`, Windows build, release (`.github/workflows`) |

## System requirements

| | server machine | client workstations |
|--|--|--|
| OS | Windows 10/11 64-bit (Linux also works for development) | Windows 10/11 64-bit |
| Python (venv install only) | 3.11 x64 | 3.11 x64 |
| Disk | ~200 MB + DB growth (a 2.6 MB DB holds ≈ 1 800 visitors) and room for `backups/` | ~300 MB (Qt) |
| Network | TCP port **3000** reachable from clients (change with `--port`) | LAN access to the server |
| Internet | not needed after installation | not needed |

The installer built by CI (`kav1_setup_<sha>.exe`) bundles its own Python
runtime, so Python is only required for the venv method below and for the
`tools/` scripts (which use only the standard library, Python 3.8+).

## Offline Windows deployment

Two supported ways. Use the **installer** if you just need to run Kav1; use the
**offline venv** if you want to run from source (and to run `tools/`).

### A. Installer (no Python needed)
1. Take `kav1_setup_<sha>.exe` from the GitHub release (or build it, below).
2. Run it on the server and on each client (installs per-user to
   `%APPDATA%\Kav1`: `server\server.exe`, `client\main.exe` + Desktop shortcuts).
3. Start **Kav1 Server** on the server machine, then **Kav1 App** on clients.

Build it yourself (online Windows machine, Python 3.11, Inno Setup 6):
```bat
pip install -r requirements.txt pyinstaller
build_windows.bat
"C:\Program Files (x86)\Inno Setup 6\ISCC.exe" kav1.iss
```

### B. Offline venv from local wheels

**1. On a machine WITH internet** (any OS; Python 3.11 + pip), download every
dependency as a Windows 3.11 wheel into `wheels\`:
```bat
:: server only (small)
pip download -r requirements-server.txt -d wheels --only-binary=:all: --platform win_amd64 --python-version 3.11
:: client (PySide6 is ~200 MB) - run this too if the machine needs the GUI
pip download -r requirements-client.txt -d wheels --only-binary=:all: --platform win_amd64 --python-version 3.11
```
Copy to the offline machine (USB): the repository folder, the `wheels\` folder,
and the Python 3.11 x64 installer from python.org (if Python is not installed).
`wheels/` is git-ignored. Keep a `pip freeze > requirements.lock.txt` from a
known-good machine to pin exact versions for reproducible re-installs.

**2. On the OFFLINE machine**, in the repository folder:
```bat
py -3.11 -m venv .venv
.venv\Scripts\python -m pip install --no-index --find-links=wheels -r requirements-server.txt
:: and, on workstations that run the GUI:
.venv\Scripts\python -m pip install --no-index --find-links=wheels -r requirements-client.txt
```
`--no-index` guarantees pip never tries the network. If it reports a missing
package, re-run step 1 for it — nothing else is needed.

## Running

Server (start it **from the `backend\` folder** — the database path is relative
to the working directory, see [Configuration](#configuration)):
```bat
cd backend
..\.venv\Scripts\python server.py --host 0.0.0.0 --port 3000
```
Client (asks for the server address, e.g. `192.168.1.10:3000`):
```bat
cd frontend
..\.venv\Scripts\python main.py
```
API docs while the server runs: `http://<server>:3000/docs`.

First run creates `backend\local_database.db` automatically
(`Base.metadata.create_all`). To apply schema changes later use Alembic from
`backend\` (see [backend/README.md](backend/README.md)).

## Configuration

Kav1 has almost no configuration; everything that exists is listed in
[`.env.example`](.env.example). In short: bind address/port are server CLI flags,
the DB path is `./local_database.db` relative to the server's working directory
(hard-coded in `backend/app/database.py`), and the client asks for the server
address at start-up. **Always start the server from the same folder**, otherwise
it silently creates a second empty database.

## Project structure

```
.
├── backend/                FastAPI server
│   ├── server.py           CLI entry (uvicorn, --host/--port)
│   ├── server.spec         PyInstaller spec
│   ├── alembic.ini, alembic/   DB migrations
│   └── app/
│       ├── main.py         FastAPI app, create_all, router
│       ├── database.py     engine + session (SQLite file)
│       ├── models.py       Visitor, VisitorLog
│       ├── schemas.py      Pydantic request models
│       ├── fields.py       well-known property keys, validation, expiry logic
│       ├── crud.py         all queries
│       ├── routes.py       REST + /ws endpoints
│       ├── websocket.py    connection manager / "sync" broadcast
│       ├── visitor_logger.py  daily text log in visitor_logs/
│       └── version.py      build identifier (reads version.txt)
├── frontend/               PySide6 desktop client (see frontend/README.md)
│   ├── main.py, main.spec
│   └── app/{core,views,utils}/
├── tools/                  DB diagnostics and fixes (standalone, stdlib only)
│   ├── diagnose_db.py, fix_01_enable_wal.py, fix_02_add_indexes.py,
│   │   fix_03_vacuum_analyze.py, bump_version.py
│   └── windows/*.bat       double-click wrappers
├── docs/                   DB_DIAGNOSIS.md, VERSIONING.md
├── requirements*.txt       all / server / client dependencies
├── VERSION, CHANGELOG.md, .env.example
├── build_windows.bat, kav1.iss      packaging
└── .github/workflows/cicdpipeline.yml
```

## Contractor fields and features

`visitors.properties` stays a free-form key/value JSON, so no schema migration
is needed. These keys have meaning for the application (constants in
`backend/app/fields.py` and `frontend/app/core/fields.py`):

| key | meaning | rules |
|-----|---------|-------|
| `פרויקט` | project the contractor belongs to | free text; the server also recognises `פרויקטים`, `project`, `projects` in existing records |
| `אבטחת מידע` | information-security status | exactly one of `מאושר` / `מאושר חריג על ידי מפקד היחידה` / `לא מאושר` |
| `תוקף אבטחת מידע` | validity of the approval | required when the status is one of the two approved values |
| `תוקף סיווג` | validity of the security classification | optional; when filled it is tracked for expiry |

Dates are stored as `YYYY-MM-DD` (the API also accepts `DD/MM/YYYY`,
`DD.MM.YYYY`, `DD-MM-YYYY` and normalises them). Invalid values are rejected
with HTTP 422 and a message.

* **Order:** the list of visitors inside is sorted by latest arrival first.
* **Project filter:** the combo box above the list filters by project.
* **Expiry alerts:** rows with an expired / soon-to-expire date are coloured and
  marked; the *Expiring approvals* button shows the counts and opens a table of
  everyone expired or expiring within N days (default 30), soonest first.

## Database schema

SQLite file `local_database.db`, two tables (`backend/app/models.py`):

**`visitors`**

| column      | type    | notes |
|-------------|---------|-------|
| `dbid`      | INTEGER | PK, autoincrement |
| `name`      | VARCHAR | NOT NULL, indexed |
| `visitorid` | VARCHAR | NOT NULL, **UNIQUE**, indexed — the business ID used by the API |
| `inside`    | BOOLEAN | NOT NULL, default false |
| `properties`| JSON    | free-form key/values (phone, company, …) |

**`visitor_logs`** (audit trail)

| column         | type     | notes |
|----------------|----------|-------|
| `id`           | INTEGER  | PK |
| `visitor_dbid` | INTEGER  | NOT NULL, FK → `visitors.dbid` `ON DELETE CASCADE` |
| `action`       | VARCHAR  | `creation`, `entry`, `exit`, `update` |
| `timestamp`    | DATETIME | default `datetime.now` (local time, naive) |

Indexes created by the app: `ix_visitors_dbid`, `ix_visitors_name`,
`ix_visitors_visitorid` (unique), `ix_visitor_logs_id`.
**Not present** (and needed — see [docs/DB_DIAGNOSIS.md](docs/DB_DIAGNOSIS.md)):
`visitor_logs(visitor_dbid, timestamp)` and `visitor_logs(timestamp)`; added by
`tools/fix_02_add_indexes.py` (new databases get them from `models.py`). SQLite foreign keys are not enforced by default.

## REST API

| method | path | purpose |
|--------|------|---------|
| GET  | `/visitors` | all visitors |
| GET  | `/visitors/inside[?project=]` | visitors currently inside, latest arrival first, with `project`, `infosec`, `expiry` |
| GET  | `/projects` | distinct projects with total / inside counts |
| GET  | `/visitors/expiring?days=30&inside_only=false` | expired or expiring approvals, soonest first |
| POST | `/visitor` | create |
| GET  | `/visitors/{visitor_id}` | one visitor |
| PUT  | `/visitors/{visitor_id}` | edit name / id / properties |
| POST | `/visitors/{visitor_id}/status?is_inside=` | entry / exit |
| POST | `/visitors/{visitor_id}/delete` | delete (cascades logs) |
| GET  | `/visitors/search?search_query=` | name substring |
| GET  | `/visitors/search-by-key-value?key=&value=` | match a `properties` key |
| GET  | `/logs?limit=` · `/logs/{visitor_id}` | audit log |
| WS   | `/ws` | server → clients `sync` |

## Database maintenance tools

Standalone scripts in `tools/` (standard library only, no pip install needed).
Each one **backs up first** (verified copy in `backups\` next to the database,
made with SQLite's online-backup API), is **idempotent**, and **never deletes
data**; when there is nothing to change it makes no backup and no change. They
ask you to drag `local_database.db` into the window (or press Enter to search automatically;
`--db PATH` / `KAV1_DB` also work). The diagnostic prints its result as numbered pages, each sized to fit
one console window, so it can be photographed page by page.

| double-click (`tools\windows\`) | script | what it does | server |
|---|---|---|---|
| `1_diagnose_db.bat` | `diagnose_db.py` | read-only report: size, rows, indexes, WAL, fragmentation, query timings + plans, ranked findings | may run |
| `2_fix_enable_wal.bat` | `fix_01_enable_wal.py` | switch to WAL journal mode (once) | **stop** |
| `3_fix_add_indexes.bat` | `fix_02_add_indexes.py` | add missing `visitor_logs` indexes + ANALYZE | preferably stop |
| `4_fix_vacuum_analyze.bat` | `fix_03_vacuum_analyze.py` | checkpoint, VACUUM, ANALYZE (only if fragmented) | **stop** |

| `5_probe_server.bat` | `probe_server.py` | black-box check of the RUNNING server: freezes (stalls) while you use it, slow endpoints (after an optional login), slow login check, server CPU / memory / connections | running |

| `6_permissions_check.bat` | `permissions_check.py` | snapshot of every role's permissions; run before and after a server restart to see exactly what changed (read-only) | any |
| `7_find_code.bat` | `code_locator.py` | finds where the server source handles roles / permissions / start-up seeding and shows those lines page by page (read-only; hides sensitive lines) | any |

Why Kav1 is slow and what each fix buys: [docs/DB_DIAGNOSIS.md](docs/DB_DIAGNOSIS.md).
To roll back any step: stop the server, copy the matching file from `backups\`
over `local_database.db`, delete `local_database.db-wal`/`-shm`, start again.

## Versioning

[Semantic Versioning](https://semver.org/) with a `VERSION` file, a
[Keep a Changelog](https://keepachangelog.com/) `CHANGELOG.md` and annotated git
tags `vX.Y.Z`. When to bump major/minor/patch and how to release:
[docs/VERSIONING.md](docs/VERSIONING.md) (`python tools/bump_version.py patch`).

## License

Licensed under the [GNU General Public License](https://www.gnu.org/licenses/gpl-3.0.html).
You are free to use, modify and distribute the project under its terms.
