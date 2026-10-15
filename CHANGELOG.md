# Changelog

All notable changes to Kav1 are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).
See [docs/VERSIONING.md](docs/VERSIONING.md) for the release process.

## [Unreleased]

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
