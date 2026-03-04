"""Shared config preset helpers.

This module centralizes default-recommendation logic used by CLI onboarding and
WebUI one-click setup to keep behavior consistent.
"""

from __future__ import annotations

from orbitclaw.platform.config.schema import Config, MCPServerConfig, ProfileOverridesConfig


def merge_unique(items: list[str] | None, additions: list[str] | None) -> list[str]:
    """Append values while preserving order and removing blanks/duplicates."""
    out: list[str] = []
    for value in [*(items or []), *(additions or [])]:
        v = str(value).strip()
        if v and v not in out:
            out.append(v)
    return out


def apply_recommended_tool_defaults(config: Config, *, include_profiles: bool = False) -> None:
    """Apply lightweight MCP/tool defaults with optional profile seeding."""
    tools = config.tools

    if not tools.web.search.provider or tools.web.search.provider not in {"exa_mcp", "disabled"}:
        tools.web.search.provider = "exa_mcp"

    if "exa" not in tools.mcp_servers:
        tools.mcp_servers["exa"] = MCPServerConfig(
            url="https://mcp.exa.ai/mcp?tools=web_search_exa,get_code_context_exa&exaApiKey=${EXA_API_KEY}"
        )

    if "docloader" not in tools.mcp_servers:
        tools.mcp_servers["docloader"] = MCPServerConfig(
            command="uvx",
            args=["awslabs.document-loader-mcp-server@latest"],
            env={"FASTMCP_LOG_LEVEL": "ERROR"},
        )

    tools.mcp_enabled_servers = merge_unique(tools.mcp_enabled_servers, ["exa", "docloader"])
    tools.mcp_enabled_tools = merge_unique(
        tools.mcp_enabled_tools,
        ["web_search_exa", "get_code_context_exa", "read_document", "read_image"],
    )

    tools.aliases.setdefault("code_search", "mcp_exa_get_code_context_exa")
    tools.aliases.setdefault("doc_read", "mcp_docloader_read_document")
    tools.aliases.setdefault("image_read", "mcp_docloader_read_image")

    if include_profiles:
        _seed_default_profiles(config)


def _seed_default_profiles(config: Config) -> None:
    """Seed lightweight profile presets for first-time users."""
    profiles = config.profiles
    if "cn_dev" not in profiles.items:
        profiles.items["cn_dev"] = ProfileOverridesConfig(
            tools={"web": {"search": {"provider": "exa_mcp"}}},
            skills={"disabled": ["clawhub", "tmux", "summarize", "weather"]},
        )
    if "research" not in profiles.items:
        profiles.items["research"] = ProfileOverridesConfig(
            tools={"web": {"search": {"provider": "exa_mcp"}}},
            skills={"disabled": ["clawhub", "tmux"]},
        )
    if "offline" not in profiles.items:
        profiles.items["offline"] = ProfileOverridesConfig(
            tools={"web": {"search": {"provider": "disabled"}}},
            skills={"disabled": ["clawhub", "weather"]},
        )
    if not profiles.active:
        profiles.active = "cn_dev"
