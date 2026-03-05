#!/usr/bin/env bash
set -euo pipefail

SERVER_HOST="${SERVER_HOST:-}"
SERVER_USER="${SERVER_USER:-root}"
SERVER_DIR="${SERVER_DIR:-/root/LunaeClaw}"
VERIFY_WEBUI="${VERIFY_WEBUI:-1}"
VERIFY_GATEWAY_STATE="${VERIFY_GATEWAY_STATE:-1}"
ALLOW_WAITING_CONFIG="${ALLOW_WAITING_CONFIG:-1}"
SERVER_SSH_KEY="${SERVER_SSH_KEY:-}"
REPORT_DIR="${REPORT_DIR:-release/internal/reports}"

if [[ -z "${SERVER_HOST}" ]]; then
  echo "[server-acceptance] SERVER_HOST is required"
  echo "[server-acceptance] example:"
  echo "  SERVER_HOST=203.0.113.10 make verify-server-acceptance"
  exit 1
fi

mkdir -p "${REPORT_DIR}"
REPORT_FILE="${REPORT_DIR}/server-acceptance-$(date -u +%Y%m%d-%H%M%S).log"
exec > >(tee -a "${REPORT_FILE}") 2>&1

REMOTE="${SERVER_USER}@${SERVER_HOST}"
SSH_OPTS=(-o StrictHostKeyChecking=accept-new)
if [[ -n "${SERVER_SSH_KEY}" ]]; then
  SSH_OPTS+=(-i "${SERVER_SSH_KEY}")
fi

echo "[server-acceptance] target: ${REMOTE}"
echo "[server-acceptance] repo: ${SERVER_DIR}"
echo "[server-acceptance] verify webui: ${VERIFY_WEBUI}"
echo "[server-acceptance] verify gateway state freshness: ${VERIFY_GATEWAY_STATE}"
echo "[server-acceptance] allow waiting_config: ${ALLOW_WAITING_CONFIG}"
echo "[server-acceptance] report: ${REPORT_FILE}"

ssh "${SSH_OPTS[@]}" "${REMOTE}" bash -s -- "${SERVER_DIR}" "${VERIFY_WEBUI}" "${VERIFY_GATEWAY_STATE}" "${ALLOW_WAITING_CONFIG}" <<'EOF'
set -euo pipefail

REPO_DIR="$1"
VERIFY_WEBUI="$2"
VERIFY_GATEWAY_STATE="$3"
ALLOW_WAITING_CONFIG="$4"
HOST_DATA_DIR="${LUNAECLAW_HOST_DATA_DIR:-${LUNAECLAW_DATA_DIR:-${REPO_DIR}/.lunaeclaw-data}}"

if [[ ! -d "${REPO_DIR}" ]]; then
  if [[ "${REPO_DIR}" == "/root/LunaeClaw" && -d "/root/OrbitClaw" ]]; then
    REPO_DIR="/root/OrbitClaw"
  fi
fi

if [[ ! -d "${REPO_DIR}" ]]; then
  echo "[server-acceptance] missing repo dir: ${REPO_DIR}"
  exit 1
fi
if ! command -v docker >/dev/null 2>&1; then
  echo "[server-acceptance] docker is not installed on server"
  exit 1
fi
if ! docker compose version >/dev/null 2>&1; then
  echo "[server-acceptance] docker compose is not available"
  exit 1
fi

cd "${REPO_DIR}"

echo "[server-acceptance] compose config check"
docker compose config -q

echo "[server-acceptance] bring up gateway"
docker compose up -d lunaeclaw-gateway
sleep 2
docker compose ps lunaeclaw-gateway

echo "[server-acceptance] runtime status check"
docker compose run --rm lunaeclaw-cli status

echo "[server-acceptance] runtime doctor check"
docker compose run --rm lunaeclaw-cli doctor

if [[ "${VERIFY_GATEWAY_STATE}" == "1" ]]; then
  echo "[server-acceptance] gateway.state freshness check"
  export REPO_DIR HOST_DATA_DIR ALLOW_WAITING_CONFIG
  python3 - <<'PY'
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

repo_dir = Path(os.environ["REPO_DIR"])
host_data_dir = Path(os.environ.get("HOST_DATA_DIR") or (repo_dir / ".lunaeclaw-data"))
allow_waiting = str(os.environ.get("ALLOW_WAITING_CONFIG") or "1") == "1"
state_path = host_data_dir / "runtime" / "gateway.state.json"
if not state_path.exists():
    print(f"[server-acceptance] missing gateway state file: {state_path}")
    sys.exit(1)

try:
    payload = json.loads(state_path.read_text(encoding="utf-8"))
except Exception as exc:
    print(f"[server-acceptance] failed to parse gateway state: {exc}")
    sys.exit(1)

status = str(payload.get("status") or "").lower()
updated_at = float(payload.get("updatedAt") or 0.0)
age = time.time() - updated_at
fingerprint = str(payload.get("fingerprint") or "")
print(f"[server-acceptance] gateway state status={status}, age={age:.1f}s, fingerprint={fingerprint[:12]}")

allowed = {"running"}
if allow_waiting:
    allowed.add("waiting_config")
if status not in allowed:
    print(f"[server-acceptance] unexpected gateway status: {status}, allowed={sorted(allowed)}")
    sys.exit(1)
if status == "running" and age > 20:
    print("[server-acceptance] gateway heartbeat is stale (>20s)")
    sys.exit(1)
PY
fi

if [[ "${VERIFY_WEBUI}" == "1" ]]; then
  echo "[server-acceptance] webui health check"
  docker compose --profile webui up -d --no-deps lunaeclaw-webui
  TOKEN_FILE="${HOST_DATA_DIR}/webui.path-token"
  if [[ ! -f "${TOKEN_FILE}" ]]; then
    TOKEN_FILE="${HOST_DATA_DIR}/webui.path_token"
  fi
  TOKEN="$(cat "${TOKEN_FILE}" 2>/dev/null | tr -d '\r\n')"
  if [[ -z "${TOKEN}" ]]; then
    echo "[server-acceptance] webui path token not found"
    exit 1
  fi
  echo "[server-acceptance] webui token prefix: ${TOKEN:0:6}***"

  HEALTH_URL="http://127.0.0.1:18791/${TOKEN}/healthz"
  INDEX_URL="http://127.0.0.1:18791/${TOKEN}/"
  if command -v curl >/dev/null 2>&1; then
    curl -fsS "${HEALTH_URL}" >/dev/null
    status_code="$(curl -s -o /dev/null -w '%{http_code}' "${INDEX_URL}")"
  elif command -v wget >/dev/null 2>&1; then
    wget -q -O /dev/null "${HEALTH_URL}"
    status_code="$(wget -S --spider "${INDEX_URL}" 2>&1 | awk '/HTTP\//{code=$2} END{print code}')"
  else
    echo "[server-acceptance] neither curl nor wget is available"
    exit 1
  fi

  case "${status_code}" in
    200|302|303|307|308)
      echo "[server-acceptance] webui index status: ${status_code}"
      ;;
    *)
      echo "[server-acceptance] unexpected webui index status: ${status_code}"
      exit 1
      ;;
  esac
fi

echo "[server-acceptance] PASS"
EOF

echo "[server-acceptance] finished"
echo "[server-acceptance] report saved to ${REPORT_FILE}"
