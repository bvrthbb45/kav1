# Why Kav1 is slow and "hangs" — analysis

> **Scope and honesty.** The production database (≈2.6 MB, ≈1 852 visitors) is
> not in this repository, so nothing below was measured on it. The causes come
> from reading the code (`backend/app/*.py`) and were reproduced on a
> **synthetic database with the identical schema** (1 852 visitors, 308 inside,
> 60 000 log rows) by running the real FastAPI app under uvicorn. Run
> `tools/diagnose_db.py` on the real file; it reports the same checks with the
> real numbers (see "Confirming on the real DB").

## Summary

The database is tiny — size, fragmentation and `VACUUM` are **not** the
problem. The slowness is structural:

1. `visitor_logs` has **no index on `visitor_dbid` or `timestamp`**.
2. `GET /visitors/inside` is an **N+1**: one query for the visitors, then one
   *unindexed full-table scan of `visitor_logs` per inside visitor*.
3. Every entry/exit/edit broadcasts `"sync"`, and **every connected client then
   calls that expensive endpoint** — one click becomes *clients × N+1*.
4. Sync DB + file I/O inside `async def` routes **freezes the whole server**
   (HTTP and WebSocket) for the duration of each commit.
5. Default SQLite settings (rollback journal, no `busy_timeout`) make writers
   and readers block each other.

## Evidence (synthetic data, local SSD, so real disks will look worse)

Measured through the real app with `tools/fix_*` applied step by step:

| scenario                                                         | before fixes | indexes + WAL |
|------------------------------------------------------------------|-------------:|--------------:|
| `GET /visitors/inside`, one client, idle                         | 824 ms       | 93 ms         |
| 8 clients call `/visitors/inside` at once ("sync" storm), wall   | 2 970 ms     | 2 630 ms      |
| a trivial 1-row lookup issued during that storm                  | 169 ms       | 45 ms         |
| status change (`async def` route) issued during the storm        | 167 ms       | 39 ms         |
| same data, one JOIN query instead of N+1 (raw SQLite)            | —            | **≈1–3 ms**   |

Take-aways:

* The indexes remove ~90% of the single-request cost (824 → 93 ms) and WAL
  removes most of the writer/reader blocking.
* **The DB scripts alone do not cure the storm** (still ≈2.6 s): the remaining
  93 ms/request is Python/ORM overhead of the 309 queries and it is CPU-bound,
  so 8 simultaneous requests serialize on the GIL. The N+1 must be replaced by
  one query (code change, below). That is the single most valuable follow-up.

## Cause by cause

### 1. Missing indexes (fix: `tools/fix_02_add_indexes.py`)
`models.py` indexes `visitors.dbid/name/visitorid` and `visitor_logs.id`, but the
queries filter and sort on columns that have none:

| query (file)                                               | needs                          |
|------------------------------------------------------------|--------------------------------|
| `get_latest_log_for_visitor` — `WHERE visitor_dbid=? ORDER BY timestamp DESC LIMIT 1` | `(visitor_dbid, timestamp)` |
| `get_logs` — `ORDER BY timestamp DESC LIMIT n`             | `(timestamp)`                  |
| `get_logs_for_visitor`, ORM cascade on `delete_visitor`    | `(visitor_dbid)` (prefix of the composite) |

Without them SQLite does `SCAN visitor_logs` + `USE TEMP B-TREE FOR ORDER BY`
each time. The script adds both indexes (no data change), then `ANALYZE`.
Cost: ≈ +70 bytes per log row of disk (e.g. ~3.7 MB per 50 k rows).
`ix_visitors_dbid` is redundant with the primary key; left alone (harmless).

Note: `Base.metadata.create_all()` never adds indexes to existing tables and the
Alembic history is empty (`pass`) for `visitors`, so these indexes must be
created by the script (or a new Alembic revision) on existing installs.

### 2. N+1 in `GET /visitors/inside` (`routes.py`)
```python
for v in visitors:                                   # 1 query + 1 per visitor
    latest_log = crud.get_latest_log_for_visitor(db, v.dbid)
```
Proposed replacement (validated at ≈1–3 ms on the synthetic data, needs the
composite index):
```sql
SELECT v.dbid, v.name, v.visitorid, v.properties, v.inside, l.action, l.timestamp
FROM visitors v
LEFT JOIN visitor_logs l ON l.id = (
    SELECT id FROM visitor_logs WHERE visitor_dbid = v.dbid
    ORDER BY timestamp DESC, id DESC LIMIT 1)
WHERE v.inside
```
`GET /logs` has a smaller N+1 (one visitor lookup per log row, `limit` up to
1000 from the client dialog) — fix with a JOIN as well.

