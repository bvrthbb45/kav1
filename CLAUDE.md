# kav1

Python project: `backend/` (server, alembic migrations) and `frontend/` (desktop client).

## ECC workflow

This repo enables the [ECC](https://github.com/affaan-m/ECC) plugin (`ecc@ecc`) at project scope.
Approve the marketplace when Claude Code prompts on first open. Rules for Python live in `.claude/rules/ecc/`.

Default flow for new work:

1. `/ecc:plan "describe the feature"` — implementation blueprint
2. `tdd-workflow` skill — write the failing test first
3. `/code-review` — fresh-context review
4. `/build-fix` if the build breaks; `/security-scan` before release
