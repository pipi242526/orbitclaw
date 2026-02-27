#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.." || exit 1

if ! command -v docker >/dev/null 2>&1; then
  echo "docker not found"
  exit 1
fi

if ! docker compose version >/dev/null 2>&1; then
  echo "docker compose plugin not found"
  exit 1
fi

cleanup() {
  docker compose down -v >/dev/null 2>&1 || true
}
trap cleanup EXIT

echo "=== Building compose images ==="
docker compose build nanobot-gateway nanobot-webui

echo "=== Starting compose services ==="
docker compose up -d --force-recreate nanobot-gateway nanobot-webui

echo "=== Running non-interactive diagnostics inside gateway ==="
# Keep smoke tests deterministic: avoid onboarding prompts in CI/non-TTY runs.
run_gateway_cmd() {
  local output_file="$1"
  shift
  timeout -k 5s 60s docker compose exec -T nanobot-gateway "$@" >"$output_file" 2>&1
}

STATUS_FILE="/tmp/nanobot_status_smoke.txt"
DOCTOR_FILE="/tmp/nanobot_doctor_smoke.txt"

if ! run_gateway_cmd "$STATUS_FILE" nanobot status; then
  echo "  FAIL: nanobot status timed out or failed"
  cat "$STATUS_FILE" || true
  exit 1
fi
if ! run_gateway_cmd "$DOCTOR_FILE" nanobot doctor; then
  echo "  FAIL: nanobot doctor timed out or failed"
  cat "$DOCTOR_FILE" || true
  exit 1
fi

STATUS_OUTPUT="$(cat "$STATUS_FILE")"
DOCTOR_OUTPUT="$(cat "$DOCTOR_FILE")"

check() {
  local haystack="$1"
  local needle="$2"
  if echo "$haystack" | grep -q "$needle"; then
    echo "  PASS: found '$needle'"
  else
    echo "  FAIL: missing '$needle'"
    return 1
  fi
}

echo "=== Validating status output ==="
check "$STATUS_OUTPUT" "nanobot Status"
check "$STATUS_OUTPUT" "Context budget"
check "$STATUS_OUTPUT" "Budget alerts"
check "$STATUS_OUTPUT" "Web search provider"
check "$STATUS_OUTPUT" "MCP servers"

echo "=== Validating doctor output ==="
check "$DOCTOR_OUTPUT" "nanobot Doctor"
check "$DOCTOR_OUTPUT" "Summary"
check "$DOCTOR_OUTPUT" "Findings"

echo "=== Validating Web UI path-token + healthz ==="
TOKEN="$(docker compose exec -T nanobot-webui sh -lc 'cat /root/.nanobot/webui.path-token 2>/dev/null || cat /root/.nanobot/webui.path_token 2>/dev/null || true' | tr -d '\r\n')"
if [[ -z "${TOKEN}" ]]; then
  echo "  FAIL: webui path token not generated"
  exit 1
fi

HEALTHZ="$(curl -fsS "http://127.0.0.1:18791/${TOKEN}/healthz")"
if [[ "$HEALTHZ" != "ok" ]]; then
  echo "  FAIL: unexpected healthz response: $HEALTHZ"
  exit 1
fi

DASH_HTML="$(curl -fsS "http://127.0.0.1:18791/${TOKEN}/?lang=en")"
check "$DASH_HTML" "Health Score"
check "$DASH_HTML" "Token Budget Radar"
check "$DASH_HTML" "Resource Radar"

echo "=== Docker smoke PASS ==="
