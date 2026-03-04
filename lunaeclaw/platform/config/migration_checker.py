"""Config migration hint checker with normalized severity and fix suggestions."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from lunaeclaw.platform.config.loader import inspect_config_hints


@dataclass(frozen=True)
class ConfigMigrationFinding:
    severity: str
    message: str
    suggestion: str


def _suggestion_for_hint(hint: str) -> str:
    text = (hint or "").strip()
    if text.startswith("config parse error:"):
        return "Fix JSON syntax in config file, then rerun `lunaeclaw doctor` (or open WebUI and save the related page)."
    if text.startswith("config read error:"):
        return "Check file permissions/path and ensure config.json is readable."
    if "legacy key `tools.exec.restrictToWorkspace`" in text:
        return "Move the value to `tools.restrictToWorkspace` and resave config."
    if "legacy web.search.provider detected" in text:
        return "Set tools.web.search.provider to `exa_mcp` or `disabled`."
    if "unknown web.search.provider" in text:
        return "Use `exa_mcp` or `disabled` for tools.web.search.provider."
    if "contains duplicates" in text:
        return "Remove duplicate entries and resave config."
    if "contains blank key/value" in text or "contains self mapping" in text:
        return "Clean invalid aliases under tools.aliases and resave."
    if "model allowlist uses endpoint prefix" in text:
        return "Store plain model names in providers.endpoints.<name>.models (without endpoint prefix)."
    if "`channels.sendToolHints=true`" in text:
        return "Set channels.sendToolHints=false to avoid leaking tool traces."
    if "config root should be a JSON object" in text:
        return "Ensure config.json root is a JSON object."
    return "Open WebUI, review Config migration hints, and resave related pages."


def _severity_for_hint(hint: str) -> str:
    text = (hint or "").strip()
    if text.startswith("config parse error:") or text.startswith("config read error:"):
        return "error"
    if "config root should be a JSON object" in text:
        return "error"
    return "warn"


def collect_config_migration_findings(config_path: Path | None = None) -> list[ConfigMigrationFinding]:
    findings: list[ConfigMigrationFinding] = []
    for hint in inspect_config_hints(config_path):
        findings.append(
            ConfigMigrationFinding(
                severity=_severity_for_hint(hint),
                message=hint,
                suggestion=_suggestion_for_hint(hint),
            )
        )
    return findings

