.PHONY: setup setup-dev clean-cache lint test test-internal quality line-report audit-public prepublish export-public verify-local verify-server verify-server-acceptance verify gateway webui

setup:
	uv sync

setup-dev:
	uv sync --extra dev

clean-cache:
	python3 scripts/quality/cleanup_runtime_cache.py

lint:
	uv run --extra dev ruff check .

test:
	@set -e; \
	trap 'python3 scripts/quality/cleanup_runtime_cache.py >/dev/null 2>&1 || true' EXIT; \
	uv run --extra dev pytest -q tests/public

test-internal:
	@set -e; \
	trap 'python3 scripts/quality/cleanup_runtime_cache.py >/dev/null 2>&1 || true' EXIT; \
	uv run --extra dev pytest -q tests/internal

quality:
	@set -e; \
	trap 'python3 scripts/quality/cleanup_runtime_cache.py >/dev/null 2>&1 || true' EXIT; \
	uv run --extra dev python scripts/quality/lint_changed.py; \
	uv run --extra dev python scripts/quality/file_line_report.py; \
	uv run --extra dev pytest -q tests/public; \
	uv run --extra dev pytest -q tests/internal

line-report:
	uv run --extra dev python scripts/quality/file_line_report.py

audit-public:
	./scripts/release/repo_public_audit.sh

prepublish:
	./scripts/release/repo_public_audit.sh
	./scripts/release/prepublish_check.sh
	uv run --extra dev ruff check .
	uv run --extra dev pytest -q tests/public
	uv run --extra dev pytest -q tests/internal

export-public:
	./scripts/release/export_public_snapshot.sh

verify-local:
	./scripts/release/verify_local.sh

verify-server:
	./scripts/release/verify_server.sh

verify-server-acceptance:
	./scripts/release/server_acceptance.sh

verify:
	./scripts/release/verify_local.sh
	./scripts/release/verify_server.sh

gateway:
	uv run lunaeclaw gateway

webui:
	uv run lunaeclaw webui --host 0.0.0.0 --port 18791
