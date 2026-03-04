#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
OUT_DIR="${1:-${ROOT_DIR}/.public-release}"

cd "${ROOT_DIR}"

python3 scripts/quality/cleanup_runtime_cache.py >/dev/null 2>&1 || true

rm -rf "${OUT_DIR}"
mkdir -p "${OUT_DIR}"

copy_path() {
  local p="$1"
  if [[ ! -e "${p}" ]]; then
    return 0
  fi
  local parent
  parent="$(dirname "${p}")"
  mkdir -p "${OUT_DIR}/${parent}"
  rsync -a \
    --exclude '__pycache__/' \
    --exclude '*.pyc' \
    --exclude '.pytest_cache/' \
    --exclude '.ruff_cache/' \
    "${p}" "${OUT_DIR}/${parent}/"
}

# Public whitelist
for path in \
  .dockerignore \
  .gitignore \
  Dockerfile \
  docker-compose.yml \
  LICENSE \
  NOTICE \
  Makefile \
  pyproject.toml \
  uv.lock \
  PUBLIC_WHITELIST.md \
  README.md \
  README.zh-CN.md \
  SECURITY.md \
  SECURITY.zh-CN.md \
  release/lint-baseline.txt \
  .github \
  assets \
  bridge \
  orbitclaw \
  scripts \
  docs/public \
  tests/public
do
  copy_path "${path}"
done

echo "[export-public] snapshot ready: ${OUT_DIR}"
echo "[export-public] included docs/public, tests/public, release/lint-baseline.txt"
