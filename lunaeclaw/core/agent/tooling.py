"""Shared helpers for agent tool policy and tool-output handling."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

_WEB_SEARCH_PROVIDERS = {"exa_mcp", "disabled"}


def normalize_name_set(values: Iterable[str] | None) -> set[str]:
    """Normalize an optional string list into a lowercase set."""
    if not values:
        return set()
    return {str(v).strip().lower() for v in values if str(v).strip()}


def normalize_tool_aliases(aliases: Mapping[str, str] | None) -> dict[str, str]:
    """Normalize configured tool aliases and drop empty keys/targets."""
    if not aliases:
        return {}
    normalized: dict[str, str] = {}
    for key, target in aliases.items():
        k = str(key).strip()
        v = str(target).strip()
        if k and v:
            normalized[k] = v
    return normalized


def normalize_web_search_provider(value: str | None) -> str:
    mode = (value or "exa_mcp").strip().lower()
    return mode if mode in _WEB_SEARCH_PROVIDERS else "exa_mcp"


def is_tool_enabled(enabled_tools: set[str], name: str) -> bool:
    """Return True if tool is enabled by config (empty set means allow all)."""
    return not enabled_tools or name.lower() in enabled_tools


def is_mcp_server_enabled(
    name: str,
    *,
    enabled_servers: set[str],
    disabled_servers: set[str],
) -> bool:
    lname = str(name).lower()
    if enabled_servers and lname not in enabled_servers:
        return False
    if lname in disabled_servers:
        return False
    return True


def should_try_exa_mcp_search(provider: str, exa_mcp_configured: bool) -> bool:
    if provider == "disabled":
        return False
    return exa_mcp_configured


def truncate_tool_output(
    result: Any,
    tool_name: str,
    *,
    limit: int,
    source_label: str = "lunaeclaw",
) -> Any:
    """Keep tool output bounded to reduce context/token blowup in long runs."""
    if not isinstance(result, str):
        return result
    if len(result) <= limit:
        return result
    omitted = len(result) - limit
    note = (
        f"\n\n[truncated by {source_label}: {omitted} chars omitted from `{tool_name}` output "
        "to control context size. Ask for a narrower query/file/section if needed.]"
    )
    return result[:limit] + note
