# GitHub Publishing Guide

This repository is intended to publish only reusable runtime code and selected public docs.

## Keep in GitHub

- Runtime code under `lunaeclaw/`
- Public docs (`README*`, `docs/public/`, `SECURITY*`, `LICENSE`, `NOTICE`)
- CI/release files (`.github/`, `scripts/`, `release/lint-baseline.txt`)
- Minimal public tests under `tests/public/`

## Keep local only (do not push)

- Server credentials, host lists, deployment shortcuts tied to your own infra
- Personal planning notes and debugging scratch files
- Local override configs (`*.local.*`, `config.local.json`)
- Temporary run artifacts (`tmp/`, local logs, ad-hoc exports)
- Runtime bind-mount data (`.lunaeclaw-data/`)
- Internal docs and checklists (`docs/internal/`, `release/internal/`)
- Internal tests (`tests/internal/`)

Use these locations for local-only content:

- `.local/` (recommended)
- `local/` or `notes/`

They are ignored by `.gitignore`.

## Extra safety (per machine, not committed)

For one-off local files you do not want to track, add patterns to:

`.git/info/exclude`

Example:

```bash
echo ".deploy-private/" >> .git/info/exclude
echo "my-server-checklist.md" >> .git/info/exclude
```

## Pre-publish checklist

```bash
# 1) See exactly what will be committed
git status --short

# 2) Verify no local/private files are staged
git diff --cached --name-only

# 3) Run quality checks
make lint
make test
```

## One-shot public snapshot

```bash
make prepublish
make export-public
```

Then publish from `.public-release/` instead of the full local workspace.
