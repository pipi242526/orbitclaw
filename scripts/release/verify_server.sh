#!/usr/bin/env bash
set -euo pipefail

SERVER_HOST="${SERVER_HOST:-}"
SERVER_USER="${SERVER_USER:-root}"
SERVER_DIR="${SERVER_DIR:-/root/LunaeClaw}"
VERIFY_WEBUI="${VERIFY_WEBUI:-1}"

if [[ -z "${SERVER_HOST}" ]]; then
  echo "[verify-server] SERVER_HOST is required"
  echo "[verify-server] example:"
  echo "  SERVER_HOST=203.0.113.10 make verify-server"
  exit 1
fi

REMOTE="${SERVER_USER}@${SERVER_HOST}"
SSH_OPTS=(-o StrictHostKeyChecking=accept-new)

echo "[verify-server] target: ${REMOTE}"
echo "[verify-server] repo: ${SERVER_DIR}"

ssh "${SSH_OPTS[@]}" "${REMOTE}" bash -s -- "${SERVER_DIR}" "${VERIFY_WEBUI}" <<'EOF'
set -euo pipefail
REPO_DIR="$1"
VERIFY_WEBUI="$2"
HOST_DATA_DIR="${LUNAECLAW_HOST_DATA_DIR:-${LUNAECLAW_DATA_DIR:-${REPO_DIR}/.lunaeclaw-data}}"

if [[ ! -d "${REPO_DIR}" ]]; then
  if [[ "${REPO_DIR}" == "/root/LunaeClaw" && -d "/root/OrbitClaw" ]]; then
    REPO_DIR="/root/OrbitClaw"
  fi
fi

if [[ ! -d "${REPO_DIR}" ]]; then
  echo "[verify-server] missing repo dir: ${REPO_DIR}"
  exit 1
fi

cd "${REPO_DIR}"

echo "[verify-server] docker compose status check"
docker compose run --rm lunaeclaw-cli status

if [[ "${VERIFY_WEBUI}" == "1" ]]; then
  echo "[verify-server] webui health check"
  docker compose --profile webui up -d --no-deps lunaeclaw-webui

  TOKEN_FILE="${HOST_DATA_DIR}/webui.path-token"
  if [[ ! -f "${TOKEN_FILE}" ]]; then
    TOKEN_FILE="${HOST_DATA_DIR}/webui.path_token"
  fi
  TOKEN="$(cat "${TOKEN_FILE}" 2>/dev/null | tr -d '\r\n')"
  if [[ -z "${TOKEN}" ]]; then
    echo "[verify-server] webui path token not found"
    exit 1
  fi

  if command -v curl >/dev/null 2>&1; then
    curl -fsS "http://127.0.0.1:18791/${TOKEN}/healthz" >/dev/null
  elif command -v wget >/dev/null 2>&1; then
    wget -q -O /dev/null "http://127.0.0.1:18791/${TOKEN}/healthz"
  else
    echo "[verify-server] neither curl nor wget is available"
    exit 1
  fi
fi

echo "[verify-server] done"
EOF
