#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"

echo "==> release smoke: compile checks"
python3 -m py_compile \
  lunaeclaw/core/context/context.py \
  lunaeclaw/core/agent/loop.py \
  lunaeclaw/core/agent/subagent.py \
  lunaeclaw/capabilities/tools/media.py \
  lunaeclaw/capabilities/tools/export.py \
  lunaeclaw/capabilities/tools/web.py \
  lunaeclaw/app/cli/commands.py \
  lunaeclaw/platform/config/schema.py \
  lunaeclaw/app/webui/server.py

echo "==> release smoke: focused tests"
if command -v uv >/dev/null 2>&1; then
  uv run --extra dev pytest -q \
    tests/public/test_budget_utils.py \
    tests/public/test_context_language_hint.py \
    tests/public/test_files_hub_tool.py \
    tests/public/test_export_file_tool.py \
    tests/public/test_web_fetch_tool.py
else
  python3 -m pytest -q \
    tests/public/test_budget_utils.py \
    tests/public/test_context_language_hint.py \
    tests/public/test_files_hub_tool.py \
    tests/public/test_export_file_tool.py \
    tests/public/test_web_fetch_tool.py
fi

echo "==> release smoke: config/status sanity"
if command -v lunaeclaw >/dev/null 2>&1; then
  lunaeclaw status >/tmp/lunaeclaw_status_smoke.txt
  lunaeclaw doctor >/tmp/lunaeclaw_doctor_smoke.txt
  echo "status: /tmp/lunaeclaw_status_smoke.txt"
  echo "doctor: /tmp/lunaeclaw_doctor_smoke.txt"
else
  echo "lunaeclaw CLI not found in PATH, skipped status/doctor runtime checks."
fi

echo "==> release smoke: PASS"
