#!/usr/bin/env bash
set -euo pipefail

echo "[audit-public] checking tracked filenames against local-only patterns..."

tracked_files="$(git ls-files)"
if [[ -z "${tracked_files}" ]]; then
  echo "[audit-public] no tracked files."
  exit 0
fi

deny_name_pattern='(^|/)(\.local|local|notes|tmp|docs/internal|tests/internal|release/internal|\.public-release|\.lunaeclaw-data)/|\.env\.local$|\.env\..*\.local$|\.local\.(json|ya?ml|toml)$|(^|/)config\.local\.json$|(^|/)deploy\.local\.sh$|(^|/)server\.local\.txt$'

name_hits="$(printf '%s\n' "${tracked_files}" | grep -E "${deny_name_pattern}" || true)"
if [[ -n "${name_hits}" ]]; then
  echo "[audit-public] blocked: local-only file names are tracked:"
  printf '%s\n' "${name_hits}" | sed 's/^/  - /'
  exit 1
fi

echo "[audit-public] scanning tracked text for high-risk secret literals..."

secret_hits="$(
  rg -n -S \
    -g '!uv.lock' \
    -g '!*.svg' \
    -g '!*.png' \
    -g '!*.jpg' \
    -g '!*.jpeg' \
    -g '!*.gif' \
    -g '!*.pdf' \
    '(sk-[A-Za-z0-9]{20,}|-----BEGIN (RSA|EC|OPENSSH|DSA)? ?PRIVATE KEY-----|ghp_[A-Za-z0-9]{20,}|xox[baprs]-[A-Za-z0-9-]{10,}|AKIA[0-9A-Z]{16})' \
    . || true
)"

if [[ -n "${secret_hits}" ]]; then
  echo "[audit-public] blocked: possible secret literals detected:"
  printf '%s\n' "${secret_hits}" | sed 's/^/  - /'
  exit 1
fi

echo "[audit-public] pass."
