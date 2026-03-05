"""Shared diagnostics helpers for Web UI pages."""

from __future__ import annotations

from lunaeclaw.app.webui.common import _is_env_placeholder
from lunaeclaw.app.webui.i18n import ui_copy as _ui_copy
from lunaeclaw.platform.config.migration_checker import collect_config_migration_findings
from lunaeclaw.platform.config.schema import Config

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


def collect_channel_runtime_issues(raw_cfg: Config, resolved_cfg: Config, *, ui_lang: str = "en") -> list[str]:
    """Check enabled channels for unresolved required credentials."""
    def t(en: str, zh_cn: str) -> str:
        return _ui_copy(ui_lang, en, zh_cn)
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
            # If placeholder survives after env resolution, the env var is still missing.
            if resolved_val and _is_env_placeholder(resolved_val):
                resolved_val = ""
            if resolved_val:
                continue
            if raw_val.startswith("${") and raw_val.endswith("}"):
                issues.append(
                    t(
                        "{channel}: missing env `{name}`",
                        "{channel}: 缺少环境变量 `{name}`",
                    ).format(
                        channel=channel,
                        name=raw_val[2:-1],
                    )
                )
            else:
                issues.append(
                    t("{channel}: missing `{field}`", "{channel}: 缺少 `{field}`").format(
                        channel=channel,
                        field=field_name,
                    )
                )
    return issues


def collect_tool_policy_diagnostics(cfg: Config, *, ui_lang: str = "en") -> list[str]:
    """Collect non-blocking tool policy conflicts and foot-guns."""
    def t(en: str, zh_cn: str) -> str:
        return _ui_copy(ui_lang, en, zh_cn)
    warnings: list[str] = []
    enabled_builtin = {t.strip() for t in (cfg.tools.enabled or []) if t.strip()}
    if cfg.tools.enabled:
        unknown = sorted([t for t in enabled_builtin if t not in _BUILTIN_TOOL_NAMES])
        if unknown:
            warnings.append(
                t(
                    f"tools.enabled includes unknown built-in tools: {', '.join(unknown)}",
                    f"tools.enabled 包含未知内置工具: {', '.join(unknown)}",
                )
            )
    if cfg.tools.enabled and "message" not in enabled_builtin:
        warnings.append(
            t(
                "tools.enabled does not include `message`; some channel replies may fail.",
                "tools.enabled 未包含 `message`，部分渠道回传可能异常。",
            )
        )
    if cfg.tools.enabled and "spawn" not in enabled_builtin:
        warnings.append(
            t(
                "tools.enabled does not include `spawn`; background sub-agent capability is disabled.",
                "tools.enabled 未包含 `spawn`，后台子代理能力不可用。",
            )
        )

    aliases = cfg.tools.aliases or {}
    for k, v in aliases.items():
        if not str(k).strip() or not str(v).strip():
            warnings.append(
                t("invalid alias: {lhs} -> {rhs}", "alias 无效: {lhs} -> {rhs}").format(
                    lhs=repr(k),
                    rhs=repr(v),
                )
            )
        elif str(k).strip() == str(v).strip():
            warnings.append(
                t("invalid alias (self-mapping): {lhs} -> {rhs}", "alias 无效（自映射）: {lhs} -> {rhs}").format(
                    lhs=k,
                    rhs=v,
                )
            )

    enabled_servers = {x.strip() for x in (cfg.tools.mcp_enabled_servers or []) if x.strip()}
    disabled_servers = {x.strip() for x in (cfg.tools.mcp_disabled_servers or []) if x.strip()}
    overlap_servers = sorted(enabled_servers & disabled_servers)
    if overlap_servers:
        warnings.append(
            t(
                f"MCP servers appear in both enabled/disabled lists: {', '.join(overlap_servers)}",
                f"MCP 服务同时在 enabled/disabled: {', '.join(overlap_servers)}",
            )
        )

    enabled_tools = {x.strip() for x in (cfg.tools.mcp_enabled_tools or []) if x.strip()}
    disabled_tools = {x.strip() for x in (cfg.tools.mcp_disabled_tools or []) if x.strip()}
    overlap_tools = sorted(enabled_tools & disabled_tools)
    if overlap_tools:
        warnings.append(
            t(
                f"MCP tools appear in both enabled/disabled lists: {', '.join(overlap_tools)}",
                f"MCP 工具同时在 enabled/disabled: {', '.join(overlap_tools)}",
            )
        )

    provider_mode = (cfg.tools.web.search.provider or "exa_mcp").strip().lower()
    if provider_mode == "exa_mcp":
        if "exa" not in (cfg.tools.mcp_servers or {}):
            warnings.append(
                t(
                    "web_search is set to exa_mcp, but exa MCP server is not configured.",
                    "web_search 使用 exa_mcp，但未配置 exa MCP server。",
                )
            )
        if cfg.tools.enabled and "web_search" not in enabled_builtin:
            warnings.append(
                t(
                    "web_search provider is enabled, but web_search is not in tools.enabled.",
                    "web_search provider 已启用，但 web_search 不在 tools.enabled。",
                )
            )

    return warnings


def collect_config_migration_hints(config_path) -> list[str]:
    """Expose config-loader migration hints in Web UI."""
    return [item.message for item in collect_config_migration_findings(config_path)]
