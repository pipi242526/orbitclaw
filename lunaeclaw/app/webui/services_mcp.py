"""Service helpers for WebUI MCP mutations."""

from __future__ import annotations

from typing import Any

from orbitclaw.platform.config.presets import merge_unique as _merge_unique


def is_mcp_server_enabled(cfg: Any, server_name: str) -> bool:
    return ((not cfg.tools.mcp_enabled_servers) or (server_name in cfg.tools.mcp_enabled_servers)) and (
        server_name not in (cfg.tools.mcp_disabled_servers or [])
    )


def set_mcp_server_enabled(cfg: Any, *, server_name: str, enabled: bool) -> None:
    all_names = list(cfg.tools.mcp_servers.keys())
    current_enabled = cfg.tools.mcp_enabled_servers or []
    current_disabled = cfg.tools.mcp_disabled_servers or []
    if not current_enabled:
        current_enabled = list(all_names)
    enabled_set = {x for x in current_enabled if x in all_names}
    disabled_set = {x for x in current_disabled if x in all_names}
    if enabled:
        enabled_set.add(server_name)
        disabled_set.discard(server_name)
    else:
        enabled_set.discard(server_name)
        disabled_set.add(server_name)
    cfg.tools.mcp_enabled_servers = sorted(enabled_set)
    cfg.tools.mcp_disabled_servers = sorted(disabled_set)


def remove_mcp_server(cfg: Any, *, server_name: str) -> None:
    del cfg.tools.mcp_servers[server_name]
    cfg.tools.mcp_enabled_servers = [x for x in (cfg.tools.mcp_enabled_servers or []) if x != server_name]
    cfg.tools.mcp_disabled_servers = [x for x in (cfg.tools.mcp_disabled_servers or []) if x != server_name]


def install_mcp_server(cfg: Any, *, server_name: str, server_config: Any, enable_now: bool = True) -> None:
    cfg.tools.mcp_servers[server_name] = server_config
    if enable_now:
        cfg.tools.mcp_enabled_servers = _merge_unique(cfg.tools.mcp_enabled_servers, [server_name])
