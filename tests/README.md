# Tests Layout

- `tests/public/`: minimal regression suite intended for GitHub/CI.
- `tests/internal/`: extended local/private regression suite (not for public push).

Default `pytest` path is `tests/public` (see `pyproject.toml`).

For internal full checks, run:

```bash
make test-internal
```

