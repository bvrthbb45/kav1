# Versioning and releases

Kav1 follows [Semantic Versioning 2.0.0](https://semver.org/): `MAJOR.MINOR.PATCH`.
The single source of truth is the `VERSION` file at the repo root (currently
`0.1.0`). Release history lives in [CHANGELOG.md](../CHANGELOG.md)
([Keep a Changelog](https://keepachangelog.com/en/1.1.0/) format).

While MAJOR is `0` the API/schema may still change; we still apply the rules
below so that upgrades stay predictable. Go to `1.0.0` when the system is in
stable daily production use and the REST API + DB schema are considered stable.

## When to bump what

| bump      | when                                                                                         | examples |
|-----------|----------------------------------------------------------------------------------------------|----------|
| **MAJOR** | Anything that breaks existing installs or integrations: removed/renamed REST endpoint or field, client and server no longer compatible, DB migration that is not backward compatible or needs manual steps, dropped Windows/Python version. | rename `visitorid`; remove `/visitors/{id}/delete` |
| **MINOR** | Backward-compatible new capability or schema addition (new endpoint, new optional field, new table/column via an Alembic migration, new UI feature, new tool script). | new "export" button; new `notes` column |
| **PATCH** | Backward-compatible bug fix, performance fix, docs/tooling that does not change behaviour. | add missing indexes; make a route non-blocking; typo fix |

Rules of thumb: if a user must do something when upgrading → MAJOR (or at least
call it out under `### Changed`/`### Removed` and the release notes). Client and
server must be released together; mixed versions are only supported within the
same MAJOR.MINOR.

## Day to day: the changelog

Every user-visible change adds a bullet under `## [Unreleased]` **in the same
PR**, in one of: `Added`, `Changed`, `Deprecated`, `Removed`, `Fixed`, `Security`.
Write for operators, not developers.

## Cutting a release

```bash
git checkout main && git pull
python tools/bump_version.py patch      # or minor / major;  add --dry-run to preview
git push origin HEAD vX.Y.Z             # branch + the new annotated tag
```
`bump_version.py` requires a clean tree and a non-empty Unreleased section, then:
bumps `VERSION`, moves Unreleased into `## [X.Y.Z] - date`, refreshes the compare
links, updates `AppVersion` in `kav1.iss`, commits `Release vX.Y.Z` and creates
the annotated tag `vX.Y.Z`. Manually, that is the same as editing those files
and running `git tag -a vX.Y.Z -m "Kav1 X.Y.Z"`.

Tag format: `vMAJOR.MINOR.PATCH` (e.g. `v0.1.0`); pre-releases `v0.2.0-rc.1`.
Never move or delete a pushed tag — release a new patch instead.

## Relationship with the existing CI tags

`.github/workflows/cicdpipeline.yml` already tags **every build** with the short
commit SHA (e.g. `a1b2c3d`) and publishes it as a "Preview/Release Build". Those
are *build identifiers*, not versions, and they coexist with the `vX.Y.Z` tags.
Suggested (not yet applied, because the workflow cannot be tested from here):
build installers from `v*` tags only for real releases and name them
`kav1_setup_<version>.exe`, so operators install a numbered version, not a SHA.

## Database changes

Schema changes go through Alembic (`backend/README.md`) and are at least a MINOR
bump; mention the migration in the changelog. Note the current history only
contains the `visitor_logs` table — indexes added by `tools/fix_02_add_indexes.py`
are not part of any migration yet (a follow-up should add one).

## First tag

`v0.1.0` is the baseline described in the changelog. Create it on the commit
that contains this documentation **after it is merged** (so the tag points at a
commit that exists on `main`, not at a branch tip that may be squashed):
```bash
git tag -a v0.1.0 -m "Kav1 0.1.0" <merge-commit-sha> && git push origin v0.1.0
```
