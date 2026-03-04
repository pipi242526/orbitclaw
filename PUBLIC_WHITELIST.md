# Public Whitelist

The following paths are intended for GitHub publication:

- `.github/`
- `assets/`
- `bridge/`
- `orbitclaw/`
- `scripts/`
- `docs/public/`
- `tests/public/`
- `release/lint-baseline.txt`
- `README.md`, `README.zh-CN.md`
- `SECURITY.md`, `SECURITY.zh-CN.md`
- `LICENSE`, `NOTICE`
- `Dockerfile`, `docker-compose.yml`
- `Makefile`, `pyproject.toml`, `uv.lock`
- `.gitignore`, `.dockerignore`

The following paths are internal/local-only:

- `docs/internal/`
- `tests/internal/`
- `release/internal/`
- `.public-release/`

Use:

```bash
make prepublish
make export-public
```

to generate a publishable snapshot under `.public-release/`.