### 3. "sync" storm (`routes.py`, `frontend/.../main_window.py`)
`change_status`, `delete_visitor` and `update_visitor` call
`ws_manager.broadcast("sync")`; each client reacts with `get_visitors_inside()`.
With *k* clients one action costs *k* full reloads. Mitigations, cheapest
first: fix #1/#2 (makes each reload cheap); then push the changed visitor in the
message instead of "reload everything", or debounce reloads client-side.
Broadcast also never removes dead sockets (`websocket.py`: failed connections
stay in `active_connections`, and `disconnect()` raises if called twice).

### 4. Event-loop blocking (`routes.py`)
`change_status`, `delete_visitor`, `update_visitor` are `async def` but call the
synchronous SQLAlchemy session (two commits per entry/exit: the update and the
`visitor_logs` row) and write the daily log file synchronously. While a commit
fsyncs (milliseconds on SSD, **tens to hundreds of ms on a spinning disk or with
antivirus scanning the file**) nothing else on the server runs — including
WebSocket pings, which is what "the server doesn't respond half the time" looks
like. Fix: declare these routes with plain `def` (FastAPI then runs them in the
thread pool, exactly like the `GET` routes already are), or wrap the DB work in
`run_in_threadpool`. Also merge the two commits into one.

### 5. SQLite defaults (`database.py`; scripts: `fix_01_enable_wal.py`)
* Rollback-journal mode: each commit writes/fsyncs a journal and a writer needs
  exclusive access, so a long read stalls writes and vice-versa. **WAL** (persisted
  in the file) fixes this; script included.
* The pool default (5 + 10 overflow connections, 30 s wait) is exhausted when
  >15 requests run at once, e.g. a storm of slow `/visitors/inside` calls; extra
  requests wait up to 30 s and then fail — looks like a hang.
* `busy_timeout`, `synchronous=NORMAL` (safe with WAL) and `foreign_keys=ON` are
  **per-connection** settings: they cannot be applied by a script, only in code:

```python
# backend/app/database.py (proposed, not applied)
from sqlalchemy import event

@event.listens_for(engine, "connect")
def _pragmas(dbapi_con, _):
    cur = dbapi_con.cursor()
    cur.execute("PRAGMA journal_mode=WAL")
    cur.execute("PRAGMA synchronous=NORMAL")
    cur.execute("PRAGMA busy_timeout=5000")
    cur.execute("PRAGMA foreign_keys=ON")   # enable only after fk_check passes
    cur.close()
```
  Also: `DATABASE_URL = "sqlite:///./local_database.db"` is relative to the
  *working directory*. Starting the server from a different folder silently
  creates a second, empty database.

### 6. Smaller items
* `GET /visitors` returns every visitor (JSON column included) with no paging.
* Frontend `Log` keeps every message — including full response bodies — in an
  in-memory list forever and prints to the console: a client left open all day
  grows without bound and UI thread work increases.
* `schemas.py` uses pydantic v1 `class Config: orm_mode` (a warning on v2; pin
  or migrate when the dependency set is frozen).
* `vacuum`/fragmentation: only relevant if the diagnostic shows free pages ≥ 5%.

## Recommended order

1. Stop the server → `tools\windows\1_diagnose_db.bat` (read-only + backup) and
   keep the report.
2. `2_fix_enable_wal.bat` (server stopped), `3_fix_add_indexes.bat`,
   `4_fix_vacuum_analyze.bat` only if the report shows fragmentation.
3. Start the server, observe. Expect single-request latency to drop ~10×.
4. Code follow-up PR (needs your go-ahead; touches the app, so it gets its own
   changelog entry and version bump): single-query `/visitors/inside`,
   `def` instead of `async def` for DB routes, per-connection pragmas, one commit
   per action. Only then consider new features.

## Confirming on the real DB

`diagnose_db.py` is read-only (after taking its own verified backup) and prints:
files/pragmas/fragmentation, integrity, row counts and space per object,
existing indexes, timing **and query plan** for each backend query, the
simulated `/visitors/inside` cost, commit latency on a throw-away copy
(rollback journal vs WAL on *your* disk), and a ranked list of findings with
the script that fixes each. If the real numbers disagree with this analysis
(e.g. few log rows, or already WAL), trust the report and tell me — the
causes above are ranked by the code, not by your data.

## Rollback

Every tool writes its backup to `backups/` next to the database before
changing anything, e.g. `local_database.pre-indexes.20261015_145131.db`.
To roll back: stop the server, keep the current file aside, copy the backup over
`local_database.db`, delete any `local_database.db-wal` / `-shm` files, start
the server. The scripts never delete backups.
