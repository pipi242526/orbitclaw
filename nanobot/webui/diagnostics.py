"""Shared diagnostics helpers for Web UI pages."""

from __future__ import annotations

from typing import Any

from nanobot.config.loader import inspect_config_hints
from nanobot.config.schema import Config

_BUILTIN_TOOL_NAMES = {
    "read_file",
    "write_file",
    "edit_file",
    "list_dir",
    "exec",
    "web_search",
    "web_fetch",
    "files_hub",
    "export_file",
    "weather",
    "claude_code",
    "message",
    "spawn",
    "cron",
}


def collect_channel_runtime_issues(raw_cfg: Config, resolved_cfg: Config) -> list[str]:
    """Check enabled channels for unresolved required credentials."""
    # keep spec local to avoid importing the full webui server module.
    required_specs: dict[str, list[str]] = {
        "telegram": ["token"],
        "discord": ["token"],
        "feishu": ["app_id", "app_secret"],
        "dingtalk": ["client_id", "client_secret"],
        "qq": ["app_id", "secret"],
        "slack": ["bot_token", "app_token"],
        "mochat": ["claw_token"],
    }
    issues: list[str] = []
    for channel, fields in required_specs.items():
        raw_channel = getattr(raw_cfg.channels, channel)
        resolved_channel = getattr(resolved_cfg.channels, channel)
        if not bool(getattr(raw_channel, "enabled", False)):
            continue
        for field_name in fields:
            raw_val = str(getattr(raw_channel, field_name) or "").strip()
            resolved_val = str(getattr(resolved_channel, field_name) or "").strip()
            if resolved_val:
                continue
            if raw_val.startswith("${") and raw_val.endswith("}"):
                issues.append(f"{channel}: missing env `{raw_val[2:-1]}`")
            else:
                issues.append(f"{channel}: missing `{field_name}`")
    return issues


def collect_tool_policy_diagnostics(cfg: Config) -> list[str]:
    """Collect non-blocking tool policy conflicts and foot-guns."""
    warnings: list[str] = []
    enabled_builtin = {t.strip() for t in (cfg.tools.enabled or []) if t.strip()}
    if cfg.tools.enabled:
        unknown = sorted([t for t in enabled_builtin if t not in _BUILTIN_TOOL_NAMES])
        if unknown:
            warnings.append(f"tools.enabled 包含未知内置工具: {', '.join(unknown)}")
    if cfg.tools.enabled and "message" not in enabled_builtin:
        warnings.append("tools.enabled 未包含 `message`，部分渠道回传可能异常。")
    if cfg.tools.enabled and "spawn" not in enabled_builtin:
        warnings.append("tools.enabled 未包含 `spawn`，后台子代理能力不可用。")

    aliases = cfg.tools.aliases or {}
    for k, v in aliases.items():
        if not str(k).strip() or not str(v).strip():
            warnings.append(f"alias 无效: {k!r} -> {v!r}")
        elif str(k).strip() == str(v).strip():
            warnings.append(f"alias 无效（自映射）: {k} -> {v}")

    enabled_servers = {x.strip() for x in (cfg.tools.mcp_enabled_servers or []) if x.strip()}
    disabled_servers = {x.strip() for x in (cfg.tools.mcp_disabled_servers or []) if x.strip()}
    overlap_servers = sorted(enabled_servers & disabled_servers)
    if overlap_servers:
        warnings.append(f"MCP 服务同时在 enabled/disabled: {', '.join(overlap_servers)}")

    enabled_tools = {x.strip() for x in (cfg.tools.mcp_enabled_tools or []) if x.strip()}
    disabled_tools = {x.strip() for x in (cfg.tools.mcp_disabled_tools or []) if x.strip()}
    overlap_tools = sorted(enabled_tools & disabled_tools)
    if overlap_tools:
        warnings.append(f"MCP 工具同时在 enabled/disabled: {', '.join(overlap_tools)}")

    provider_mode = (cfg.tools.web.search.provider or "exa_mcp").strip().lower()
    if provider_mode == "exa_mcp":
        if "exa" not in (cfg.tools.mcp_servers or {}):
            warnings.append("web_search 使用 exa_mcp，但未配置 exa MCP server。")
        if cfg.tools.enabled and "web_search" not in enabled_builtin:
            warnings.append("web_search provider 已启用，但 web_search 不在 tools.enabled。")

    return warnings


def collect_config_migration_hints(config_path) -> list[str]:
    """Expose config-loader migration hints in Web UI."""
    return inspect_config_hints(config_path)
