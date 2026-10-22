# Changelog

All notable changes to Kav1 are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).
See [docs/VERSIONING.md](docs/VERSIONING.md) for the release process.

## [Unreleased]

### Added
- `tools/code_patch.py` (+ `windows/10_apply_patch.bat`): applies a small reviewed `*.patch.json` text patch to server source files with preview, backup, syntax check, idempotence and `--revert`
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
- `tools/permissions_watch.py` (+ `9_watch_permissions.bat`): read-only live watcher that
  records the exact moment a role gains / loses a permission, to tell a start-up change
  from a login-time change.
- `tools/permissions_restore.py` (+ `8_restore_permissions.bat`): restores role-permission
  links lost at a server restart from a saved snapshot / baseline in one run. Adds only,
  verified backup first, idempotent, confirmation before writing, integrity check after.
  A stop-gap: it repairs the damage; the cause (code removing admin.* / reports.* /
  control.panel from non-admin roles) still needs a code fix.
- `tools/probe_server.py` v2: can log in (hidden password, or `--header`), so the real
  pages are measured instead of answering 401; never calls backup / export / download /
  logout-like GET endpoints (`--include-heavy` overrides); times one real data page during
  the watch next to the server alive-check; says INCONCLUSIVE when everything answered 401.
- `tools/code_locator.py --preset fields`: also searches `.html` / `.js` (skips minified
  libraries) for where contractor fields are defined and validated in a web UI + API.
- `tools/permissions_check.py` (+ `6_permissions_check.bat`): snapshots every role's
  permissions and compares with the previous snapshot - proves what a server restart
  changes (role permissions reported to shrink after restart).
- `tools/code_locator.py` (+ `7_find_code.bat`): read-only finder / viewer of the lines
  of the server source that handle roles, permissions and start-up seeding, for machines
  whose code cannot leave the network (hides lines that look like secrets).
- `tools/probe_server.py` (+ `5_probe_server.bat`): live, read-only (GET only) server
  probe that needs no access to the server code - detects freezes while the system is
  used, slow endpoints, slow auth, and (Windows) server CPU / memory / connections.

### Changed
- Field names now follow the production data: classification validity `תוקף סב"ט`,
  security-approval validity `תוקף אישור`, visa validity `תוקף ויזה` (aliases keep older
  spellings). Dates are read the way they are typed there: `01.02.2026`, `01.01.26`,
  `01.012026`, ranges (`01.07.2024 - 01.07.2026`: the end counts); unreadable dates are
  kept as typed and never block saving.
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
