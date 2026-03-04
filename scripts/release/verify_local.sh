#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "${ROOT_DIR}"
trap 'python3 scripts/quality/cleanup_runtime_cache.py >/dev/null 2>&1 || true' EXIT

echo "[verify-local] start"
./scripts/release/repo_public_audit.sh
./scripts/release/prepublish_check.sh
uv run --extra dev ruff check .
uv run --extra dev pytest -q tests/public
echo "[verify-local] done"
