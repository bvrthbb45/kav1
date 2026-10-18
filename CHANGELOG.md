# Changelog

All notable changes to Kav1 are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).
See [docs/VERSIONING.md](docs/VERSIONING.md) for the release process.

## [Unreleased]

### Added
- Contractors currently inside are listed **latest arrival first**
  (`GET /visitors/inside` is sorted by the time of the latest `entry` log).
- **Project filter**: new `פרויקט` property, `GET /projects`,
  `GET /visitors/inside?project=` and a project combo box in the client.
- **Expiry alerts**: optional `תוקף סיווג`; `GET /visitors/expiring`; coloured
  rows, an *Expiring approvals* button with counters and a table of expired /
  soon-to-expire approvals in the client.
- **Information security** property `אבטחת מידע` with three values (`מאושר`,
  `מאושר חריג על ידי מפקד היחידה`, `לא מאושר`) and a mandatory validity date
  `תוקף אבטחת מידע` for the two approved values. Create/edit dialogs have
  dedicated fields; the server validates and normalises them (HTTP 422 on bad
  input). No database migration: values live in `visitors.properties`.

### Fixed
- **Data loss:** updating only the name or ID of a visitor (`PUT /visitors/{id}`
  without `properties`) replaced its properties with `{}`; omitted properties
  are now left untouched.
- `openpyxl` (used by the client's Excel export) was missing from the
  requirements; added to `requirements-client.txt`.
- `GET /visitors/inside` ran one query per inside visitor (N+1); it is now a
  single query. `GET /logs` likewise no longer looks up each visitor separately.
- Entry/exit/update/delete no longer block the whole server: the database and
  log-file work of these routes now runs in the thread pool instead of on the
  event loop, and each action uses one commit instead of two.
- Dead WebSocket connections are dropped on broadcast; double disconnect no
  longer raises.

### Added (tools)
- `tools/probe_server.py` (+ `5_probe_server.bat`): live, read-only (GET only) server
  probe that needs no access to the server code - detects freezes while the system is
  used, slow endpoints, slow auth, and (Windows) server CPU / memory / connections.

### Changed
- `tools/diagnose_db.py` v2.1: Hebrew text is printed as Latin transliteration (Windows
  consoles show it garbled), every contractor field is profiled (fill rate, date-like
  fields, categories) so field names do not have to be guessed.
- `tools/diagnose_db.py` v2: asks you to drag the database file into the window (Enter
  = search by itself; also asks when there are none or several), shows the result as a few console pages that each fit one screen
  (to be photographed on an air-gapped machine), predicts the numbers after the
  fixes, also checks whether the file sits in OneDrive / on a network drive, raw
  disk speed and the contractor fields in use, and keeps going if one check fails.
  It never prints visitor names or IDs. The fix scripts use the same database
  search and ask for confirmation before changing a database (`--yes` skips).
- SQLite connections set `busy_timeout=5000` (and `synchronous=NORMAL` once the
  file is in WAL mode). The app never changes the journal mode itself; run
  `tools/fix_01_enable_wal.py`.
- `visitor_logs` models declare the `(visitor_dbid, timestamp)` and
  `(timestamp)` indexes. New databases get them automatically; **existing
  databases must run `tools/fix_02_add_indexes.py`** (without it the new
  single query still scans the log table).

## [0.1.0] - 2026-10-15

First version tracked under semantic versioning. It documents and baselines the
code that already existed; no application behaviour changed.

### Added
- README with system description, stack, requirements, project structure,
  database schema and Windows offline deployment instructions.
- `.env.example` documenting the (few) configuration knobs.
- `VERSION` file, this changelog and `docs/VERSIONING.md` (release process,
  when to bump major / minor / patch) plus `tools/bump_version.py`.
- Database tooling in `tools/`: `diagnose_db.py` (read-only diagnostics, takes a
  verified backup first) and the standalone, idempotent, backup-first fixes
  `fix_01_enable_wal.py`, `fix_02_add_indexes.py`, `fix_03_vacuum_analyze.py`,
  with click-and-run `.bat` wrappers in `tools/windows/`.
- `docs/DB_DIAGNOSIS.md`: analysis of the slowness / hangs.

[Unreleased]: https://github.com/bvrthbb45/kav1/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/bvrthbb45/kav1/releases/tag/v0.1.0
