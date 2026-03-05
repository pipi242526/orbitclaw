# Open Source Boundary Rules

This repository is public-facing. Keep only reusable runtime content in GitHub.

## 1) Must stay local (never commit)

- Server access data: host/IP lists, SSH aliases, bastion details
- Deployment scripts tied to personal infra
- Secrets: API keys, tokens, passwords, private certificates/keys
- Personal notes, temporary debugging files, ad-hoc exports
- Runtime bind-mount data (`.lunaeclaw-data/`)
- Local override config files (`*.local.*`, `config.local.json`)
- Internal-only trees (`docs/internal/`, `tests/internal/`, `release/internal/`)

## 2) Allowed in GitHub

- Runtime source code
- Public docs and operation guides under `docs/public/`
- Minimal public tests under `tests/public/`
- Generic CI/release scripts and `release/lint-baseline.txt`
- Safe config examples with placeholders only

## 3) Naming rules for local-only files

Put local-only files under:

- `.local/` (recommended)
- `local/`
- `notes/`
- `tmp/`

Or use names matching:

- `*.local.json|yaml|yml|toml`
- `config.local.json`
- `deploy.local.sh`
- `server.local.txt`

These patterns are ignored by `.gitignore`.

## 4) Required checks before push

```bash
make audit-public
make prepublish
```

`make audit-public` checks tracked files for:

- local-only filename patterns accidentally tracked
- high-risk secret literals (e.g. `sk-...`, private key blocks)

## 5) If a local/private file was committed by mistake

```bash
git rm --cached <path>
echo "<path>" >> .git/info/exclude   # local machine only
```

Then rotate any exposed credentials immediately.
