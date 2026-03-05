#!/usr/bin/env bash
set -euo pipefail

echo "[prepublish] checking staged files for local/private patterns..."

staged_files="$(git diff --cached --name-only)"
if [[ -z "${staged_files}" ]]; then
  echo "[prepublish] no staged files."
  exit 0
fi

deny_pattern='(^|/)(\.local|local|notes|tmp|docs/internal|tests/internal|release/internal|\.public-release|\.lunaeclaw-data)/|\.env\.local$|\.env\..*\.local$|\.local\.(json|ya?ml|toml)$|(^|/)config\.local\.json$|(^|/)deploy\.local\.sh$|(^|/)server\.local\.txt$'

violations="$(printf '%s\n' "${staged_files}" | grep -E "${deny_pattern}" || true)"
if [[ -n "${violations}" ]]; then
  echo "[prepublish] blocked: found local/private files in staged changes:"
  printf '%s\n' "${violations}" | sed 's/^/  - /'
  echo "[prepublish] unstage or move them before pushing."
  exit 1
fi

echo "[prepublish] pass."
