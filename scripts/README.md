# Scripts Layout

This directory is grouped by intent:

- `scripts/quality/`: local + CI quality checks (`lint_changed.py`, `file_line_report.py`)
- `scripts/release/`: publish and verification helpers (`repo_public_audit.sh`, `verify_local.sh`, `verify_server.sh`, `server_acceptance.sh`, `release_smoke.sh`, `upstream_patch_audit.py`)
- `scripts/catalog/`: catalog/build helper scripts (`build_webui_copy_catalog.py`)

Most routine commands are wrapped in `Makefile` targets, so prefer running:

```bash
make quality
make verify-local
make verify-server
make verify-server-acceptance
make prepublish
make export-public
make test-internal
```

Cache cleanup:

- `make test`, `make quality`, and `make verify-local` run `tests/public` and automatically clear `.pytest_cache`, `.ruff_cache`, and `__pycache__` on exit.
- `make test-internal` runs `tests/internal` for local/private regression.
- Manual cleanup: `make clean-cache`.
- Public release snapshot: `make export-public` (outputs `.public-release/` with whitelist-only content).
