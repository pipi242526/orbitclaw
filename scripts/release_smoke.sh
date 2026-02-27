#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

echo "==> release smoke: compile checks"
python3 -m py_compile \
  nanobot/agent/context.py \
  nanobot/agent/loop.py \
  nanobot/agent/subagent.py \
  nanobot/agent/tools/media.py \
  nanobot/agent/tools/export.py \
  nanobot/agent/tools/web.py \
  nanobot/cli/commands.py \
  nanobot/config/schema.py \
  nanobot/webui/server.py

echo "==> release smoke: focused tests"
if command -v uv >/dev/null 2>&1; then
  uv run --extra dev pytest -q \
    tests/test_budget_utils.py \
    tests/test_context_language_hint.py \
    tests/test_files_hub_tool.py \
    tests/test_export_file_tool.py \
    tests/test_web_fetch_tool.py
else
  python3 -m pytest -q \
    tests/test_budget_utils.py \
    tests/test_context_language_hint.py \
    tests/test_files_hub_tool.py \
    tests/test_export_file_tool.py \
    tests/test_web_fetch_tool.py
fi

echo "==> release smoke: config/status sanity"
if command -v nanobot >/dev/null 2>&1; then
  nanobot status >/tmp/nanobot_status_smoke.txt
  nanobot doctor >/tmp/nanobot_doctor_smoke.txt
  echo "status: /tmp/nanobot_status_smoke.txt"
  echo "doctor: /tmp/nanobot_doctor_smoke.txt"
else
  echo "nanobot CLI not found in PATH, skipped status/doctor runtime checks."
fi

echo "==> release smoke: PASS"
